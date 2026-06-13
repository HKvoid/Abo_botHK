import discord
import os
import re
import random
import asyncio
from datetime import timezone
from groq import Groq

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
TOKEN = os.getenv("TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TU_ID = 1180967503682355220 # <-- ID

CANAL_VERIFICACION = "verificación"
ROL_VERIFICADO = "Miembro"

# ─────────────────────────────────────────
# CLIENTE
# ─────────────────────────────────────────
groq_client = Groq(api_key=GROQ_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = discord.Client(intents=intents)

# ─────────────────────────────────────────
# LISTAS DE RESPUESTAS
# ─────────────────────────────────────────
FALLBACKS_GENERALES = [
    "¿Me hablaste o fue el viento?",
    "Error 404: Cerebro no encontrado",
    "Procesando... nah mentira, ni idea",
    "Eso qué, ¿comida?",
    "Simón que sí... ah no, no entendí",
    "Me dio amnesia temporal",
    "Pregúntale a Google, yo toy ocupado",
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
    "Eres Abo, bot de Discord mexicano. "
    "Respondes en máximo 2 oraciones cortas. "
    "Usa humor y jerga: 'we', 'mijo', 'nmms', 'pa'. "
    "Sé sarcástico pero COHERENTE. No digas cosas sin sentido. "
    "PROHIBIDO decir 'no puedo', 'lo siento'. Si no sabes di 'ni idea we'. "
    "No te metas con mamás. No asumas género. No digas 'simio'."
)

SISTEMA_BIENVENIDA = (
    "Eres Abo. Dale bienvenida sarcástica pero chida a alguien nuevo, 1 oración. "
    "Dile que se presente en este canal pa darle acceso. Con humor mexicano."
)

SISTEMA_VERIFICADO = (
    "Eres Abo. Alguien acaba de presentarse y lo verificaste. Dale bienvenida al server, 1 oración. "
    "Sé sarcástico pero buena onda. Con jerga mexicana."
)

async def preguntar_ia(prompt: str, sistema: str = SISTEMA_BASE, fallback_lista: list[str] = FALLBACKS_GENERALES, fallback_clave: str = "general", max_tokens: int = 150) -> str:
    try:
        chat = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": sistema},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.9,
            frequency_penalty=1.2,
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
# EVENTOS
# ─────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"[Abo] Vivo y coleando: {bot.user} | Servidores: {len(bot.guilds)}")
    estados = [
        "las verificaciones",
        "que se presenten",
        "la puerta del server",
        "quién entra y quién no"
    ]
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=random.choice(estados)))

@bot.event
async def on_member_join(member: discord.Member):
    canal = discord.utils.get(member.guild.text_channels, name=CANAL_VERIFICACION)
    if not canal:
        print(f"[Abo] No encontré el canal #{CANAL_VERIFICACION}. Crea uno we")
        return

    bienvenida = await preguntar_ia(
        f"Saluda a {member.display_name} que acaba de entrar y dile que se presente",
        sistema=SISTEMA_BIENVENIDA,
        fallback_lista=["Preséntate pa darte acceso we", "¿Quién chingados eres? Preséntate", "Nuevo detectado. Di tu nombre o lárgate"],
        fallback_clave="bienvenida",
        max_tokens=50
    )

    # Embed de verificación CON FORMATO INCLUIDO
    embed = discord.Embed(
        title="🔒 Verificación de LatamOS",
        description=f"""{member.mention} {bienvenida}

**─── ✦ Copia y llena esto ✦ ───**
👤 **Nombre:** 
🎂 **Edad:** 
🌎 **País:** 
🎮 **Juegos favoritos:** 
🎵 **Música favorita:** 
😄 **Hobbies:** 
💬 **Sobre mí:** 

**─── ✦ Bienvenido/a ✦ ───**""",
        color=0xFF4500
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="Sin presentación no hay acceso | Powered by Abo")
    await canal.send(embed=embed)

