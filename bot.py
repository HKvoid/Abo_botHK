import discord
import os
import re
import random
import asyncio
import sqlite3
import logging
import aiohttp
import io
from datetime import timedelta
from groq import Groq
from discord import app_commands
from discord.ext import commands

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
bot = commands.Bot(command_prefix="!", intents=intents)
ULTIMOS_FANTASMAS = {}

def is_staff():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id == TU_ID: return True
        return any(rol.name in ROLES_COMANDOS for rol in interaction.user.roles)
    return app_commands.check(predicate)

db = sqlite3.connect("abo_memoria.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("""CREATE TABLE IF NOT EXISTS memoria (user_id INTEGER, canal_id INTEGER, rol TEXT, contenido TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS warns (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, user_id INTEGER, mod_id INTEGER, reason TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
db.commit()

def guardar_mensaje(user_id, canal_id, rol, contenido):
    cursor.execute("INSERT INTO memoria (user_id, canal_id, rol, contenido) VALUES (?,?,?,?)", (user_id, canal_id, rol, contenido))
    cursor.execute("""DELETE FROM memoria WHERE rowid NOT IN (SELECT rowid FROM memoria WHERE user_id =? AND canal_id =? ORDER BY timestamp DESC LIMIT 30) AND user_id =? AND canal_id =?""", (user_id, canal_id, user_id, canal_id))
    db.commit()

def obtener_historial(user_id, canal_id, limite=30):
    cursor.execute("SELECT rol, contenido FROM memoria WHERE user_id =? AND canal_id =? ORDER BY timestamp DESC LIMIT?", (user_id, canal_id, limite))
    return list(reversed(cursor.fetchall()))

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

COLOR_ROLES = {"Vivid Red": 0xE74C3C, "Orange": 0xE67E22, "Yellow": 0xF1C40F, "Green": 0x2ECC71, "Blue": 0x3498DB, "Purple": 0x9B59B6, "Pink": 0xFF69B4, "Cyan": 0x1ABC9C, "White": 0xECF0F1, "Black": 0x2C3E50, "Booster Gold": 0xFFD700, "Booster Silver": 0xC0C0C0, "Aurora": 0x00FFFF, "Neon": 0x39FF14, "Blood": 0x8B0000, "Ocean": 0x006994, "Galaxy": 0x4B0082, "Fire": 0xFF4500, "Ice": 0xADD8E6, "Forest": 0x228B22}

class ColorSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=name, emoji="🎨") for name in COLOR_ROLES.keys()]
        super().__init__(placeholder="Select a color", min_values=1, max_values=1, options=options)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild, member, color_name = interaction.guild, interaction.user, self.values[0]
        roles_a_quitar = [guild.get_role(discord.utils.get(guild.roles, name=n).id) for n in COLOR_ROLES.keys() if discord.utils.get(guild.roles, name=n)]
        if roles_a_quitar: await member.remove_roles(*roles_a_quitar, reason="Cambio de color")
        new_role = discord.utils.get(guild.roles, name=color_name)
        if new_role: await member.add_roles(new_role); await interaction.followup.send(f"You changed your color to {new_role.mention}", ephemeral=True)
        else: await interaction.followup.send(f"❌ No existe el rol `{color_name}`. Usa `/create_colors` we.", ephemeral=True)

class ColorView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None); self.add_item(ColorSelect())

