"""Comando de reset del servidor."""
import datetime
import io
import json
import discord
from discord import app_commands
from discord.ext import commands
from core import TU_ID, log

class ConfirmarResetModal(discord.ui.Modal, title="⚠️ Confirmar reset total"):
    def __init__(self, guild: discord.Guild):
        super().__init__()
        self.guild = guild
        self.nombre = discord.ui.TextInput(
            label=f'Escribe "{guild.name}" para confirmar',
            placeholder=guild.name,
            required=True,
        )
        self.add_item(self.nombre)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        if self.nombre.value.strip() != self.guild.name:
            return await interaction.followup.send(
                "❌ El nombre no coincide. Reset cancelado, nada fue tocado.",
                ephemeral=True,
            )

        guild = self.guild

        # ── 1. BACKUP JSON ──
        backup = {
            "guild_id": guild.id,
            "guild_name": guild.name,
            "generado": datetime.datetime.utcnow().isoformat(),
            "roles": [],
            "canales": [],
        }

        for rol in guild.roles:
            backup["roles"].append({
                "id": rol.id, "nombre": rol.name, "color": str(rol.color),
                "posicion": rol.position, "hoist": rol.hoist,
                "mentionable": rol.mentionable, "permisos": rol.permissions.value,
                "managed": rol.managed,
            })

        for canal in guild.channels:
            overwrites = {
                str(target.id): ow._values
                for target, ow in canal.overwrites.items()
            }
            backup["canales"].append({
                "id": canal.id, "nombre": canal.name, "tipo": str(canal.type),
                "posicion": canal.position,
                "categoria": canal.category.name if canal.category else None,
                "topic": getattr(canal, "topic", None),
                "overwrites": overwrites,
            })

        json_bytes = json.dumps(backup, indent=2, ensure_ascii=False).encode("utf-8")
        archivo = discord.File(
            io.BytesIO(json_bytes),
            filename=f"backup_{guild.id}_{int(datetime.datetime.utcnow().timestamp())}.json",
        )
        await interaction.followup.send(
            "💾 Backup generado. Empezando el reset ahora...", file=archivo, ephemeral=True
        )

        # ── 2. BORRAR HILOS Y CANALES ──
        canales_borrados = 0
        for canal in list(guild.channels):
            try:
                await canal.delete(reason=f"Reset total ejecutado por {interaction.user}")
                canales_borrados += 1
            except (discord.Forbidden, discord.HTTPException) as e:
                log.error(f"[reset_servidor] no pude borrar canal {canal.name}: {e}")

        # ── 3. BORRAR ROLES (excepto @everyone, managed, y por encima del bot) ──
        roles_borrados = 0
        bot_top_role = guild.me.top_role
        for rol in list(guild.roles):
            if rol.is_default() or rol.managed:
                continue
            if rol >= bot_top_role:
                continue
            try:
                await rol.delete(reason=f"Reset total ejecutado por {interaction.user}")
                roles_borrados += 1
            except (discord.Forbidden, discord.HTTPException) as e:
                log.error(f"[reset_servidor] no pude borrar rol {rol.name}: {e}")

        try:
            await interaction.user.send(
                f"✅ Reset de **{guild.name}** completado.\n"
                f"Canales borrados: {canales_borrados}\n"
                f"Roles borrados: {roles_borrados}\n"
                f"(el backup JSON te lo mandé en la respuesta del comando)"
            )
        except discord.Forbidden:
            pass


class ResetCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="reset_servidor",
        description="⚠️ SOLO OWNER: borra todos los canales y roles, previo backup en JSON",
    )
    async def reset_servidor(self, interaction: discord.Interaction):
        if interaction.user.id != TU_ID:
            return await interaction.response.send_message(
                "No tienes permiso para usar este comando 🔒", ephemeral=True
            )
        await interaction.response.send_modal(ConfirmarResetModal(interaction.guild))
