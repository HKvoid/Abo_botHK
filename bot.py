import discord
import requests
import os
from discord.ext import commands

TOKEN = os.getenv("TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

def preguntar_ia(prompt):
    API_URL = "https://api-inference.huggingface.co/models/TinyLlama/TinyLlama-1.1B-Chat-v1.0"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    
    payload = {
        "inputs": f"<|system|>Eres Abo, un bot de Discord empático, además de que eres un moderador que evita que los demás se falten el respeto. Respondes corto, en español, con calidez. Terminas con 🌹 solo si la persona está triste.<|user|>{prompt}<|assistant|>",
        "parameters": {"max_new_tokens": 80, "temperature": 0.7}
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        texto = response.json()[0]['generated_text'].split("<|assistant|>")[-1].strip()
        return texto[:1800]
    except:
        return "Ando procesando bro"

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    if 'discord.gg/' in message.content.lower():
        await message.delete()
        await message.channel.send(f'{message.author.mention} sin spam bro', delete_after=5)
        return

    # Responde cuando lo mencionan o le responden
    if bot.user.mentioned_in(message) or message.reference:
        respuesta = preguntar_ia(message.content)
        await message.reply(f"Abo🌹: {respuesta}")
        return

    await bot.process_commands(message)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, cantidad: int = 5):
    await ctx.channel.purge(limit=cantidad + 1)
    await ctx.send(f"🧹 Borré {cantidad} mensajes", delete_after=3)

@bot.event
async def on_ready():
    print(f'✅ {bot.user} online con IA')

bot.run(TOKEN)