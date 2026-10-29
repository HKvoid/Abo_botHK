"""Comandos de moderación y administración de roles."""
import re
from datetime import timedelta
import discord
from discord import app_commands
from discord.ext import commands
from core import TU_ID, has_guild_permission, log

class ModCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="ban", description="[Staff] Banea a un usuario")
    @app_commands.describe(user="A quién banear", reason="Razón del ban")
    @app_commands.default_permissions(ban_members=True)
    @has_guild_permission("ban_members")
    async def ban(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Se pasó de la raya"):
        if user.id == interaction.user.id:
            return await interaction.response.send_message("¿En serio intentas banearte a ti mismo? Que no 😅", ephemeral=True)
        await interaction.response.defer()
        try: await user.ban(reason=f"{reason} | By {interaction.user}"); await interaction.followup.send(f"{user.mention} fue baneado del servidor. Razón: {reason} 🔨")
        except discord.Forbidden: await interaction.followup.send("No tengo permisos suficientes para banear a ese usuario 🔒")

    @app_commands.command(name="mute", description="[Staff] Da timeout a un usuario")
    @app_commands.describe(user="A quién mutear", time="10m, 2h, 1d")
    @app_commands.default_permissions(moderate_members=True)
    @has_guild_permission("moderate_members")
    async def mute(self, interaction: discord.Interaction, user: discord.Member, time: str = "10m"):
        if user.id == interaction.user.id:
            return await interaction.response.send_message("¿En serio intentas mutearte a ti mismo? Que no 😅", ephemeral=True)
        mult = {"m": 60, "h": 3600, "d": 86400}
        unidad = time[-1] if time else ""
        if unidad not in mult or not time[:-1].isdigit():
            return await interaction.response.send_message("Formato inválido. Usa algo como `10m`, `2h` o `1d` ⏱️", ephemeral=True)
        tiempo_seg = int(time[:-1]) * mult[unidad]
        if tiempo_seg <= 0 or tiempo_seg > 28 * 86400:
            return await interaction.response.send_message("El tiempo debe ser mayor a 0 y de máximo 28 días ⏱️", ephemeral=True)
        await interaction.response.defer()
        try:
            await user.timeout(timedelta(seconds=tiempo_seg), reason=f"Muted by {interaction.user}")
            await interaction.followup.send(f"{user.mention} fue silenciado por {time} 🤐")
        except discord.Forbidden:
            await interaction.followup.send("No tengo permisos suficientes para mutear a ese usuario 🔒")
        except discord.HTTPException as e:
            log.error(f"[Mute Error] {e}")
            await interaction.followup.send("Algo falló al intentar mutear; inténtalo de nuevo 🔁")

    @app_commands.command(name="limpia", description="[Staff] Borra mensajes")
    @app_commands.describe(amount="Cantidad 1-100")
    @app_commands.default_permissions(manage_messages=True)
    @has_guild_permission("manage_messages")
    async def limpia(self, interaction: discord.Interaction, amount: int = 5):
        if amount > 100: amount = 100
        await interaction.response.defer(ephemeral=True)
        borrados = await interaction.channel.purge(limit=amount + 1)
        await interaction.followup.send(f"Borré {len(borrados)-1} mensajes, quedó como nuevo 🧹", ephemeral=True)

    @app_commands.command(name="addrol", description="Da un rol a varios users")
    @app_commands.default_permissions(manage_roles=True)
    @has_guild_permission("manage_roles")
    async def addrol(self, interaction: discord.Interaction, rol: discord.Role, users: str):
        mentions = re.findall(r'<@!?(\d+)>', users)
        if interaction.user.id != TU_ID and rol.position >= interaction.user.top_role.position:
            return await interaction.response.send_message("No puedes asignar un rol superior al tuyo, lindo intento 😏", ephemeral=True)
        await interaction.response.defer()
        exitos, fallos = [], []
        for uid in mentions:
            user = interaction.guild.get_member(int(uid))
            if user:
                try: await user.add_roles(rol); exitos.append(user.name)
                except discord.HTTPException: fallos.append(user.name)
        await interaction.followup.send(f"Rol asignado a: {', '.join(exitos)} ✅\nNo se pudo asignar a: {', '.join(fallos)} ❌" if fallos else f"Rol asignado a: {', '.join(exitos)} ✅")

    @app_commands.command(name="delrol", description="Quita un rol a varios users")
    @app_commands.default_permissions(manage_roles=True)
    @has_guild_permission("manage_roles")
    async def delrol(self, interaction: discord.Interaction, rol: discord.Role, users: str):
        await interaction.response.defer()
        mentions = re.findall(r'<@!?(\d+)>', users); exitos, fallos = [], []
        for uid in mentions:
            user = interaction.guild.get_member(int(uid))
            if user:
                try: await user.remove_roles(rol); exitos.append(user.name)
                except discord.HTTPException: fallos.append(user.name)
        await interaction.followup.send(f"Rol quitado a: {', '.join(exitos)} 🗑️\nNo se pudo quitar a: {', '.join(fallos)} ❌" if fallos else f"Rol quitado a: {', '.join(exitos)} 🗑️")

