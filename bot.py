import discord
import os
import re
import random
import asyncio
import sqlite3
import logging
from datetime import timedelta
from groq import Groq

# ─────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("Abo")

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
TOKEN = os.getenv("TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TU_ID = 1180967503682355220
ROL_MIEMBRO = "MemberLT"

ROLES_COMANDOS = ["Admin", "Mod", "Semi Admin", "ViceRoot", "Root"]

# MEJORA 1: Validar variables de entorno al inicio, falla rápido con mensaje claro
if not TOKEN:
    raise RuntimeError("❌ Falta la variable de entorno TOKEN")
if not GROQ_API_KEY:
    raise RuntimeError("❌ Falta la variable de entorno GROQ_API_KEY")

groq_client = Groq(api_key=GROQ_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = discord.Client(intents=intents)

# VARIABLES GLOBALES PA LA PURGA
ULTIMOS_FANTASMAS = {}
PURGA_PENDIENTE = {}  # guild_id: True/False

# ─────────────────────────────────────────
# FUNCIÓN PA CHECAR PERMISOS DE COMANDOS
# ─────────────────────────────────────────
def puede_usar_comandos(member: discord.Member) -> bool:
    if member.id == TU_ID:
        return True
    if isinstance(member, discord.User):
        return False
    return any(rol.name in ROLES_COMANDOS for rol in member.roles)

# ─────────────────────────────────────────
# MEMORIA CON SQLITE - 30
# MEJORA 2: check_same_thread=False para evitar errores en contexto async
# ─────────────────────────────────────────
db = sqlite3.connect("abo_memoria.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS memoria (
    user_id INTEGER,
    canal_id INTEGER,
    rol TEXT,
    contenido TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
db.commit()

def guardar_mensaje(user_id, canal_id, rol, contenido):
    cursor.execute("INSERT INTO memoria (user_id, canal_id, rol, contenido) VALUES (?,?,?,?)",
                   (user_id, canal_id, rol, contenido))
    cursor.execute("""
        DELETE FROM memoria WHERE rowid NOT IN (
            SELECT rowid FROM memoria
            WHERE user_id =? AND canal_id =?
            ORDER BY timestamp DESC LIMIT 30
        ) AND user_id =? AND canal_id =?
    """, (user_id, canal_id, user_id, canal_id))
    db.commit()

def obtener_historial(user_id, canal_id, limite=30):
    cursor.execute("""
        SELECT rol, contenido FROM memoria
        WHERE user_id =? AND canal_id =?
        ORDER BY timestamp DESC LIMIT?
    """, (user_id, canal_id, limite))
    historial = cursor.fetchall()
    return list(reversed(historial))

# ─────────────────────────────────────────
# PERSONALIDAD ABO
# ─────────────────────────────────────────
SISTEMA_ABO = (
    "Eres Abo, bot de Discord. "
    "Respondes en máximo 2 oraciones cortas. "
    "Usa humor y jerga: 'we', 'nmms', 'pa'. "
    "Sé sarcástico pero COHERENTE. No digas cosas sin sentido. "
    "PROHIBIDO decir 'no puedo', 'lo siento'. Si no sabes di 'ni idea we'. "
    "No te metas con mamás. No asumas género. No digas 'simio'. "
    "Usa el historial de conversación para tener contexto."
)

async def preguntar_ia(prompt: str, user_id: int, canal_id: int) -> str:
    try:
        historial = obtener_historial(user_id, canal_id)
        mensajes = [{"role": "system", "content": SISTEMA_ABO}]
        for rol, contenido in historial:
            mensajes.append({"role": rol, "content": contenido})
        mensajes.append({"role": "user", "content": prompt})
        chat = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=mensajes,
            max_tokens=150,
            temperature=0.9
        )
        respuesta = chat.choices[0].message.content.strip()
        guardar_mensaje(user_id, canal_id, "user", prompt)
        guardar_mensaje(user_id, canal_id, "assistant", respuesta)
        return respuesta if respuesta else "Ni idea we"
    except Exception as e:
        # MEJORA 3: Loggear el error real en vez de solo print
        log.error(f"[Groq Error] {e}")
        return "Me bugueé we"

# ─────────────────────────────────────────
# EVENTOS
# ─────────────────────────────────────────
@bot.event
async def on_ready():
    log.info(f"Online: {bot.user} | Memoria de 30 activa")
    log.info(f"Roles con comandos: {', '.join(ROLES_COMANDOS)}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="LatamOS"))

@bot.event
async def on_message(message: discord.Message):
    global ULTIMOS_FANTASMAS, PURGA_PENDIENTE
    if message.author.bot:
        return
    lower = message.content.lower()

    # ── DMs solo para el owner ──
    if isinstance(message.channel, discord.DMChannel) and message.author.id == TU_ID:
        if lower.startswith("!say "):
            partes = message.content.split(" ", 2)
            if len(partes) < 3:
                await message.channel.send("Uso: `!say #nombre-canal tu mensaje` we")
                return
            canal_nombre = partes[1].replace("#", "").replace("💬", "")
            texto = partes[2]
            canal_obj = None
            server_obj = None
            for guild in bot.guilds:
                for canal in guild.text_channels:
                    if canal_nombre.lower() in canal.name.lower():
                        canal_obj = canal
                        server_obj = guild
                        break
                if canal_obj:
                    break
            if canal_obj:
                try:
                    await canal_obj.send(texto)
                    await message.channel.send(f"✅ Enviado a #{canal_obj.name} en **{server_obj.name}**")
                except discord.Forbidden:
                    await message.channel.send("❌ No tengo permisos pa escribir ahí we")
            else:
                await message.channel.send(f"❌ No encontré el canal `{canal_nombre}`")
        return

    # ── Help ──
    if lower in {"!help", "!cmd"}:
        embed = discord.Embed(
            title="🔥 Comandos de Abo",
            description="Esto es lo que sé hacer mijo",
            color=0x00ff00
        )
        embed.add_field(
            name="💬 Chat con IA",
            value="`@Abo tu pregunta` - Háblame y te respondo con memoria de 30\n`@Abo dile a @user: mensaje` - Le paso tu recado",
            inline=False
        )
        embed.add_field(
            name="🔨 Moderación (Solo staff)",
            value="`!banea @user razón` - Destierra alv\n`!mutea @user 10m` - Silencia por tiempo\n`!explota @user` - Lo banea con estilo\n`!purgaafk confirmar` - Patea a tiesos de 15d",
            inline=False
        )
        embed.add_field(
            name="🧹 Limpieza (Solo staff)",
            value="`!limpia 10` - Borra 10 mensajes\n`!scan` - Busca fantasmas con 0 mensajes en 15d",
            inline=False
        )
        embed.add_field(
            name="👥 Roles (Solo staff)",
            value="`!addrol @user1 @user2 Rol` - Da rol a varios\n`!delrol @user1 @user2 Rol` - Quita rol a varios",
            inline=False
        )
        embed.add_field(
            name="🧠 Memoria",
            value="`!olvidame` - Borro lo que recuerdo de ti en este canal",
            inline=False
        )
        embed.add_field(
            name="💬 Otros (Solo staff)",
            value="`!say texto` - Yo digo lo que escribas",
            inline=False
        )
        embed.set_footer(text="Comandos de moderación solo pa roles autorizados")
        await message.channel.send(embed=embed)
        return

    # ── MEJORA 4: !olvidame disponible para CUALQUIER usuario, no solo staff ──
    if lower.startswith("!olvidame"):
        cursor.execute("DELETE FROM memoria WHERE user_id =? AND canal_id =?",
                       (message.author.id, message.channel.id))
        db.commit()
        await message.channel.send("✅ Ya te olvidé we, borrón y cuenta nueva")
        return

    # ── Menciones al bot ──
    if bot.user in message.mentions:
        texto = re.sub(r"<@!?\d+>", "", message.content).strip()
        match_dile = re.search(r'(?:dile|menciona|etiqueta) a <@!?(\d+)>:?\s*(.*)', message.content, re.IGNORECASE)
        if match_dile:
            user_id = int(match_dile.group(1))
            mensaje = match_dile.group(2).strip()
            user_obj = message.guild.get_member(user_id)
            if user_obj:
                await message.channel.send(f"{user_obj.mention} {mensaje}" if mensaje else f"{user_obj.mention}")
            else:
                await message.channel.send("No encontré a ese we")
            return

        if texto.lower() in {"hola", "ola", "wenas", "we", "hi", "q", "que", "hey", "k", "", "abo"}:
            await message.channel.send(random.choice(["Qué onda", "Qué pedo", "Dime we", "Aquí andamos"]))
            return
        async with message.channel.typing():
            respuesta = await preguntar_ia(texto, message.author.id, message.channel.id)
        respuesta_safe = respuesta.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
        await message.channel.send(respuesta_safe, allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))

    # ── Bloquear comandos a no-staff ──
    if not puede_usar_comandos(message.author):
        if lower.startswith("!"):
            await message.channel.send("Waos")
        return

    # ── COMANDOS STAFF ──

    elif lower.startswith("!banea"):
        if not message.mentions:
            await message.channel.send("Menciona a quién we: `!banea @user razón`")
            return
        user = message.mentions[0]
        razon = message.content.split(" ", 2)[2] if len(message.content.split()) > 2 else "Se pasó de verga"
        try:
            await user.ban(reason=razon)
            await message.channel.send(f"🔨 {user.name} fue desterrado alv. Razón: {razon}")
        except discord.Forbidden:
            await message.channel.send("No tengo permisos pa banearlo we")
        except Exception as e:
            log.error(f"[banea] {e}")
            await message.channel.send("No lo pude banear we, revisa mis perms")

    elif lower.startswith("!mutea"):
        if not message.mentions:
            await message.channel.send("Menciona a quién we: `!mutea @user 10m`")
            return
        partes = message.content.split()
        user = message.mentions[0]
        # MEJORA 5: Tomar el último argumento como tiempo (evita colisión con la mención)
        tiempo_str = partes[-1] if len(partes) > 2 else "10m"
        # Si el último arg es una mención, default a 10m
        if tiempo_str.startswith("<@"):
            tiempo_str = "10m"
        tiempo_seg = 600
        try:
            if tiempo_str.endswith("m"):
                tiempo_seg = int(tiempo_str[:-1]) * 60
            elif tiempo_str.endswith("h"):
                tiempo_seg = int(tiempo_str[:-1]) * 3600
            elif tiempo_str.endswith("d"):
                tiempo_seg = int(tiempo_str[:-1]) * 86400
        except ValueError:
            await message.channel.send("Tiempo inválido we, usa por ej: `10m`, `2h`, `1d`")
            return
        try:
            await user.timeout(timedelta(seconds=tiempo_seg))
            await message.channel.send(f"🤐 Silenciado {user.name} por {tiempo_str}")
        except discord.Forbidden:
            await message.channel.send("No tengo permisos pa mutearlo we")
        except Exception as e:
            log.error(f"[mutea] {e}")
            await message.channel.send("No lo pude mutear we")

    elif lower.startswith("!explota"):
        if not message.mentions:
            await message.channel.send("¿A quién exploto we? `!explota @user`")
            return
        user = message.mentions[0]
        try:
            await message.channel.send(f"{user.mention} EXPLOTÓ 💣")
            await asyncio.sleep(1)
            await user.ban(reason=f"Explotado por {message.author}")
            await message.channel.send(f"Quedaron los puros pedazos de {user.name} we")
        except discord.Forbidden:
            await message.channel.send("El wey trae chaleco antibombas (sin permisos)")
        except Exception as e:
            log.error(f"[explota] {e}")
            await message.channel.send("El wey trae chaleco antibombas")

    # SCAN DE ACTIVIDAD 15 DÍAS + PREGUNTA PURGA
    elif lower.startswith("!scan"):
        async with message.channel.typing():
            rol_miembro = discord.utils.get(message.guild.roles, name=ROL_MIEMBRO)
            if not rol_miembro:
                await message.channel.send(f"No hay rol '{ROL_MIEMBRO}' we")
                return
            todos = {m.id: m for m in rol_miembro.members if not m.bot}
            actividad = {mid: 0 for mid in todos.keys()}
            hace_15dias = discord.utils.utcnow() - timedelta(days=15)
            for canal in message.guild.text_channels:
                if not canal.permissions_for(message.guild.me).read_message_history:
                    continue
                try:
                    async for msg in canal.history(limit=None, after=hace_15dias):
                        if msg.author.id in actividad:
                            actividad[msg.author.id] += 1
                except Exception as e:
                    log.warning(f"[scan] No pude leer #{canal.name}: {e}")
                    continue
            fantasmas_ids = [mid for mid, count in actividad.items() if count == 0]
            fantasmas_mentions = [todos[mid].mention for mid in fantasmas_ids]
            ULTIMOS_FANTASMAS[message.guild.id] = fantasmas_ids
            PURGA_PENDIENTE[message.guild.id] = False

        if fantasmas_mentions:
            await message.channel.send(
                f"**Tiesos con 0 mensajes en 15d:** {len(fantasmas_mentions)}\n"
                f"{', '.join(fantasmas_mentions[:20])}"
            )
            await message.channel.send("¿Los pateo alv? Usa `!purgaafk confirmar` pa desterrarlos we 😈")
        else:
            await message.channel.send("No hay tiesos we, todos activos 🔥")
            ULTIMOS_FANTASMAS[message.guild.id] = []

    # PURGA AFK CON CONFIRMACIÓN
    elif lower.startswith("!purgaafk"):
        guild_id = message.guild.id
        if guild_id not in ULTIMOS_FANTASMAS or not ULTIMOS_FANTASMAS[guild_id]:
            await message.channel.send("Primero haz un `!scan` we, no tengo a quién patear")
            return

        if lower == "!purgaafk confirmar":
            await message.channel.send(f"😈 Iniciando purga de {len(ULTIMOS_FANTASMAS[guild_id])} tiesos...")
            pateados = 0
            fallos = 0

            for user_id in ULTIMOS_FANTASMAS[guild_id]:
                user = message.guild.get_member(user_id)
                if user and not user.bot:
                    try:
                        await user.kick(reason="Inactividad 15d - Purga automática de Abo")
                        pateados += 1
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        log.warning(f"[purgaafk] No pude patear a {user_id}: {e}")
                        fallos += 1

            await message.channel.send(
                f"✅ Purga terminada: {pateados} pateados, {fallos} fallaron por perms we"
            )
            ULTIMOS_FANTASMAS[guild_id] = []
            PURGA_PENDIENTE[guild_id] = False
        else:
            await message.channel.send(
                f"⚠️ Vas a patear a {len(ULTIMOS_FANTASMAS[guild_id])} usuarios por inactividad.\n"
                "Escribe `!purgaafk confirmar` pa proceder o cancela y ya."
            )

    elif lower.startswith("!say "):
        texto = message.content[5:]
        # MEJORA 6: Borrar el mensaje del comando en servidor (ya lo hacía en DM, faltaba aquí)
        try:
            await message.delete()
        except discord.Forbidden:
            pass
        await message.channel.send(texto)

    elif lower.startswith("!limpia"):
        partes = lower.split()
        # MEJORA 7: +1 para incluir el propio comando en el purge, limitado a 100 mensajes reales
        num = int(partes[1]) + 1 if len(partes) > 1 and partes[1].isdigit() else 6
        if num > 101:
            num = 101
        borrados = await message.channel.purge(limit=num)
        # -1 porque el comando del usuario también se borró
        confirmacion = await message.channel.send(f"🧹 {len(borrados) - 1} mensajes alv")
        await asyncio.sleep(3)
        await confirmacion.delete()

    elif lower.startswith("!addrol"):
        partes = message.content.split()
        if len(partes) < 3 or not message.mentions:
            await message.channel.send("Uso: `!addrol @user1 @user2 NombreDelRol`")
            return
        nombre_rol = " ".join(partes[1 + len(message.mentions):])
        if not nombre_rol:
            await message.channel.send("¿Y el nombre del rol apa? `!addrol @user1 @user2 Miembro`")
            return
        rol = discord.utils.get(message.guild.roles, name=nombre_rol)
        if not rol:
            await message.channel.send(f"❌ No existe el rol `{nombre_rol}` we")
            return
        exitos = []
        fallos = []
        for user in message.mentions:
            try:
                await user.add_roles(rol, reason=f"Rol dado por {message.author}")
                exitos.append(user.name)
            except Exception as e:
                log.warning(f"[addrol] {user.name}: {e}")
                fallos.append(user.name)
        msg = ""
        if exitos:
            msg += f"✅ Rol `{rol.name}` dado a: {', '.join(exitos)}\n"
        if fallos:
            msg += f"❌ No pude dárselo a: {', '.join(fallos)}"
        await message.channel.send(msg)

    elif lower.startswith("!delrol"):
        partes = message.content.split()
        if len(partes) < 3 or not message.mentions:
            await message.channel.send("Uso: `!delrol @user1 @user2 NombreDelRol`")
            return
        nombre_rol = " ".join(partes[1 + len(message.mentions):])
        rol = discord.utils.get(message.guild.roles, name=nombre_rol)
        if not rol:
            await message.channel.send(f"❌ No existe el rol `{nombre_rol}`")
            return
        exitos = []
        fallos = []
        for user in message.mentions:
            try:
                await user.remove_roles(rol, reason=f"Rol quitado por {message.author}")
                exitos.append(user.name)
            except Exception as e:
                log.warning(f"[delrol] {user.name}: {e}")
                fallos.append(user.name)
        msg = ""
        if exitos:
            msg += f"🗑️ Rol `{rol.name}` quitado a: {', '.join(exitos)}\n"
        if fallos:
            msg += f"❌ No pude quitárselo a: {', '.join(fallos)}"
        await message.channel.send(msg)

bot.run(TOKEN)
