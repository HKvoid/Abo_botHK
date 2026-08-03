import discord
import os
import re
import random
import asyncio
import sqlite3
import logging
import json
import io
import datetime
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
ROL_VERIFICADO_ID = 1517969743812755456  # rol que se asigna con !verificar
ROL_MIEMBRO = "Miembro"
ROLES_COMANDOS = ["Admin", "Moderador", "Shogun 🦈", "ViceRoot", "Root", "Daimyō", "Rōnin"]
ROLES_STAFF_COLOR = ["Staff"]

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

def is_staff_color():
    """Solo quienes tengan el rol 'Staff' pueden usar /staffcolor."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id == TU_ID: return True
        return any(rol.name in ROLES_STAFF_COLOR for rol in interaction.user.roles)
    return app_commands.check(predicate)

# ─────────────────────────────────────────
# DB MEMORIA + IA IGUAL
# ─────────────────────────────────────────
db = sqlite3.connect("abo_memoria.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("""CREATE TABLE IF NOT EXISTS memoria (user_id INTEGER, canal_id INTEGER, rol TEXT, contenido TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS warns (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, user_id INTEGER, moderator_id INTEGER, reason TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS color_roles (guild_id INTEGER, categoria TEXT, clave TEXT, role_id INTEGER, PRIMARY KEY (guild_id, categoria, clave))""")
cursor.execute("""CREATE TABLE IF NOT EXISTS purga_exceptions (guild_id INTEGER, user_id INTEGER, razon TEXT, added_by INTEGER, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (guild_id, user_id))""")
db.commit()

# ─────────────────────────────────────────
# EXCEPCIONES DE PURGA AFK
# ─────────────────────────────────────────
def agregar_excepcion(guild_id: int, user_id: int, razon: str, added_by: int):
    cursor.execute(
        """INSERT INTO purga_exceptions (guild_id, user_id, razon, added_by) VALUES (?,?,?,?)
           ON CONFLICT(guild_id, user_id) DO UPDATE SET razon=excluded.razon, added_by=excluded.added_by, timestamp=CURRENT_TIMESTAMP""",
        (guild_id, user_id, razon, added_by)
    )
    db.commit()

def quitar_excepcion(guild_id: int, user_id: int) -> bool:
    cursor.execute("DELETE FROM purga_exceptions WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    borrado = cursor.rowcount > 0
    db.commit()
    return borrado

def es_excepcion(guild_id: int, user_id: int) -> bool:
    cursor.execute("SELECT 1 FROM purga_exceptions WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    return cursor.fetchone() is not None

def listar_excepciones(guild_id: int):
    cursor.execute("SELECT user_id, razon, added_by, timestamp FROM purga_exceptions WHERE guild_id=? ORDER BY timestamp DESC", (guild_id,))
    return cursor.fetchall()

# ─────────────────────────────────────────
# RESOLUCIÓN DE ROLES DE COLOR POR ID (robusto ante renombres)
# Cada color/clave se guarda junto a su role_id la primera vez que se
# encuentra (por nombre). De ahí en adelante se busca SIEMPRE por ID,
# así que renombrar el rol en Discord ya no rompe nada.
# ─────────────────────────────────────────
def guardar_color_role_id(guild_id: int, categoria: str, clave: str, role_id: int):
    cursor.execute(
        """INSERT INTO color_roles (guild_id, categoria, clave, role_id) VALUES (?,?,?,?)
           ON CONFLICT(guild_id, categoria, clave) DO UPDATE SET role_id=excluded.role_id""",
        (guild_id, categoria, clave, role_id)
    )
    db.commit()

def obtener_color_role_id(guild_id: int, categoria: str, clave: str):
    cursor.execute("SELECT role_id FROM color_roles WHERE guild_id=? AND categoria=? AND clave=?", (guild_id, categoria, clave))
    row = cursor.fetchone()
    return row[0] if row else None

def resolver_color_role(guild: discord.Guild, categoria: str, clave: str):
    """Devuelve el discord.Role para (categoria, clave). Primero busca por ID guardado
    (inmune a renombres); si no hay ID cacheado o el rol fue borrado, cae a buscar por
    nombre = clave y, si lo encuentra, cachea el ID para blindarlo a futuro."""
    role_id = obtener_color_role_id(guild.id, categoria, clave)
    if role_id:
        role = guild.get_role(role_id)
        if role:
            return role
    role = discord.utils.get(guild.roles, name=clave)
    if role:
        guardar_color_role_id(guild.id, categoria, clave, role.id)
    return role

def resolver_color_roles(guild: discord.Guild, categoria: str, claves):
    """Resuelve una lista de claves a sus discord.Role (omite los que no existan)."""
    roles = [resolver_color_role(guild, categoria, clave) for clave in claves]
    return [r for r in roles if r]

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
        # El SDK de Groq es síncrono; lo mandamos a un hilo aparte para no bloquear
        # el event loop de discord.py (si no, el bot entero se congela mientras espera la IA).
        chat = await asyncio.to_thread(
            groq_client.chat.completions.create,
            model="llama-3.3-70b-versatile", messages=mensajes, max_tokens=150, temperature=0.9
        )
        respuesta = chat.choices[0].message.content.strip()
        guardar_mensaje(user_id, canal_id, "user", prompt); guardar_mensaje(user_id, canal_id, "assistant", respuesta)
        return respuesta if respuesta else "Sinceramente, ni idea 🤔"
    except Exception as e:
        log.error(f"[Groq Error] {e}"); return "Se me cruzaron los cables, intenta de nuevo 🤖"

# ─────────────────────────────────────────
# COG COLORES
# ─────────────────────────────────────────
COLOR_ROLES = {
    "Orange": 0xE67E22, "Yellow": 0xF1C40F, "Green": 0x2ECC71, "Blue": 0x3498DB,
    "Purple": 0x9B59B6, "Pink": 0xFF69B4, "Cyan": 0x1ABC9C, "White": 0xECF0F1, "Black": 0x2C3E50,
    "Silver": 0xC0C0C0, "Aurora": 0x00FFFF, "Neon": 0x39FF14, "Blood": 0x8B0000,
    "Ocean": 0x006994, "Galaxy": 0x4B0082, "Forest": 0x228B22,
}

# ── Vista privada con el dropdown (ephemeral, solo para quien hizo clic) ──
class ColorSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        options = []
        for clave in COLOR_ROLES.keys():
            role = resolver_color_role(guild, "color", clave)
            label = role.name if role else clave  # muestra el nombre actual del rol, aunque lo hayan renombrado
            options.append(discord.SelectOption(label=label, value=clave, emoji="🎨"))
        super().__init__(placeholder="Elige tu color...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild, member, color_name = interaction.guild, interaction.user, self.values[0]
        roles_a_quitar = resolver_color_roles(guild, "color", COLOR_ROLES.keys())
        new_role = resolver_color_role(guild, "color", color_name)
        if not new_role:
            return await interaction.followup.send(f"Ese rol (`{color_name}`) todavía no existe. Prueba primero con `/create_colors` 🤔", ephemeral=True)
        try:
            if roles_a_quitar: await member.remove_roles(*roles_a_quitar, reason="Cambio de color")
            await member.add_roles(new_role)
            await interaction.followup.send(f"Listo, tu color ahora es {new_role.mention} 🎨", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("No tengo permisos suficientes para asignar ese rol; revisa mi jerarquía, por favor 🔒", ephemeral=True)

class ColorSelectView(discord.ui.View):
    def __init__(self, guild: discord.Guild): super().__init__(timeout=60); self.add_item(ColorSelect(guild))

# ── Vista pública combinada: un botón para colores básicos y otro para Booster ──
class ColorMenuView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Basic Colors", style=discord.ButtonStyle.secondary, emoji="🎨", custom_id="color_basic_button")
    async def abrir_basicos(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed_privado = discord.Embed(
            title="Elige tu color 🎨",
            description="Selecciona un color del menú de abajo. Solo tú puedes ver este mensaje.",
            color=0x2B2D31
        )
        embed_privado.set_footer(text="Solo puedes tener un color activo a la vez.")
        await interaction.response.send_message(embed=embed_privado, view=ColorSelectView(interaction.guild), ephemeral=True)

    @discord.ui.button(label="Booster Colors", style=discord.ButtonStyle.secondary, emoji="💎", custom_id="color_booster_button")
    async def abrir_booster(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _es_booster(interaction.user):
            return await interaction.response.send_message("Este menú es exclusivo para Server Boosters, así que ya sabes qué hacer 💎", ephemeral=True)
        embed_privado = discord.Embed(
            title="Elige tu color de Booster 💎",
            description="Selecciona un color del menú de abajo. Solo tú puedes ver este mensaje.",
            color=0x2B2D31
        )
        embed_privado.set_footer(text="Solo puedes tener un color de Booster activo a la vez.")
        await interaction.response.send_message(embed=embed_privado, view=BoosterColorSelectView(interaction.guild), ephemeral=True)

def build_combined_color_embed(guild: discord.Guild):
    """Embed público con Basic Colors y Booster Colors juntos, más los dos botones abajo."""
    basic_lines = []
    for name in COLOR_ROLES.keys():
        role = resolver_color_role(guild, "color", name)
        mention = role.mention if role else f"**{name}**"
        basic_lines.append(mention)

    booster_lines = []
    for name in BOOSTER_COLOR_ROLES.keys():
        role = resolver_color_role(guild, "boostercolor", name)
        mention = role.mention if role else f"**{name}**"
        booster_lines.append(mention)

    embed = discord.Embed(
        title="Color Roles 🎨",
        description=(
            "Personaliza el color de tu nombre en el servidor.\n"
            "Solo puedes tener **un color activo** a la vez.\n\u200b"
        ),
        color=0x2B2D31
    )
    embed.add_field(name="Basic Colors:", value="\n".join(basic_lines), inline=False)
    embed.add_field(name="Booster Colors:", value="\n".join(booster_lines), inline=False)
    embed.set_footer(text="Abo Colors • Booster Colors es exclusivo para Server Boosters")
    return embed

class ColorsCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="color", description="Muestra el menú de colores del servidor")
    async def color_menu(self, interaction: discord.Interaction):
        embed = build_combined_color_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, view=ColorMenuView())

    @app_commands.command(name="create_colors", description="[Staff] Crea los 20 roles de color si no existen")
    @is_staff()
    async def create_colors(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); creados = 0
        for name, color_hex in COLOR_ROLES.items():
            role = resolver_color_role(interaction.guild, "color", name)
            if not role:
                role = await interaction.guild.create_role(name=name, colour=discord.Colour(color_hex), reason="Abo Colors"); creados += 1
            guardar_color_role_id(interaction.guild.id, "color", name, role.id)
        await interaction.followup.send(f"Listo: creé {creados} rol(es) nuevo(s). Los demás ya existían y quedaron blindados por ID ante futuros renombres ✅", ephemeral=True)

# ─────────────────────────────────────────
# COG STAFF COLORS (exclusivo Root/ViceRoot/Admin/Moderador)
# Los roles de color los crea un admin manualmente en Discord (Ajustes > Roles).
# Aquí solo se listan los NOMBRES exactos de esos roles para que aparezcan en el menú.
# ─────────────────────────────────────────
STAFF_COLOR_ROLES = [
    "CStaff1",
    "CStaff2",
    "CStaff3",
    "CStaff4",
    "CStaff5",
    "CStaff6",
    "CStaff7",
    "CStaff8",
]

class StaffColorSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        options = []
        for clave in STAFF_COLOR_ROLES:
            role = resolver_color_role(guild, "staffcolor", clave)
            label = role.name if role else clave
            options.append(discord.SelectOption(label=label, value=clave, emoji="🌈"))
        super().__init__(placeholder="Elige tu color de Staff...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        # Chequeo extra por si la vista queda viva y alguien más la toca
        if interaction.user.id != TU_ID and not any(rol.name in ROLES_STAFF_COLOR for rol in interaction.user.roles):
            return await interaction.response.send_message("Este menú es exclusivo para el rol Staff, lo siento 🔒", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        guild, member, color_name = interaction.guild, interaction.user, self.values[0]
        roles_a_quitar = resolver_color_roles(guild, "staffcolor", STAFF_COLOR_ROLES)
        new_role = resolver_color_role(guild, "staffcolor", color_name)
        if not new_role:
            return await interaction.followup.send(f"Ese rol (`{color_name}`) todavía no existe en el servidor. Pídele a un admin que lo cree 🙏", ephemeral=True)
        try:
            if roles_a_quitar: await member.remove_roles(*roles_a_quitar, reason="Cambio de color Staff")
            await member.add_roles(new_role)
            await interaction.followup.send(f"Listo, tu color de Staff ahora es {new_role.mention} 🌈", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("No tengo permisos suficientes para asignar ese rol; revisa mi jerarquía, por favor 🔒", ephemeral=True)

class StaffColorSelectView(discord.ui.View):
    def __init__(self, guild: discord.Guild): super().__init__(timeout=60); self.add_item(StaffColorSelect(guild))

class StaffColorsCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="staffcolor", description="[Staff] Elige tu color exclusivo de Staff")
    @is_staff_color()
    async def staffcolor(self, interaction: discord.Interaction):
        lineas = []
        for name in STAFF_COLOR_ROLES:
            rol = resolver_color_role(interaction.guild, "staffcolor", name)
            lineas.append(rol.mention if rol else f"@{name} *(rol no creado)*")

        embed = discord.Embed(
            title="Colores de Staff 🌈",
            description=(
                "Colores exclusivos para el rol **Staff**.\n"
                "Selecciona uno del menú abajo. Solo puedes tener un color de Staff activo a la vez.\n\n"
                + "\n".join(lineas)
            ),
            color=0x8E44AD
        )
        await interaction.response.send_message(embed=embed, view=StaffColorSelectView(interaction.guild))

# ─────────────────────────────────────────
# COG BOOSTER COLORS (exclusivo Server Booster)
# Funciona igual que los colores normales: Abo crea los roles automáticamente
# con /create_booster_colors, pero solo pueden usarlos quienes boosteen el server.
# ─────────────────────────────────────────
BOOSTER_COLOR_ROLES = {
    "Onix": 0xB76E79,
    "Aqua": 0xFFBF00,
    "Sunset": 0x50C878,
    "Ice": 0x0F52BA,
    "Amethyst": 0xB57EDC,
}

def _es_booster(member: discord.Member) -> bool:
    """Detecta Boosters sin depender del nombre del rol: usa member.premium_since
    (estado oficial de boosteo de Discord) y, como respaldo, el rol de Booster
    nativo del server (guild.premium_subscriber_role), que Discord resuelve
    siempre por ID aunque el rol se renombre."""
    if member.id == TU_ID: return True
    if member.premium_since is not None: return True
    booster_role = member.guild.premium_subscriber_role
    return booster_role is not None and booster_role in member.roles

class BoosterColorSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        options = []
        for clave in BOOSTER_COLOR_ROLES.keys():
            role = resolver_color_role(guild, "boostercolor", clave)
            label = role.name if role else clave
            options.append(discord.SelectOption(label=label, value=clave, emoji="💎"))
        super().__init__(placeholder="Elige tu color de Booster...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        # Chequeo extra por si la vista queda viva y alguien más la toca
        if not _es_booster(interaction.user):
            return await interaction.response.send_message("Este menú es exclusivo para Server Boosters, así que ya sabes qué hacer 💎", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        guild, member, color_name = interaction.guild, interaction.user, self.values[0]
        roles_a_quitar = resolver_color_roles(guild, "boostercolor", BOOSTER_COLOR_ROLES.keys())
        new_role = resolver_color_role(guild, "boostercolor", color_name)
        if not new_role:
            return await interaction.followup.send(f"Ese rol (`{color_name}`) todavía no existe. Prueba primero con `/create_booster_colors` 💎", ephemeral=True)
        try:
            if roles_a_quitar: await member.remove_roles(*roles_a_quitar, reason="Cambio de color Booster")
            await member.add_roles(new_role)
            await interaction.followup.send(f"Listo, tu color de Booster ahora es {new_role.mention}. Gracias por el apoyo al server 💎", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("No tengo permisos suficientes para asignar ese rol; revisa mi jerarquía, por favor 🔒", ephemeral=True)

class BoosterColorSelectView(discord.ui.View):
    def __init__(self, guild: discord.Guild): super().__init__(timeout=60); self.add_item(BoosterColorSelect(guild))

class BoosterColorsCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="create_booster_colors", description="[Staff] Crea los 5 roles de color de Booster si no existen")
    @is_staff()
    async def create_booster_colors(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); creados = 0
        for name, color_hex in BOOSTER_COLOR_ROLES.items():
            role = resolver_color_role(interaction.guild, "boostercolor", name)
            if not role:
                role = await interaction.guild.create_role(name=name, colour=discord.Colour(color_hex), reason="Abo Booster Colors"); creados += 1
            guardar_color_role_id(interaction.guild.id, "boostercolor", name, role.id)
        await interaction.followup.send(f"Listo: creé {creados} rol(es) de Booster nuevo(s). Los demás ya existían y quedaron blindados por ID ante futuros renombres ✅", ephemeral=True)

# ─────────────────────────────────────────
# COG MODERACIÓN - TODO A /
# ─────────────────────────────────────────
class ModCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="ban", description="[Staff] Banea a un usuario")
    @app_commands.describe(user="A quién banear", reason="Razón del ban")
    @is_staff()
    async def ban(self, interaction: discord.Interaction, user: discord.Member, reason: str = "Se pasó de la raya"):
        if user.id == interaction.user.id:
            return await interaction.response.send_message("¿En serio intentas banearte a ti mismo? Que no 😅", ephemeral=True)
        await interaction.response.defer()
        try: await user.ban(reason=f"{reason} | By {interaction.user}"); await interaction.followup.send(f"{user.mention} fue baneado del servidor. Razón: {reason} 🔨")
        except discord.Forbidden: await interaction.followup.send("No tengo permisos suficientes para banear a ese usuario 🔒")

    @app_commands.command(name="mute", description="[Staff] Da timeout a un usuario")
    @app_commands.describe(user="A quién mutear", time="10m, 2h, 1d")
    @is_staff()
    async def mute(self, interaction: discord.Interaction, user: discord.Member, time: str = "10m"):
        if user.id == interaction.user.id:
            return await interaction.response.send_message("¿En serio intentas mutearte a ti mismo? Que no 😅", ephemeral=True)
        mult = {"m": 60, "h": 3600, "d": 86400}
        unidad = time[-1] if time else ""
        if unidad not in mult or not time[:-1].isdigit():
            return await interaction.response.send_message("Formato inválido. Usa algo como `10m`, `2h` o `1d` ⏱️", ephemeral=True)
        tiempo_seg = int(time[:-1]) * mult[unidad]
        if tiempo_seg <= 0 or tiempo_seg > 28 * 86400:
            return await interaction.response.send_message("El tiempo debe ser mayor a 0 y de máximo 28 días ⏱️", ephemeral=True)
        await interaction.response.defer()
        try:
            await user.timeout(timedelta(seconds=tiempo_seg), reason=f"Muted by {interaction.user}")
            await interaction.followup.send(f"{user.mention} fue silenciado por {time} 🤐")
        except discord.Forbidden:
            await interaction.followup.send("No tengo permisos suficientes para mutear a ese usuario 🔒")
        except discord.HTTPException as e:
            log.error(f"[Mute Error] {e}")
            await interaction.followup.send("Algo falló al intentar mutear; inténtalo de nuevo 🔁")

    @app_commands.command(name="limpia", description="[Staff] Borra mensajes")
    @app_commands.describe(amount="Cantidad 1-100")
    @is_staff()
    async def limpia(self, interaction: discord.Interaction, amount: int = 5):
        if amount > 100: amount = 100
        await interaction.response.defer(ephemeral=True)
        borrados = await interaction.channel.purge(limit=amount + 1)
        await interaction.followup.send(f"Borré {len(borrados)-1} mensajes, quedó como nuevo 🧹", ephemeral=True)

    @app_commands.command(name="addrol", description="Da un rol a varios users")
    @is_staff()
    async def addrol(self, interaction: discord.Interaction, rol: discord.Role, users: str):
        mentions = re.findall(r'<@!?(\d+)>', users)
        if interaction.user.id != TU_ID and rol.position >= interaction.user.top_role.position:
            return await interaction.response.send_message("No puedes asignar un rol superior al tuyo, lindo intento 😏", ephemeral=True)
        await interaction.response.defer()
        exitos, fallos = [], []
        for uid in mentions:
            user = interaction.guild.get_member(int(uid))
            if user:
                try: await user.add_roles(rol); exitos.append(user.name)
                except discord.HTTPException: fallos.append(user.name)
        await interaction.followup.send(f"Rol asignado a: {', '.join(exitos)} ✅\nNo se pudo asignar a: {', '.join(fallos)} ❌" if fallos else f"Rol asignado a: {', '.join(exitos)} ✅")

    @app_commands.command(name="delrol", description="Quita un rol a varios users")
    @is_staff()
    async def delrol(self, interaction: discord.Interaction, rol: discord.Role, users: str):
        await interaction.response.defer()
        mentions = re.findall(r'<@!?(\d+)>', users); exitos, fallos = [], []
        for uid in mentions:
            user = interaction.guild.get_member(int(uid))
            if user:
                try: await user.remove_roles(rol); exitos.append(user.name)
                except discord.HTTPException: fallos.append(user.name)
        await interaction.followup.send(f"Rol quitado a: {', '.join(exitos)} 🗑️\nNo se pudo quitar a: {', '.join(fallos)} ❌" if fallos else f"Rol quitado a: {', '.join(exitos)} 🗑️")

# ─────────────────────────────────────────
# COG PURGA
# ─────────────────────────────────────────
async def recolectar_canales_con_historial(guild: discord.Guild):
    """Junta TODOS los canales/hilos del server donde puede haber mensajes:
    texto, voz (chat de voz), stage, hilos activos y archivados (incluyendo
    los de canales de foro). Así el /scan refleja la actividad real y no
    solo lo que pasó en los canales de texto de siempre."""
    canales = []
    canales.extend(guild.text_channels)
    canales.extend(guild.voice_channels)
    # Nota: los canales de Stage NO tienen historial de mensajes en discord.py
    # (no son Messageable), a diferencia de los de voz normales. Si se incluyen
    # aquí, .history() revienta con AttributeError y tumba todo el /scan.

    try:
        canales.extend(await guild.active_threads())
    except discord.HTTPException as e:
        log.error(f"[Scan active_threads Error] {e}")

    vistos_ids = {c.id for c in canales}
    # guild.forum_channels no existe en versiones viejas de discord.py; lo resolvemos
    # a mano filtrando guild.channels, y si el tipo ForumChannel ni siquiera existe
    # en esta versión de la librería, simplemente no hay canales de foro que sumar.
    canales_foro = getattr(guild, "forum_channels", None)
    if canales_foro is None:
        ForumChannel = getattr(discord, "ForumChannel", None)
        canales_foro = [c for c in guild.channels if ForumChannel and isinstance(c, ForumChannel)]

    for canal in list(guild.text_channels) + list(canales_foro):
        try:
            perms = canal.permissions_for(guild.me)
            if not perms.read_message_history: continue
            async for hilo in canal.archived_threads(limit=None):
                if hilo.id not in vistos_ids:
                    canales.append(hilo); vistos_ids.add(hilo.id)
            if perms.manage_threads:
                async for hilo in canal.archived_threads(limit=None, private=True):
                    if hilo.id not in vistos_ids:
                        canales.append(hilo); vistos_ids.add(hilo.id)
        except (discord.Forbidden, discord.HTTPException):
            continue
        except Exception as e:
            log.error(f"[Scan archived_threads canal={getattr(canal, 'id', '?')} Error] {e}")
            continue
    return canales

class PurgaCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="scan", description="[Staff] Escaneo masivo de TODOS los canales: busca miembros con 0 mensajes en 15d")
    @is_staff()
    async def scan(self, interaction: discord.Interaction):
        await interaction.response.defer()
        rol_miembro = discord.utils.get(interaction.guild.roles, name=ROL_MIEMBRO)
        if not rol_miembro: return await interaction.followup.send(f"No encontré el rol '{ROL_MIEMBRO}' en este servidor 🤷")
        todos = {m.id: m for m in rol_miembro.members if not m.bot}; actividad = {mid: 0 for mid in todos.keys()}
        hace_15dias = discord.utils.utcnow() - timedelta(days=15)

        canales = await recolectar_canales_con_historial(interaction.guild)
        canales_escaneados = 0
        for canal in canales:
            if not hasattr(canal, "history"): continue
            try:
                perms = canal.permissions_for(interaction.guild.me)
                if not perms.read_message_history: continue
                async for msg in canal.history(limit=None, after=hace_15dias):
                    if msg.author.id in actividad: actividad[msg.author.id] += 1
                canales_escaneados += 1
            except (discord.Forbidden, discord.HTTPException):
                continue
            except Exception as e:
                log.error(f"[Scan canal={getattr(canal, 'id', '?')} Error] {e}")
                continue

        excepciones_guild = {row[0] for row in listar_excepciones(interaction.guild.id)}
        fantasmas_ids = [mid for mid, count in actividad.items() if count == 0 and mid not in excepciones_guild]
        saltados_por_excepcion = [mid for mid, count in actividad.items() if count == 0 and mid in excepciones_guild]
        ULTIMOS_FANTASMAS[interaction.guild.id] = fantasmas_ids

        pie = f"\n📡 Canales/hilos escaneados: {canales_escaneados}"
        if saltados_por_excepcion:
            pie += f"\n🛡️ {len(saltados_por_excepcion)} en excepción (no incluido en la lista)"

        if not fantasmas_ids:
            return await interaction.followup.send("No encontré miembros inactivos, todos andan vivitos y coleando 🔥" + pie)

        all_mentions = [interaction.guild.get_member(mid).mention for mid in fantasmas_ids if interaction.guild.get_member(mid)]
        header = f"Scan completado — {len(fantasmas_ids)} inactivo(s) en los últimos 15 días 👻\n"
        chunks = []; current = header
        for m in all_mentions:
            if len(current) + len(m) + 1 > 1900:
                chunks.append(current); current = m + " "
            else: current += m + " "
        chunks.append(current)
        for i, chunk in enumerate(chunks):
            if i == len(chunks) - 1: chunk += f"\nUsa `/purgaafk` cuando quieras expulsarlos.{pie}"
            await interaction.channel.send(chunk)

    @app_commands.command(name="purgaafk", description="[Staff] Patea a los del último /scan")
    @is_staff()
    async def purgaafk(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id not in ULTIMOS_FANTASMAS or not ULTIMOS_FANTASMAS[guild_id]:
            return await interaction.response.send_message("Primero ejecuta un `/scan`, por favor 🔍", ephemeral=True)
        await interaction.response.defer()
        pateados = 0; protegidos = 0
        for user_id in ULTIMOS_FANTASMAS[guild_id]:
            if es_excepcion(guild_id, user_id):
                protegidos += 1; continue  # doble chequeo por si lo agregaron a excepciones después del /scan
            user = interaction.guild.get_member(user_id)
            if user and not user.bot:
                try: await user.kick(reason="Inactividad 15d - Abo"); pateados += 1; await asyncio.sleep(0.5)
                except discord.HTTPException: pass
        msg = f"Purga terminada: {pateados} expulsado(s) ✅"
        if protegidos: msg += f" | {protegidos} protegido(s) por excepción 🛡️"
        await interaction.followup.send(msg)
        ULTIMOS_FANTASMAS[guild_id] = []

    grupo_excepciones = app_commands.Group(name="purgaexc", description="[Staff] Excepciones de la purga AFK")

    @grupo_excepciones.command(name="add", description="[Staff] Agrega a un usuario a la lista de excepciones de purga")
    @app_commands.describe(user="Usuario que avisó que estará inactivo", razon="Motivo/razón (opcional)")
    @is_staff()
    async def purgaexc_add(self, interaction: discord.Interaction, user: discord.Member, razon: str = "Avisó inactividad temporal"):
        agregar_excepcion(interaction.guild.id, user.id, razon, interaction.user.id)
        await interaction.response.send_message(
            f"{user.mention} fue añadido a la lista de excepciones de purga. No será expulsado por AFK aunque el `/scan` lo marque inactivo 🛡️\nRazón: {razon}"
        )

    @grupo_excepciones.command(name="quitar", description="[Staff] Quita a un usuario de la lista de excepciones de purga")
    @app_commands.describe(user="Usuario a quitar de excepciones")
    @is_staff()
    async def purgaexc_quitar(self, interaction: discord.Interaction, user: discord.Member):
        if quitar_excepcion(interaction.guild.id, user.id):
            await interaction.response.send_message(f"{user.mention} fue quitado de la lista de excepciones 🗑️")
        else:
            await interaction.response.send_message(f"{user.mention} no estaba en la lista de excepciones 🤷", ephemeral=True)

    @grupo_excepciones.command(name="lista", description="[Staff] Muestra la lista de excepciones de purga")
    @is_staff()
    async def purgaexc_lista(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        filas = listar_excepciones(interaction.guild.id)
        if not filas:
            return await interaction.followup.send("No hay nadie en la lista de excepciones ahora mismo 🤷", ephemeral=True)
        embed = discord.Embed(title="Excepciones de Purga AFK 🛡️", color=0x2ECC71)
        for user_id, razon, added_by, ts in filas:
            miembro = interaction.guild.get_member(user_id)
            nombre = miembro.mention if miembro else f"ID:{user_id}"
            mod = interaction.guild.get_member(added_by)
            mod_nombre = mod.display_name if mod else f"ID:{added_by}"
            embed.add_field(name=nombre, value=f"**Razón:** {razon}\n**Añadido por:** {mod_nombre}\n**Fecha:** {ts[:10]}", inline=False)
        embed.set_footer(text=f"Total: {len(filas)} excepción(es)")
        await interaction.followup.send(embed=embed, ephemeral=True)

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


# ─────────────────────────────────────────
# COG RESET SERVIDOR (solo owner, con backup JSON + confirmación)
# ─────────────────────────────────────────
class ConfirmarResetModal(discord.ui.Modal, title="⚠️ Confirmar reset total"):
    def __init__(self, guild: discord.Guild):
        super().__init__()
        self.guild = guild
        self.nombre = discord.ui.TextInput(
            label=f'Escribe "{guild.name}" para confirmar',
            placeholder=guild.name,
            required=True,
        )
        self.add_item(self.nombre)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        if self.nombre.value.strip() != self.guild.name:
            return await interaction.followup.send(
                "❌ El nombre no coincide. Reset cancelado, nada fue tocado.",
                ephemeral=True,
            )

        guild = self.guild

        # ── 1. BACKUP JSON ──
        backup = {
            "guild_id": guild.id,
            "guild_name": guild.name,
            "generado": datetime.datetime.utcnow().isoformat(),
            "roles": [],
            "canales": [],
        }

        for rol in guild.roles:
            backup["roles"].append({
                "id": rol.id, "nombre": rol.name, "color": str(rol.color),
                "posicion": rol.position, "hoist": rol.hoist,
                "mentionable": rol.mentionable, "permisos": rol.permissions.value,
                "managed": rol.managed,
            })

        for canal in guild.channels:
            overwrites = {
                str(target.id): ow._values
                for target, ow in canal.overwrites.items()
            }
            backup["canales"].append({
                "id": canal.id, "nombre": canal.name, "tipo": str(canal.type),
                "posicion": canal.position,
                "categoria": canal.category.name if canal.category else None,
                "topic": getattr(canal, "topic", None),
                "overwrites": overwrites,
            })

        json_bytes = json.dumps(backup, indent=2, ensure_ascii=False).encode("utf-8")
        archivo = discord.File(
            io.BytesIO(json_bytes),
            filename=f"backup_{guild.id}_{int(datetime.datetime.utcnow().timestamp())}.json",
        )
        await interaction.followup.send(
            "💾 Backup generado. Empezando el reset ahora...", file=archivo, ephemeral=True
        )

        # ── 2. BORRAR HILOS Y CANALES ──
        canales_borrados = 0
        for canal in list(guild.channels):
            try:
                await canal.delete(reason=f"Reset total ejecutado por {interaction.user}")
                canales_borrados += 1
            except (discord.Forbidden, discord.HTTPException) as e:
                log.error(f"[reset_servidor] no pude borrar canal {canal.name}: {e}")

        # ── 3. BORRAR ROLES (excepto @everyone, managed, y por encima del bot) ──
        roles_borrados = 0
        bot_top_role = guild.me.top_role
        for rol in list(guild.roles):
            if rol.is_default() or rol.managed:
                continue
            if rol >= bot_top_role:
                continue
            try:
                await rol.delete(reason=f"Reset total ejecutado por {interaction.user}")
                roles_borrados += 1
            except (discord.Forbidden, discord.HTTPException) as e:
                log.error(f"[reset_servidor] no pude borrar rol {rol.name}: {e}")

        try:
            await interaction.user.send(
                f"✅ Reset de **{guild.name}** completado.\n"
                f"Canales borrados: {canales_borrados}\n"
                f"Roles borrados: {roles_borrados}\n"
                f"(el backup JSON te lo mandé en la respuesta del comando)"
            )
        except discord.Forbidden:
            pass


class ResetCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="reset_servidor",
        description="⚠️ SOLO OWNER: borra todos los canales y roles, previo backup en JSON",
    )
    async def reset_servidor(self, interaction: discord.Interaction):
        if interaction.user.id != TU_ID:
            return await interaction.response.send_message(
                "No tienes permiso para usar este comando 🔒", ephemeral=True
            )
        await interaction.response.send_modal(ConfirmarResetModal(interaction.guild))


# ─────────────────────────────────────────
# COG HELP
# ─────────────────────────────────────────
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
        if es_staff:
            embed.add_field(name="⚠️ Warns 🔒", value=(
                "`/warn <user> [razón]` — Warnea a un usuario (auto-mute en 3, auto-ban en 5)\n"
                "`/warns <user>` — Ve el historial de warns (solo tú lo ves)\n"
                "`/unwarn <user> <cantidad>` — Quita una cantidad exacta de warns (los más antiguos primero)\n"
                "`/clearwarns <user>` — Borra todos los warns de un usuario\n"
                "`/addrol <rol> <users>` — Da un rol a varios usuarios\n"
                "`/delrol <rol> <users>` — Quita un rol a varios usuarios\n"
                "`!verificar @user` — Da el rol de verificación al usuario mencionado"
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
            if interaction.user.id == TU_ID:
                embed.add_field(name="☢️ Reset Servidor 🔒 (solo owner)", value=(
                    "`/reset_servidor` — Borra TODOS los canales y roles, con backup JSON previo y confirmación por nombre"
                ), inline=False)

        embed.set_footer(text="Abo Bot • Prefix: slash /")
        await interaction.response.send_message(embed=embed, ephemeral=True)



_bot_iniciado = False  # evita re-registrar cogs/vistas si on_ready se dispara varias veces (reconexiones)

@bot.event
async def on_ready():
    global _bot_iniciado
    # Se registra SIEMPRE y de primero: si esto no corre, los botones de paneles
    # viejos (mensajes ya publicados) quedan sin handler y la interacción falla
    # en silencio, aunque el resto del bot funcione con normalidad.
    try:
        bot.add_view(ColorMenuView())
    except Exception as e:
        log.error(f"[add_view Error] {e}")

    if not _bot_iniciado:
        try:
            await bot.add_cog(ColorsCog(bot)); await bot.add_cog(StaffColorsCog(bot)); await bot.add_cog(BoosterColorsCog(bot)); await bot.add_cog(ModCog(bot)); await bot.add_cog(PurgaCog(bot))
            await bot.add_cog(WarnsCog(bot)); await bot.add_cog(HelpCog(bot)); await bot.add_cog(ResetCog(bot))
            await bot.tree.sync() # REGISTRA TODO A DISCORD
            _bot_iniciado = True
            log.info(f"Online: {bot.user} | {len(bot.tree.get_commands())} slash commands cargados")
        except Exception as e:
            log.error(f"[on_ready setup Error] {e}")
    else:
        log.info(f"Reconectado: {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="LatamOS"))

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        msg = "No tienes permiso para usar este comando, lo siento 🔒"
    else:
        log.error(f"[Command Error] {interaction.command}: {error}")
        msg = "Algo salió mal ejecutando el comando; inténtalo de nuevo en un momento 😅"
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except discord.HTTPException:
        pass

@bot.event
async def on_message(message: discord.Message): # La IA por mención se queda
    if message.author.bot: return
    if bot.user in message.mentions:
        texto = re.sub(r"<@!?\d+>", "", message.content).strip()
        async with message.channel.typing(): respuesta = await preguntar_ia(texto, message.author.id, message.channel.id)
        await message.channel.send(respuesta.replace("@everyone", "@\u200beveryone"), allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))

    # Comando !verificar @user -> da el rol de verificado por ID
    if message.content.startswith("!verificar"):
        es_staff = message.author.id == TU_ID or any(rol.name in ROLES_COMANDOS for rol in message.author.roles)
        if not es_staff:
            return await message.channel.send("No tienes permiso para usar este comando 🔒")
        if not message.mentions:
            return await message.channel.send("Menciona a un usuario así: `!verificar @user`")
        member = message.mentions[0]
        rol_verificado = message.guild.get_role(ROL_VERIFICADO_ID)
        if not rol_verificado:
            return await message.channel.send("No encontré el rol de verificación en el servidor (revisa el ID) ⚠️")
        try:
            await member.add_roles(rol_verificado, reason=f"Verificado por {message.author}")
            await message.channel.send(f"{member.mention} fue verificado y recibió el rol {rol_verificado.mention} ✅")
        except discord.Forbidden:
            await message.channel.send("No tengo permisos suficientes para asignar ese rol; revisa mi jerarquía 🔒")
        return

    # Bloqueo de! viejos
    if message.content.startswith("!") and not await bot.is_owner(message.author):
        return

try:
    bot.run(TOKEN)
finally:
    db.close()
