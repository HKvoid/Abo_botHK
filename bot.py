import discord
import openai
import os
import asyncio
from datetime import timedelta

TOKEN = os.getenv("DISCORD_TOKEN")
openai.api_key = os.getenv("GROQ_API_KEY")
openai.api_base = "https://api.groq.com/openai/v1"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = discord.Client(intents=intents)

# ===== CONFIG =====
TU_ID = 1180967503682355220 # Tu ID de Discord
ROL_MIEMBRO = "MemberLT" # Rol pa scan

SISTEMA_ABO = """Eres Abo, bot tóxico de LatamOS. Responde corto, con humor mexicano. 
Usa 'we', 'alch', 'nmms'. Insulta leve pero gracioso. Máximo 2 líneas. Si te piden algo ilegal di 'nmms no we'."""

@bot.event
async def on_ready():
    print(f"Abo online como {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot: return
    lower = message.content.lower()

    # 1. PERSONALIDAD ABO - SI LA MENCIONAN
    if bot.user.mentioned_in(message):
        respuesta = openai.ChatCompletion.create(
            model="llama3-8b-8192",
            messages=[{"role":"system","content":SISTEMA_ABO},
                      {"role":"user","content":message.content}],
            max_tokens=100,
            temperature=0.9
        )
        await message.reply(respuesta.choices[0].message.content)

    # 2. BANEAR
    elif lower.startswith("!banea"):
        if not message.mentions:
            await message.channel.send("Menciona a quién we: `!banea @user razón`")
            return
        user = message.mentions[0]
        razon = message.content.split(" ", 2)[2] if len(message.content.split()) > 2 else "Se pasó de verga"
        try:
            await user.ban(reason=razon)
            await message.channel.send(f"Ya me chingué a {user.name} we. Razón: {razon} 🔨")
        except:
            await message.channel.send("No lo pude banear, tiene más poder que yo o no tengo perms")

    # 3. MUTEAR
    elif lower.startswith("!mutea"):
        if not message.mentions:
            await message.channel.send("Menciona a quién we: `!mutea @user 10m razón`")
            return
        partes = message.content.split()
        user = message.mentions[0]
        tiempo_str = partes[2] if len(partes) > 2 else "10m"
        
        tiempo_seg = 600
        if tiempo_str.endswith("m"): tiempo_seg = int(tiempo_str[:-1]) * 60
        elif tiempo_str.endswith("h"): tiempo_seg = int(tiempo_str[:-1]) * 3600
        elif tiempo_str.endswith("d"): tiempo_seg = int(tiempo_str[:-1]) * 86400
        
        try:
            await user.timeout(timedelta(seconds=tiempo_seg), reason="Muteado por Abo")
            await message.channel.send(f"Silenciado {user.name} por {tiempo_str} we 🤐")
        except:
            await message.channel.send("No lo pude mutear we, revisa mis perms")

    # 4. EXPLOTAR = BAN + MENSAJE ÉPICO
    elif lower.startswith("!explota"):
        if not message.mentions:
            await message.channel.send("¿A quién exploto we? `!explota @user`")
            return
        user = message.mentions[0]
        try:
            await message.channel.send(f"💣 ALV {user.mention} EXPLOTÓ 💣\n*boom*")
            await asyncio.sleep(2)
            await user.ban(reason=f"Explotado por {message.author}")
            await message.channel.send(f"Quedaron los puros pedazos de {user.name} we")
        except:
            await message.channel.send("El wey trae chaleco antibombas, no lo pude explotar")

    # 5. SCAN DE ACTIVIDAD
    elif lower.startswith("!scan"):
        await message.channel.send("Escaneando fantasmas... ⏳")
        rol_miembro = discord.utils.get(message.guild.roles, name=ROL_MIEMBRO)
        if not rol_miembro:
            await message.channel.send("No hay rol 'Miembro' we")
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
        cantidad = message.content.split()
        num = int(cantidad[1]) + 1 if len(cantidad) > 1 and cantidad[1].isdigit() else 6
        if num > 101: num = 101
        eliminados = await message.channel.purge(limit=num)
        await message.channel.send(f"Limpié {len(eliminados)-1} mensajes we 🧹", delete_after=3)

    # 8. ADD ROL
    elif lower.startswith("!addrol"):
        if not message.mentions or len(message.content.split()) < 3:
            await message.channel.send("Uso: `!addrol @user NombreDelRol`")
            return
        user = message.mentions[0]
        nombre_rol = message.content.split(" ", 2)[2]
        rol = discord.utils.get(message.guild.roles, name=nombre_rol)
        if not rol:
            await message.channel.send("No existe ese rol we")
            return
        try:
            await user.add_roles(rol)
            await message.channel.send(f"Le di rol {rol.name} a {user.name} we ✅")
        except:
            await message.channel.send("No le pude dar rol, estoy abajo de ese rol")

    # 9. QUITAR ROL
    elif lower.startswith("!delrol"):
        if not message.mentions or len(message.content.split()) < 3:
            await message.channel.send("Uso: `!delrol @user NombreDelRol`")
            return
        user = message.mentions[0]
        nombre_rol = message.content.split(" ", 2)[2]
        rol = discord.utils.get(message.guild.roles, name=nombre_rol)
        if not rol:
            await message.channel.send("No existe ese rol we")
            return
        try:
            await user.remove_roles(rol)
            await message.channel.send(f"Le quité rol {rol.name} a {user.name} we ❌")
        except:
            await message.channel.send("No le pude quitar rol we")

bot.run(TOKEN)
