import discord
import os
from groq import Groq

TOKEN = os.getenv("TOKEN")
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

def preguntar_ia(prompt):
    try:
        print(f"Llamando Groq con prompt: {prompt[:50]}...") # Log 1
        chat = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "Eres Abo, un bot de Discord empático, moderador. Respondes corto, en español, con calidez. Terminas con 🌹 solo si la persona está triste."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=80,
            temperature=0.7
        )
        print(f"Groq Status: OK") # Log 2
        return chat.choices[0].message.content[:1800]
    except Exception as e:
        print(f"Error Groq DETALLADO: {type(e).__name__}: {e}") # Log 3 clave
        return "Ando procesando bro"
@bot.event
async def on_ready():
    print(f"✅ Abo#9097 online con Groq")

@bot.event
async def on_message(message):
    if message.author == bot.user: # Fix doble mensaje
        return
    
    if bot.user.mentioned_in(message):
        async with message.channel.typing(): # Pa que salga "Abo está escribiendo..."
            respuesta = preguntar_ia(message.content)
        await message.channel.send(respuesta)

bot.run(TOKEN)
