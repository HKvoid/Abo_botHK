import discord
import os
import re
import random
import asyncio
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from groq import Groq

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
TOKEN = os.getenv("TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TU_ID = 1180967503682355220 # <-- CAMBIA ESTO POR TU ID REAL

MAX_WARNS = 3
SPAM_LIMITE = 5
SPAM_VENTANA = 6
TIMEOUT_SEG = 300
CAPS_UMBRAL = 0.7
CAPS_MIN_LEN = 10

# ─────────────────────────────────────────
# CLIENTE
# ─────────────────────────────────────────
groq_client = Groq(api_key=GROQ_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = discord.Client(intents=intents)

# ─────────────────────────────────────────
# ESTADO EN MEMORIA
# ─────────────────────────────────────────
warns: dict[int, int] = defaultdict(int)
spam_tracker: dict[int, deque] = defaultdict(deque)
ultimo_regaño: dict[int, datetime] = {}

# ─────────────────────────────────────────
# LISTAS DE MODERACIÓN
# ─────────────────────────────────────────
LINK_REGEX = re.compile(r'(https?://|discord\.gg/|bit\.ly/|t\.me/)', re.IGNORECASE)

FALLBACKS_GENERALES = [
    "jaja", "ni idea", "ah sí claro",
    "interesante eso", "meh", "procesa… procesando… nope",
]

ultimo_fallback: dict[str, int] = {}

def fallback_sin_repetir(lista: list[str], clave: str) -> str:
    ultimo = ultimo_fallback.get(clave, -1)
    opciones = [i for i in range(len(lista)) if i!= ultimo]
    idx = random.choice(opciones)
    ultimo_fallback[clave] = idx
    return lista[idx]

# ─────────────────────────────────────────
# IA - PROMPTS NEUTROS
# ─────────────────────────────────────────
SISTEMA_BASE = (
    "Eres Abo, moderador de Discord. "
    "Hablas en español mexicano informal, directo y sin formalidades. "
    "Tus respuestas son cortas: máximo 2 oraciones. "
    "No uses apodos como 'simio', 'bro', 'carnal' a menos que el usuario los use primero. "
    "PROHIBIDO decir 'no puedo', 'lo siento', 'disculpa'. NUNCA te disculpes. "
    "Si no sabes algo di 'ni idea'. "
    "Usa lenguaje neutro, no asumas el género de nadie."
)

SISTEMA_SPAM = (
    "Eres Abo, moderador. "
    "Alguien está mandando mensajes demasiado rápido. Dile que se calme, directo, en 1 oración. "
    "Sin apodos ni emojis."
)

SISTEMA_CAPS = (
    "Eres Abo, moderador. "
    "Alguien está GRITANDO con mayúsculas. Dile que baje el volumen, directo, en 1 oración. "
    "Sin apodos."
)

async def preguntar_ia(prompt: str, sistema: str = SISTEMA_BASE, fallback_lista: list[str] = FALLBACKS_GENERALES, fallback_clave: str = "general", max_tokens: int = 60) -> str:
    try:
        chat = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": sistema},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=1.3,
            frequency_penalty=1.8,
            top_p=0.9
        )
        respuesta = chat.choices[0].message.content.strip()
        respuesta = re.sub(r'\*{1,2}(.*?)\*{1,2}', r'\1', respuesta)
        if not respuesta or len(respuesta) < 4:
            return fallback_sin_repetir(fallback_lista, fallback_clave)
        return respuesta
    except Exception as e:
        print(f"[Groq Error] {e}")
        return fallback_sin_repetir(fallback_lista, fallback_clave)

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────
def cooldown_regaño(user_id: int, segundos: int = 10) -> bool:
    ahora = datetime.now(timezone.utc)
    ultimo = ultimo_regaño.get(user_id)
    if ultimo and (ahora - ultimo).total_seconds() < segundos:
        return False
    ultimo_regaño[user_id] = ahora
    return True

def registrar_spam(user_id: int) -> bool:
    ahora = datetime.now(timezone.utc)
    cola = spam_tracker[user_id]
    while cola and (ahora - cola[0]).total_seconds() > SPAM_VENTANA:
        cola.popleft()
    cola.append(ahora)
    return len(cola) >= SPAM_LIMITE

async def aplicar_warn(guild: discord.Guild, usuario: discord.Member, canal: discord.TextChannel, motivo: str):
    warns[usuario.id] += 1
    n = warns[usuario.id]
    if n >= MAX_WARNS:
        try:
            await usuario.kick(reason=f"[Abo] {MAX_WARNS} warns acumulados: {motivo}")
            warns[usuario.id] = 0
            await canal.send(f"🦍 {usuario.mention} acumuló {MAX_WARNS} warns… ya te fuiste.")
        except discord.Forbidden:
            await canal.send("Quiero kickear pero no tengo permisos.")
    else:
        restantes = MAX_WARNS - n
        await canal.send(f"⚠️ {usuario.mention} warn #{n}. Te quedan {restantes} chance{'s' if restantes!= 1 else ''}.")

async def aplicar_timeout(usuario: discord.Member, canal: discord.TextChannel, segundos: int, motivo: str):
    try:
        hasta = discord.utils.utcnow() + timedelta(seconds=segundos)
        await usuario.timeout(hasta, reason=f"[Abo] {motivo}")
        minutos = segundos // 60
        await canal.send(f"🔇 {usuario.mention} timeout de {minutos} min. Motivo: {motivo}.")
    except discord.Forbidden:
        await canal.send("No tengo perms para el timeout.")

# ─────────────────────────────────────────
# EVENTOS
# ─────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"[Abo] Listo: {bot.user} | Servidores: {len(bot.guilds)}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="el orden del server"))

@bot.event
async def on_member_join(member: discord.Member):
    canal = discord.utils.get(member.guild.text_channels, name="general") or member.guild.system_channel
    if canal:
        await canal.send(f"👋 Bienvenid@ {member.mention}. Lee las reglas porfa.")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.author == bot.user:
        return

    if hasattr(bot, 'procesados') and message.id in bot.procesados:
        return
    if not hasattr(bot, 'procesados'):
        bot.procesados = set()
    bot.procesados.add(message.id)
    if len(bot.procesados) > 100:
        bot.procesados.clear()

    autor = message.author
    guild = message.guild
    canal = message.channel
    contenido = message.content

    # ── COMANDOS DEL ADMIN ──────────────────────────────────────────
    if autor.id == TU_ID:
        lower = contenido.lower()

        #!banea @usuario o!banea ID
        if lower.startswith("!banea"):
            user_id = None
            if message.mentions:
                user_id = message.mentions[0].id
            else:
                partes = contenido.split()
                if len(partes) > 1 and partes[1].isdigit():
                    user_id = int(partes[1])
            if user_id:
                try:
                    user = await bot.fetch_user(user_id)
                    await guild.ban(user, reason="[Abo] Baneado por admin")
                    await canal.send(f"🔨 {user.name} banead@. Adiós.")
                except discord.Forbidden:
                    await canal.send("No tengo perms para banear.")
                except discord.NotFound:
                    await canal.send("No encontré a esa persona.")
            else:
                await canal.send("Uso: `!banea @usuario` o `!banea ID`")
            return

        #!desbanea @usuario o!desbanea ID
        if lower.startswith("!desbanea"):
            user_id = None
            if message.mentions:
                user_id = message.mentions[0].id
            else:
                partes = contenido.split()
                if len(partes) > 1 and partes[1].isdigit():
                    user_id = int(partes[1])
            if user_id:
                try:
                    banned_users = guild.bans()
                    async for ban_entry in banned_users:
                        if ban_entry.user.id == user_id:
                            await guild.unban(ban_entry.user, reason="[Abo] Desbaneado por admin")
                            await canal.send(f"✅ {ban_entry.user.name} desbanead@. Ya puede volver.")
                            return
                    await canal.send("Esa persona no está baneada.")
                except discord.Forbidden:
                    await canal.send("No tengo perms para desbanear.")
            else:
                await canal.send("Uso: `!desbanea @usuario` o `!desbanea ID`")
            return

        #!kickea @usuario
        if lower.startswith("!kickea") and message.mentions:
            target = message.mentions[0]
            try:
                await guild.kick(target, reason="[Abo] Kickead@ por admin")
                await canal.send(f"👟 {target.name} kickead@. A pensar afuera.")
            except discord.Forbidden:
                await canal.send("No tengo perms para kickear.")
            return

        #!timeout @usuario [minutos]
        if lower.startswith("!timeout") and message.mentions:
            target = message.mentions[0]
            partes = lower.split()
            minutos = 5
            for p in partes:
                if p.isdigit():
                    minutos = int(p)
                    break
            await aplicar_timeout(target, canal, minutos * 60, "orden del admin")
            return

        #!warn @usuario
        if lower.startswith("!warn") and message.mentions:
            target = message.mentions[0]
            await aplicar_warn(guild, target, canal, "warn manual")
            return

        #!warns @usuario
        if lower.startswith("!warns") and message.mentions:
            target = message.mentions[0]
            n = warns[target.id]
            await canal.send(f"📋 {target.mention} tiene {n} warn(s).")
            return

        #!limpia N
        if lower.startswith("!limpia"):
            partes = lower.split()
            n = 5
            if len(partes) > 1 and partes[1].isdigit():
                n = min(int(partes[1]), 100)
            borrados = await canal.purge(limit=n + 1)
            confirmacion = await canal.send(f"🧹 {len(borrados)-1} mensajes borrados.")
            await asyncio.sleep(4)
            await confirmacion.delete()
            return

    # ── ANTI-SPAM ────────────────────────────────────────────────────
    if registrar_spam(autor.id) and cooldown_regaño(autor.id, segundos=15):
        try:
            await message.delete()
        except:
            pass
        respuesta = await preguntar_ia(
            f"{autor.display_name} está mandando mensajes rapidísimo",
            sistema=SISTEMA_SPAM,
            fallback_lista=["Relájate, no es una carrera."],
            fallback_clave="spam",
            max_tokens=40,
        )
        await canal.send(f"{autor.mention} {respuesta}")
        await aplicar_warn(guild, autor, canal, "spam")
        return

    # ── ANTI-LINKS ───────────────────────────────────────────────────
    es_mod = isinstance(autor, discord.Member) and autor.guild_permissions.manage_messages
    if not es_mod and LINK_REGEX.search(contenido):
        try:
            await message.delete()
        except:
            pass
        await canal.send(f"{autor.mention} No mandes links sin permiso.")
        await aplicar_warn(guild, autor, canal, "link sin permiso")
        return

    # ── DETECTOR CAPS ────────────────────────────────────────────────
    letras = [c for c in contenido if c.isalpha()]
    if (
        len(contenido) >= CAPS_MIN_LEN
        and letras
        and sum(1 for c in letras if c.isupper()) / len(letras) >= CAPS_UMBRAL
        and cooldown_regaño(autor.id, segundos=30)
    ):
        respuesta = await preguntar_ia(
            f"'{contenido}' — alguien está gritando con mayúsculas",
            sistema=SISTEMA_CAPS,
            fallback_lista=["Baja el volumen."],
            fallback_clave="caps",
            max_tokens=40,
        )
        await canal.send(f"{autor.mention} {respuesta}")
        return

    # ── MENCIÓN DIRECTA ──────────────────────────────────────────────
    if bot.user.mentioned_in(message):
        texto = re.sub(r"<@!?\d+>", "", contenido).strip()
        saludos = {"hola", "ola", "wenas", "we", "hi", "q", "que", "hey", "k", ""}
        if texto.lower() in saludos:
            await canal.send("Qué onda")
            return
        async with canal.typing():
            respuesta = await preguntar_ia(texto, max_tokens=80)
        await canal.send(respuesta)

# ─────────────────────────────────────────
# ARRANQUE
# ─────────────────────────────────────────
bot.run(TOKEN)
