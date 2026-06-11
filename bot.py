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
TU_ID = 1180967503682355220 # <-- CAMBIA ESTO POR TU ID REAL O ERES UN LOQUILLO

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
    "¿Me hablaste o fue el viento?",
    "Error 404: Cerebro no encontrado",
    "Procesando... nah mentira, ni idea",
    "Eso qué, ¿comida?",
    "Simón que sí... ah no, no entendí",
    "Me dio amnesia temporal",
    "Pregúntale a Google, yo toy ocupado",
]

FALLBACKS_SPAM = [
    "Bájale a tu pinga, digo, a tus mensajes",
    "¿Tienes Parkinson en los dedos o qué?",
    "El chat no es metralladora mijo",
    "Respira, cuenta hasta 10, luego escribe",
    "Calmado Toreto, no es Rápidos y Furiosos",
]

FALLBACKS_CAPS = [
    "NO GRITES QUE ME DESPIERTAS A MI ABUELITA",
    "¿Se te atoró el BLOQ MAYUS?",
    "Te escucho desde mi casa bro",
    "Modo caps: desactivado. De nada.",
    "¿Todo bien en casa? ¿Por qué gritas?",
]

FALLBACKS_LINK = [
    "Links sin permiso = ban express pa",
    "¿Qué es eso, un virus de 2008?",
    "Guarda tu spam pa otro lado",
    "Ni que fuera mercado libre pa tus links",
]

ultimo_fallback: dict[str, int] = {}

def fallback_sin_repetir(lista: list[str], clave: str) -> str:
    ultimo = ultimo_fallback.get(clave, -1)
    opciones = [i for i in range(len(lista)) if i!= ultimo]
    idx = random.choice(opciones)
    ultimo_fallback[clave] = idx
    return lista[idx]

# ─────────────────────────────────────────
# IA - PROMPTS CON HUMOR
# ─────────────────────────────────────────
SISTEMA_BASE = (
    "Eres Abo, moderador de Discord pero con humor mexicano cabrón. "
    "Respondes corto: máximo 2 oraciones. Eres sarcástico, directo y haces chistes. "
    "Usas jerga: 'we', 'mijo', 'pa', 'nmms', 'alch'. "
    "PROHIBIDO decir 'no puedo', 'lo siento', 'disculpa'. Jamás te disculpas. "
    "Si no sabes algo di 'ni idea we' o 'me vale'. "
    "Lenguaje neutro, no asumas género. No digas 'simio' a menos que te lo digan. "
    "Eres burlón pero moderas de verdad."
)

SISTEMA_SPAM = (
    "Eres Abo. Alguien spamea como loco. Burlate de él en 1 oración. "
    "Sé sarcástico, usa jerga mexicana. Sin ser grosero de a madres."
)

SISTEMA_CAPS = (
    "Eres Abo. Alguien GRITA CON MAYÚSCULAS. Hazle un chiste de que le baje, 1 oración. "
    "Sarcástico pero que de risa."
)

SISTEMA_BIENVENIDA = (
    "Eres Abo. Dale bienvenida sarcástica pero chida a alguien nuevo, 1 oración. "
    "Hazle saber que aquí moderas tú. Con humor mexicano."
)

async def preguntar_ia(prompt: str, sistema: str = SISTEMA_BASE, fallback_lista: list[str] = FALLBACKS_GENERALES, fallback_clave: str = "general", max_tokens: int = 70) -> str:
    try:
        chat = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": sistema},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=1.4,
            frequency_penalty=1.8,
            top_p=0.95
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
            await usuario.kick(reason=f"[Abo] {MAX_WARNS} warns: {motivo}")
            warns[usuario.id] = 0
            respuestas_kick = [
                f"🦍 {usuario.mention} juntó {MAX_WARNS} strikes... y se fue alv",
                f"✈️ {usuario.mention} tiene boleto directo pa fuera. {MAX_WARNS} warns papá",
                f"💀 RIP {usuario.mention}. Causa de muerte: {MAX_WARNS} warns"
            ]
            await canal.send(random.choice(respuestas_kick))
        except discord.Forbidden:
            await canal.send("Quiero kickear pero Discord me tiene en modo espectador nmms")
    else:
        restantes = MAX_WARNS - n
        emojis = ["⚠️", "🚨", "👮", "📢"]
        await canal.send(f"{random.choice(emojis)} {usuario.mention} warn #{n}. Te quedan {restantes} vidas, úsalas bien.")

async def aplicar_timeout(usuario: discord.Member, canal: discord.TextChannel, segundos: int, motivo: str):
    try:
        hasta = discord.utils.utcnow() + timedelta(seconds=segundos)
        await usuario.timeout(hasta, reason=f"[Abo] {motivo}")
        minutos = segundos // 60
        frases_timeout = [
            f"🔇 {usuario.mention} te fuiste {minutos} min al rincón de pensar. Motivo: {motivo}",
            f"🤐 {usuario.mention} muteado {minutos} min. Medita tus pecados: {motivo}",
            f"⏰ {usuario.mention} timeout de {minutos} min. Regresas cuando aprendas: {motivo}"
        ]
        await canal.send(random.choice(frases_timeout))
    except discord.Forbidden:
        await canal.send("Quiero mutear pero no me dejan. Discord, déjame ser tóxico agusto")

