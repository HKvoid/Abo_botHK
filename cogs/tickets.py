"""Sistema de tickets privado con panel y controles persistentes."""
import asyncio
import html
import io
import re

import asyncpg
import discord
from discord import app_commands
from discord.ext import commands

from core import log
from database import db

_ticket_locks: dict[tuple[int, int], asyncio.Lock] = {}


def _ticket_name(member: discord.Member) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", member.display_name.lower()).strip("-")
    return f"ticket-{(slug or 'usuario')[:85]}"


async def _is_ticket_staff(member: discord.Member, guild_id: int) -> bool:
    if member.guild_permissions.administrator or member.guild_permissions.manage_channels:
        return True
    staff_role_id = await db.get_setting(guild_id, "ticket_staff_role_id")
    if not staff_role_id:
        return False
    return any(role.id == int(staff_role_id) for role in member.roles)


async def _create_ticket(interaction: discord.Interaction, title: str, details: str):
    guild = interaction.guild
    member = interaction.user
    if guild is None or not isinstance(member, discord.Member):
        return await interaction.followup.send("Los tickets solo se pueden abrir dentro del servidor.", ephemeral=True)

    lock = _ticket_locks.setdefault((guild.id, member.id), asyncio.Lock())
    async with lock:
        existing = await db.fetchrow(
            """SELECT channel_id FROM tickets
               WHERE guild_id = $1 AND opener_id = $2 AND status = 'open'""",
            guild.id, member.id,
        )
        if existing:
            channel = guild.get_channel(existing["channel_id"])
            if channel:
                return await interaction.followup.send(
                    f"Ya tienes un ticket abierto: {channel.mention}", ephemeral=True,
                )
            await db.execute(
                "UPDATE tickets SET status = 'closed', closed_at = NOW() WHERE channel_id = $1",
                existing["channel_id"],
            )

        settings = await db.get_settings(guild.id)
        category_id = settings.get("ticket_category_id")
        staff_role_id = settings.get("ticket_staff_role_id")
        category = guild.get_channel(int(category_id)) if category_id else None
        staff_role = guild.get_role(int(staff_role_id)) if staff_role_id else None
        if not isinstance(category, discord.CategoryChannel) or staff_role is None:
            return await interaction.followup.send(
                "El sistema de tickets aún no está configurado. Pide al staff que ejecute `/ticket_config`.",
                ephemeral=True,
            )

        bot_member = guild.me
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
                attach_files=True, embed_links=True,
            ),
            staff_role: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
                manage_messages=True,
            ),
        }
        if bot_member:
            overwrites[bot_member] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
                manage_channels=True, manage_messages=True, attach_files=True,
            )

        channel = await guild.create_text_channel(
            name=_ticket_name(member),
            category=category,
            overwrites=overwrites,
            topic=f"Ticket de {member} | {title[:180]}",
            reason=f"Ticket abierto por {member} ({member.id})",
        )
        try:
            ticket = await db.fetchrow(
                """INSERT INTO tickets (guild_id, channel_id, opener_id, title, details)
                   VALUES ($1, $2, $3, $4, $5) RETURNING id""",
                guild.id, channel.id, member.id, title, details,
            )
        except asyncpg.UniqueViolationError:
            await channel.delete(reason="Se evitó un ticket duplicado")
            existing = await db.fetchrow(
                """SELECT channel_id FROM tickets
                   WHERE guild_id = $1 AND opener_id = $2 AND status = 'open'""",
                guild.id, member.id,
            )
            existing_channel = guild.get_channel(existing["channel_id"]) if existing else None
            message = f"Ya tienes un ticket abierto: {existing_channel.mention}" if existing_channel else "Ya hay un ticket abierto para tu cuenta."
            return await interaction.followup.send(message, ephemeral=True)
        except Exception:
            await channel.delete(reason="No se pudo guardar el ticket en Neon")
            raise

        embed = discord.Embed(
            title=f"Ticket #{ticket['id']} · {title[:200]}",
            description=(
                f"Hola {member.mention}, el staff atenderá tu solicitud aquí.\n\n"
                f"**Detalles**\n{details[:3500]}\n\n"
                "Usa los botones para reclamar o cerrar el ticket."
            ),
            color=0x5865F2,
        )
        embed.set_footer(text=f"Abierto por {member} · ID {member.id}")
        await channel.send(
            content=f"{staff_role.mention} · nuevo ticket de {member.mention}",
            embed=embed,
            view=TicketControlView(),
            allowed_mentions=discord.AllowedMentions(roles=True, users=True, everyone=False),
        )
        await interaction.followup.send(f"Tu ticket está listo: {channel.mention}", ephemeral=True)


