"""Escaneo de actividad y comandos de purga AFK."""
import asyncio
from datetime import timedelta
import discord
from discord import app_commands
from discord.ext import commands
from core import (ROL_MIEMBRO, is_staff, listar_excepciones,
                  agregar_excepcion, quitar_excepcion, es_excepcion, log)
from database import db

async def recolectar_canales_con_historial(guild: discord.Guild):
    """Junta TODOS los canales/hilos del server donde puede haber mensajes:
    texto, voz (chat de voz), stage, hilos activos y archivados (incluyendo
    los de canales de foro). Así el /scan refleja la actividad real y no
    solo lo que pasó en los canales de texto de siempre."""
    canales = []
    canales.extend(guild.text_channels)
    canales.extend(guild.voice_channels)
    # Nota: los canales de Stage NO tienen historial de mensajes en discord.py
    # (no son Messageable), a diferencia de los de voz normales. Si se incluyen
    # aquí, .history() revienta con AttributeError y tumba todo el /scan.

    try:
        canales.extend(await guild.active_threads())
    except discord.HTTPException as e:
        log.error(f"[Scan active_threads Error] {e}")

    vistos_ids = {c.id for c in canales}
    # guild.forum_channels no existe en versiones viejas de discord.py; lo resolvemos
    # a mano filtrando guild.channels, y si el tipo ForumChannel ni siquiera existe
    # en esta versión de la librería, simplemente no hay canales de foro que sumar.
    canales_foro = getattr(guild, "forum_channels", None)
    if canales_foro is None:
        ForumChannel = getattr(discord, "ForumChannel", None)
        canales_foro = [c for c in guild.channels if ForumChannel and isinstance(c, ForumChannel)]

    for canal in list(guild.text_channels) + list(canales_foro):
        try:
            perms = canal.permissions_for(guild.me)
            if not perms.read_message_history: continue
            async for hilo in canal.archived_threads(limit=None):
                if hilo.id not in vistos_ids:
                    canales.append(hilo); vistos_ids.add(hilo.id)
            if perms.manage_threads:
                async for hilo in canal.archived_threads(limit=None, private=True):
                    if hilo.id not in vistos_ids:
                        canales.append(hilo); vistos_ids.add(hilo.id)
        except (discord.Forbidden, discord.HTTPException):
            continue
        except Exception as e:
            log.error(f"[Scan archived_threads canal={getattr(canal, 'id', '?')} Error] {e}")
            continue
    return canales

class PurgaCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="scan", description="[Staff] Escaneo masivo de TODOS los canales: busca miembros con 0 mensajes en 15d")
    @is_staff()
    async def scan(self, interaction: discord.Interaction):
        await interaction.response.defer()
        rol_miembro = discord.utils.get(interaction.guild.roles, name=ROL_MIEMBRO)
        if not rol_miembro: return await interaction.followup.send(f"No encontré el rol '{ROL_MIEMBRO}' en este servidor 🤷")
        todos = {m.id: m for m in rol_miembro.members if not m.bot}; actividad = {mid: 0 for mid in todos.keys()}
        hace_15dias = discord.utils.utcnow() - timedelta(days=15)

        canales = await recolectar_canales_con_historial(interaction.guild)
        canales_escaneados = 0
        for canal in canales:
            if not hasattr(canal, "history"): continue
            try:
                perms = canal.permissions_for(interaction.guild.me)
                if not perms.read_message_history: continue
                async for msg in canal.history(limit=None, after=hace_15dias):
                    if msg.author.id in actividad: actividad[msg.author.id] += 1
                canales_escaneados += 1
            except (discord.Forbidden, discord.HTTPException):
                continue
            except Exception as e:
                log.error(f"[Scan canal={getattr(canal, 'id', '?')} Error] {e}")
                continue

        excepciones_guild = {row[0] for row in await listar_excepciones(interaction.guild.id)}
        fantasmas_ids = [mid for mid, count in actividad.items() if count == 0 and mid not in excepciones_guild]
        saltados_por_excepcion = [mid for mid, count in actividad.items() if count == 0 and mid in excepciones_guild]
        await db.save_purge_scan(interaction.guild.id, fantasmas_ids)

        pie = f"\n📡 Canales/hilos escaneados: {canales_escaneados}"
        if saltados_por_excepcion:
            pie += f"\n🛡️ {len(saltados_por_excepcion)} en excepción (no incluido en la lista)"

        if not fantasmas_ids:
            return await interaction.followup.send("No encontré miembros inactivos, todos andan vivitos y coleando 🔥" + pie)

        all_mentions = [interaction.guild.get_member(mid).mention for mid in fantasmas_ids if interaction.guild.get_member(mid)]
        header = f"Scan completado — {len(fantasmas_ids)} inactivo(s) en los últimos 15 días 👻\n"
        chunks = []; current = header
        for m in all_mentions:
            if len(current) + len(m) + 1 > 1900:
                chunks.append(current); current = m + " "
            else: current += m + " "
        chunks.append(current)
        for i, chunk in enumerate(chunks):
            if i == len(chunks) - 1: chunk += f"\nUsa `/purgaafk` cuando quieras expulsarlos.{pie}"
            await interaction.channel.send(chunk)

    @app_commands.command(name="purgaafk", description="[Staff] Patea a los del último /scan")
    @is_staff()
    async def purgaafk(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        fantasmas_ids = await db.get_purge_scan(guild_id)
        if not fantasmas_ids:
            return await interaction.response.send_message("Primero ejecuta un `/scan`, por favor 🔍", ephemeral=True)
        await interaction.response.defer()
        pateados = 0; protegidos = 0
        for user_id in fantasmas_ids:
            if await es_excepcion(guild_id, user_id):
                protegidos += 1; continue  # doble chequeo por si lo agregaron a excepciones después del /scan
            user = interaction.guild.get_member(user_id)
            if user and not user.bot:
                try: await user.kick(reason="Inactividad 15d - Abo"); pateados += 1; await asyncio.sleep(0.5)
                except discord.HTTPException: pass
        msg = f"Purga terminada: {pateados} expulsado(s) ✅"
        if protegidos: msg += f" | {protegidos} protegido(s) por excepción 🛡️"
        await interaction.followup.send(msg)
        await db.save_purge_scan(guild_id, [])

    grupo_excepciones = app_commands.Group(name="purgaexc", description="[Staff] Excepciones de la purga AFK")

    @grupo_excepciones.command(name="add", description="[Staff] Agrega a un usuario a la lista de excepciones de purga")
    @app_commands.describe(user="Usuario que avisó que estará inactivo", razon="Motivo/razón (opcional)")
    @is_staff()
    async def purgaexc_add(self, interaction: discord.Interaction, user: discord.Member, razon: str = "Avisó inactividad temporal"):
        await agregar_excepcion(interaction.guild.id, user.id, razon, interaction.user.id)
        await interaction.response.send_message(
            f"{user.mention} fue añadido a la lista de excepciones de purga. No será expulsado por AFK aunque el `/scan` lo marque inactivo 🛡️\nRazón: {razon}"
        )

    @grupo_excepciones.command(name="quitar", description="[Staff] Quita a un usuario de la lista de excepciones de purga")
    @app_commands.describe(user="Usuario a quitar de excepciones")
    @is_staff()
    async def purgaexc_quitar(self, interaction: discord.Interaction, user: discord.Member):
        if await quitar_excepcion(interaction.guild.id, user.id):
            await interaction.response.send_message(f"{user.mention} fue quitado de la lista de excepciones 🗑️")
        else:
            await interaction.response.send_message(f"{user.mention} no estaba en la lista de excepciones 🤷", ephemeral=True)

    @grupo_excepciones.command(name="lista", description="[Staff] Muestra la lista de excepciones de purga")
    @is_staff()
    async def purgaexc_lista(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        filas = await listar_excepciones(interaction.guild.id)
        if not filas:
            return await interaction.followup.send("No hay nadie en la lista de excepciones ahora mismo 🤷", ephemeral=True)
        embed = discord.Embed(title="Excepciones de Purga AFK 🛡️", color=0x2ECC71)
        for user_id, razon, added_by, ts in filas:
            miembro = interaction.guild.get_member(user_id)
            nombre = miembro.mention if miembro else f"ID:{user_id}"
            mod = interaction.guild.get_member(added_by)
            mod_nombre = mod.display_name if mod else f"ID:{added_by}"
            fecha = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
            embed.add_field(name=nombre, value=f"**Razón:** {razon}\n**Añadido por:** {mod_nombre}\n**Fecha:** {fecha}", inline=False)
        embed.set_footer(text=f"Total: {len(filas)} excepción(es)")
        await interaction.followup.send(embed=embed, ephemeral=True)
