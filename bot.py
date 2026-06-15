import discord
import os
import re
import random
import asyncio
from datetime import timedelta
from groq import Groq

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
TOKEN = os.getenv("TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TU_ID = 1180967503682355220
ROL_MIEMBRO = "MemberLT" # Rol pa scan

groq_client = Groq(api_key=GROQ_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = discord.Client(intents=intents)

# ─────────────────────────────────────────
# PERSONALIDAD ABO
# ─────────────────────────────────────────
SISTEMA_ABO = (
    "Eres Abo, bot de Discord mexicano. "
    "Respondes en máximo 2 oraciones cortas. "
    "Usa humor y jerga: 'we', 'mijo', 'nmms', 'pa'. "
    "Sé sarcástico pero COHERENTE. No digas cosas sin sentido. "
    "PROHIBIDO decir 'no puedo', 'lo siento'. Si no sabes di 'ni idea we'. "
    "No te metas con mamás. No asumas género. No digas 'simio'."
)

async def preguntar_ia(prompt: str) -> str:
    try:
        chat = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SISTEMA_ABO},
                {"role": "user", "content": prompt},
            ],
            max_tokens=150,
            temperature=0.9
        )
        respuesta = chat.choices[0].message.content.strip()
        return respuesta if respuesta else "Ni idea we"
    except:
        return "Me bugueé we"

# ─────────────────────────────────────────
# EVENTOS
# ─────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"[Abo] Online: {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="LatamOS"))

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot: return
    lower = message.content.lower()

    # 1. PERSONALIDAD - SI LA MENCIONAN
    if bot.user.mentioned_in(message):
        texto = re.sub(r"<@!?\d+>", "", message.content).strip()
        if texto.lower() in {"hola", "ola", "wenas", "we", "hi", "q", "que", "hey", "k", "", "abo"}:
            await message.channel.send(random.choice(["Qué onda", "Qué pedo", "Dime we", "Aquí andamos"]))
            return
        async with message.channel.typing():
            respuesta = await preguntar_ia(texto)
        await message.channel.send(respuesta)

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

    # 6. SAY
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

bot.run(TOKEN)
