"""Comando de ayuda categorizado y paginado."""
import discord
from discord import app_commands
from discord.ext import commands
from core import TU_ID, ROLES_COMANDOS


class HelpView(discord.ui.View):
    def __init__(self, owner_id: int, pages: list[discord.Embed]):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.pages = pages
        self.index = 0
        self._sync()

    def _sync(self):
        self.previous.disabled = self.index <= 0
        self.next.disabled = self.index >= len(self.pages) - 1
        self.counter.label = f"Página {self.index + 1}/{len(self.pages)}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Solo quien abrió esta ayuda puede cambiar de página.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Anterior", emoji="◀️", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index -= 1
        self._sync()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="Página 1/1", style=discord.ButtonStyle.primary)
    async def counter(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

    @discord.ui.button(label="Siguiente", emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index += 1
        self._sync()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def _page(title: str, description: str, category: str, number: int, total: int, color=0x3498DB):
        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_footer(text=f"Abo Bot • {category} • Página {number}/{total}")
        return embed

    @app_commands.command(name="help", description="Muestra los comandos de Abo por categorías")
    async def help(self, interaction: discord.Interaction):
        is_staff = interaction.user.id == TU_ID or any(r.name in ROLES_COMANDOS for r in interaction.user.roles)
        category_pages = [
            ("Inicio", "🤖 **IA**\nMenciona a Abo en un mensaje para hablar con él.\n\n🎨 **Colores**\n`/color` — Abre el menú de colores.\n\n🎫 **Soporte**\nUsa el panel de tickets para abrir una conversación privada con el staff.\n\n🎴 **Abo Cards**\n`/cguia` — Guía breve de todos los comandos de cartas con prefijo `!` y slash `/`."),
        ]
        if is_staff:
            category_pages.extend([
                ("Moderación", "🔨 `/ban usuario [razón]` — Banea a un usuario.\n🤐 `/mute usuario [tiempo]` — Aplica timeout (`10m`, `2h`, `1d`).\n⚠️ `/warn usuario [razón]` — Registra una advertencia.\n📋 `/warns usuario` — Consulta el historial.\n🧹 `/unwarn usuario cantidad` — Retira warns.\n🗑️ `/clearwarns usuario` — Limpia el historial.\n🧽 `/limpia cantidad` — Borra mensajes."),
                ("Administración y configuración", "🎨 `/create_colors` — Crea roles de colores.\n✨ `/create_booster_colors` — Crea roles para boosters.\n🎫 `/ticket_config` — Configura tickets.\n📌 `/ticket_panel` — Publica el panel de tickets.\n📄 `/ticket_transcript canal` — Obtén una transcripción.\n👋 `/welcome_config` y `/leave_config` — Configura mensajes de entrada y salida.\n🔕 `/welcome_off` y `/leave_off` — Desactiva esos mensajes.\n👻 `/scan`, `/purgaafk` y `/purgaexc` — Herramientas de purga AFK."),
            ])
            if interaction.user.id == TU_ID:
                category_pages.append(("Owner", "☢️ `/reset_servidor` — Reinicia el servidor con respaldo y confirmación.\n\nEste comando está limitado exclusivamente al owner."))

        total = len(category_pages)
        pages = [self._page(f"Comandos de Abo · {title} 📖", text, title, i + 1, total) for i, (title, text) in enumerate(category_pages)]
        await interaction.response.send_message(embed=pages[0], view=HelpView(interaction.user.id, pages), ephemeral=True)
