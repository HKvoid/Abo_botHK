"""Comandos y menú de colores para Server Boosters."""
import discord
from discord import app_commands
from discord.ext import commands

from core import (
    BOOSTER_COLOR_ROLES,
    _es_booster,
    guardar_color_role_id,
    is_staff,
    resolver_color_role,
    resolver_color_roles,
)


class BoosterColorSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        options = [discord.SelectOption(label=key, value=key, emoji="💎") for key in BOOSTER_COLOR_ROLES]
        super().__init__(placeholder="Elige tu color de Booster...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not _es_booster(interaction.user):
            return await interaction.response.send_message(
                "Este menú es exclusivo para Server Boosters, así que ya sabes qué hacer 💎",
                ephemeral=True,
            )
        await interaction.response.defer(ephemeral=True)
        guild, member, color_name = interaction.guild, interaction.user, self.values[0]
        roles_a_quitar = await resolver_color_roles(guild, "boostercolor", BOOSTER_COLOR_ROLES.keys())
        new_role = await resolver_color_role(guild, "boostercolor", color_name)
        if not new_role:
            return await interaction.followup.send(
                f"Ese rol (`{color_name}`) todavía no existe. Prueba primero con `/create_booster_colors` 💎",
                ephemeral=True,
            )
        try:
            if roles_a_quitar:
                await member.remove_roles(*roles_a_quitar, reason="Cambio de color Booster")
            await member.add_roles(new_role)
            await interaction.followup.send(
                f"Listo, tu color de Booster ahora es {new_role.mention}. Gracias por el apoyo al server 💎",
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "No tengo permisos suficientes para asignar ese rol; revisa mi jerarquía, por favor 🔒",
                ephemeral=True,
            )


class BoosterColorSelectView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=60)
        self.add_item(BoosterColorSelect(guild))


class BoosterColorsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="create_booster_colors", description="[Staff] Crea los 5 roles de color de Booster si no existen")
    @is_staff()
    async def create_booster_colors(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        creados = 0
        for name, color_hex in BOOSTER_COLOR_ROLES.items():
            role = await resolver_color_role(interaction.guild, "boostercolor", name)
            if not role:
                role = await interaction.guild.create_role(
                    name=name, colour=discord.Colour(color_hex), reason="Abo Booster Colors",
                )
                creados += 1
            await guardar_color_role_id(interaction.guild.id, "boostercolor", name, role.id)
        await interaction.followup.send(
            f"Listo: creé {creados} rol(es) de Booster nuevo(s). Los demás ya existían y quedaron "
            "blindados por ID ante futuros renombres ✅",
            ephemeral=True,
        )
