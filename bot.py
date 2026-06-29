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
# CONFIG
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
bot = commands.Bot(command_prefix="!", intents=intents) # El! ya no se usa, pero Bot lo pide

ULTIMOS_FANTASMAS = {} # guild_id: [user_ids]

# ─────────────────────────────────────────
# CHECK PA STAFF
# ─────────────────────────────────────────
def is_staff():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id == TU_ID: return True
        return any(rol.name in ROLES_COMANDOS for rol in interaction.user.roles)
    return app_commands.check(predicate)

# ─────────────────────────────────────────
# DB MEMORIA + IA IGUAL
# ─────────────────────────────────────────
db = sqlite3.connect("abo_memoria.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("""CREATE TABLE IF NOT EXISTS memoria (user_id INTEGER, canal_id INTEGER, rol TEXT, contenido TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS warns (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, user_id INTEGER, moderator_id INTEGER, reason TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
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

# ─────────────────────────────────────────
# COG COLORES
# ─────────────────────────────────────────
COLOR_ROLES = {
    "Vivid Red": 0xE74C3C, "Orange": 0xE67E22, "Yellow": 0xF1C40F, "Green": 0x2ECC71, "Blue": 0x3498DB,
    "Purple": 0x9B59B6, "Pink": 0xFF69B4, "Cyan": 0x1ABC9C, "White": 0xECF0F1, "Black": 0x2C3E50,
    "Gold": 0xFFD700, "Silver": 0xC0C0C0, "Aurora": 0x00FFFF, "Neon": 0x39FF14, "Blood": 0x8B0000,
    "Ocean": 0x006994, "Galaxy": 0x4B0082, "Fire": 0xFF4500, "Ice": 0xADD8E6, "Forest": 0x228B22,
}

# ── Vista privada con el dropdown (ephemeral, solo para quien hizo clic) ──
class ColorSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=name, emoji="🎨") for name in COLOR_ROLES.keys()]
        super().__init__(placeholder="Elige tu color...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild, member, color_name = interaction.guild, interaction.user, self.values[0]
        roles_a_quitar = [guild.get_role(discord.utils.get(guild.roles, name=n).id) for n in COLOR_ROLES.keys() if discord.utils.get(guild.roles, name=n)]
        if roles_a_quitar: await member.remove_roles(*roles_a_quitar, reason="Cambio de color")
        new_role = discord.utils.get(guild.roles, name=color_name)
        if new_role:
            await member.add_roles(new_role)
            await interaction.followup.send(f"✅ Tu color ahora es {new_role.mention}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ No existe el rol `{color_name}`. Usa `/create_colors` we.", ephemeral=True)

class ColorSelectView(discord.ui.View):
    def __init__(self): super().__init__(timeout=60); self.add_item(ColorSelect())

# ── Vista pública con solo el botón ──
class ColorButtonView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="🎨 Seleccionar color", style=discord.ButtonStyle.primary)
    async def abrir_selector(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed_privado = discord.Embed(
            title="🎨 Elige tu color",
            description="Selecciona un color del menú. Solo tú puedes ver esto.",
            color=0x9B59B6
        )
        embed_privado.set_footer(text="Solo puedes tener un color activo a la vez.")
        await interaction.response.send_message(embed=embed_privado, view=ColorSelectView(), ephemeral=True)

def build_color_embed(guild: discord.Guild):
    """Embed público con la lista de colores disponibles y un botón."""
    lines = []
    for name in COLOR_ROLES.keys():
        role = discord.utils.get(guild.roles, name=name)
        mention = role.mention if role else f"**{name}**"
        lines.append(f"🔘 {mention}")

    embed = discord.Embed(
        title="🎨 Color Roles",
        description=(
            "Personaliza el color de tu nombre en el servidor.\n"
            "Presiona el botón de abajo para elegir. Solo puedes tener **un color activo** a la vez.\n\u200b"
        ),
        color=0x9B59B6
    )
    mid = len(lines) // 2
    embed.add_field(name="Colores disponibles", value="\n".join(lines[:mid]), inline=True)
    embed.add_field(name="\u200b", value="\n".join(lines[mid:]), inline=True)
    embed.set_footer(text="Abo Colors • Los colores dependen de los roles del servidor")
    return embed

class ColorsCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="color", description="Muestra el menú de colores del servidor")
    async def color_menu(self, interaction: discord.Interaction):
        embed = build_color_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, view=ColorButtonView())

    @app_commands.command(name="create_colors", description="[Staff] Crea los 20 roles de color si no existen")
    @is_staff()
    async def create_colors(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); creados = 0
        for name, hex in COLOR_ROLES.items():
            if not discord.utils.get(interaction.guild.roles, name=name):
                await interaction.guild.create_role(name=name, colour=discord.Colour(hex), reason="Abo Colors"); creados += 1
        await interaction.followup.send(f"✅ Creados {creados} roles. Los otros ya existían.", ephemeral=True)