async def _make_transcript(channel: discord.TextChannel) -> bytes:
    lines = [
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>Transcripción de ticket</title>",
        "<style>body{font:15px system-ui;background:#202225;color:#eee;max-width:1000px;margin:2rem auto;padding:0 1rem}article{border-bottom:1px solid #444;padding:1rem 0}.meta{color:#aaa;font-size:.85rem}.body{white-space:pre-wrap;overflow-wrap:anywhere}.file{color:#9bd}</style>",
        "</head><body><h1>Transcripción del ticket</h1>",
    ]
    async for message in channel.history(limit=None, oldest_first=True):
        stamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        author = html.escape(f"{message.author} ({message.author.id})")
        content = html.escape(message.clean_content or "[sin texto]")
        attachments = "".join(
            f"<p class='file'><a href='{html.escape(item.url, quote=True)}'>{html.escape(item.filename)}</a></p>"
            for item in message.attachments
        )
        lines.append(
            f"<article><div class='meta'>{stamp} · {author}</div>"
            f"<div class='body'>{content}</div>{attachments}</article>"
        )
    lines.append("</body></html>")
    return "\n".join(lines).encode("utf-8")


class TicketCreateModal(discord.ui.Modal, title="Abrir un ticket"):
    asunto = discord.ui.TextInput(
        label="Asunto", placeholder="¿En qué podemos ayudarte?", max_length=100, required=True,
    )
    detalles = discord.ui.TextInput(
        label="Detalles", style=discord.TextStyle.paragraph,
        placeholder="Describe tu solicitud con el mayor detalle posible.",
        min_length=5, max_length=1500, required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await _create_ticket(interaction, self.asunto.value.strip(), self.detalles.value.strip())


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Crear ticket", style=discord.ButtonStyle.primary,
        emoji="🎫", custom_id="abo:ticket:create:v1",
    )
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketCreateModal())


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Reclamar", style=discord.ButtonStyle.secondary,
        emoji="🙋", custom_id="abo:ticket:claim:v1",
    )
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Acción disponible solo en el servidor.", ephemeral=True)
        ticket = await db.fetchrow(
            "SELECT id, status, claimed_by FROM tickets WHERE channel_id = $1",
            interaction.channel_id,
        )
        if not ticket or ticket["status"] != "open":
            return await interaction.response.send_message("Este ticket ya está cerrado o no existe.", ephemeral=True)
        if not await _is_ticket_staff(interaction.user, interaction.guild.id):
            return await interaction.response.send_message("Solo el staff puede reclamar tickets.", ephemeral=True)
        if ticket["claimed_by"] and ticket["claimed_by"] != interaction.user.id:
            return await interaction.response.send_message("Este ticket ya lo está atendiendo otro miembro del staff.", ephemeral=True)
        await db.execute(
            "UPDATE tickets SET claimed_by = $1 WHERE channel_id = $2 AND status = 'open'",
            interaction.user.id, interaction.channel_id,
        )
        await interaction.response.send_message(
            f"{interaction.user.mention} se hará cargo de este ticket.",
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )

    @discord.ui.button(
        label="Cerrar ticket", style=discord.ButtonStyle.danger,
        emoji="🔒", custom_id="abo:ticket:close:v1",
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Acción disponible solo en el servidor.", ephemeral=True)
        ticket = await db.fetchrow(
            "SELECT id, opener_id, status FROM tickets WHERE channel_id = $1",
            interaction.channel_id,
        )
        if not ticket or ticket["status"] != "open":
            return await interaction.response.send_message("Este ticket ya está cerrado o no existe.", ephemeral=True)
        is_opener = ticket["opener_id"] == interaction.user.id
        if not is_opener and not await _is_ticket_staff(interaction.user, interaction.guild.id):
            return await interaction.response.send_message("Solo quien abrió el ticket o el staff puede cerrarlo.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)
        channel = interaction.channel
        transcript_message = None
        transcript = None
        settings = await db.get_settings(interaction.guild.id)
        log_channel_id = settings.get("ticket_log_channel_id")
        destination = interaction.guild.get_channel(int(log_channel_id)) if log_channel_id else None
        if not isinstance(destination, discord.TextChannel):
            destination = channel
        try:
            transcript = await _make_transcript(channel)
            attachment = discord.File(io.BytesIO(transcript), filename=f"ticket-{ticket['id']}-transcript.html")
            transcript_message = await destination.send(
                content=f"Transcripción del ticket #{ticket['id']} · cerrado por {interaction.user} · canal {channel.mention}",
                file=attachment,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.HTTPException) as error:
            log.warning("No se pudo exportar transcripción de ticket %s: %s", ticket["id"], error)

        transcript_url = transcript_message.attachments[0].url if transcript_message and transcript_message.attachments else None
        await db.execute(
            """UPDATE tickets SET status = 'closed', closed_by = $1, closed_at = NOW(),
               transcript_message_id = $2, transcript_url = $3, transcript_html = $4
               WHERE channel_id = $5 AND status = 'open'""",
            interaction.user.id,
            transcript_message.id if transcript_message else None,
            transcript_url,
            transcript,
            interaction.channel_id,
        )
        if isinstance(channel, discord.TextChannel):
            opener = interaction.guild.get_member(ticket["opener_id"])
            try:
                if opener:
                    await channel.set_permissions(
                        opener, view_channel=True, send_messages=False,
                        add_reactions=False, reason="Ticket cerrado",
                    )
                await channel.edit(name=f"closed-{channel.name}"[:100], reason="Ticket cerrado")
            except discord.Forbidden:
                log.warning("No se pudieron ajustar permisos al cerrar ticket %s", ticket["id"])
        await interaction.followup.send(
            "Ticket cerrado. La transcripción se guardó en el canal de registros." if transcript_message
            else "Ticket cerrado. La transcripción quedó conservada en Neon, pero no pude enviarla al canal de registros.",
            ephemeral=True,
        )
        try:
            await channel.send(f"Ticket cerrado por {interaction.user.mention}.", view=TicketControlView())
        except discord.HTTPException:
            pass


class TicketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ticket_config", description="Configura categoría, rol de staff y canal de registros")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        categoria="Categoría donde se crearán los tickets",
        rol_staff="Rol que tendrá acceso a los tickets",
        canal_registros="Canal privado donde se guardarán las transcripciones",
    )
    async def ticket_config(
        self,
        interaction: discord.Interaction,
        categoria: discord.CategoryChannel,
        rol_staff: discord.Role,
        canal_registros: discord.TextChannel,
    ):
        if rol_staff.is_default():
            return await interaction.response.send_message(
                "No uses @everyone como rol de staff; eso haría visibles los tickets para todos.",
                ephemeral=True,
            )
        await db.set_settings(interaction.guild_id, {
            "ticket_category_id": str(categoria.id),
            "ticket_staff_role_id": str(rol_staff.id),
            "ticket_log_channel_id": str(canal_registros.id),
        })
        await interaction.response.send_message(
            f"Tickets configurados: categoría {categoria.name}, staff {rol_staff.mention} y registros {canal_registros.mention}.",
            ephemeral=True,
        )

    @app_commands.command(name="ticket_panel", description="Publica el panel para abrir tickets")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(canal="Canal donde publicar el panel de tickets")
    async def ticket_panel(self, interaction: discord.Interaction, canal: discord.TextChannel):
        settings = await db.get_settings(interaction.guild_id)
        if not all(settings.get(key) for key in (
            "ticket_category_id", "ticket_staff_role_id", "ticket_log_channel_id",
        )):
            return await interaction.response.send_message(
                "Primero configura el sistema con `/ticket_config`.", ephemeral=True,
            )
        embed = discord.Embed(
            title="Centro de soporte 🎫",
            description=(
                "Pulsa **Crear ticket** para abrir una conversación privada con el staff. "
                "Describe el asunto y los detalles en el formulario."
            ),
            color=0x5865F2,
        )
        embed.set_footer(text=f"{interaction.guild.name} · Soporte")
        await canal.send(embed=embed, view=TicketPanelView())
        await interaction.response.send_message(f"Panel de tickets publicado en {canal.mention}.", ephemeral=True)

    @app_commands.command(name="ticket_transcript", description="Descarga una transcripción guardada en Neon")
    @app_commands.guild_only()
    @app_commands.describe(canal="Canal del ticket cerrado")
    async def ticket_transcript(self, interaction: discord.Interaction, canal: discord.TextChannel):
        if canal.guild.id != interaction.guild_id:
            return await interaction.response.send_message("Ese canal no pertenece a este servidor.", ephemeral=True)
        ticket = await db.fetchrow(
            "SELECT id, opener_id, transcript_html FROM tickets WHERE channel_id = $1",
            canal.id,
        )
        if not ticket or ticket["transcript_html"] is None:
            return await interaction.response.send_message(
                "No hay una transcripción guardada para ese ticket.", ephemeral=True,
            )
        is_opener = ticket["opener_id"] == interaction.user.id
        is_staff = isinstance(interaction.user, discord.Member) and await _is_ticket_staff(
            interaction.user, interaction.guild_id,
        )
        if not is_opener and not is_staff:
            return await interaction.response.send_message(
                "Solo quien abrió el ticket o el staff configurado puede descargarlo.", ephemeral=True,
            )
        file = discord.File(
            io.BytesIO(bytes(ticket["transcript_html"])),
            filename=f"ticket-{ticket['id']}-transcript.html",
        )
        await interaction.response.send_message(file=file, ephemeral=True)
