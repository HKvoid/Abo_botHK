"""Comandos de advertencias (warns) persistidos en Neon."""
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from core import has_guild_permission
from database import db


class WarnsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="warn", description="[Staff] Warn a un usuario")
    @app_commands.describe(user="A quién warnear", reason="Razón del warn")
    @app_commands.default_permissions(moderate_members=True)
    @has_guild_permission("moderate_members")
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Mal comportamiento"):
        await interaction.response.defer()
        await db.execute(
            "INSERT INTO warns (guild_id, user_id, moderator_id, reason) VALUES ($1, $2, $3, $4)",
            interaction.guild.id, user.id, interaction.user.id, reason,
        )
        total = await db.fetchval(
            "SELECT COUNT(*) FROM warns WHERE guild_id = $1 AND user_id = $2",
            interaction.guild.id, user.id,
        )

        embed = discord.Embed(title="Warn aplicado ⚠️", color=0xF1C40F)
        embed.add_field(name="Usuario", value=user.mention, inline=True)
        embed.add_field(name="Warn #", value=str(total), inline=True)
        embed.add_field(name="Razón", value=reason, inline=False)
        embed.add_field(name="Por", value=interaction.user.mention, inline=True)
        embed.set_footer(text=f"ID: {user.id}")
        await interaction.followup.send(embed=embed)

        if total == 3:
            try:
                await user.timeout(timedelta(days=1), reason="Auto-Mod: 3 warns")
                await interaction.channel.send(
                    f"Auto-Mod: {user.mention} fue muteado 1 día tras acumular 3 warns 🤐",
                    delete_after=10,
                )
            except discord.Forbidden:
                pass
        elif total >= 5:
            try:
                await user.ban(reason="Auto-Mod: 5 warns")
                await interaction.channel.send(
                    f"Auto-Mod: {user.mention} fue baneado tras acumular 5 warns 🔨",
                    delete_after=10,
                )
            except discord.Forbidden:
                pass

    @app_commands.command(name="warns", description="Muestra el historial de warns de un usuario")
    @app_commands.describe(user="Usuario a consultar")
    @app_commands.default_permissions(moderate_members=True)
    @has_guild_permission("moderate_members")
    async def warns(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        rows = await db.fetch(
            """SELECT id, reason, moderator_id, created_at FROM warns
               WHERE guild_id = $1 AND user_id = $2 ORDER BY created_at ASC, id ASC""",
            interaction.guild.id, user.id,
        )
        if not rows:
            return await interaction.followup.send(
                f"{user.mention} tiene el historial limpio, sin warns ✅", ephemeral=True,
            )
        embed = discord.Embed(title=f"Warns de {user.display_name} ⚠️", color=0xE67E22)
        embed.set_thumbnail(url=user.display_avatar.url)
        for index, row in enumerate(rows, 1):
            moderator = interaction.guild.get_member(row["moderator_id"])
            moderator_name = moderator.display_name if moderator else f"ID:{row['moderator_id']}"
            date = row["created_at"].strftime("%Y-%m-%d")
            embed.add_field(
                name=f"Warn #{index} (ID:{row['id']})",
                value=f"**Razón:** {row['reason']}\n**Por:** {moderator_name}\n**Fecha:** {date}",
                inline=False,
            )
        embed.set_footer(text=f"Total: {len(rows)} warns | ID: {user.id}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="clearwarns", description="[Staff] Borra todos los warns de un usuario")
    @app_commands.describe(user="Usuario a limpiar")
    @app_commands.default_permissions(moderate_members=True)
    @has_guild_permission("moderate_members")
    async def clearwarns(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer()
        await db.execute(
            "DELETE FROM warns WHERE guild_id = $1 AND user_id = $2",
            interaction.guild.id, user.id,
        )
        await interaction.followup.send(f"Historial de warns de {user.mention} borrado por completo 🧹")

    @app_commands.command(name="unwarn", description="[Staff] Quita una cantidad exacta de warns a un usuario")
    @app_commands.describe(user="Usuario a limpiar", cantidad="Cuántos warns quitar (los más antiguos primero)")
    @app_commands.default_permissions(moderate_members=True)
    @has_guild_permission("moderate_members")
    async def unwarn(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        cantidad: app_commands.Range[int, 1, 100] = 1,
    ):
        await interaction.response.defer()
        async with db._pool().acquire() as connection:
            async with connection.transaction():
                rows = await connection.fetch(
                    """SELECT id FROM warns WHERE guild_id = $1 AND user_id = $2
                       ORDER BY created_at ASC, id ASC LIMIT $3""",
                    interaction.guild.id, user.id, cantidad,
                )
                ids = [row["id"] for row in rows]
                if ids:
                    await connection.execute(
                        "DELETE FROM warns WHERE id = ANY($1::bigint[]) AND guild_id = $2 AND user_id = $3",
                        ids, interaction.guild.id, user.id,
                    )
                restantes = await connection.fetchval(
                    "SELECT COUNT(*) FROM warns WHERE guild_id = $1 AND user_id = $2",
                    interaction.guild.id, user.id,
                )
        if not ids:
            return await interaction.followup.send(
                f"{user.mention} tiene el historial limpio, sin warns ✅",
            )
        await interaction.followup.send(
            f"Se quitaron {len(ids)} warn(s) a {user.mention}. Le quedan **{restantes}** 🧹",
        )
