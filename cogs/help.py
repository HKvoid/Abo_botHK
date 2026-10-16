"""Comando de ayuda."""
import discord
from discord import app_commands
from discord.ext import commands
from core import TU_ID, ROLES_COMANDOS

class HelpCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="help", description="Muestra todos los comandos de Abo")
    async def help(self, interaction: discord.Interaction):
        es_staff = interaction.user.id == TU_ID or any(r.name in ROLES_COMANDOS for r in interaction.user.roles)
        embed = discord.Embed(title="Comandos de Abo 📖", color=0x3498DB,
                              description="Todos los slash commands disponibles. Los marcados con 🔒 son solo Staff.")
        embed.set_thumbnail(url=interaction.guild.me.display_avatar.url)

        # Públicos
        embed.add_field(name="🤖 IA", value="`@Abo <mensaje>` — Háblale a Abo con IA", inline=False)
        embed.add_field(name="🎨 Color", value="`/color` — Elige tu color de nombre (incluye Booster Colors si aplica)", inline=False)
        embed.add_field(name="🎫 Soporte", value="Usa el botón del panel de tickets para abrir una conversación privada con el staff.", inline=False)
        embed.add_field(name="🎴 Abo Cards", value=(
            "`/sobre` — Abre un sobre de 3 cartas\n"
            "`/coleccion [usuario]` — Consulta un álbum\n"
            "`/carta <nombre>` — Mira una carta e imagen\n"
            "`/diario_cartas` y `/saldo_cartas` — Economía\n"
            "`/intercambiar_carta` — Intercambia con otro miembro\n"
            "`/mercado` — Compra, publica o retira cartas\n"
            "`/ranking_cartas` — Ranking por valor de colección"
        ), inline=False)
        if es_staff:
            embed.add_field(name="⚠️ Warns 🔒", value=(
                "`/warn <user> [razón]` — Warnea a un usuario (auto-mute en 3, auto-ban en 5)\n"
                "`/warns <user>` — Ve el historial de warns (solo tú lo ves)\n"
                "`/unwarn <user> <cantidad>` — Quita una cantidad exacta de warns (los más antiguos primero)\n"
                "`/clearwarns <user>` — Borra todos los warns de un usuario\n"
                "`/addrol <rol> <users>` — Da un rol a varios usuarios\n"
                "`/delrol <rol> <users>` — Quita un rol a varios usuarios\n"
            ), inline=False)
            embed.add_field(name="🛡️ Moderación 🔒", value=(
                "`/ban <user> [razón]` — Banea a un usuario\n"
                "`/mute <user> [tiempo]` — Timeout (ej: `10m`, `2h`, `1d`)\n"
                "`/limpia <cantidad>` — Borra mensajes (máx 100)"
            ), inline=False)
            embed.add_field(name="👻 Purga AFK 🔒", value=(
                "`/scan` — Escaneo masivo de TODOS los canales (texto, voz, stage e hilos) buscando miembros sin mensajes en 15 días\n"
                "`/purgaafk` — Patea a los del último /scan\n"
                "`/purgaexc add <user> [razón]` — Agrega a alguien a excepciones (no se purga aunque esté inactivo)\n"
                "`/purgaexc quitar <user>` — Quita a alguien de excepciones\n"
                "`/purgaexc lista` — Ve quién está en excepciones"
            ), inline=False)
            embed.add_field(name="🎨 Setup 🔒", value=(
                "`/create_colors` — Crea los 20 roles de color\n"
                "`/create_booster_colors` — Crea los 5 roles de color de Booster"
            ), inline=False)
            embed.add_field(name="🌈 Staff Colors 🔒", value=(
                "`/staffcolor` — Elige tu color exclusivo de Staff (solo rol Staff)\n"
                "*(los roles de color los crea un admin manualmente en Discord)*"
            ), inline=False)
            embed.add_field(name="💎 Booster Colors 🔒", value=(
                "El botón **Booster Colors** dentro de `/color` es exclusivo para Server Boosters\n"
                "*(Abo crea los 5 roles automáticamente con `/create_booster_colors`)*"
            ), inline=False)
            embed.add_field(name="🎫 Tickets 🔒", value=(
                "`/ticket_config <categoria> <rol_staff> <canal_registros>` — Configura tickets y transcripciones\n"
                "`/ticket_panel <canal>` — Publica el panel persistente para abrir tickets\n"
                "`/ticket_transcript <canal>` — Descarga la copia guardada en Neon (solo quien abrió o staff)"
            ), inline=False)
            embed.add_field(name="👋 Bienvenidas y despedidas 🔒", value=(
                "`/welcome_config <canal> <texto> [imagen_url]` y `/leave_config <canal> <texto> [imagen_url]`\n"
                "Variables disponibles: `{user}`, `{username}`, `{server}`, `{member_count}`\n"
                "`/welcome_off` y `/leave_off` — Desactiva cada mensaje"
            ), inline=False)
            if interaction.user.id == TU_ID:
                embed.add_field(name="☢️ Reset Servidor 🔒 (solo owner)", value=(
                    "`/reset_servidor` — Borra TODOS los canales y roles, con backup JSON previo y confirmación por nombre"
                ), inline=False)

        embed.set_footer(text="Abo Bot • Prefix: slash /")
        await interaction.response.send_message(embed=embed, ephemeral=True)
