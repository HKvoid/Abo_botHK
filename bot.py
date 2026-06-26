import discord
import os
import re
import random
import asyncio
import sqlite3
from datetime import timedelta
from groq import Groq

# ─────────────────────────────────────────
# CONFIG - METE TUS 3 KEYS AQUÍ
# ─────────────────────────────────────────
TOKEN = os.getenv("TOKEN")
GROQ_KEYS = [
    os.getenv("GROQ_KEY1"), # Key principal
    os.getenv("GROQ_KEY2"), # Key secundaria
    os.getenv("GROQ_KEY3"), # Key de respaldo
]
TU_ID = 1180967503682355220
ROL_MIEMBRO = "MemberLT"
ROLES_COMANDOS = ["Admin", "Mod", "Semi Admin", "ViceRoot", "Root"]

# Sistema de rotación
key_actual = 0
groq_clients = [Groq(api_key=k) for k in GROQ_KEYS if k] # Filtra las None por si no pusiste las 3

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = discord.Client(intents=intents)

# ─────────────────────────────────────────
# FUNCIÓN PA CHECAR PERMISOS DE COMANDOS
# ─────────────────────────────────────────
def puede_usar_comandos(member: discord.Member) -> bool:
    if member.id == TU_ID: return True
    if isinstance(member, discord.User): return False
    return any(rol.name in ROLES_COMANDOS for rol in member.roles)

