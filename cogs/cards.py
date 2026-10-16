"""Abo Cards: colección social, sobres, economía, intercambio y mercado."""
from __future__ import annotations

import io
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from core import db

ASSET_DIR = Path(__file__).resolve().parent.parent / "assets" / "cards"
PACK_PRICE = 100
DAILY_BASE = 250

RARITY_META = {
    "Común": (0x95A5A6, 100),
    "Rara": (0x3498DB, 250),
    "Épica": (0x9B59B6, 500),
    "Legendaria": (0xF1C40F, 1000),
}

# El catálogo inicial usa las cartas entregadas por el usuario.
EMOJI_BY_SLUG = {
    "mielabo": ("MIELABO", "1560744239107940422"),
    "abopro": ("ABOPRO", "1560744237333745724"),
    "abo_deluxe": ("ABODELUXE", "1560744235026751629"),
    "reflexiabo": ("REFLEXIABO", "1560744232656838818"),
    "ranabo": ("RANABO", "1560744231046479992"),
    "hatsune_abo": ("HATSUNEABO", "1560744227279732756"),
    "empanizabo": ("EMPANIZABO", "1560744199622492221"),
    "aspirabo": ("ASPIRABO", "1560744183818625114"),
    "asesinabo": ("ASESINABO", "1560744167158579270"),
    "glotonabo": ("GLOTONABO", "1560743883690054234"),
    "sueterabo": ("SUETERABO", "1560743813142679683"),
    "tacosabo": ("TACOSABO", "1560743787309965393"),
    "starabo": ("STARABO", "1560743769433841665"),
    "sopabo": ("SOPABO", "1560743747933704192"),
    "abomaid": ("MAIDABO", "1560743731051630773"),
    "abosaurio": ("ABOSAURIO", "1560743712521199758"),
    "abojama": ("ABOJAMA", "1560743687561027624"),
}

RARITY_EMOJI = {"Común": "⚪", "Rara": "🔵", "Épica": "🟣", "Legendaria": "🟡"}

CATALOG = [
    ("abo_deluxe", "Abo Deluxe", "Legendaria", "abo_deluxe.png", 4, 1000),
    ("abopro", "Abo Pro", "Épica", "abopro.png", 10, 500),
    ("asesinabo", "Asesinabo", "Épica", "asesinabo.png", 10, 500),
    ("aspirabo", "Aspirabo", "Rara", "aspirabo.png", 22, 250),
    ("empanizabo", "Empanizabo", "Rara", "empanizabo.png", 22, 250),
    ("glotonabo", "Glotonabo", "Común", "glotonabo.png", 42, 100),
    ("hatsune_abo", "Hatsune Abo", "Épica", "hatsune_abo.png", 10, 500),
    ("mielabo", "Mielabo", "Rara", "mielabo.png", 22, 250),
    ("ranabo", "Ranabo", "Común", "ranabo.png", 42, 100),
    ("reflexiabo", "Reflexiabo", "Rara", "reflexiabo.png", 22, 250),
    ("sopabo", "Sopabo", "Común", "sopabo.png", 42, 100),
    ("starabo", "Starabo", "Legendaria", "starabo.png", 4, 1000),
    ("sueterabo", "Suéterabo", "Rara", "sueterabo.png", 22, 250),
    ("tacosabo", "Tacosabo", "Común", "tacosabo.png", 42, 100),
    ("abojama", "Abojama", "Común", "abojama.jpg", 42, 100),
    ("abomaid", "Abomaid", "Rara", "abomaid.jpg", 22, 250),
    ("abosaurio", "Abosaurio", "Épica", "abosaurio.jpg", 10, 500),
]


def notice(title: str, description: str, color: int = 0x5865F2) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text="Abo Cards · Colecciona, intercambia y presume")
    return embed


def rarity_color(rarity: str) -> int:
    return RARITY_META.get(rarity, (0x5865F2, 100))[0]


def coins_text(value: int) -> str:
    return f"{value:,}".replace(",", " ")


