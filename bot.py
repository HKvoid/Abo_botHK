import discord
import os
import re
import random
import asyncio
import sqlite3
from datetime import timedelta
from groq import Groq

# ─────────────────────────────────────────
# CONFIG: Si está wea funciona, es un milagro.
# ─────────────────────────────────────────
TOKEN = os.getenv("TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TU_ID = 1180967503682355220
ROL_MIEMBRO = "MemberLT"

# ROLES QUE PUEDEN USAR COMANDOS - PON AQUÍ LOS NOMBRES EXACTOS
ROLES_COMANDOS = ["Admin", "Mod", "Semi Admin", "ViceRoot", "Root", "SemiMod"] # <-- Edita esto we

groq_client = Groq(api_key=GROQ_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = discord.Client(intents=intents)

# ─────────────────────────────────────────
# FUNCIÓN PA CHECAR PERMISOS DE COMANDOS
# ─────────────────────────────────────────
def puede_usar_comandos(member: discord.Member) -> bool:
    """Checa si el user puede usar comandos"""
    if member.id == TU_ID: # Tú siempre puedes we
        return True
    if isinstance(member, discord.User): # Por si es DM
        return False
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
            ORDER BY timestamp DESC LIMIT 10
        ) AND user_id =? AND canal_id =?
    """, (user_id, canal_id, user_id, canal_id))
    db.commit()

def obtener_historial(user_id, canal_id, limite=8):
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
        print(f"[Groq Error] {e}")
        return "Me bugueé we"

# ─────────────────────────────────────────
# EVENTOS
# ─────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"[Abo] Online: {bot.user} | Memoria activa")
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

    # 0. HELP / CMD - TODOS PUEDEN VERLO
    if lower in {"!help", "!cmd"}:
        embed = discord.Embed(
            title="🔥 Comandos de Abo",
            description="Esto es lo que sé hacer mijo",
            color=0x00ff00
        )
        embed.add_field(
            name="💬 Chat con IA",
            value="`@Abo tu pregunta` - Háblame y te respondo con memoria",
            inline=False
        )
        embed.add_field(
            name="🔨 Moderación (Solo staff)",
            value="`!banea @user razón` - Destierra alv\n`!mutea @user 10m` - Silencia por tiempo\n`!explota @user` - Lo banea con estilo",
            inline=False
        )
        embed.add_field(
            name="🧹 Limpieza (Solo staff)",
            value="`!limpia 10` - Borra 10 mensajes\n`!scan` - Busca fantasmas con 0 mensajes",
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
        embed.add_field(
            name="🚨 Emergencia (Solo Root/ViceRoot)",
            value="`!lockdown` - Cierra todos los chats\n`!unlock` - Abre todos los chats",
            inline=False
        )
        embed.set_footer(text="Comandos de moderación solo pa roles autorizados")
        await message.channel.send(embed=embed)
        return

    # 1. PERSONALIDAD - TODOS PUEDEN HABLARLE
    if bot.user in message.mentions:
        texto = re.sub(r"<@!?\d+>", "", message.content).strip()
        if texto.lower() in {"hola", "ola", "wenas", "we", "hi", "q", "que", "hey", "k", "", "abo"}:
            await message.channel.send(random.choice(["Qué onda", "Qué pedo", "Dime we", "Aquí andamos"]))
            return
        async with message.channel.typing():
            respuesta = await preguntar_ia(texto, message.author.id, message.channel.id)
        await message.channel.send(respuesta)

    # A PARTIR DE AQUÍ SON COMANDOS - CHECAR PERMISOS
    if not puede_usar_comandos(message.author):
        if lower.startswith("!"):
            await message.channel.send("No tienes permisos pa usar comandos we 🔒")
        return

    # 2. BANEAR
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

    # 3. MUTEAR
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

    # 4. EXPLOTAR
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

    # 5. SCAN DE ACTIVIDAD
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

    # 6. SAY EN SERVER
    elif lower.startswith("!say "):
        texto = message.content[5:]
        await message.delete()
        await message.channel.send(texto)

    # 7. LIMPIA
    elif lower.startswith("!limpia"):
        partes = lower.split()
        num = int(partes[1]) + 1 if len(partes) > 1 and partes[1].isdigit() else 6
        if num > 101: num = 101
        borrados = await message.channel.purge(limit=num)
        confirmacion = await message.channel.send(f"🧹 {len(borrados)-1} mensajes alv")
        await asyncio.sleep(3)
        await confirmacion.delete()

    # 8. ADD ROL MÚLTIPLES
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
            except:
                fallos.append(user.name)

        msg = ""
        if exitos: msg += f"✅ Rol `{rol.name}` dado a: {', '.join(exitos)}\n"
        if fallos: msg += f"❌ No pude dárselo a: {', '.join(fallos)}"
        await message.channel.send(msg)

    # 9. QUITAR ROL MÚLTIPLES
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

    # 10. BORRAR MEMORIA - ESTE SÍ PUEDEN TODOS
    elif lower.startswith("!olvidame"):
        cursor.execute("DELETE FROM memoria WHERE user_id =? AND canal_id =?",
                      (message.author.id, message.channel.id))
        db.commit()
        await message.channel.send("✅ Ya te olvidé we, borrón y cuenta nueva")

    # 11. LOCKDOWN - CIERRA TODO EL SERVER
    elif lower.startswith("!lockdown"):
        rol_viceroot = discord.utils.get(message.guild.roles, name="ViceRoot")
        tiene_viceroot = rol_viceroot in message.author.roles if rol_viceroot else False

        if message.author.id!= TU_ID and not tiene_viceroot: # Solo tú o ViceRoot
            await message.channel.send("Esto solo lo activa el Root o ViceRoot we 🔒")
            return

        await message.channel.send("⚠️ **INICIANDO PROTOCOLO DE EMERGENCIA...** ⚠️")

        canales_afectados = 0
        mensaje_aviso = "🚨 **El servidor acaba de tener problemas con un ataque, se han deshabilitado los chats hasta que el Root atienda el asunto, porfavor tengan paciencia** 🚨"

        for canal in message.guild.text_channels:
            try:
                # Quita send_messages al @everyone
                overwrite_everyone = canal.overwrites_for(message.guild.default_role)
                overwrite_everyone.send_messages = False
                await canal.set_permissions(message.guild.default_role, overwrite=overwrite_everyone)

                # Quita send_messages a todos los roles menos bots/staff alto
                for rol in message.guild.roles:
                    if rol.name == "@everyone" or rol.is_bot_managed():
                        continue
                    if rol.permissions.administrator: # No tocar admins
                        continue
                    overwrite = canal.overwrites_for(rol)
                    overwrite.send_messages = False
                    await canal.set_permissions(rol, overwrite=overwrite)

                # Manda el aviso solo si puede escribir ahí
                if canal.permissions_for(message.guild.me).send_messages:
                    await canal.send(mensaje_aviso)

                canales_afectados += 1
                await asyncio.sleep(0.5) # Pa no rate limitear a Discord

            except discord.Forbidden:
                continue
            except Exception as e:
                print(f"[Lockdown Error] {canal.name}: {e}")

        await message.channel.send(f"🔒 **LOCKDOWN COMPLETO** | {canales_afectados} canales cerrados. Solo Admins pueden hablar.")

    # 12. UNLOCK - ABRE TODO EL SERVER
    elif lower.startswith("!unlock"):
        rol_viceroot = discord.utils.get(message.guild.roles, name="ViceRoot")
        tiene_viceroot = rol_viceroot in message.author.roles if rol_viceroot else False

        if message.author.id!= TU_ID and not tiene_viceroot: # Solo tú o ViceRoot
            await message.channel.send("Esto solo lo desactiva el Root o ViceRoot we 🔓")
            return

        await message.channel.send("🔓 **Quitando lockdown...**")

        canales_afectados = 0
        mensaje_aviso = "✅ **Servidor restaurado. Ya pueden escribir normal. Disculpen las molestias** ✅"

        for canal in message.guild.text_channels:
            try:
                # Regresa send_messages al @everyone
                overwrite_everyone = canal.overwrites_for(message.guild.default_role)
                overwrite_everyone.send_messages = None # None = hereda del server
                await canal.set_permissions(message.guild.default_role, overwrite=overwrite_everyone)

                # Quita el override de todos los roles pa que hereden normal
                for rol, overwrite in canal.overwrites.items():
                    if isinstance(rol, discord.Role) and not rol.permissions.administrator:
                        overwrite.send_messages = None
                        await canal.set_permissions(rol, overwrite=overwrite)

                if canal.permissions_for(message.guild.me).send_messages:
                    await canal.send(mensaje_aviso)

                canales_afectados += 1
                await asyncio.sleep(0.5)

            except discord.Forbidden:
                continue
            except Exception as e:
                print(f"[Unlock Error] {canal.name}: {e}")

        await message.channel.send(f"🔓 **UNLOCK COMPLETO** | {canales_afectados} canales restaurados.")

bot.run(TOKEN)