# ─────────────────────────────────────────
# COG MODERACIÓN - TODO A /
# ─────────────────────────────────────────
class ModCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="ban", description="[Staff] Banea a un usuario")
    @app_commands.describe(user="A quién banear", reason="Razón del ban")
    @is_staff()
    async def ban(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Se pasó de verga"):
        await interaction.response.defer()
        try: await user.ban(reason=f"{reason} | By {interaction.user}"); await interaction.followup.send(f"🔨 {user.mention} desterrado alv. Razón: {reason}")
        except discord.Forbidden: await interaction.followup.send("❌ No tengo permisos pa banearlo we")

    @app_commands.command(name="mute", description="[Staff] Da timeout a un usuario")
    @app_commands.describe(user="A quién mutear", time="10m, 2h, 1d")
    @is_staff()
    async def mute(self, interaction: discord.Interaction, user: discord.Member, time: str = "10m"):
        await interaction.response.defer()
        try:
            mult = {"m": 60, "h": 3600, "d": 86400}; tiempo_seg = int(time[:-1]) * mult[time[-1]]
            await user.timeout(timedelta(seconds=tiempo_seg), reason=f"Muted by {interaction.user}")
            await interaction.followup.send(f"🤐 {user.mention} silenciado por {time}")
        except: await interaction.followup.send("❌ Tiempo inválido we. Usa `10m`, `2h`, `1d`")

    @app_commands.command(name="limpia", description="[Staff] Borra mensajes")
    @app_commands.describe(amount="Cantidad 1-100")
    @is_staff()
    async def limpia(self, interaction: discord.Interaction, amount: int = 5):
        if amount > 100: amount = 100
        await interaction.response.defer(ephemeral=True)
        borrados = await interaction.channel.purge(limit=amount + 1)
        await interaction.followup.send(f"🧹 {len(borrados)-1} mensajes alv", ephemeral=True)

    @app_commands.command(name="addrol", description="Da un rol a varios users")
    @is_staff()
    async def addrol(self, interaction: discord.Interaction, rol: discord.Role, users: str):
        await interaction.response.defer()
        mentions = re.findall(r'<@!?(\d+)>', users); exitos, fallos = [], []
        for uid in mentions:
            user = interaction.guild.get_member(int(uid))
            if user:
                try: await user.add_roles(rol); exitos.append(user.name)
                except: fallos.append(user.name)
        await interaction.followup.send(f"✅ Dado a: {', '.join(exitos)}\n❌ Falló: {', '.join(fallos)}" if fallos else f"✅ Dado a: {', '.join(exitos)}")

    @app_commands.command(name="delrol", description="Quita un rol a varios users")
    @is_staff()
    async def delrol(self, interaction: discord.Interaction, rol: discord.Role, users: str):
        await interaction.response.defer()
        mentions = re.findall(r'<@!?(\d+)>', users); exitos, fallos = [], []
        for uid in mentions:
            user = interaction.guild.get_member(int(uid))
            if user:
                try: await user.remove_roles(rol); exitos.append(user.name)
                except: fallos.append(user.name)
        await interaction.followup.send(f"🗑️ Quitado a: {', '.join(exitos)}\n❌ Falló: {', '.join(fallos)}" if fallos else f"🗑️ Quitado a: {', '.join(exitos)}")

# ─────────────────────────────────────────
# COG PURGA
# ─────────────────────────────────────────
class PurgaCog(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @app_commands.command(name="scan", description="[Staff] Busca miembros con 0 mensajes en 15d")
    @is_staff()
    async def scan(self, interaction: discord.Interaction):
        await interaction.response.defer()
        rol_miembro = discord.utils.get(interaction.guild.roles, name=ROL_MIEMBRO)
        if not rol_miembro: return await interaction.followup.send(f"No hay rol '{ROL_MIEMBRO}' we")
        todos = {m.id: m for m in rol_miembro.members if not m.bot}; actividad = {mid: 0 for mid in todos.keys()}
        hace_15dias = discord.utils.utcnow() - timedelta(days=15)
        for canal in interaction.guild.text_channels:
            if not canal.permissions_for(interaction.guild.me).read_message_history: continue
            async for msg in canal.history(limit=None, after=hace_15dias):
                if msg.author.id in actividad: actividad[msg.author.id] += 1
        fantasmas_ids = [mid for mid, count in actividad.items() if count == 0]
        ULTIMOS_FANTASMAS[interaction.guild.id] = fantasmas_ids
        if not fantasmas_ids:
            return await interaction.followup.send("✅ No hay tiesos we 🔥")
        all_mentions = [interaction.guild.get_member(mid).mention for mid in fantasmas_ids if interaction.guild.get_member(mid)]
        header = f"👻 **Scan — {len(fantasmas_ids)} inactivos en 15d:**\n"
        chunks = []; current = header
        for m in all_mentions:
            if len(current) + len(m) + 1 > 1900:
                chunks.append(current); current = m + " "
            else: current += m + " "
        chunks.append(current)
        for i, chunk in enumerate(chunks):
            if i == len(chunks) - 1: chunk += "\nUsa `/purgaafk` pa patearlos."
            await interaction.channel.send(chunk)

    @app_commands.command(name="purgaafk", description="[Staff] Patea a los del último /scan")
    @is_staff()
    async def purgaafk(self, interaction: discord.Interaction):
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

# ─────────────────────────────────────────
# COG WARNS
# ─────────────────────────────────────────
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

        embed = discord.Embed(title="⚠️ Warn aplicado", color=0xF1C40F)
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
                await interaction.channel.send(f"🤐 Auto-Mod: {user.mention} muteado 1d por 3 warns.", delete_after=10)
            except discord.Forbidden:
                pass
        elif total >= 5:
            try:
                await user.ban(reason="Auto-Mod: 5 warns")
                await interaction.channel.send(f"🔨 Auto-Mod: {user.mention} baneado por 5 warns.", delete_after=10)
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
            return await interaction.followup.send(f"✅ {user.mention} no tiene warns we.", ephemeral=True)
        embed = discord.Embed(title=f"⚠️ Warns de {user.display_name}", color=0xE67E22)
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
        await interaction.followup.send(f"🧹 Warns de {user.mention} borrados.")


# ─────────────────────────────────────────
# COG IMAGINE
# ─────────────────────────────────────────
class ImagineCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="imagine", description="Genera una imagen con IA a partir de un prompt")
    @app_commands.describe(prompt="Descripción de la imagen que quieres generar")
    async def imagine(self, interaction: discord.Interaction, prompt: str):
        await interaction.response.defer()
        image_url = f"https://image.pollinations.ai/prompt/{discord.utils.escape_markdown(prompt).replace(' ', '%20')}?width=1024&height=1024&nologo=true"
        embed = discord.Embed(title="🎨 Imagen generada", description=f"**Prompt:** {prompt}", color=0x9B59B6)
        embed.set_image(url=image_url)
        embed.set_footer(text=f"Pedida por {interaction.user.display_name} • Pollinations.ai")
        await interaction.followup.send(embed=embed)


# ─────────────────────────────────────────
# COG HELP
# ─────────────────────────────────────────
class HelpCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="help", description="Muestra todos los comandos de Abo")
    async def help(self, interaction: discord.Interaction):
        es_staff = interaction.user.id == TU_ID or any(r.name in ROLES_COMANDOS for r in interaction.user.roles)
        embed = discord.Embed(title="📖 Comandos de Abo", color=0x3498DB,
                              description="Todos los slash commands disponibles. Los marcados con 🔒 son solo Staff.")
        embed.set_thumbnail(url=interaction.guild.me.display_avatar.url)

        # Públicos
        embed.add_field(name="🤖 IA", value="`@Abo <mensaje>` — Háblale a Abo con IA", inline=False)
        embed.add_field(name="🎨 Color", value="`/color` — Elige tu color de nombre\n`/imagine <prompt>` — Genera una imagen con IA", inline=False)
        embed.add_field(name="⚠️ Warns", value=(
            "`/warns <user>` — Ve el historial de warns (🔒 solo tú lo ves)\n"
            "`/clearwarns <user>` — Borra los warns de un usuario (solo Staff)\n"
            "`/addrol <rol> <users>` — Da un rol a varios usuarios (solo Staff)\n"
            "`/delrol <rol> <users>` — Quita un rol a varios usuarios (solo Staff)"
        ), inline=False)

        if es_staff:
            embed.add_field(name="⚠️ Warns avanzados 🔒", value=(
                "`/warn <user> [razón]` — Warnea a un usuario (auto-mute en 3, auto-ban en 5)"
            ), inline=False)
            embed.add_field(name="🛡️ Moderación 🔒", value=(
                "`/ban <user> [razón]` — Banea a un usuario\n"
                "`/mute <user> [tiempo]` — Timeout (ej: `10m`, `2h`, `1d`)\n"
                "`/limpia <cantidad>` — Borra mensajes (máx 100)"
            ), inline=False)
            embed.add_field(name="👻 Purga AFK 🔒", value=(
                "`/scan` — Busca miembros sin mensajes en 15 días\n"
                "`/purgaafk` — Patea a los del último /scan"
            ), inline=False)
            embed.add_field(name="🎨 Setup 🔒", value="`/create_colors` — Crea los 20 roles de color", inline=False)

        embed.set_footer(text="Abo Bot • Prefix: slash /")
        await interaction.response.send_message(embed=embed, ephemeral=True)



@bot.event
async def on_ready():
    await bot.add_cog(ColorsCog(bot)); await bot.add_cog(ModCog(bot)); await bot.add_cog(PurgaCog(bot))
    await bot.add_cog(WarnsCog(bot)); await bot.add_cog(ImagineCog(bot)); await bot.add_cog(HelpCog(bot))
    await bot.tree.sync() # REGISTRA TODO A DISCORD
    log.info(f"Online: {bot.user} | {len(bot.tree.get_commands())} slash commands cargados")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="LatamOS"))

@bot.event
async def on_message(message: discord.Message): # La IA por mención se queda
    if message.author.bot: return
    if bot.user in message.mentions:
        texto = re.sub(r"<@!?\d+>", "", message.content).strip()
        async with message.channel.typing(): respuesta = await preguntar_ia(texto, message.author.id, message.channel.id)
        await message.channel.send(respuesta.replace("@everyone", "@\u200beveryone"), allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))

    # Bloqueo de! viejos
    if message.content.startswith("!") and not await bot.is_owner(message.author):
        await message.channel.send("Waos, ya son `/` we", delete_after=3)

bot.run(TOKEN)
