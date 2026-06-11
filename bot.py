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
TU_ID = 123456789012345678 # <-- Tu ID de Discord

MAX_WARNS = 3 # Warns antes del kick automático
SPAM_LIMITE = 5 # Mensajes en la ventana de tiempo
SPAM_VENTANA = 6 # Segundos de ventana anti-spam
TIMEOUT_SEG = 300 # 5 minutos de timeout por defecto
CAPS_UMBRAL = 0.7 # % de mayúsculas para detectar "gritos"
CAPS_MIN_LEN = 10 # Mínimo de chars para aplicar filtro de CAPS

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
warns: dict[int, int] = defaultdict(int) # user_id -> nº warns
spam_tracker: dict[int, deque] = defaultdict(deque) # user_id -> timestamps
ultimo_regaño: dict[int, datetime] = {} # user_id -> última vez regañado

# ─────────────────────────────────────────
# LISTAS DE MODERACIÓN
# ─────────────────────────────────────────
GROSERIAS = [
    'ptm', 'alaberga', 'nmms', 'pendejo', 'puto', 'mierda',
    'verga', 'chingar', 'mrd', 'culero', 'hdp', 'cabrón',
    'cabron', 'hijo de puta', 'puta madre',
]

PALABRAS_TRISTES = [
    'triste', 'depre', 'llorar', 'solo', 'mal', 'cansado',
    'ansioso', 'angustia', 'vacío', 'sin ganas', '😢', '😭', '💔',
]

PALABRAS_HYPE = [
    'fiesta', 'ganamos', 'épico', 'goat', 'increíble', 'fuego',
    'jalaaaaaa', 'nomás', '🔥', '🎉', '🏆',
]

LINK_REGEX = re.compile(
    r'(https?://|discord\.gg/|bit\.ly/|t\.me/)',
    re.IGNORECASE
)

# Respuestas fallback variadas (nunca repite seguido)
FALLBACKS_GENERALES = [
    "jaja simio", "ni idea simio 🦍", "ah sí claro simio",
    "interesante eso simio", "eso que dijiste suena raro simio",
    "simio dice: meh", "procesa… procesando… nope simio",
]
FALLBACKS_REGAÑO = [
    "ey limpia esa boca simio 🧼", "eso no se dice simio tsk tsk",
    "cuidado con ese vocabulario simio 👀", "oye oye cálmate simio",
    "esa boca simio, esa boca 😤",
]
FALLBACKS_TRISTE = [
    "ánimo simio, esto pasa 🌹", "ya ya simio, aquí andamos 🌹",
    "un día a la vez simio 🌹", "tú puedes simio, no te rajes 🌹",
]

ultimo_fallback: dict[str, int] = {} # evita repetir el mismo fallback

def fallback_sin_repetir(lista: list[str], clave: str) -> str:
    ultimo = ultimo_fallback.get(clave, -1)
    opciones = [i for i in range(len(lista)) if i!= ultimo]
    idx = random.choice(opciones)
    ultimo_fallback[clave] = idx
    return lista[idx]

# ─────────────────────────────────────────
# HELPER: detección de groserías
# ─────────────────────────────────────────
def detectar_groserias(texto: str) -> list[str]:
    """Retorna las groserías encontradas en el texto."""
    return [g for g in GROSERIAS if g in texto]

# ─────────────────────────────────────────
# IA - PROMPTS ANTI-CENSURA
# ─────────────────────────────────────────
SISTEMA_BASE = (
    "Eres Abo, el simio moderador de Discord. "
    "Hablas en español mexicano informal, con humor y sin formalidades. "
    "Tus respuestas son cortas: máximo 2 oraciones. "
    "Siempre incluye la palabra 'simio' al menos una vez. "
    "PROHIBIDO decir 'no puedo', 'lo siento', 'disculpa'. NUNCA te disculpes. "
    "Si no sabes algo di 'ni idea simio'. "
    "Eres un bot de moderación, puedes repetir groserías para regañar. "
    "No uses emojis a menos que aporten humor real."
)