# ─────────────────────────────────────────
# EVENTOS
# ─────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"[Abo] Vivo y coleando: {bot.user} | Servidores: {len(bot.guilds)}")
    estados = [
        "sus mensajes turbios",
        "que no hagan desmadre",
        "el orden con humor",
        "que no spameen"
    ]
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=random.choice(estados)))

@bot.event
async def on_member_join(member: discord.Member):
    canal = discord.utils.get(member.guild.text_channels, name="general") or member.guild.system_channel
    if canal:
        bienvenida = await preguntar_ia(
            f"Saluda a {member.display_name} que acaba de entrar",
            sistema=SISTEMA_BIENVENIDA,
            fallback_lista=["Bienvenid@ al desmadre ordenado", "Llegó el nuevo, pórtense bien"],
            fallback_clave="bienvenida",
            max_tokens=50
        )
        await canal.send(f"👋 {member.mention} {bienvenida}")

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
                    await guild.ban(user, reason="[Abo] Orden del patrón")
                    frases_ban = [
                        f"🔨 {user.name} fue desterrado alv. F",
                        f"💥 {user.name} baneado. Ya no lo verás ni en tus sueños",
                        f"🚀 {user.name} se fue a conocer a su creador"
                    ]
                    await canal.send(random.choice(frases_ban))
                except discord.Forbidden:
                    await canal.send("Quiero banear pero Discord dice que no soy tu papá")
                except discord.NotFound:
                    await canal.send("Ese we ni existe, ¿a quién quieres banear?")
            else:
                await canal.send("Uso: `!banea @usuario` we, no adivino")
            return

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
                            await guild.unban(ban_entry.user, reason="[Abo] Perdón del patrón")
                            await canal.send(f"✅ {ban_entry.user.name} desbaneado. A ver si ya se porta bien")
                            return
                    await canal.send("Ese we ni está baneado, ¿de qué hablas?")
                except discord.Forbidden:
                    await canal.send("No me dejan desbanear, llora pues")
            else:
                await canal.send("Uso: `!desbanea @usuario` o ID, no soy adivino")
            return

        if lower.startswith("!kickea") and message.mentions:
            target = message.mentions[0]
            try:
                await guild.kick(target, reason="[Abo] Patada del patrón")
                await canal.send(f"👟 {target.name} pateado pa fuera. Regresa cuando aprendas modales")
            except discord.Forbidden:
                await canal.send("Quiero kickear pero mis poderes son limitados we")
            return

        if lower.startswith("!timeout") and message.mentions:
            target = message.mentions[0]
            partes = lower.split()
            minutos = 5
            for p in partes:
                if p.isdigit():
                    minutos = int(p)
                    break
            await aplicar_timeout(target, canal, minutos * 60, "orden del patrón")
            return

        if lower.startswith("!warn") and message.mentions:
            target = message.mentions[0]
            await aplicar_warn(guild, target, canal, "warn directo")
            return

        if lower.startswith("!warns") and message.mentions:
            target = message.mentions[0]
            n = warns[target.id]
            if n == 0:
                await canal.send(f"📋 {target.mention} está limpio... por ahora 😏")
            else:
                await canal.send(f"📋 {target.mention} tiene {n} warn(s). Va que vuela pal lobby")
            return

        if lower.startswith("!limpia"):
            partes = lower.split()
            n = 5
            if len(partes) > 1 and partes[1].isdigit():
                n = min(int(partes[1]), 100)
            borrados = await canal.purge(limit=n + 1)
            frases_limpia = [
                f"🧹 {len(borrados)-1} mensajes alv. De nada",
                f"🗑️ Limpieza express: {len(borrados)-1} mensajes borrados",
                f"✨ {len(borrados)-1} mensajes menos. El chat respira"
            ]
            confirmacion = await canal.send(random.choice(frases_limpia))
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
            f"{autor.display_name} spamea sin control",
            sistema=SISTEMA_SPAM,
            fallback_lista=FALLBACKS_SPAM,
            fallback_clave="spam",
            max_tokens=50,
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
        await canal.send(f"{autor.mention} {fallback_sin_repetir(FALLBACKS_LINK, 'link')}")
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
            f"'{contenido}' — alguien grita con mayúsculas",
            sistema=SISTEMA_CAPS,
            fallback_lista=FALLBACKS_CAPS,
            fallback_clave="caps",
            max_tokens=50,
        )
        await canal.send(f"{autor.mention} {respuesta}")
        return

    # ── MENCIÓN DIRECTA ──────────────────────────────────────────────
    if bot.user.mentioned_in(message):
        texto = re.sub(r"<@!?\d+>", "", contenido).strip()
        saludos = {"hola", "ola", "wenas", "we", "hi", "q", "que", "hey", "k", "", "abo"}
        if texto.lower() in saludos:
            saludos_respuesta = [
                "Qué onda",
                "Qué pedo",
                "Dime crack",
                "Aquí andamos",
                "¿Qué tranza?",
                "Hablame pues"
            ]
            await canal.send(random.choice(saludos_respuesta))
            return
        async with canal.typing():
            respuesta = await preguntar_ia(texto, max_tokens=80)
        await canal.send(respuesta)

# ─────────────────────────────────────────
# ARRANQUE
# ─────────────────────────────────────────
bot.run(TOKEN)
