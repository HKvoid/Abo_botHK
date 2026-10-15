"""Comando y menú de colores exclusivos para Staff."""
import discord
from discord import app_commands
from discord.ext import commands

from core import (
    ROLES_STAFF_COLOR,
    STAFF_COLOR_ROLES,
    TU_ID,
    is_staff_color,
    resolver_color_role,
    resolver_color_roles,
)


class StaffColorSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        options = [discord.SelectOption(label=key, value=key, emoji="🌈") for key in STAFF_COLOR_ROLES]
        super().__init__(placeholder="Elige tu color de Staff...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != TU_ID and not any(role.name in ROLES_STAFF_COLOR for role in interaction.user.roles):
            return await interaction.response.send_message(
                "Este menú es exclusivo para el rol Staff, lo siento 🔒", ephemeral=True,
            )
        await interaction.response.defer(ephemeral=True)
        guild, member, color_name = interaction.guild, interaction.user, self.values[0]
        roles_a_quitar = await resolver_color_roles(guild, "staffcolor", STAFF_COLOR_ROLES)
        new_role = await resolver_color_role(guild, "staffcolor", color_name)
        if not new_role:
            return await interaction.followup.send(
                f"Ese rol (`{color_name}`) todavía no existe en el servidor. Pídele a un admin que lo cree 🙏",
                ephemeral=True,
            )
        try:
            if roles_a_quitar:
                await member.remove_roles(*roles_a_quitar, reason="Cambio de color Staff")
            await member.add_roles(new_role)
            await interaction.followup.send(f"Listo, tu color de Staff ahora es {new_role.mention} 🌈", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(
                "No tengo permisos suficientes para asignar ese rol; revisa mi jerarquía, por favor 🔒",
                ephemeral=True,
            )


class StaffColorSelectView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=60)
        self.add_item(StaffColorSelect(guild))


class StaffColorsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="staffcolor", description="[Staff] Elige tu color exclusivo de Staff")
    @is_staff_color()
    async def staffcolor(self, interaction: discord.Interaction):
        lineas = []
        for name in STAFF_COLOR_ROLES:
            role = await resolver_color_role(interaction.guild, "staffcolor", name)
            lineas.append(role.mention if role else f"@{name} *(rol no creado)*")
        embed = discord.Embed(
            title="Colores de Staff 🌈",
            description=(
                "Colores exclusivos para el rol **Staff**.\n"
                "Selecciona uno del menú abajo. Solo puedes tener un color de Staff activo a la vez.\n\n"
                + "\n".join(lineas)
            ),
            color=0x8E44AD,
        )
        await interaction.response.send_message(embed=embed, view=StaffColorSelectView(interaction.guild))