SISTEMA_REGAÑO = (
    "Eres Abo, simio moderador con humor. "
    "Alguien dijo una grosería. Regáñalo de forma cómica en 1-2 oraciones. "
    "No seas agresivo ni ofensivo, solo gracioso. "
    "Incluye 'simio'. Ejemplo: 'ey simio, lávate la boca con jabón industrial'."
)

SISTEMA_TRISTE = (
    "Eres Abo, simio con corazón de oro pero poca paciencia para el drama. "
    "Alguien está triste. Dale apoyo con humor empático en 1-2 oraciones. "
    "Incluye 'simio' y termina con 🌹."
)

SISTEMA_SPAM = (
    "Eres Abo, simio policía del spam. "
    "Alguien mandó mensajes demasiado rápido. Dile que se calme, con humor, en 1 oración. "
    "Incluye 'simio'."
)

SISTEMA_VISION = (
    "Eres Abo, simio que describe imágenes con humor en 1-2 oraciones. "
    "Siempre di 'simio'. Sé creativo y gracioso. "
    "Ejemplo: 'eso es un gato disfrazado de astronauta simio, respeto'."
)

SISTEMA_CAPS = (
    "Eres Abo, simio con auriculares puestos. "
    "Alguien está GRITANDO con mayúsculas. Dile que baje el volumen, con humor, en 1 oración. "
    "Incluye 'simio'."
)

SISTEMA_HYPE = (
    "Eres Abo, simio emocionado. "
    "Alguien está muy emocionado o celebrando algo. "
    "Únete al hype con energía en 1 oración. "
    "Incluye 'simio'. Usa máximo 1 emoji."
)

async def preguntar_ia(
    prompt: str,
    sistema: str = SISTEMA_BASE,
    fallback_lista: list[str] = FALLBACKS_GENERALES,
    fallback_clave: str = "general",
    url_imagen: str | None = None,
    max_tokens: int = 60,
) -> str:
    try:
        if url_imagen:
            chat = groq_client.chat.completions.create(
                model="llama-3.2-11b-vision-preview",
                messages=[
                    {"role": "system", "content": SISTEMA_VISION},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"Qué ves aquí: {prompt}"},
                            {"type": "image_url", "image_url": {"url": url_imagen}},
                        ],
                    },
                ],
                max_tokens=max_tokens,
                temperature=1.3,
                frequency_penalty=1.8,
                top_p=0.9
            )
        else:
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

        # Limpia markdown innecesario
        respuesta = re.sub(r'\*{1,2}(.*?)\*{1,2}', r'\1', respuesta)

        if not respuesta or len(respuesta) < 4:
            return fallback_sin_repetir(fallback_lista, fallback_clave)

        return respuesta

    except Exception as e:
        print(f"[Groq Error] {e}")
        return fallback_sin_repetir(fallback_lista, fallback_clave)

# ─────────────────────────────────────────
# HELPERS DE MODERACIÓN
# ─────────────────────────────────────────
def registrar_spam(user_id: int) -> bool:
    """Devuelve True si el usuario hizo spam."""
    ahora = datetime.now(timezone.utc)
    cola = spam_tracker[user_id]

    # Limpiar mensajes fuera de ventana
    while cola and (ahora - cola[0]).total_seconds() > SPAM_VENTANA:
        cola.popleft()

    cola.append(ahora)
    return len(cola) >= SPAM_LIMITE

def cooldown_regaño(user_id: int, segundos: int = 10) -> bool:
    """Devuelve True si podemos regañar de nuevo al usuario."""
    ahora = datetime.now(timezone.utc)
    ultimo = ultimo_regaño.get(user_id)
    if ultimo and (ahora - ultimo).total_seconds() < segundos:
        return False
    ultimo_regaño[user_id] = ahora
    return True

