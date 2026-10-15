"""Configuración y utilidades compartidas de Abo."""
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


logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("Abo")

TOKEN = os.getenv("TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TU_ID = 1180967503682355220
ROL_MIEMBRO = "Miembro"
ROLES_COMANDOS = ["Admin", "Moderador", "Shogun 🦈", "ViceRoot", "Root", "Daimyō", "Rōnin"]
ROLES_STAFF_COLOR = ["Staff"]

if not TOKEN or not GROQ_API_KEY:
    raise RuntimeError("❌ Falta TOKEN o GROQ_API_KEY")

groq_client = Groq(api_key=GROQ_API_KEY)
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

SISTEMA_ABO = (
    "Eres Abo, un bot de Discord con personalidad sarcástica. Respondes SIEMPRE en español, "
    "en 1 sola oración, corta y natural, como si fueras un amigo chateando. "
    "Usa 'we', 'nmms', 'pa' con moderación, no en cada mensaje. "
    "NUNCA describas tu propia personalidad, ni digas cosas como 'estoy aquí para responder con sarcasmo' "
    "o listes lo que puedes hacer. Si te saludan, solo saluda de vuelta con humor breve, sin explicaciones. "
    "No hagas preguntas retóricas largas ni des opciones tipo menú."
)
async def preguntar_ia(prompt: str, user_id: int, canal_id: int) -> str:
    try:
        historial = obtener_historial(user_id, canal_id)
        mensajes = [{"role": "system", "content": SISTEMA_ABO}] + [{"role": r, "content": c} for r, c in historial] + [{"role": "user", "content": prompt}]
        # El SDK de Groq es síncrono; lo mandamos a un hilo aparte para no bloquear
        # el event loop de discord.py (si no, el bot entero se congela mientras espera la IA).
        # max_tokens subido y reasoning_effort bajo: gpt-oss-20b es un modelo de razonamiento
        # que gasta tokens "pensando" antes de responder; con poco margen se quedaba sin
        # tokens para el contenido final y devolvía la respuesta vacía.
        chat = await asyncio.to_thread(
            groq_client.chat.completions.create,
            model = "qwen/qwen3.8-27b", messages=mensajes, max_tokens=500, temperature=0.9
        )
        respuesta = chat.choices[0].message.content.strip()
        guardar_mensaje(user_id, canal_id, "user", prompt); guardar_mensaje(user_id, canal_id, "assistant", respuesta)
        return respuesta if respuesta else "Sinceramente, ni idea 🤔"
    except Exception as e:
        log.error(f"[Groq Error] {e}"); return "Se me cruzaron los cables, intenta de nuevo 🤖"

COLOR_ROLES = {
    "Orange": 0xE67E22, "Yellow": 0xF1C40F, "Green": 0x2ECC71, "Blue": 0x3498DB,
    "Purple": 0x9B59B6, "Pink": 0xFF69B4, "Cyan": 0x1ABC9C, "White": 0xECF0F1, "Black": 0x2C3E50,
    "Silver": 0xC0C0C0, "Aurora": 0x00FFFF, "Neon": 0x39FF14, "Blood": 0x8B0000,
    "Ocean": 0x006994, "Galaxy": 0x4B0082, "Forest": 0x228B22,
}
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
