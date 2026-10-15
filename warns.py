"""Comandos de advertencias (warns)."""
from datetime import timedelta
import discord
from discord import app_commands
from discord.ext import commands
from core import cursor, db, is_staff

class WarnsCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="warn", description="[Staff] Warn a un usuario")
    @app_commands.describe(user="A quién warnear", reason="Razón del warn")
    @is_staff()
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Mal comportamiento"):
        await interaction.response.defer()
        cursor.execute("INSERT INTO warns (guild_id, user_id, moderator_id, reason) VALUES (?,?,?,?)",
                       (interaction.guild.id, user.id, interaction.user.id, reason))
        db.commit()
        cursor.execute("SELECT COUNT(*) FROM warns WHERE guild_id=? AND user_id=?",
                       (interaction.guild.id, user.id))
        total = cursor.fetchone()[0]

        embed = discord.Embed(title="Warn aplicado ⚠️", color=0xF1C40F)
        embed.add_field(name="Usuario", value=user.mention, inline=True)
        embed.add_field(name="Warn #", value=str(total), inline=True)
        embed.add_field(name="Razón", value=reason, inline=False)
        embed.add_field(name="Por", value=interaction.user.mention, inline=True)
        embed.set_footer(text=f"ID: {user.id}")
        await interaction.followup.send(embed=embed)

        # Auto-Mod
        if total == 3:
            try:
                await user.timeout(timedelta(days=1), reason="Auto-Mod: 3 warns")
                await interaction.channel.send(f"Auto-Mod: {user.mention} fue muteado 1 día tras acumular 3 warns 🤐", delete_after=10)
            except discord.Forbidden:
                pass
        elif total >= 5:
            try:
                await user.ban(reason="Auto-Mod: 5 warns")
                await interaction.channel.send(f"Auto-Mod: {user.mention} fue baneado tras acumular 5 warns 🔨", delete_after=10)
            except discord.Forbidden:
                pass

    @app_commands.command(name="warns", description="Muestra el historial de warns de un usuario")
    @app_commands.describe(user="Usuario a consultar")
    @is_staff()
    async def warns(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        cursor.execute("SELECT id, reason, moderator_id, timestamp FROM warns WHERE guild_id=? AND user_id=? ORDER BY timestamp ASC",
                       (interaction.guild.id, user.id))
        rows = cursor.fetchall()
        if not rows:
            return await interaction.followup.send(f"{user.mention} tiene el historial limpio, sin warns ✅", ephemeral=True)
        embed = discord.Embed(title=f"Warns de {user.display_name} ⚠️", color=0xE67E22)
        embed.set_thumbnail(url=user.display_avatar.url)
        for i, (wid, reason, mod_id, ts) in enumerate(rows, 1):
            mod = interaction.guild.get_member(mod_id)
            mod_name = mod.display_name if mod else f"ID:{mod_id}"
            embed.add_field(name=f"Warn #{i} (ID:{wid})", value=f"**Razón:** {reason}\n**Por:** {mod_name}\n**Fecha:** {ts[:10]}", inline=False)
        embed.set_footer(text=f"Total: {len(rows)} warns | ID: {user.id}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="clearwarns", description="[Staff] Borra todos los warns de un usuario")
    @app_commands.describe(user="Usuario a limpiar")
    @is_staff()
    async def clearwarns(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer()
        cursor.execute("DELETE FROM warns WHERE guild_id=? AND user_id=?", (interaction.guild.id, user.id))
        db.commit()
        await interaction.followup.send(f"Historial de warns de {user.mention} borrado por completo 🧹")

    @app_commands.command(name="unwarn", description="[Staff] Quita una cantidad exacta de warns a un usuario")
    @app_commands.describe(user="Usuario a limpiar", cantidad="Cuántos warns quitar (los más antiguos primero)")
    @is_staff()
    async def unwarn(self, interaction: discord.Interaction, user: discord.Member, cantidad: app_commands.Range[int, 1, 100] = 1):
        await interaction.response.defer()

        cursor.execute("SELECT id FROM warns WHERE guild_id=? AND user_id=? ORDER BY timestamp ASC LIMIT ?",
                       (interaction.guild.id, user.id, cantidad))
        ids = [row[0] for row in cursor.fetchall()]

        if not ids:
            return await interaction.followup.send(f"{user.mention} tiene el historial limpio, sin warns ✅")

        cursor.executemany("DELETE FROM warns WHERE id=?", [(wid,) for wid in ids])
        db.commit()

        cursor.execute("SELECT COUNT(*) FROM warns WHERE guild_id=? AND user_id=?",
                       (interaction.guild.id, user.id))
        restantes = cursor.fetchone()[0]

        await interaction.followup.send(
            f"Se quitaron {len(ids)} warn(s) a {user.mention}. Le quedan **{restantes}** 🧹"
        )