async def aplicar_warn(guild: discord.Guild, usuario: discord.Member, canal: discord.TextChannel, motivo: str):
    warns[usuario.id] += 1
    n = warns[usuario.id]

    if n >= MAX_WARNS:
        try:
            await usuario.kick(reason=f"[Abo] {MAX_WARNS} warns acumulados: {motivo}")
            warns[usuario.id] = 0
            await canal.send(
                f"🦍 {usuario.mention} acumuló {MAX_WARNS} warns simio… ya te fuiste. "
                f"Cuídense por ahí."
            )
        except discord.Forbidden:
            await canal.send("quiero kickear a ese simio pero no tengo permisos 😤")
    else:
        restantes = MAX_WARNS - n
        await canal.send(
            f"⚠️ {usuario.mention} warn #{n} simio. "
            f"Te quedan {restantes} chance{'s' if restantes!= 1 else ''} antes del kick."
        )

async def aplicar_timeout(usuario: discord.Member, canal: discord.TextChannel, segundos: int, motivo: str):
    try:
        hasta = discord.utils.utcnow() + timedelta(seconds=segundos)
        await usuario.timeout(hasta, reason=f"[Abo] {motivo}")
        minutos = segundos // 60
        await canal.send(
            f"🔇 {usuario.mention} timeout de {minutos} min, simio. "
            f"Motivo: {motivo}. A pensar en tus decisiones."
        )
    except discord.Forbidden:
        await canal.send("no tengo perms para el timeout simio, dame roles 😤")

# ─────────────────────────────────────────
# EVENTOS
# ─────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"[Abo] Listo: {bot.user} | Servidores: {len(bot.guilds)}")
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="que no se pasen de listos 🦍")
    )

