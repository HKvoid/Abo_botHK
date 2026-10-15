"""Configuración, permisos y utilidades compartidas de Abo."""
import asyncio
import logging
import os

import discord
from discord import app_commands
from groq import Groq

from database import db

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


def is_staff():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id == TU_ID:
            return True
        return any(role.name in ROLES_COMANDOS for role in interaction.user.roles)
    return app_commands.check(predicate)


def is_staff_color():
    """Solo quienes tengan el rol 'Staff' pueden usar /staffcolor."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id == TU_ID:
            return True
        return any(role.name in ROLES_STAFF_COLOR for role in interaction.user.roles)
    return app_commands.check(predicate)


# Persistencia de excepciones de purga.
async def agregar_excepcion(guild_id: int, user_id: int, razon: str, added_by: int):
    await db.execute(
        """INSERT INTO purge_exceptions (guild_id, user_id, razon, added_by)
           VALUES ($1, $2, $3, $4)
           ON CONFLICT (guild_id, user_id) DO UPDATE
           SET razon = EXCLUDED.razon, added_by = EXCLUDED.added_by, created_at = NOW()""",
        guild_id, user_id, razon, added_by,
    )


async def quitar_excepcion(guild_id: int, user_id: int) -> bool:
    status = await db.execute(
        "DELETE FROM purge_exceptions WHERE guild_id = $1 AND user_id = $2",
        guild_id, user_id,
    )
    return status.endswith("1")


async def es_excepcion(guild_id: int, user_id: int) -> bool:
    return await db.fetchval(
        "SELECT EXISTS(SELECT 1 FROM purge_exceptions WHERE guild_id = $1 AND user_id = $2)",
        guild_id, user_id,
    )


async def listar_excepciones(guild_id: int):
    rows = await db.fetch(
        """SELECT user_id, razon, added_by, created_at FROM purge_exceptions
           WHERE guild_id = $1 ORDER BY created_at DESC""",
        guild_id,
    )
    return [tuple(row) for row in rows]


# Roles de color se resuelven contra Neon por servidor, incluso después de reinicios.
async def guardar_color_role_id(guild_id: int, categoria: str, clave: str, role_id: int):
    await db.execute(
        """INSERT INTO color_roles (guild_id, categoria, clave, role_id)
           VALUES ($1, $2, $3, $4)
           ON CONFLICT (guild_id, categoria, clave) DO UPDATE SET role_id = EXCLUDED.role_id""",
        guild_id, categoria, clave, role_id,
    )


async def obtener_color_role_id(guild_id: int, categoria: str, clave: str):
    return await db.fetchval(
        "SELECT role_id FROM color_roles WHERE guild_id = $1 AND categoria = $2 AND clave = $3",
        guild_id, categoria, clave,
    )


async def resolver_color_role(guild: discord.Guild, categoria: str, clave: str):
    role_id = await obtener_color_role_id(guild.id, categoria, clave)
    if role_id:
        role = guild.get_role(role_id)
        if role:
            return role
    role = discord.utils.get(guild.roles, name=clave)
    if role:
        await guardar_color_role_id(guild.id, categoria, clave, role.id)
    return role


async def resolver_color_roles(guild: discord.Guild, categoria: str, claves):
    roles = []
    for key in claves:
        role = await resolver_color_role(guild, categoria, key)
        if role:
            roles.append(role)
    return roles


async def guardar_mensaje(user_id: int, canal_id: int, rol: str, contenido: str):
    async with db._pool().acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                "INSERT INTO memory (user_id, channel_id, role, content) VALUES ($1, $2, $3, $4)",
                user_id, canal_id, rol, contenido,
            )
            await connection.execute(
                """DELETE FROM memory WHERE user_id = $1 AND channel_id = $2
                   AND id NOT IN (
                       SELECT id FROM memory WHERE user_id = $1 AND channel_id = $2
                       ORDER BY created_at DESC, id DESC LIMIT 30
                   )""",
                user_id, canal_id,
            )


async def obtener_historial(user_id: int, canal_id: int, limite: int = 30):
    rows = await db.fetch(
        """SELECT role, content FROM memory WHERE user_id = $1 AND channel_id = $2
           ORDER BY created_at DESC, id DESC LIMIT $3""",
        user_id, canal_id, limite,
    )
    return [(row["role"], row["content"]) for row in reversed(rows)]


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
        historial = await obtener_historial(user_id, canal_id)
        mensajes = (
            [{"role": "system", "content": SISTEMA_ABO}]
            + [{"role": role, "content": content} for role, content in historial]
            + [{"role": "user", "content": prompt}]
        )
        chat = await asyncio.to_thread(
            groq_client.chat.completions.create,
            model="qwen/qwen3.8-27b", messages=mensajes, max_tokens=500, temperature=0.9,
        )
        respuesta = (chat.choices[0].message.content or "").strip()
        await guardar_mensaje(user_id, canal_id, "user", prompt)
        if respuesta:
            await guardar_mensaje(user_id, canal_id, "assistant", respuesta)
        return respuesta or "Sinceramente, ni idea 🤔"
    except Exception as error:
        log.exception("[Groq/Neon Error] %s", error)
        return "Se me cruzaron los cables, intenta de nuevo 🤖"


COLOR_ROLES = {
    "Orange": 0xE67E22, "Yellow": 0xF1C40F, "Green": 0x2ECC71, "Blue": 0x3498DB,
    "Purple": 0x9B59B6, "Pink": 0xFF69B4, "Cyan": 0x1ABC9C, "White": 0xECF0F1, "Black": 0x2C3E50,
    "Silver": 0xC0C0C0, "Aurora": 0x00FFFF, "Neon": 0x39FF14, "Blood": 0x8B0000,
    "Ocean": 0x006994, "Galaxy": 0x4B0082, "Forest": 0x228B22,
}
STAFF_COLOR_ROLES = [f"CStaff{i}" for i in range(1, 9)]
BOOSTER_COLOR_ROLES = {
    "Onix": 0xB76E79, "Aqua": 0xFFBF00, "Sunset": 0x50C878,
    "Ice": 0x0F52BA, "Amethyst": 0xB57EDC,
}


def _es_booster(member: discord.Member) -> bool:
    if member.id == TU_ID:
        return True
    if member.premium_since is not None:
        return True
    booster_role = member.guild.premium_subscriber_role
    return booster_role is not None and booster_role in member.roles
