"""Punto de entrada de Abo. Los comandos viven en cogs independientes."""
import re

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

from core import TOKEN, db, log, preguntar_ia
from cogs.colors import ColorMenuView, ColorsCog
from cogs.staff_colors import StaffColorsCog
from cogs.booster_colors import BoosterColorsCog
from cogs.moderation import ModCog
from cogs.purge import PurgaCog
from cogs.warns import WarnsCog
from cogs.reset import ResetCog
from cogs.help import HelpCog
from cogs.tickets import TicketCog, TicketPanelView, TicketControlView, load_configured_ticket_views
from cogs.greetings import GreetingsCog
from cogs.cards import CardsCog, ensure_card_catalog

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class AboBot(commands.Bot):
    async def setup_hook(self):
        await db.connect()
        await ensure_card_catalog()
        log.info("Conexión persistente a Neon inicializada")
        # La vista persistente se registra una vez al iniciar, incluso tras reinicios.
        self.add_view(ColorMenuView())
        self.add_view(TicketPanelView())
        self.add_view(TicketControlView())
        await load_configured_ticket_views(self)
        cogs = (
            ColorsCog, StaffColorsCog, BoosterColorsCog, CardsCog, ModCog,
            PurgaCog, WarnsCog, TicketCog, GreetingsCog, HelpCog, ResetCog,
        )
        for cog_class in cogs:
            await self.add_cog(cog_class(self))
        cards_cog = self.get_cog("CardsCog")
        if cards_cog:
            await cards_cog.restore_trade_sessions()
        await self.tree.sync()
        log.info("Cogs cargados y comandos slash sincronizados: %s", len(self.tree.get_commands()))

    async def close(self):
        try:
            await super().close()
        finally:
            await db.close()


bot = AboBot(command_prefix=commands.when_mentioned, intents=intents)


@bot.event
async def on_ready():
    log.info("Online: %s", bot.user)
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="LatamOS")
    )


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        msg = "No tienes permiso para usar este comando, lo siento 🔒"
    else:
        log.error("[Command Error] %s: %s", interaction.command, error)
        msg = "Algo salió mal ejecutando el comando; inténtalo de nuevo en un momento 😅"
    try:
        embed = discord.Embed(title="Abo encontró un problema", description=msg, color=0xED4245)
        embed.set_footer(text="Abo · Revisa los permisos o inténtalo de nuevo")
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.HTTPException:
        pass


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    cards_cog = bot.get_cog("CardsCog")
    if cards_cog and await cards_cog.handle_trade_message(message):
        return
    if cards_cog and await cards_cog.handle_card_prefix(message):
        return
    if bot.user in message.mentions:
        texto = re.sub(r"<@!?\d+>", "", message.content).strip()
        async with message.channel.typing():
            respuesta = await preguntar_ia(texto, message.author.id, message.channel.id)
        await message.channel.send(
            respuesta.replace("@everyone", "@\u200beveryone"),
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )


if __name__ == "__main__":
    bot.run(TOKEN)