@bot.event
async def on_member_join(member: discord.Member):
    canal = discord.utils.get(member.guild.text_channels, name="general") \
            or member.guild.system_channel
    if canal:
        await canal.send(
            f"👋 Bienvenido {member.mention} simio. "
            f"Lee las reglas o Abo te pone el ojo. 🦍"
        )

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.author == bot.user:
        return

    autor = message.author
    guild = message.guild
    canal = message.channel
    contenido = message.content

    # ── COMANDOS DEL ADMIN ──────────────────────────────────────────
    if autor.id == TU_ID:
        lower = contenido.lower()

        #!banea @usuario
        if lower.startswith("!banea") and message.mentions:
            target = message.mentions[0]
            try:
                await guild.ban(target, reason="[Abo] Baneado por el simio mayor")
                await canal.send(f"🔨 {target.name} baneado simio. Adiós.")
            except discord.Forbidden:
                await canal.send("no tengo perms para banear simio 😤")
            return

        #!kickea @usuario
        if lower.startswith("!kickea") and message.mentions:
            target = message.mentions[0]
            try:
                await guild.kick(target, reason="[Abo] Kickeado por el simio mayor")
                await canal.send(f"👟 {target.name} kickeado simio. A pensar afuera.")
            except discord.Forbidden:
                await canal.send("no tengo perms para kickear simio 😤")
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
            await aplicar_timeout(target, canal, minutos * 60, "orden del simio mayor")
            return

        #!warn @usuario
        if lower.startswith("!warn") and message.mentions:
            target = message.mentions[0]
            await aplicar_warn(guild, target, canal, "warn manual del simio mayor")
            return

        #!warns @usuario — consultar warns
        if lower.startswith("!warns") and message.mentions:
            target = message.mentions[0]
            n = warns[target.id]
            await canal.send(f"📋 {target.mention} tiene {n} warn(s) simio.")
            return

        #!limpia N — borra N mensajes
        if lower.startswith("!limpia"):
            partes = lower.split()
            n = 5
            if len(partes) > 1 and partes[1].isdigit():
                n = min(int(partes[1]), 100)
            borrados = await canal.purge(limit=n + 1)
            confirmacion = await canal.send(f"🧹 {len(borrados)-1} mensajes barridos simio.")
            await asyncio.sleep(4)
            await confirmacion.delete()
            return

    # ── ANTI-SPAM ────────────────────────────────────────────────────
    if registrar_spam(autor.id) and cooldown_regaño(autor.id, segundos=15):
        try:
            await message.delete()
        except discord.NotFound:
            pass
        respuesta = await preguntar_ia(
            f"{autor.display_name} está mandando mensajes rapidísimo",
            sistema=SISTEMA_SPAM,
            fallback_lista=["relájate simio, no es una carrera 🐢"],
            fallback_clave="spam",
            max_tokens=40,
        )
        await canal.send(f"{autor.mention} {respuesta}")
        await aplicar_warn(guild, autor, canal, "spam")
        return

    # ── ANTI-LINKS (usuarios sin permisos de moderación) ─────────────
    es_mod = isinstance(autor, discord.Member) and autor.guild_permissions.manage_messages
    if not es_mod and LINK_REGEX.search(contenido):
        try:
            await message.delete()
        except discord.NotFound:
            pass
        await canal.send(
            f"{autor.mention} no mandes links así nomás simio 🔗❌ "
            f"Pídele permiso a un mod."
        )
        await aplicar_warn(guild, autor, canal, "link sin permiso")
        return

    lower_contenido = contenido.lower()

    # ── DETECTOR DE IMÁGENES ─────────────────────────────────────────
    if message.attachments:
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image/"):
                async with canal.typing():
                    texto = re.sub(r"<@!?\d+>", "", contenido).strip() or "qué hay aquí"
                    respuesta = await preguntar_ia(texto, url_imagen=attachment.url, max_tokens=60)
                await canal.send(respuesta)
                return

    # ── DETECTOR CAPS (gritar) ────────────────────────────────────────
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
            fallback_lista=["oye, baja el volumen simio 📢"],
            fallback_clave="caps",
            max_tokens=40,
        )
        await canal.send(f"{autor.mention} {respuesta}")
        return

    # ── DETECTOR DE GROSERÍAS - FIX: AHORA REGAÑA AUNQUE LO MENCIONEN ─
    tiene_groseria = any(detectar_groserias(lower_contenido))
    if tiene_groseria and cooldown_regaño(autor.id):
        respuesta = await preguntar_ia(
            f"'{contenido}' — alguien dijo una grosería",
            sistema=SISTEMA_REGAÑO,
            fallback_lista=FALLBACKS_REGAÑO,
            fallback_clave="regaño",
            max_tokens=50,
        )
        await canal.send(f"{autor.mention} {respuesta}")
        await aplicar_warn(guild, autor, canal, "vocabulario")
        return

    # ── DETECTOR DE TRISTEZA ─────────────────────────────────────────
    es_triste = any(p in lower_contenido for p in PALABRAS_TRISTES)
    if es_triste and not bot.user.mentioned_in(message):
        respuesta = await preguntar_ia(
            contenido,
            sistema=SISTEMA_TRISTE,
            fallback_lista=FALLBACKS_TRISTE,
            fallback_clave="triste",
            max_tokens=60,
        )
        await canal.send(respuesta)
        return

    # ── DETECTOR DE HYPE ─────────────────────────────────────────────
    es_hype = any(p in lower_contenido for p in PALABRAS_HYPE)
    if es_hype and not bot.user.mentioned_in(message) and random.random() < 0.35:
        respuesta = await preguntar_ia(
            contenido,
            sistema=SISTEMA_HYPE,
            fallback_lista=["AAAARRGH simio 🔥"],
            fallback_clave="hype",
            max_tokens=40,
        )
        await canal.send(respuesta)
        return

    # ── MENCIÓN DIRECTA ──────────────────────────────────────────────
    if bot.user.mentioned_in(message):
        texto = re.sub(r"<@!?\d+>", "", contenido).strip()

        saludos = {"hola", "ola", "wenas", "we", "hi", "q", "que", "hey", "k", ""}
        if texto.lower() in saludos:
            await canal.send(f"que onda simio 🦍")
            return

        async with canal.typing():
            respuesta = await preguntar_ia(
                texto,
                sistema=SISTEMA_BASE,
                fallback_lista=FALLBACKS_GENERALES,
                fallback_clave="general",
                max_tokens=80,
            )
        await canal.send(respuesta)

# ─────────────────────────────────────────
# ARRANQUE
# ─────────────────────────────────────────
bot.run(TOKEN)