@bot.event
async def on_message(message: discord.Message):
    # ── COMANDOS DESDE DM SOLO PA TI ───────────────────────────────
    if isinstance(message.channel, discord.DMChannel) and message.author.id == TU_ID:
        if message.content.startswith("say "):
            partes = message.content.split(" ", 2)
            if len(partes) < 3:
                await message.channel.send("Uso: `say general tu mensaje` we")
                return

            canal_nombre = partes[1].replace("#", "")
            texto = partes[2]

            canal_obj = None
            server_obj = None
            for guild in bot.guilds:
                canal_obj = discord.utils.get(guild.text_channels, name=canal_nombre)
                if canal_obj:
                    server_obj = guild
                    break

            if canal_obj:
                try:
                    await canal_obj.send(texto)
                    await message.channel.send(f"✅ Enviado a #{canal_obj.name} en **{server_obj.name}**")
                except discord.Forbidden:
                    await message.channel.send("❌ No tengo permisos pa escribir ahí")
            else:
                await message.channel.send(f"❌ No encontré el canal `{canal_nombre}`")
            return

        if message.content.lower() == "canales":
            lista = []
            for guild in bot.guilds:
                for canal in guild.text_channels:
                    lista.append(f"`{canal.name}` → {guild.name}")
            if lista:
                texto = "**Canales disponibles:**\n" + "\n".join(lista[:25])
                await message.channel.send(texto)
            else:
                await message.channel.send("No estoy en ningún server we")
            return

    # ── IGNORA BOTS Y DUPLICADOS ──────────────────────────────────
    if message.author.bot or message.author == bot.user:
        return

    # ── SISTEMA DE VERIFICACIÓN ───────────────────────────────────
    if message.channel.name == CANAL_VERIFICACION and not message.author.guild_permissions.administrator:
        rol_verificado = discord.utils.get(message.guild.roles, name=ROL_VERIFICADO)

        if rol_verificado in message.author.roles:
            pass
        else:
            if len(message.content.strip()) > 10:
                if rol_verificado:
                    try:
                        await message.author.add_roles(rol_verificado, reason="Verificación completada")

                        aprobado = await preguntar_ia(
                            f"{message.author.display_name} se presentó diciendo: {message.content}",
                            sistema=SISTEMA_VERIFICADO,
                            fallback_lista=[
                                "Ya estás dentro mijo, no la cagues",
                                "Verificado. Bienvenido al desmadre",
                                "Listo, ya eres parte de la banda"
                            ],
                            fallback_clave="verificado",
                            max_tokens=50
                        )

                        embed = discord.Embed(
                            title="✅ Verificado",
                            description=f"{message.author.mention} {aprobado}",
                            color=0x00FF00
                        )
                        embed.set_footer(text=f"Miembro #{len(message.guild.members)} | Ya tienes acceso al server")
                        await message.channel.send(embed=embed)

                    except discord.Forbidden:
                        await message.channel.send("❌ No tengo permisos pa darte el rol. Habla con un admin")
                else:
                    await message.channel.send(f"❌ No encontré el rol `{ROL_VERIFICADO}`. Créalo we")
            else:
                await message.add_reaction("❌")
                await message.channel.send(f"{message.author.mention} eso no es presentación. Mínimo 10 letras pa", delete_after=5)
            return

    # ── COMANDOS DEL ADMIN ──────────────────────────────────────────
    if message.author.id == TU_ID:
        lower = message.content.lower()

        if lower.startswith("!banea"):
            user_id = None
            if message.mentions:
                user_id = message.mentions[0].id
            else:
                partes = message.content.split()
                if len(partes) > 1 and partes[1].isdigit():
                    user_id = int(partes[1])
            if user_id:
                try:
                    user = await bot.fetch_user(user_id)
                    await message.guild.ban(user, reason="[Abo] Orden del patrón")
                    frases_ban = [
                        f"🔨 {user.name} fue desterrado alv. F",
                        f"💥 {user.name} baneado. Ya no lo verás ni en tus sueños",
                        f"🚀 {user.name} se fue a conocer a su creador"
                    ]
                    await message.channel.send(random.choice(frases_ban))
                except discord.Forbidden:
                    await message.channel.send("Quiero banear pero Discord dice que no soy tu papá")
                except discord.NotFound:
                    await message.channel.send("Ese we ni existe, ¿a quién quieres banear?")
            else:
                await message.channel.send("Uso: `!banea @usuario` we, no adivino")
            return

        if lower.startswith("!desbanea"):
            user_id = None
            if message.mentions:
                user_id = message.mentions[0].id
            else:
                partes = message.content.split()
                if len(partes) > 1 and partes[1].isdigit():
                    user_id = int(partes[1])
            if user_id:
                try:
                    async for ban_entry in message.guild.bans():
                        if ban_entry.user.id == user_id:
                            await message.guild.unban(ban_entry.user, reason="[Abo] Perdón del patrón")
                            await message.channel.send(f"✅ {ban_entry.user.name} desbaneado. A ver si ya se porta bien")
                            return
                    await message.channel.send("Ese we ni está baneado, ¿de qué hablas?")
                except discord.Forbidden:
                    await message.channel.send("No me dejan desbanear, llora pues")
            else:
                await message.channel.send("Uso: `!desbanea @usuario` o ID, no soy adivino")
            return

        if lower.startswith("!limpia"):
            partes = lower.split()
            n = 5
            if len(partes) > 1 and partes[1].isdigit():
                n = min(int(partes[1]), 100)
            borrados = await message.channel.purge(limit=n + 1)
            frases_limpia = [
                f"🧹 {len(borrados)-1} mensajes alv. De nada",
                f"🗑️ Limpieza express: {len(borrados)-1} mensajes borrados",
                f"✨ {len(borrados)-1} mensajes menos. El chat respira"
            ]
            confirmacion = await message.channel.send(random.choice(frases_limpia))
            await asyncio.sleep(4)
            await confirmacion.delete()
            return

        if lower.startswith("!verificar") and message.mentions:
            target = message.mentions[0]
            rol_verificado = discord.utils.get(message.guild.roles, name=ROL_VERIFICADO)
            if rol_verificado:
                try:
                    await target.add_roles(rol_verificado, reason="Verificación manual del admin")
                    await message.channel.send(f"✅ {target.mention} verificado manualmente. Ya tiene acceso")
                except discord.Forbidden:
                    await message.channel.send("❌ No tengo permisos pa dar roles")
            else:
                await message.channel.send(f"❌ No encontré el rol `{ROL_VERIFICADO}`")
            return

        if lower.startswith("!addrolall"):
            partes = message.content.split(" ", 1)
            if len(partes) < 2:
                await message.channel.send("Uso: `!addrolall NombreDelRol` we")
                return

            nombre_rol = partes[1]
            rol = discord.utils.get(message.guild.roles, name=nombre_rol)
            if not rol:
                await message.channel.send(f"❌ No existe el rol `{nombre_rol}`")
                return

            await message.channel.send(f"⏳ Dándole rol `{rol.name}` a todos... Esto puede tardar")
            contador = 0
            fallos = 0

            async with message.channel.typing():
                for miembro in message.guild.members:
                    if rol not in miembro.roles and not miembro.bot:
                        try:
                            await miembro.add_roles(rol, reason=f"Rol masivo a todos por {message.author.name}")
                            contador += 1
                            await asyncio.sleep(1)
                        except:
                            fallos += 1

            await message.channel.send(f"✅ Listo. Rol `{rol.name}` dado a {contador} usuarios. Fallos: {fallos}")
            return

        if lower.startswith("!addrol") or lower.startswith("!darrol"):
            partes = message.content.split()
            if len(partes) < 3 or not message.mentions:
                await message.channel.send("Uso: `!addrol @user1 @user2 @user3 NombreDelRol` we")
                return

            nombre_rol = " ".join(partes[1 + len(message.mentions):])
            if not nombre_rol:
                await message.channel.send("¿Y el nombre del rol apa? `!addrol @user1 @user2 Miembro`")
                return

            rol = discord.utils.get(message.guild.roles, name=nombre_rol)
            if not rol:
                await message.channel.send(f"❌ No existe el rol `{nombre_rol}`. Checa que esté bien escrito")
                return

            exitos = []
            fallos = []

            for user in message.mentions:
                try:
                    await user.add_roles(rol, reason=f"Rol masivo por {message.author.name}")
                    exitos.append(user.mention)
                except discord.Forbidden:
                    fallos.append(user.mention)
                except:
                    fallos.append(user.mention)

            if exitos:
                await message.channel.send(f"✅ Rol `{rol.name}` dado a: {', '.join(exitos)}")
            if fallos:
                await message.channel.send(f"❌ No pude dárselo a: {', '.join(fallos)}. Revisa mis permisos")
            return

        if lower.startswith("!delrol") or lower.startswith("!quitarrol"):
            partes = message.content.split()
            if len(partes) < 3 or not message.mentions:
                await message.channel.send("Uso: `!delrol @user1 @user2 @user3 NombreDelRol` we")
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
                    await user.remove_roles(rol, reason=f"Rol quitado por {message.author.name}")
                    exitos.append(user.mention)
                except:
                    fallos.append(user.mention)

            if exitos:
                await message.channel.send(f"🗑️ Rol `{rol.name}` quitado a: {', '.join(exitos)}")
            if fallos:
                await message.channel.send(f"❌ No pude quitárselo a: {', '.join(fallos)}")
            return

    # ── MENCIÓN DIRECTA ──────────────────────────────────────────────
    if bot.user.mentioned_in(message):
        texto = re.sub(r"<@!?\d+>", "", message.content).strip()
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
            await message.channel.send(random.choice(saludos_respuesta))
            return
        async with message.channel.typing():
            respuesta = await preguntar_ia(texto, max_tokens=150)
        await message.channel.send(respuesta)

# ─────────────────────────────────────────
# ARRANQUE
# ─────────────────────────────────────────
bot.run(TOKEN)
