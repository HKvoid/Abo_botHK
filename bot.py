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
        chat = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "Eres Abo, un bot de Discord empático, también eres un moderador del servidor, tu trabajo es evitar que los demás se falten el respeto. Responde en 1 línea máximo, casual, en español latino. Usa 'simio/a' solo 1 vez. Solo pon 🌹 si detectas tristeza. Prohibido repetir palabras o frases."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=60, # Menos tokens = menos chance de repetir
            temperature=0.3, # Más bajo = más serio, menos loro
            top_p=0.9,
            stop=["¿En qué","Hola","simio simio"] # Lo corta si intenta repetir
        )
        respuesta = chat.choices[0].message.content.strip()
        
        # Mata oraciones duplicadas aunque estén pegadas
        oraciones = respuesta.replace('?','?|').replace('.','.|').split('|')
        oraciones_unicas = []
        for o in oraciones:
            o = o.strip()
            if o and o not in oraciones_unicas:
                oraciones_unicas.append(o)
        
        respuesta = ' '.join(oraciones_unicas)
        return respuesta[:1800]
        
    except Exception as e:
        print(f"Error Groq DETALLADO: {type(e).__name__}: {e}")
        return "Neuronas muertas❌"

@bot.event
async def on_message(message):
    if message.author == bot.user: # Fix doble mensaje
        return
    
    if bot.user.mentioned_in(message):
        async with message.channel.typing(): # Pa que salga "Abo está escribiendo..."
            respuesta = preguntar_ia(message.content)
        await message.channel.send(respuesta)

bot.run(TOKEN)