async def ensure_card_catalog() -> None:
    rows = []
    for slug, name, rarity, image_file, weight, value in CATALOG:
        emoji_name, emoji_id = EMOJI_BY_SLUG.get(slug, ("", ""))
        rows.append({"slug": slug, "name": name, "rarity": rarity, "image_file": image_file,
                     "drop_weight": weight, "base_value": value, "emoji_name": emoji_name, "emoji_id": emoji_id})
    await db.execute(
        """INSERT INTO card_catalog (slug,name,rarity,image_file,drop_weight,base_value,emoji_name,emoji_id)
           SELECT x.slug,x.name,x.rarity,x.image_file,x.drop_weight,x.base_value,x.emoji_name,x.emoji_id
           FROM jsonb_to_recordset($1::jsonb) AS x(
             slug text,name text,rarity text,image_file text,drop_weight int,base_value int,
             emoji_name text,emoji_id text)
           ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name,rarity=EXCLUDED.rarity,
             image_file=EXCLUDED.image_file,drop_weight=EXCLUDED.drop_weight,base_value=EXCLUDED.base_value,
             emoji_name=EXCLUDED.emoji_name,emoji_id=EXCLUDED.emoji_id,active=TRUE""",
        __import__("json").dumps(rows),
    )


def card_emoji(row) -> str:
    if row.get("emoji_name") and row.get("emoji_id"):
        return f"<:{row['emoji_name']}:{row['emoji_id']}>"
    return RARITY_EMOJI.get(row.get("rarity"), "🎴")


async def ensure_wallet(guild_id: int, user_id: int) -> None:
    await db.execute(
        "INSERT INTO card_wallets (guild_id, user_id) VALUES ($1,$2) ON CONFLICT DO NOTHING",
        guild_id, user_id,
    )


async def card_row(slug: str):
    value = slug.strip()
    return await db.fetchrow("SELECT * FROM card_catalog WHERE active=TRUE AND (slug=$1 OR name ILIKE $2)", value.lower(), value)


async def add_card(connection, guild_id: int, user_id: int, slug: str, quantity: int = 1) -> None:
    await connection.execute(
        """INSERT INTO card_inventory (guild_id,user_id,card_slug,quantity)
           VALUES ($1,$2,$3,$4) ON CONFLICT (guild_id,user_id,card_slug) DO UPDATE
           SET quantity=card_inventory.quantity+EXCLUDED.quantity""",
        guild_id, user_id, slug, quantity,
    )


async def choose_cards(connection, amount: int = 3) -> list[str]:
    rows = await connection.fetch("SELECT slug, drop_weight FROM card_catalog WHERE active=TRUE")
    population = [row["slug"] for row in rows]
    weights = [row["drop_weight"] for row in rows]
    return random.choices(population, weights=weights, k=amount)


class CardsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="diario_cartas", description="Reclama tus Abo Coins diarios para comprar sobres")
    @app_commands.guild_only()
    async def diario_cartas(self, interaction: discord.Interaction):
        now = datetime.now(timezone.utc)
        async with db._pool().acquire() as connection:
            async with connection.transaction():
                wallet = await connection.fetchrow(
                    """INSERT INTO card_wallets (guild_id,user_id) VALUES ($1,$2)
                       ON CONFLICT (guild_id,user_id) DO UPDATE SET updated_at=NOW()
                       RETURNING coins, daily_claimed_at, daily_streak""",
                    interaction.guild_id, interaction.user.id,
                )
                last = wallet["daily_claimed_at"]
                if last and last.date() == now.date():
                    return await interaction.response.send_message(
                        embed=notice("Diario ya reclamado ⏳", "Vuelve mañana para recibir más Abo Coins.", 0xFEE75C), ephemeral=True,
                    )
                streak = wallet["daily_streak"] + 1 if last and (now.date() - last.date()) == timedelta(days=1) else 1
                reward = min(DAILY_BASE + (streak - 1) * 25, 500)
                await connection.execute(
                    "UPDATE card_wallets SET coins=coins+$1, daily_claimed_at=$2, daily_streak=$3, updated_at=NOW() WHERE guild_id=$4 AND user_id=$5",
                    reward, now, streak, interaction.guild_id, interaction.user.id,
                )
                balance = wallet["coins"] + reward
        await interaction.response.send_message(
            embed=notice("Recompensa diaria ✨", f"Recibiste **{coins_text(reward)} Abo Coins**.\nRacha: **{streak} días**\nSaldo: **{coins_text(balance)}**", 0x57F287), ephemeral=True,
        )

    @app_commands.command(name="saldo_cartas", description="Muestra tu saldo de Abo Coins")
    @app_commands.guild_only()
    async def saldo_cartas(self, interaction: discord.Interaction):
        await ensure_wallet(interaction.guild_id, interaction.user.id)
        coins = await db.fetchval("SELECT coins FROM card_wallets WHERE guild_id=$1 AND user_id=$2", interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(embed=notice("Tu saldo 💰", f"Tienes **{coins_text(coins)} Abo Coins**.\nUsa `/sobre` para comprar un sobre de 3 cartas."), ephemeral=True)

    @app_commands.command(name="sobre", description="Compra un sobre de 3 cartas aleatorias")
    @app_commands.guild_only()
    async def sobre(self, interaction: discord.Interaction):
        await ensure_wallet(interaction.guild_id, interaction.user.id)
        async with db._pool().acquire() as connection:
            async with connection.transaction():
                wallet = await connection.fetchrow("SELECT coins FROM card_wallets WHERE guild_id=$1 AND user_id=$2 FOR UPDATE", interaction.guild_id, interaction.user.id)
                if wallet["coins"] < PACK_PRICE:
                    return await interaction.response.send_message(embed=notice("No alcanzan las monedas 💸", f"El sobre cuesta **{PACK_PRICE} Abo Coins** y tienes **{wallet['coins']}**.", 0xED4245), ephemeral=True)
                drawn = await choose_cards(connection, 3)
                await connection.execute("UPDATE card_wallets SET coins=coins-$1, updated_at=NOW() WHERE guild_id=$2 AND user_id=$3", PACK_PRICE, interaction.guild_id, interaction.user.id)
                for slug in drawn:
                    await add_card(connection, interaction.guild_id, interaction.user.id, slug)
                rows = await connection.fetch("SELECT slug,name,rarity,emoji_name,emoji_id FROM card_catalog WHERE slug=ANY($1::text[])", drawn)
                by_slug = {row["slug"]: row for row in rows}
                balance = wallet["coins"] - PACK_PRICE
        lines = [f"{card_emoji(by_slug[s])} {by_slug[s]['rarity']} · **{by_slug[s]['name']}**" for s in drawn]
        await interaction.response.send_message(embed=notice("¡Sobre abierto! 🎴", "\n".join(f"• {line}" for line in lines) + f"\n\nSaldo restante: **{coins_text(balance)} Abo Coins**"), ephemeral=True)

    @app_commands.command(name="coleccion", description="Muestra tu colección de cartas")
    @app_commands.guild_only()
    async def coleccion(self, interaction: discord.Interaction, usuario: discord.Member | None = None):
        target = usuario or interaction.user
        rows = await db.fetch(
            """SELECT c.name,c.rarity,c.emoji_name,c.emoji_id,i.quantity,c.base_value FROM card_inventory i JOIN card_catalog c ON c.slug=i.card_slug
               WHERE i.guild_id=$1 AND i.user_id=$2 AND i.quantity>0 ORDER BY c.rarity DESC,c.name""",
            interaction.guild_id, target.id,
        )
        total = sum(row["quantity"] for row in rows)
        value = sum(row["quantity"] * row["base_value"] for row in rows)
        if not rows:
            description = "Aún no tienes cartas. Usa `/sobre` para abrir tu primer sobre."
        else:
            description = "\n".join(f"{card_emoji(row)} **{row['name']}** · {row['rarity']} · ×{row['quantity']}" for row in rows[:25])
            if len(rows) > 25: description += f"\n… y {len(rows)-25} cartas más"
        embed = notice(f"Colección de {target.display_name} 📚", description)
        embed.add_field(name="Cartas únicas", value=str(len(rows)), inline=True)
        embed.add_field(name="Total de cartas", value=str(total), inline=True)
        embed.add_field(name="Valor base", value=f"{coins_text(value)} Abo Coins", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="carta", description="Muestra los detalles de una carta")
    @app_commands.guild_only()
    @app_commands.describe(nombre="Nombre o slug de la carta")
    async def carta(self, interaction: discord.Interaction, nombre: str):
        row = await db.fetchrow("SELECT * FROM card_catalog WHERE active=TRUE AND (slug=$1 OR name ILIKE $2)", nombre.lower(), nombre)
        if not row:
            return await interaction.response.send_message(embed=notice("Carta no encontrada", "Revisa el nombre en `/coleccion` o `/ranking_cartas`.", 0xED4245), ephemeral=True)
        owned = await db.fetchval("SELECT quantity FROM card_inventory WHERE guild_id=$1 AND user_id=$2 AND card_slug=$3", interaction.guild_id, interaction.user.id, row["slug"]) or 0
        embed = notice(f"{card_emoji(row)} {row['name']}", f"Rareza: **{row['rarity']}**\nValor base: **{coins_text(row['base_value'])} Abo Coins**\nTu colección: **×{owned}**", rarity_color(row["rarity"]))
        path = ASSET_DIR / row["image_file"]
        if row.get("image_data"):
            filename = row["image_file"] or f"{row['slug']}.png"
            file = discord.File(io.BytesIO(bytes(row["image_data"])), filename=filename)
            embed.set_image(url=f"attachment://{filename}")
            return await interaction.response.send_message(embed=embed, file=file)
        if path.is_file():
            file = discord.File(path, filename=path.name)
            embed.set_image(url=f"attachment://{path.name}")
            return await interaction.response.send_message(embed=embed, file=file)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="intercambiar_carta", description="Intercambia cartas directamente con otro miembro")
    @app_commands.guild_only()
    @app_commands.describe(usuario="Miembro receptor", ofrezco="Carta que entregas", cantidad_ofrezco="Cantidad que entregas", pido="Carta que recibes", cantidad_pido="Cantidad que recibes")
    async def intercambiar_carta(self, interaction: discord.Interaction, usuario: discord.Member, ofrezco: str, cantidad_ofrezco: int, pido: str, cantidad_pido: int):
        if usuario.bot or usuario.id == interaction.user.id or cantidad_ofrezco < 1 or cantidad_pido < 1:
            return await interaction.response.send_message(embed=notice("Intercambio inválido", "Elige otro miembro y cantidades positivas.", 0xED4245), ephemeral=True)
        offered = await card_row(ofrezco)
        requested = await card_row(pido)
        if not offered or not requested:
            return await interaction.response.send_message(embed=notice("Carta no encontrada", "Usa el nombre exacto de la carta.", 0xED4245), ephemeral=True)
        async with db._pool().acquire() as connection:
            async with connection.transaction():
                a = await connection.fetchval("SELECT quantity FROM card_inventory WHERE guild_id=$1 AND user_id=$2 AND card_slug=$3 FOR UPDATE", interaction.guild_id, interaction.user.id, offered["slug"]) or 0
                b = await connection.fetchval("SELECT quantity FROM card_inventory WHERE guild_id=$1 AND user_id=$2 AND card_slug=$3 FOR UPDATE", interaction.guild_id, usuario.id, requested["slug"]) or 0
                if a < cantidad_ofrezco or b < cantidad_pido:
                    return await interaction.response.send_message(embed=notice("Intercambio rechazado", "Uno de los dos usuarios no tiene suficientes copias.", 0xED4245), ephemeral=True)
                await connection.execute("UPDATE card_inventory SET quantity=quantity-$1 WHERE guild_id=$2 AND user_id=$3 AND card_slug=$4", cantidad_ofrezco, interaction.guild_id, interaction.user.id, offered["slug"])
                await connection.execute("UPDATE card_inventory SET quantity=quantity+$1 WHERE guild_id=$2 AND user_id=$3 AND card_slug=$4", cantidad_ofrezco, interaction.guild_id, usuario.id, offered["slug"])
                await connection.execute("UPDATE card_inventory SET quantity=quantity-$1 WHERE guild_id=$2 AND user_id=$3 AND card_slug=$4", cantidad_pido, interaction.guild_id, usuario.id, requested["slug"])
                await add_card(connection, interaction.guild_id, interaction.user.id, requested["slug"], cantidad_pido)
                await connection.execute("INSERT INTO card_trades (guild_id,sender_id,receiver_id,offered_slug,offered_quantity,requested_slug,requested_quantity) VALUES ($1,$2,$3,$4,$5,$6,$7)", interaction.guild_id, interaction.user.id, usuario.id, offered["slug"], cantidad_ofrezco, requested["slug"], cantidad_pido)
        await interaction.response.send_message(embed=notice("Intercambio completado 🤝", f"{interaction.user.mention} recibió **{cantidad_ofrezco}× {card_emoji(offered)} {offered['name']}** y entregó **{cantidad_pido}× {card_emoji(requested)} {requested['name']}**."), allowed_mentions=discord.AllowedMentions(users=True))

    @app_commands.command(name="mercado_publicar", description="Publica copias de una carta en el mercado")
    @app_commands.guild_only()
    @app_commands.describe(carta="Carta a vender", cantidad="Copias", precio="Precio por copia")
    async def mercado_publicar(self, interaction: discord.Interaction, carta: str, cantidad: int, precio: int):
        row = await card_row(carta)
        if not row or cantidad < 1 or precio < 1:
            return await interaction.response.send_message(embed=notice("Publicación inválida", "Carta, cantidad y precio deben ser válidos.", 0xED4245), ephemeral=True)
        async with db._pool().acquire() as connection:
            async with connection.transaction():
                owned = await connection.fetchval("SELECT quantity FROM card_inventory WHERE guild_id=$1 AND user_id=$2 AND card_slug=$3 FOR UPDATE", interaction.guild_id, interaction.user.id, row["slug"]) or 0
                if owned < cantidad:
                    return await interaction.response.send_message(embed=notice("No tienes suficientes copias", f"Posees **×{owned}** de {row['name']}.", 0xED4245), ephemeral=True)
                await connection.execute("UPDATE card_inventory SET quantity=quantity-$1 WHERE guild_id=$2 AND user_id=$3 AND card_slug=$4", cantidad, interaction.guild_id, interaction.user.id, row["slug"])
                listing = await connection.fetchrow("INSERT INTO card_market_listings (guild_id,seller_id,card_slug,quantity,remaining,price_each) VALUES ($1,$2,$3,$4,$4,$5) RETURNING id", interaction.guild_id, interaction.user.id, row["slug"], cantidad, precio)
        await interaction.response.send_message(embed=notice("Carta publicada 🏪", f"Publicaste **×{cantidad} {card_emoji(row)} {row['name']}** a **{coins_text(precio)} Abo Coins** cada una.\nID de publicación: **#{listing['id']}**"), ephemeral=True)

    @app_commands.command(name="mercado", description="Muestra las cartas disponibles en el mercado")
    @app_commands.guild_only()
    async def mercado(self, interaction: discord.Interaction):
        rows = await db.fetch("""SELECT l.id,c.name,c.rarity,c.emoji_name,c.emoji_id,l.remaining,l.price_each FROM card_market_listings l JOIN card_catalog c ON c.slug=l.card_slug WHERE l.guild_id=$1 AND l.status='active' AND l.remaining>0 ORDER BY l.created_at DESC LIMIT 20""", interaction.guild_id)
        description = "\n".join(f"**#{r['id']}** · {card_emoji(r)} {r['name']} ({r['rarity']}) · ×{r['remaining']} · **{coins_text(r['price_each'])}** c/u" for r in rows) or "El mercado está vacío."
        await interaction.response.send_message(embed=notice("Mercado de Abo Cards 🏪", description + "\n\nCompra con `/mercado_comprar id cantidad`."))

    @app_commands.command(name="mercado_cancelar", description="Retira una publicación propia y recupera las cartas")
    @app_commands.guild_only()
    async def mercado_cancelar(self, interaction: discord.Interaction, publicacion: int):
        async with db._pool().acquire() as connection:
            async with connection.transaction():
                listing = await connection.fetchrow("SELECT * FROM card_market_listings WHERE id=$1 AND guild_id=$2 AND seller_id=$3 AND status='active' FOR UPDATE", publicacion, interaction.guild_id, interaction.user.id)
                if not listing:
                    return await interaction.response.send_message(embed=notice("Publicación no disponible", "Solo puedes retirar tus publicaciones activas.", 0xED4245), ephemeral=True)
                await add_card(connection, interaction.guild_id, interaction.user.id, listing["card_slug"], listing["remaining"])
                await connection.execute("UPDATE card_market_listings SET status='cancelled', remaining=0 WHERE id=$1", publicacion)
                card = await connection.fetchrow("SELECT name,rarity,emoji_name,emoji_id FROM card_catalog WHERE slug=$1", listing["card_slug"])
        await interaction.response.send_message(embed=notice("Publicación retirada ↩️", f"Recuperaste **×{listing['remaining']} {card_emoji(card)} {card['name']}**."), ephemeral=True)

    @app_commands.command(name="mercado_comprar", description="Compra una carta publicada en el mercado")
    @app_commands.guild_only()
    @app_commands.describe(publicacion="ID de publicación", cantidad="Cantidad a comprar")
    async def mercado_comprar(self, interaction: discord.Interaction, publicacion: int, cantidad: int = 1):
        if cantidad < 1:
            return await interaction.response.send_message(embed=notice("Cantidad inválida", "La cantidad debe ser positiva.", 0xED4245), ephemeral=True)
        async with db._pool().acquire() as connection:
            async with connection.transaction():
                listing = await connection.fetchrow("SELECT * FROM card_market_listings WHERE id=$1 AND guild_id=$2 AND status='active' FOR UPDATE", publicacion, interaction.guild_id)
                if not listing or listing["remaining"] < cantidad:
                    return await interaction.response.send_message(embed=notice("Publicación no disponible", "No existe o no quedan suficientes copias.", 0xED4245), ephemeral=True)
                if listing["seller_id"] == interaction.user.id:
                    return await interaction.response.send_message(embed=notice("Compra inválida", "No puedes comprarte tu propia publicación.", 0xED4245), ephemeral=True)
                total = listing["price_each"] * cantidad
                buyer = await connection.fetchrow("SELECT coins FROM card_wallets WHERE guild_id=$1 AND user_id=$2 FOR UPDATE", interaction.guild_id, interaction.user.id)
                if not buyer or buyer["coins"] < total:
                    return await interaction.response.send_message(embed=notice("Saldo insuficiente", f"Necesitas **{coins_text(total)} Abo Coins**.", 0xED4245), ephemeral=True)
                await connection.execute("UPDATE card_wallets SET coins=coins-$1, updated_at=NOW() WHERE guild_id=$2 AND user_id=$3", total, interaction.guild_id, interaction.user.id)
                await connection.execute("INSERT INTO card_wallets (guild_id,user_id) VALUES ($1,$2) ON CONFLICT DO NOTHING", interaction.guild_id, listing["seller_id"])
                await connection.execute("UPDATE card_wallets SET coins=coins+$1, updated_at=NOW() WHERE guild_id=$2 AND user_id=$3", total, interaction.guild_id, listing["seller_id"])
                await add_card(connection, interaction.guild_id, interaction.user.id, listing["card_slug"], cantidad)
                remaining = listing["remaining"] - cantidad
                await connection.execute("UPDATE card_market_listings SET remaining=$1,status=CASE WHEN $1=0 THEN 'sold' ELSE status END WHERE id=$2", remaining, publicacion)
                card = await connection.fetchrow("SELECT name,rarity,emoji_name,emoji_id FROM card_catalog WHERE slug=$1", listing["card_slug"])
        await interaction.response.send_message(embed=notice("Compra completada 🛒", f"Compraste **×{cantidad} {card_emoji(card)} {card['name']}** por **{coins_text(total)} Abo Coins**."), ephemeral=True)

    @app_commands.command(name="ranking_cartas", description="Ranking de coleccionistas por valor de cartas")
    @app_commands.guild_only()
    async def ranking_cartas(self, interaction: discord.Interaction):
        rows = await db.fetch("""SELECT i.user_id,SUM(i.quantity*c.base_value)::BIGINT AS value,SUM(i.quantity)::BIGINT AS total,COUNT(*)::INT AS unique_cards FROM card_inventory i JOIN card_catalog c ON c.slug=i.card_slug WHERE i.guild_id=$1 AND i.quantity>0 GROUP BY i.user_id ORDER BY value DESC,total DESC LIMIT 10""", interaction.guild_id)
        lines = []
        for index, row in enumerate(rows, 1):
            member = interaction.guild.get_member(row["user_id"])
            name = member.display_name if member else f"Usuario {row['user_id']}"
            lines.append(f"**{index}.** {name} · {coins_text(row['value'])} valor · {row['unique_cards']} únicas")
        await interaction.response.send_message(embed=notice("Ranking de coleccionistas 🏆", "\n".join(lines) or "Todavía no hay coleccionistas."))
