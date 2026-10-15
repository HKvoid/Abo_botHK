"""Comandos y menús de colores básicos."""
import discord
from discord import app_commands
from discord.ext import commands

from core import (
    BOOSTER_COLOR_ROLES,
    COLOR_ROLES,
    _es_booster,
    guardar_color_role_id,
    is_staff,
    resolver_color_role,
    resolver_color_roles,
)
from cogs.booster_colors import BoosterColorSelectView


class ColorSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        options = [
            discord.SelectOption(label=key, value=key, emoji="🎨")
            for key in COLOR_ROLES
        ]
        super().__init__(placeholder="Elige tu color...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild, member, color_name = interaction.guild, interaction.user, self.values[0]
        roles_a_quitar = await resolver_color_roles(guild, "color", COLOR_ROLES.keys())
        new_role = await resolver_color_role(guild, "color", color_name)
        if not new_role:
            return await interaction.followup.send(
                f"Ese rol (`{color_name}`) todavía no existe. Prueba primero con `/create_colors` 🤔",
                ephemeral=True,
            )
        try:
            if roles_a_quitar:
                await member.remove_roles(*roles_a_quitar, reason="Cambio de color")
            await member.add_roles(new_role)
            await interaction.followup.send(f"Listo, tu color ahora es {new_role.mention} 🎨", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(
                "No tengo permisos suficientes para asignar ese rol; revisa mi jerarquía, por favor 🔒",
                ephemeral=True,
            )


class ColorSelectView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=60)
        self.add_item(ColorSelect(guild))


class ColorMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Basic Colors", style=discord.ButtonStyle.secondary,
        emoji="🎨", custom_id="color_basic_button",
    )
    async def abrir_basicos(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="Elige tu color 🎨",
            description="Selecciona un color del menú de abajo. Solo tú puedes ver este mensaje.",
            color=0x2B2D31,
        )
        embed.set_footer(text="Solo puedes tener un color activo a la vez.")
        await interaction.response.send_message(
            embed=embed, view=ColorSelectView(interaction.guild), ephemeral=True,
        )

    @discord.ui.button(
        label="Booster Colors", style=discord.ButtonStyle.secondary,
        emoji="💎", custom_id="color_booster_button",
    )
    async def abrir_booster(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _es_booster(interaction.user):
            return await interaction.response.send_message(
                "Este menú es exclusivo para Server Boosters, así que ya sabes qué hacer 💎",
                ephemeral=True,
            )
        embed = discord.Embed(
            title="Elige tu color de Booster 💎",
            description="Selecciona un color del menú de abajo. Solo tú puedes ver este mensaje.",
            color=0x2B2D31,
        )
        embed.set_footer(text="Solo puedes tener un color de Booster activo a la vez.")
        await interaction.response.send_message(
            embed=embed, view=BoosterColorSelectView(interaction.guild), ephemeral=True,
        )


async def build_combined_color_embed(guild: discord.Guild):
    basic_lines = []
    for name in COLOR_ROLES:
        role = await resolver_color_role(guild, "color", name)
        basic_lines.append(role.mention if role else f"**{name}**")

    booster_lines = []
    for name in BOOSTER_COLOR_ROLES:
        role = await resolver_color_role(guild, "boostercolor", name)
        booster_lines.append(role.mention if role else f"**{name}**")

    embed = discord.Embed(
        title="Color Roles 🎨",
        description=(
            "Personaliza el color de tu nombre en el servidor.\n"
            "Solo puedes tener **un color activo** a la vez.\n\u200b"
        ),
        color=0x2B2D31,
    )
    embed.add_field(name="Basic Colors:", value="\n".join(basic_lines), inline=False)
    embed.add_field(name="Booster Colors:", value="\n".join(booster_lines), inline=False)
    embed.set_footer(text="Abo Colors • Booster Colors es exclusivo para Server Boosters")
    return embed


class ColorsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="color", description="Muestra el menú de colores del servidor")
    async def color_menu(self, interaction: discord.Interaction):
        embed = await build_combined_color_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, view=ColorMenuView())

    @app_commands.command(name="create_colors", description="[Staff] Crea los 20 roles de color si no existen")
    @is_staff()
    async def create_colors(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        creados = 0
        for name, color_hex in COLOR_ROLES.items():
            role = await resolver_color_role(interaction.guild, "color", name)
            if not role:
                role = await interaction.guild.create_role(
                    name=name, colour=discord.Colour(color_hex), reason="Abo Colors",
                )
                creados += 1
            await guardar_color_role_id(interaction.guild.id, "color", name, role.id)
        await interaction.followup.send(
            f"Listo: creé {creados} rol(es) nuevo(s). Los demás ya existían y quedaron "
            "blindados por ID ante futuros renombres ✅",
            ephemeral=True,
        )
