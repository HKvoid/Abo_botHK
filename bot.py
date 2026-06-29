import discord
import os
import re
import random
import asyncio
import sqlite3
import logging
from datetime import timedelta
from groq import Groq
from discord import app_commands
from discord.ext import commands

# ─────────────────────────────────────────
# LOGGING + CONFIG
# ─────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("Abo")

TOKEN = os.getenv("TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TU_ID = 1180967503682355220
ROL_MIEMBRO = "MemberLT"
ROLES_COMANDOS = ["Admin", "Mod", "Semi Admin", "ViceRoot", "Root"]

if not TOKEN or not GROQ_API_KEY:
    raise RuntimeError("❌ Falta TOKEN o GROQ_API_KEY")

groq_client = Groq(api_key=GROQ_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents) # Cambiado a Bot

# VARIABLES GLOBALES PURGA
ULTIMOS_FANTASMAS = {}

# ─────────────────────────────────────────
# CHECK PA STAFF
# ─────────────────────────────────────────
def is_staff():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id == TU_ID: return True
        return any(rol.name in ROLES_COMANDOS for rol in interaction.user.roles)
    return app_commands.check(predicate)

# ─────────────────────────────────────────
# DB MEMORIA IGUAL
# ─────────────────────────────────────────
db = sqlite3.connect("abo_memoria.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("""CREATE TABLE IF NOT EXISTS memoria (user_id INTEGER, canal_id INTEGER, rol TEXT, contenido TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
db.commit()

def guardar_mensaje(user_id, canal_id, rol, contenido):
    cursor.execute("INSERT INTO memoria (user_id, canal_id, rol, contenido) VALUES (?,?,?,?)", (user_id, canal_id, rol, contenido))
    cursor.execute("""DELETE FROM memoria WHERE rowid NOT IN (SELECT rowid FROM memoria WHERE user_id =? AND canal_id =? ORDER BY timestamp DESC LIMIT 30) AND user_id =? AND canal_id =?""", (user_id, canal_id, user_id, canal_id))
    db.commit()

def obtener_historial(user_id, canal_id, limite=30):
    cursor.execute("SELECT rol, contenido FROM memoria WHERE user_id =? AND canal_id =? ORDER BY timestamp DESC LIMIT?", (user_id, canal_id, limite))
    return list(reversed(cursor.fetchall()))

# ─────────────────────────────────────────
# IA IGUAL
# ─────────────────────────────────────────
SISTEMA_ABO = ("Eres Abo, bot de Discord. Respondes en máximo 2 oraciones. Usa 'we', 'nmms', 'pa'. Sé sarcástico pero COHERENTE.")
async def preguntar_ia(prompt: str, user_id: int, canal_id: int) -> str:
    try:
        historial = obtener_historial(user_id, canal_id)
        mensajes = [{"role": "system", "content": SISTEMA_ABO}] + [{"role": r, "content": c} for r, c in historial] + [{"role": "user", "content": prompt}]
        chat = groq_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=mensajes, max_tokens=150, temperature=0.9)
        respuesta = chat.choices[0].message.content.strip()
        guardar_mensaje(user_id, canal_id, "user", prompt); guardar_mensaje(user_id, canal_id, "assistant", respuesta)
        return respuesta if respuesta else "Ni idea we"
    except Exception as e:
        log.error(f"[Groq Error] {e}"); return "Me bugueé we"

# ─────────────────────────────────────────
# COG COLORES - LO NUEVO 🔥
# ─────────────────────────────────────────
COLOR_ROLES = { # Tus 20 colores de la foto
    "Vivid Red": 0xE74C3C, "Orange": 0xE67E22, "Yellow": 0xF1C40F, "Green": 0x2ECC71, "Blue": 0x3498DB,
    "Purple": 0x9B59B6, "Pink": 0xFF69B4, "Cyan": 0x1ABC9C, "White": 0xECF0F1, "Black": 0x2C3E50,
    "Booster Gold": 0xFFD700, "Booster Silver": 0xC0C0C0, "Aurora": 0x00FFFF, "Neon": 0x39FF14, "Blood": 0x8B0000,
    "Ocean": 0x006994, "Galaxy": 0x4B0082, "Fire": 0xFF4500, "Ice": 0xADD8E6, "Forest": 0x228B22,
}

class ColorSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=name, description=f"Color {name}", emoji="🎨") for name in COLOR_ROLES.keys()]
        super().__init__(placeholder="Select a color", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = interaction.user
        color_name = self.values[0]

        # Quita todos los colores viejos
        color_role_ids = [discord.utils.get(guild.roles, name=n).id for n in COLOR_ROLES.keys() if discord.utils.get(guild.roles, name=n)]
        await member.remove_roles(*[guild.get_role(rid) for rid in color_role_ids if guild.get_role(rid)], reason="Cambio de color")

        # Da el nuevo
        new_role = discord.utils.get(guild.roles, name=color_name)
        if new_role:
            await member.add_roles(new_role)
            await interaction.followup.send(f"You changed your color to {new_role.mention}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ No existe el rol `{color_name}`. Crea los roles primero we.", ephemeral=True)

class ColorView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None); self.add_item(ColorSelect())

class ColorsCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="color", description="Abre el menú pa cambiar tu color")
    async def color_menu(self, interaction: discord.Interaction):
        await interaction.response.send_message("Elige tu color:", view=ColorView(), ephemeral=True)

    @app_commands.command(name="create_colors", description="[Staff] Crea los 20 roles de color si no existen")
    @is_staff()
    async def create_colors(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        creados = 0
        for name, hex in COLOR_ROLES.items():
            if not discord.utils.get(interaction.guild.roles, name=name):
                await interaction.guild.create_role(name=name, colour=discord.Colour(hex), reason="Abo Colors")
                creados += 1
        await interaction.followup.send(f"✅ Creados {creados} roles de color. Los otros ya existían.", ephemeral=True)

async def setup_cogs(bot):
    await bot.add_cog(ColorsCog(bot))

# ─────────────────────────────────────────
# EVENTOS + COMANDOS VIEJOS A SLASH
# ─────────────────────────────────────────
@bot.event
async def on_ready():
    await setup_cogs(bot)
    await bot.tree.sync() # REGISTRA LOS /
    log.info(f"Online: {bot.user} | Slash Commands listos")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="LatamOS"))

@bot.event
async def on_message(message: discord.Message): # IA por mención se queda igual
    if message.author.bot: return
    if bot.user in message.mentions:
        texto = re.sub(r"<@!?\d+>", "", message.content).strip()
        async with message.channel.typing():
            respuesta = await preguntar_ia(texto, message.author.id, message.channel.id)
        await message.channel.send(respuesta.replace("@everyone", "@\u200beveryone"), allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))

# EJEMPLO:!scan pasado a /scan
@bot.tree.command(name="scan", description="[Staff] Busca miembros con 0 mensajes en 15d")
@is_staff()
async def scan(interaction: discord.Interaction):
    await interaction.response.defer()
    rol_miembro = discord.utils.get(interaction.guild.roles, name=ROL_MIEMBRO)
    if not rol_miembro: return await interaction.followup.send(f"No hay rol '{ROL_MIEMBRO}' we")

    todos = {m.id: m for m in rol_miembro.members if not m.bot}
    actividad = {mid: 0 for mid in todos.keys()}
    hace_15dias = discord.utils.utcnow() - timedelta(days=15)
    for canal in interaction.guild.text_channels:
        if not canal.permissions_for(interaction.guild.me).read_message_history: continue
        async for msg in canal.history(limit=None, after=hace_15dias):
            if msg.author.id in actividad: actividad[msg.author.id] += 1

    fantasmas_ids = [mid for mid, count in actividad.items() if count == 0]
    ULTIMOS_FANTASMAS[interaction.guild.id] = fantasmas_ids
    if fantasmas_ids:
        mentions = [interaction.guild.get_member(mid).mention for mid in fantasmas_ids[:20]]
        await interaction.followup.send(f"**Tiesos 15d:** {len(fantasmas_ids)}\n{', '.join(mentions)}\nUsa `/purgaafk` pa patearlos")
    else:
        await interaction.followup.send("No hay tiesos we 🔥")

@bot.tree.command(name="purgaafk", description="[Staff] Patea a los del último /scan")
@is_staff()
async def purgaafk(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id not in ULTIMOS_FANTASMAS or not ULTIMOS_FANTASMAS[guild_id]:
        return await interaction.response.send_message("Primero haz un `/scan` we", ephemeral=True)

    await interaction.response.defer()
    pateados = 0
    for user_id in ULTIMOS_FANTASMAS[guild_id]:
        user = interaction.guild.get_member(user_id)
        if user and not user.bot:
            try: await user.kick(reason="Inactividad 15d - Abo"); pateados += 1; await asyncio.sleep(0.5)
            except: pass
    await interaction.followup.send(f"✅ Purga terminada: {pateados} pateados")
    ULTIMOS_FANTASMAS[guild_id] = []

# TUS OTROS!ban!mute!limpia pásalos igual a @bot.tree.command()

bot.run(TOKEN)