# ─────────────────────────────────────────
# MEMORIA CON SQLITE
# ─────────────────────────────────────────
db = sqlite3.connect("abo_memoria.db")
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
            ORDER BY timestamp DESC LIMIT 100
        ) AND user_id =? AND canal_id =?
    """, (user_id, canal_id, user_id, canal_id))
    db.commit()

def obtener_historial(user_id, canal_id, limite=20):
    cursor.execute("""
        SELECT rol, contenido FROM memoria
        WHERE user_id =? AND canal_id =?
        ORDER BY timestamp DESC LIMIT?
    """, (user_id, canal_id, limite))
    historial = cursor.fetchall()
    return list(reversed(historial))

# ─────────────────────────────────────────
# PERSONALIDAD ABO + ROTACIÓN DE KEYS
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
    global key_actual

    for intento_key in range(len(groq_clients)):
        try:
            client = groq_clients[key_actual]
            historial = obtener_historial(user_id, canal_id)
            mensajes = [{"role": "system", "content": SISTEMA_ABO}]

            for rol, contenido in historial:
                mensajes.append({"role": rol, "content": contenido})

            mensajes.append({"role": "user", "content": prompt})

            chat = client.chat.completions.create(
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
            error_str = str(e).lower()
            print(f"[Groq Error Key {key_actual+1}] {e}")

            if "rate_limit" in error_str or "429" in error_str or "tokens per day" in error_str:
                key_actual = (key_actual + 1) % len(groq_clients)
                print(f"[Abo] Key agotada. Cambiando a Key {key_actual+1}")

                if intento_key == len(groq_clients) - 1:
                    return "Se me acabaron todas las vidas we, vuelve a las 6 PM 💀"
                continue
            else:
                return "Me bugueé we"

    return "Me bugueé we"

# ─────────────────────────────────────────
# EVENTOS
# ─────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"[Abo] Online: {bot.user} | {len(groq_clients)} keys cargadas")
    print(f"[Abo] Roles con comandos: {', '.join(ROLES_COMANDOS)}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="LatamOS"))

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot: return
    lower = message.content.lower()

    # ── COMANDO SAY POR DM SOLO PA TI ───────────────────────────────
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
                if canal_obj: break

            if canal_obj:
                try:
                    await canal_obj.send(texto)
                    await message.channel.send(f"✅ Enviado a #{canal_obj.name} en **{server_obj.name}**")
                except discord.Forbidden:
                    await message.channel.send("❌ No tengo permisos pa escribir ahí we")
            else:
                await message.channel.send(f"❌ No encontré el canal `{canal_nombre}`")
            return
        return

    # 0. HELP / CMD
    if lower in {"!help", "!cmd"}:
        embed = discord.Embed(
            title="🔥 Comandos de Abo",
            description="Esto es lo que sé hacer mijo",
            color=0x00ff00
        )
        embed.add_field(name="💬 Chat con IA", value="`@Abo tu pregunta` - Háblame y te respondo\n`@Abo dile a @user: mensaje` - Le paso tu recado", inline=False)
        embed.add_field(name="🔨 Moderación (Solo staff)", value="`!banea @user razón`\n`!mutea @user 10m`\n`!explota @user`", inline=False)
        embed.add_field(name="🧹 Limpieza (Solo staff)", value="`!limpia 10`\n`!scan`", inline=False)
        embed.add_field(name="👥 Roles (Solo staff)", value="`!addrol @user1 @user2 Rol`\n`!delrol @user1 @user2 Rol`", inline=False)
        embed.add_field(name="🧠 Memoria", value="`!olvidame` - Borro lo que recuerdo de ti", inline=False)
        embed.add_field(name="💬 Otros (Solo staff)", value="`!say texto`", inline=False)
        embed.set_footer(text="Comandos de moderación solo pa roles autorizados")
        await message.channel.send(embed=embed)
        return

    # 1. PERSONALIDAD
    if bot.user in message.mentions:
        texto = re.sub(r"<@!?\d+>", "", message.content).strip()

        contexto_extra = ""
        if message.reference and message.reference.message_id:
            try:
                msg_ref = await message.channel.fetch_message(message.reference.message_id)
                contexto_extra = f"[Respondiendo a {msg_ref.author.name}: {msg_ref.content[:80]}]\n"
            except: pass

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
            respuesta = await preguntar_ia(contexto_extra + texto, message.author.id, message.channel.id)

        respuesta_safe = respuesta.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
        await message.channel.send(respuesta_safe, allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))

    if not puede_usar_comandos(message.author):
        if lower.startswith("!"):
            await message.channel.send("No tienes permisos pa usar comandos we 🔒")
        return

    #...resto de comandos igual que antes...
    elif lower.startswith("!banea"):
        if not message.mentions:
            await message.channel.send("Menciona a quién we: `!banea @user razón`")
            return
        user = message.mentions[0]
        razon = message.content.split(" ", 2)[2] if len(message.content.split()) > 2 else "Se pasó de verga"
        try:
            await user.ban(reason=razon)
            await message.channel.send(f"🔨 {user.name} fue desterrado alv. Razón: {razon}")
        except:
            await message.channel.send("No lo pude banear we, revisa mis perms")

    elif lower.startswith("!mutea"):
        if not message.mentions:
            await message.channel.send("Menciona a quién we: `!mutea @user 10m`")
            return
        partes = message.content.split()
        user = message.mentions[0]
        tiempo_str = partes[2] if len(partes) > 2 else "10m"
        tiempo_seg = 600
        if tiempo_str.endswith("m"): tiempo_seg = int(tiempo_str[:-1]) * 60
        elif tiempo_str.endswith("h"): tiempo_seg = int(tiempo_str[:-1]) * 3600
        elif tiempo_str.endswith("d"): tiempo_seg = int(tiempo_str[:-1]) * 86400
        try:
            await user.timeout(timedelta(seconds=tiempo_seg))
            await message.channel.send(f"🤐 Silenciado {user.name} por {tiempo_str}")
        except:
            await message.channel.send("No lo pude mutear we")

    elif lower.startswith("!explota"):
        if not message.mentions:
            await message.channel.send("¿A quién exploto we? `!explota @user`")
            return
        user = message.mentions[0]
        try:
            await message.channel.send(f"💣 ALV {user.mention} EXPLOTÓ 💣")
            await asyncio.sleep(1)
            await user.ban(reason=f"Explotado por {message.author}")
            await message.channel.send(f"Quedaron los puros pedazos de {user.name} we")
        except:
            await message.channel.send("El wey trae chaleco antibombas")

    elif lower.startswith("!scan"):
        await message.channel.send("Escaneando fantasmas... ⏳")
        rol_miembro = discord.utils.get(message.guild.roles, name=ROL_MIEMBRO)
        if not rol_miembro:
            await message.channel.send(f"No hay rol '{ROL_MIEMBRO}' we")
            return
        todos = {m.id: m for m in rol_miembro.members if not m.bot}
        actividad = {mid: 0 for mid in todos.keys()}
        hace_30dias = discord.utils.utcnow() - timedelta(days=30)
        for canal in message.guild.text_channels:
            if not canal.permissions_for(message.guild.me).read_message_history: continue
            try:
                async for msg in canal.history(limit=None, after=hace_30dias):
                    if msg.author.id in actividad: actividad[msg.author.id] += 1
            except: continue
        fantasmas = [todos[mid].mention for mid, count in actividad.items() if count == 0]
        if fantasmas:
            await message.channel.send(f"**👻 FANTASMAS 0 mensajes en 30d:** {len(fantasmas)}\n{', '.join(fantasmas[:20])}")
        else:
            await message.channel.send("No hay fantasmas we, todos activos 🔥")

    elif lower.startswith("!say "):
        texto = message.content[5:]
        await message.delete()
        await message.channel.send(texto)

    elif lower.startswith("!limpia"):
        partes = lower.split()
        num = int(partes[1]) + 1 if len(partes) > 1 and partes[1].isdigit() else 6
        if num > 101: num = 101
        borrados = await message.channel.purge(limit=num)
        confirmacion = await message.channel.send(f"🧹 {len(borrados)-1} mensajes alv")
        await asyncio.sleep(3)
        await confirmacion.delete()

    elif lower.startswith("!addrol"):
        partes = message.content.split()
        if len(partes) < 3 or not message.mentions:
            await message.channel.send("Uso: `!addrol @user1 @user2 NombreDelRol`")
            return
        nombre_rol = " ".join(partes[1 + len(message.mentions):])
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
            except:
                fallos.append(user.name)
        msg = ""
        if exitos: msg += f"✅ Rol `{rol.name}` dado a: {', '.join(exitos)}\n"
        if fallos: msg += f"❌ No pude dárselo a: {', '.join(fallos)}"
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
            except:
                fallos.append(user.name)
        msg = ""
        if exitos: msg += f"🗑️ Rol `{rol.name}` quitado a: {', '.join(exitos)}\n"
        if fallos: msg += f"❌ No pude quitárselo a: {', '.join(fallos)}"
        await message.channel.send(msg)

    elif lower.startswith("!olvidame"):
        cursor.execute("DELETE FROM memoria WHERE user_id =? AND canal_id =?",
                      (message.author.id, message.channel.id))
        db.commit()
        await message.channel.send("✅ Ya te olvidé we, borrón y cuenta nueva")

bot.run(TOKEN)