class ColorsCog(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @app_commands.command(name="color", description="Abre el menú pa cambiar tu color")
    async def color_menu(self, interaction: discord.Interaction): await interaction.response.send_message("Elige tu color:", view=ColorView(), ephemeral=True)
    @app_commands.command(name="create_colors", description="[Staff] Crea los 20 roles de color si no existen")
    @is_staff()
    async def create_colors(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); creados = 0
        for name, hex in COLOR_ROLES.items():
            if not discord.utils.get(interaction.guild.roles, name=name):
                await interaction.guild.create_role(name=name, colour=discord.Colour(hex), reason="Abo Colors"); creados += 1
        await interaction.followup.send(f"✅ Creados {creados} roles. Los otros ya existían.", ephemeral=True)

class ModCog(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @app_commands.command(name="ban", description="[Staff] Banea a un usuario") @app_commands.describe(user="A quién banear", reason="Razón del ban") @is_staff()
    async def ban(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Se pasó de verga"):
        await interaction.response.defer(ephemeral=True)
        try: await user.ban(reason=f"{reason} | By {interaction.user}"); await interaction.followup.send(f"🔨 {user.mention} desterrado alv. Razón: {reason}")
        except discord.Forbidden: await interaction.followup.send("❌ No tengo permisos pa banearlo we")
    @app_commands.command(name="mute", description="[Staff] Da timeout a un usuario") @app_commands.describe(user="A quién mutear", time="10m, 2h, 1d") @is_staff()
    async def mute(self, interaction: discord.Interaction, user: discord.Member, time: str = "10m"):
        await interaction.response.defer(ephemeral=True)
        try: mult = {"m": 60, "h": 3600, "d": 86400}; tiempo_seg = int(time[:-1]) * mult[time[-1]]; await user.timeout(timedelta(seconds=tiempo_seg), reason=f"Muted by {interaction.user}"); await interaction.followup.send(f"🤐 {user.mention} silenciado por {time}")
        except: await interaction.followup.send("❌ Tiempo inválido we. Usa `10m`, `2h`, `1d`")
    @app_commands.command(name="limpia", description="[Staff] Borra mensajes") @app_commands.describe(amount="Cantidad 1-100") @is_staff()
    async def limpia(self, interaction: discord.Interaction, amount: int = 5):
        if amount > 100: amount = 100
        await interaction.response.defer(ephemeral=True); borrados = await interaction.channel.purge(limit=amount + 1); await interaction.followup.send(f"🧹 {len(borrados)-1} mensajes alv", ephemeral=True)
    @app_commands.command(name="addrol", description="[Staff] Da un rol a varios users") @is_staff()
    async def addrol(self, interaction: discord.Interaction, rol: discord.Role, users: str):
        await interaction.response.defer(ephemeral=True); mentions = re.findall(r'<@!?(\d+)>', users); exitos, fallos = [], []
        for uid in mentions:
            user = interaction.guild.get_member(int(uid))
            if user:
                try: await user.add_roles(rol); exitos.append(user.name)
                except: fallos.append(user.name)
        await interaction.followup.send(f"✅ Dado a: {', '.join(exitos)}\n❌ Falló: {', '.join(fallos)}" if fallos else f"✅ Dado a: {', '.join(exitos)}")
    @app_commands.command(name="delrol", description="[Staff] Quita un rol a varios users") @is_staff()
    async def delrol(self, interaction: discord.Interaction, rol: discord.Role, users: str):
        await interaction.response.defer(ephemeral=True); mentions = re.findall(r'<@!?(\d+)>', users); exitos, fallos = [], []
        for uid in mentions:
            user = interaction.guild.get_member(int(uid))
            if user:
                try: await user.remove_roles(rol); exitos.append(user.name)
                except: fallos.append(user.name)
        await interaction.followup.send(f"🗑️ Quitado a: {', '.join(exitos)}\n❌ Falló: {', '.join(fallos)}" if fallos else f"🗑️ Quitado a: {', '.join(exitos)}")

class PurgaCog(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @app_commands.command(name="scan", description="[Staff] Busca miembros con 0 mensajes en 15d") @is_staff()
    async def scan(self, interaction: discord.Interaction):
        await interaction.response.defer(); rol_miembro = discord.utils.get(interaction.guild.roles, name=ROL_MIEMBRO)
        if not rol_miembro: return await interaction.followup.send(f"No hay rol '{ROL_MIEMBRO}' we")
        todos = {m.id: m for m in rol_miembro.members if not m.bot}; actividad = {mid: 0 for mid in todos.keys()}; hace_15dias = discord.utils.utcnow() - timedelta(days=15)
        for canal in interaction.guild.text_channels:
            if not canal.permissions_for(interaction.guild.me).read_message_history: continue
            async for msg in canal.history(limit=None, after=hace_15dias):
                if msg.author.id in actividad: actividad[msg.author.id] += 1
        fantasmas_ids = [mid for mid, count in actividad.items() if count == 0]; ULTIMOS_FANTASMAS[interaction.guild.id] = fantasmas_ids
        if fantasmas_ids: mentions = [interaction.guild.get_member(mid).mention for mid in fantasmas_ids[:20]]; await interaction.followup.send(f"**Tiesos 15d:** {len(fantasmas_ids)}\n{', '.join(mentions)}\nUsa `/purgaafk` pa patearlos")
        else: await interaction.followup.send("No hay tiesos we 🔥")
    @app_commands.command(name="purgaafk", description="[Staff] Patea a los del último /scan") @is_staff()
    async def purgaafk(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id not in ULTIMOS_FANTASMAS or not ULTIMOS_FANTASMAS[guild_id]: return await interaction.response.send_message("Primero haz un `/scan` we", ephemeral=True)
        await interaction.response.defer(); pateados = 0
        for user_id in ULTIMOS_FANTASMAS[guild_id]:
            user = interaction.guild.get_member(user_id)
            if user and not user.bot:
                try: await user.kick(reason="Inactividad 15d - Abo"); pateados += 1; await asyncio.sleep(0.5)
                except: pass
        await interaction.followup.send(f"✅ Purga terminada: {pateados} pateados"); ULTIMOS_FANTASMAS[guild_id] = []

class WarnCog(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @app_commands.command(name="warn", description="[Staff] Dale un strike a un usuario") @app_commands.describe(user="A quién warnnear", reason="Razón del warn") @is_staff()
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        await interaction.response.defer(ephemeral=True)
        if user.id == interaction.user.id: return await interaction.followup.send("No te puedes warnnear a ti mismo we")
        if user.top_role >= interaction.user.top_role: return await interaction.followup.send("No le puedes pegar al de arriba we")
        cursor.execute("INSERT INTO warns (guild_id, user_id, mod_id, reason) VALUES (?,?,?,?)", (interaction.guild.id, user.id, interaction.user.id, reason)); db.commit()
        cursor.execute("SELECT COUNT(*) FROM warns WHERE guild_id =? AND user_id =?", (interaction.guild.id, user.id)); total_warns = cursor.fetchone()[0]; action_taken = ""
        if total_warns == 3: await user.timeout(timedelta(days=1), reason="3 Warns Automáticos - Abo"); action_taken = "\n🤐 Auto-Mute 1d aplicado."
        elif total_warns >= 5: await user.ban(reason="5 Warns Automáticos - Abo"); action_taken = "\n🔨 Auto-Ban aplicado."
        embed = discord.Embed(title=f"⚠️ Warn #{total_warns} a {user.name}", description=reason, color=0xffa500); embed.add_field(name="Total", value=f"{total_warns}/5 strikes", inline=True); await interaction.followup.send(embed=embed)
        if action_taken: await interaction.channel.send(f"{user.mention} {action_taken}")
    @app_commands.command(name="warns", description="[Staff] Ver historial de warns de un usuario") @is_staff()
    async def warns(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True); cursor.execute("SELECT mod_id, reason, timestamp FROM warns WHERE guild_id =? AND user_id =? ORDER BY timestamp DESC", (interaction.guild.id, user.id)); data = cursor.fetchall()
        if not data: return await interaction.followup.send(f"{user.mention} está limpio we 🔥")
        embed = discord.Embed(title=f"📜 Strikes de {user.name} | Total: {len(data)}", color=0xffa500)
        for i, (mod_id, reason, ts) in enumerate(data[:5], 1): mod = interaction.guild.get_member(mod_id); embed.add_field(name=f"#{i} - Por {mod.name if mod else 'Staff'}", value=f"`{reason}`\n`{ts[:10]}`", inline=False)
        await interaction.followup.send(embed=embed)
    @app_commands.command(name="clearwarns", description="[Staff] Borra todos los warns de un usuario") @is_staff()
    async def clearwarns(self, interaction: discord.Interaction, user: discord.Member):
        cursor.execute("DELETE FROM warns WHERE guild_id =? AND user_id =?", (interaction.guild.id, user.id)); db.commit(); await interaction.response.send_message(f"✅ {user.mention} está limpio. Perdón we.", ephemeral=True)

class ImagineCog(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @app_commands.command(name="imagine", description="Genera una imagen con IA. Ej: un gato wey") @app_commands.describe(prompt="Describe lo que quieres que Abo dibuje")
    async def imagine(self, interaction: discord.Interaction, prompt: str):
        await interaction.response.defer(); url = f"https://image.pollinations.ai/prompt/{prompt.replace(' ', '%20')}, jerga mexicana, 8k"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status!= 200: return await interaction.followup.send("Me bugueé we, intenta otra vez")
                    data = io.BytesIO(await resp.read())
            file = discord.File(data, filename="abo_imagine.png"); embed = discord.Embed(title=f"🎨 Imagen de: {prompt}", color=0x9B59B6); embed.set_image(url="attachment://abo_imagine.png"); embed.set_footer(text=f"Pedida por {interaction.user.name} | Abo IA"); await interaction.followup.send(embed=embed, file=file)
        except Exception as e: log.error(f"[Imagine Error] {e}"); await interaction.followup.send("No pude dibujarlo we, nmms")

class HelpCog(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @app_commands.command(name="help", description="Muestra todos los comandos de Abo")
    async def help(self, interaction: discord.Interaction):
        es_staff = interaction.user.id == TU_ID or any(rol.name in ROLES_COMANDOS for rol in interaction.user.roles)
        embed = discord.Embed(title="🔥 Abo v2.2 - Panel de Comandos", description="Soy tu bot todo-en-uno we. Mencióname `@Abo hola` pa chatear con IA.", color=0x5865F2)
        embed.add_field(name="🎨 Colores", value="`/color` - Menú pa cambiar tu color de nombre", inline=False)
        embed.add_field(name="🎨 IA Imagen", value="`/imagine prompt:...` - Abo te dibuja lo que quieras gratis", inline=False)
        embed.add_field(name="🧠 Utilidad", value="`/olvidame` - Borro tu historial de chat conmigo", inline=False)
        if es_staff:
            embed.add_field(name="🔨 Moderación", value="`/ban` `/mute` `/limpia` `/addrol` `/delrol`", inline=False)
            embed.add_field(name="⚠️ Sistema de Warns", value="`/warn` `/warns` `/clearwarns` - 3 warns = mute 1d, 5 = ban auto", inline=False)
            embed.add_field(name="🧹 Purga de Fantasmas", value="`/scan` `/purgaafk` - Detecta y patea inactivos 15d", inline=False)
            embed.add_field(name="⚙️ Setup", value="`/create_colors` - Crea los 20 roles de color solo", inline=False)
        else: embed.set_footer(text="¿Eres staff? Pide permisos pa ver más comandos.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    @app_commands.command(name="olvidame", description="Borra tu memoria de IA en este canal")
    async def olvidame(self, interaction: discord.Interaction):
        cursor.execute("DELETE FROM memoria WHERE user_id =? AND canal_id =?", (interaction.user.id, interaction.channel.id)); db.commit(); await interaction.response.send_message("✅ Ya te olvidé we, borrón y cuenta nueva", ephemeral=True)

@bot.event
async def on_ready():
    await bot.add_cog(ColorsCog(bot)); await bot.add_cog(ModCog(bot)); await bot.add_cog(PurgaCog(bot)); await bot.add_cog(WarnCog(bot)); await bot.add_cog(ImagineCog(bot)); await bot.add_cog(HelpCog(bot))
    await bot.tree.sync(); log.info(f"Online: {bot.user} | {len(bot.tree.get_commands())} slash commands cargados")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="LatamOS"))

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot: return
    if bot.user in message.mentions:
        texto = re.sub(r"<@!?\d+>", "", message.content).strip()
        async with message.channel.typing(): respuesta = await preguntar_ia(texto, message.author.id, message.channel.id)
        await message.channel.send(respuesta.replace("@everyone", "@\u200beveryone"), allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
    if message.content.startswith("!") and not await bot.is_owner(message.author):
        await message.channel.send("Waos, ya son `/` we", delete_after=3)

bot.run(TOKEN)
