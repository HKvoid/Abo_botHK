"""Mensajes personalizables de bienvenida y despedida."""
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

from core import log
from database import db


_PLACEHOLDERS = "Variables: `{user}`, `{username}`, `{server}` y `{member_count}`."


def _validate_message(text: str, image_url: str):
    if not text.strip():
        return "El texto no puede estar vacío."
    if len(text) > 1800:
        return "El texto debe tener como máximo 1800 caracteres."
    if image_url:
        parsed = urlparse(image_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return "La imagen debe ser una URL pública que empiece por http:// o https://."
        if len(image_url) > 1000:
            return "La URL de imagen es demasiado larga."
    return None


def _render(text: str, member: discord.Member) -> str:
    values = {
        "user": member.mention,
        "username": discord.utils.escape_markdown(member.display_name),
        "server": discord.utils.escape_markdown(member.guild.name),
        "member_count": str(member.guild.member_count or len(member.guild.members)),
    }
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


class GreetingsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _save_greeting(self, interaction: discord.Interaction, kind: str, channel: discord.TextChannel, text: str, image_url: str):
        error = _validate_message(text, image_url)
        if error:
            return await interaction.response.send_message(error, ephemeral=True)
        prefix = "welcome" if kind == "welcome" else "leave"
        await db.set_settings(interaction.guild_id, {
            f"{prefix}_channel_id": str(channel.id),
            f"{prefix}_text": text.strip(),
            f"{prefix}_image_url": image_url.strip(),
            f"{prefix}_enabled": "true",
        })
        event_name = "bienvenida" if kind == "welcome" else "despedida"
        await interaction.response.send_message(
            f"{event_name.capitalize()} configurada en {channel.mention}. {_PLACEHOLDERS}",
            ephemeral=True,
        )

    @app_commands.command(name="welcome_config", description="Configura el canal, texto e imagen de bienvenida")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        canal="Canal donde se publicarán las bienvenidas",
        texto="Texto personalizado; admite variables como {user} y {server}",
        imagen_url="URL pública de una imagen (opcional; déjala vacía para no usar imagen)",
    )
    async def welcome_config(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
        texto: str,
        imagen_url: str = "",
    ):
        await self._save_greeting(interaction, "welcome", canal, texto, imagen_url)

    @app_commands.command(name="leave_config", description="Configura el canal, texto e imagen de despedida")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        canal="Canal donde se publicarán las despedidas",
        texto="Texto personalizado; admite variables como {user} y {server}",
        imagen_url="URL pública de una imagen (opcional; déjala vacía para no usar imagen)",
    )
    async def leave_config(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
        texto: str,
        imagen_url: str = "",
    ):
        await self._save_greeting(interaction, "leave", canal, texto, imagen_url)

    @app_commands.command(name="welcome_off", description="Desactiva los mensajes de bienvenida")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome_off(self, interaction: discord.Interaction):
        await db.set_setting(interaction.guild_id, "welcome_enabled", "false")
        await interaction.response.send_message("Las bienvenidas quedaron desactivadas.", ephemeral=True)

    @app_commands.command(name="leave_off", description="Desactiva los mensajes de despedida")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def leave_off(self, interaction: discord.Interaction):
        await db.set_setting(interaction.guild_id, "leave_enabled", "false")
        await interaction.response.send_message("Las despedidas quedaron desactivadas.", ephemeral=True)

    async def _send(self, member: discord.Member, prefix: str):
        settings = await db.get_settings(member.guild.id)
        if settings.get(f"{prefix}_enabled") != "true":
            return
        channel_id = settings.get(f"{prefix}_channel_id")
        text = settings.get(f"{prefix}_text", "")
        image_url = settings.get(f"{prefix}_image_url", "")
        if not channel_id or not text:
            return
        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
            except discord.HTTPException as error:
                log.warning("No se encontró el canal de %s para guild %s: %s", prefix, member.guild.id, error)
                return
        if not isinstance(channel, discord.TextChannel):
            return
        message = _render(text, member)
        embed = None
        if image_url:
            embed = discord.Embed(color=0x5865F2)
            embed.set_image(url=image_url)
        try:
            await channel.send(
                content=message,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(
                    users=[member], roles=False, everyone=False, replied_user=False,
                ),
            )
        except discord.HTTPException as error:
            log.warning("No se pudo enviar mensaje de %s en guild %s: %s", prefix, member.guild.id, error)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.bot:
            await self._send(member, "welcome")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not member.bot:
            await self._send(member, "leave")
