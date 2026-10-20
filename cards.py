"""Abo Cards: colección social, sobres, economía, intercambio y mercado."""
from __future__ import annotations

import io
import json
import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from core import db

ASSET_DIR = Path(__file__).resolve().parent.parent / "assets" / "cards"
PACK_PRICE = 100
DAILY_BASE = 250
PITY_RARE_LIMIT = 5
PITY_EPIC_LIMIT = 15
XP_PER_PACK = 100
XP_PER_DAILY = 50

DEFAULT_CARD_MESSAGES = {
    "pack_opened": ("¡Sobre abierto! 🎴", "{cards}\n\nSaldo restante: **{balance} Abo Coins**", 0x5865F2),
    "level_up": ("¡Subiste de nivel! ✨", "Ahora eres nivel **{level}** y tienes **{xp} XP**.", 0x57F287),
    "pity_rare": ("Protección de suerte 🔵", "Tu próximo sobre garantiza al menos una carta **Rara**.", 0x3498DB),
    "pity_epic": ("Protección de suerte 🟣", "Tu próximo sobre garantiza al menos una carta **Épica**.", 0x9B59B6),
    "set_complete": ("¡Set completado! 🏆", "Completaste **{set_name}** y recibiste **{reward} Abo Coins**.", 0xF1C40F),
}

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


def character_stats_text(row) -> str:
    stats = row.get("stats") or {}
    if isinstance(stats, str):
        try:
            stats = __import__("json").loads(stats)
        except Exception:
            stats = {}
    if not isinstance(stats, dict):
        return ""
    return "\n".join(f"**{str(key)[:80]}:** {str(value)[:300]}" for key, value in stats.items())


COMBAT_STAT_KEYS = {
    "HP", "ATK", "DEF", "Speed", "Clase", "Rol", "Tipo de daño",
    "Habilidad", "Descripción de habilidad", "Daño de habilidad",
    "Tipo de daño de habilidad", "Estado de habilidad",
    "Duración de efecto de habilidad", "Probabilidad de efecto de habilidad",
    "Habilidad 2", "Descripción de habilidad 2", "Daño de habilidad 2",
    "Tipo de daño de habilidad 2", "Estado de habilidad 2",
    "Duración de efecto de habilidad 2", "Probabilidad de efecto de habilidad 2",
    "Habilidad 3", "Descripción de habilidad 3", "Daño de habilidad 3",
    "Tipo de daño de habilidad 3", "Estado de habilidad 3",
    "Duración de efecto de habilidad 3", "Probabilidad de efecto de habilidad 3",
    "Pasiva", "Descripción de pasiva", "Daño de pasiva",
    "Tipo de daño de pasiva", "Estado de pasiva",
    "Duración de efecto de pasiva", "Probabilidad de efecto de pasiva",
}


def _combat_embed_fields(row):
    """Devuelve los campos de combate con el formato visual de la ficha."""
    stats = row.get("stats") or {}
    if isinstance(stats, str):
        try:
            stats = __import__("json").loads(stats)
        except Exception:
            stats = {}
    if not isinstance(stats, dict):
        stats = {}

    def value(key, fallback="—"):
        raw = str(stats.get(key, "")).strip()
        return raw[:300] if raw else fallback

    ABILITY_ICONS = ["✨", "💫", "🌀"]
    EFFECT_ICONS = {
        "Quemadura": "🔥", "Veneno": "☠️", "Aturdimiento": "⚡",
        "Escudo": "🛡️", "Regeneración": "💚", "Silencio": "🔇",
        "Debilitado": "⬇️", "Lento": "🐢",
    }
    TYPE_ICONS = {"Físico": "💢", "Mágico": "✨", "Verdadero": "⚡", "Porcentual": "📊"}

    fields = []

    # ── Combate: stats base en una sola fila compacta ──────────────────────────
    combat_values = (("❤️", "HP"), ("⚔️", "ATK"), ("🛡️", "DEF"), ("⚡", "Speed"))
    has_combat = any(str(stats.get(key, "")).strip() for _, key in combat_values)
    if has_combat:
        stat_line = "  ".join(
            f"{emoji} **{value(key)}**" for emoji, key in combat_values
            if str(stats.get(key, "")).strip()
        )
        role = value("Rol", "")
        clase = value("Clase", "")
        dmg_type = value("Tipo de daño", "")
        role_parts = []
        if role != "—": role_parts.append(f"🎭 {role}")
        if clase != "—": role_parts.append(f"📚 {clase}")
        if dmg_type != "—": role_parts.append(f"{TYPE_ICONS.get(dmg_type, '⚔️')} {dmg_type}")
        combat_body = stat_line
        if role_parts:
            combat_body += "\n" + "  ·  ".join(role_parts)
        fields.append(("⚔️ Stats de combate", combat_body[:1024], False))

    # ── Habilidades 1-3 ────────────────────────────────────────────────────────
    for ability_number in range(1, 4):
        suffix = "" if ability_number == 1 else f" {ability_number}"
        ability = value(f"Habilidad{suffix}", "")
        if not ability or ability == "—":
            continue
        icon = ABILITY_ICONS[ability_number - 1]
        dmg = value(f"Daño de habilidad{suffix}", "")
        dmg_type = value(f"Tipo de daño de habilidad{suffix}", "")
        effect = value(f"Estado de habilidad{suffix}", "")
        duration = value(f"Duración de efecto de habilidad{suffix}", "")
        chance = value(f"Probabilidad de efecto de habilidad{suffix}", "")
        desc = value(f"Descripción de habilidad{suffix}", "")

        lines = []
        # Primera línea: daño + tipo
        dmg_parts = []
        if dmg != "—": dmg_parts.append(f"💥 **{dmg}**")
        if dmg_type != "—": dmg_parts.append(f"{TYPE_ICONS.get(dmg_type, '')} {dmg_type}")
        if dmg_parts:
            lines.append("  ·  ".join(dmg_parts))
        # Segunda línea: estado/efecto
        if effect != "—":
            effect_icon = EFFECT_ICONS.get(effect, "🔸")
            effect_str = f"{effect_icon} **{effect}**"
            if duration != "—": effect_str += f" · {duration} turnos"
            if chance != "—": effect_str += f" · {chance}% prob."
            lines.append(effect_str)
        # Descripción en cursiva
        if desc != "—":
            lines.append(f"*{desc}*")

        field_value = "\n".join(lines) if lines else "—"
        fields.append((f"{icon} Hab. {ability_number} — {ability}", field_value[:1024], False))

    # ── Pasiva ─────────────────────────────────────────────────────────────────
    passive = value("Pasiva", "")
    if passive and passive != "—":
        dmg = value("Daño de pasiva", "")
        dmg_type = value("Tipo de daño de pasiva", "")
        effect = value("Estado de pasiva", "")
        duration = value("Duración de efecto de pasiva", "")
        chance = value("Probabilidad de efecto de pasiva", "")
        desc = value("Descripción de pasiva", "")

        lines = []
        dmg_parts = []
        if dmg != "—": dmg_parts.append(f"💥 **{dmg}**")
        if dmg_type != "—": dmg_parts.append(f"{TYPE_ICONS.get(dmg_type, '')} {dmg_type}")
        if dmg_parts:
            lines.append("  ·  ".join(dmg_parts))
        if effect != "—":
            effect_icon = EFFECT_ICONS.get(effect, "🔸")
            effect_str = f"{effect_icon} **{effect}**"
            if duration != "—": effect_str += f" · {duration} turnos"
            if chance != "—": effect_str += f" · {chance}% prob."
            lines.append(effect_str)
        if desc != "—":
            lines.append(f"*{desc}*")

        field_value = "\n".join(lines) if lines else "—"
        fields.append((f"🔥 Pasiva — {passive}", field_value[:1024], False))

    # ── Stats extra (campos libres del JSON) ───────────────────────────────────
    extra = [(str(k), str(v)) for k, v in stats.items() if k not in COMBAT_STAT_KEYS and str(v).strip()]
    if extra:
        fields.append(("📊 Stats extra", "\n".join(f"**{k}:** {v}" for k, v in extra)[:1024], False))

    return fields


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
    migrated = await db.fetchval("SELECT migration_key FROM schema_migrations WHERE migration_key='character_pixel_assets_v1'")
    if not migrated:
        await db.execute("UPDATE card_catalog SET image_data=NULL,image_mime=''" )
        await db.execute("INSERT INTO schema_migrations (migration_key) VALUES ('character_pixel_assets_v1') ON CONFLICT DO NOTHING")


def card_emoji(row) -> str:
    if row.get("emoji_name") and row.get("emoji_id"):
        return f"<:{row['emoji_name']}:{row['emoji_id']}>"
    return RARITY_EMOJI.get(row.get("rarity"), "🎴")


async def collection_rows(guild_id: int, user_id: int, filter_name: str = ""):
    filter_name = (filter_name or "").strip().lower()
    if filter_name in {"faltantes", "faltantes"}:
        return await db.fetch("""SELECT c.name,c.rarity,c.emoji_name,c.emoji_id,0::int AS quantity,c.base_value
            FROM card_catalog c WHERE c.active=TRUE AND NOT EXISTS
            (SELECT 1 FROM card_inventory i WHERE i.guild_id=$1 AND i.user_id=$2 AND i.card_slug=c.slug AND i.quantity>0)
            ORDER BY c.rarity DESC,c.name""", guild_id, user_id)
    extra = ""
    args = [guild_id, user_id]
    if filter_name in {"comun", "común", "rara", "epica", "épica", "legendaria"}:
        extra = " AND c.rarity=$3"
        args.append({"comun":"Común","común":"Común","rara":"Rara","epica":"Épica","épica":"Épica","legendaria":"Legendaria"}[filter_name])
    elif filter_name in {"repetidas", "repetida"}:
        extra = " AND i.quantity>1"
    return await db.fetch(f"""SELECT c.name,c.rarity,c.emoji_name,c.emoji_id,i.quantity,c.base_value
        FROM card_inventory i JOIN card_catalog c ON c.slug=i.card_slug
        WHERE i.guild_id=$1 AND i.user_id=$2 AND i.quantity>0{extra}
        ORDER BY c.rarity DESC,c.name""", *args)


def collection_embed(target_name: str, rows, page: int, filter_name: str = ""):
    per_page = 8
    total_pages = max(1, (len(rows) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    chunk = rows[page * per_page:(page + 1) * per_page]
    description = "\n".join(f"{card_emoji(row)} **{row['name']}** · {row['rarity']} · ×{row['quantity']}" for row in chunk)
    description = description or ("No hay cartas con este filtro." if filter_name else "Aún no tienes cartas. Usa `/sobre` o `!sobre`.")
    embed = notice(f"Colección de {target_name} 📚", description)
    total = sum(row["quantity"] for row in rows)
    value = sum(row["quantity"] * row["base_value"] for row in rows)
    embed.add_field(name="Cartas mostradas", value=f"{len(rows)}", inline=True)
    embed.add_field(name="Copias", value=str(total), inline=True)
    embed.add_field(name="Valor", value=f"{coins_text(value)} Abo Coins", inline=True)
    embed.set_footer(text=f"Página {page + 1}/{total_pages} · Filtro: {filter_name or 'todas'}")
    return embed, total_pages


class CollectionView(discord.ui.View):
    def __init__(self, owner_id: int, target_name: str, rows, filter_name: str = ""):
        super().__init__(timeout=180)
        self.owner_id, self.target_name, self.rows, self.filter_name, self.page = owner_id, target_name, rows, filter_name, 0
        self._sync()

    def _sync(self):
        pages = max(1, (len(self.rows) + 7) // 8)
        self.previous.disabled = self.page <= 0
        self.next.disabled = self.page >= pages - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Solo quien abrió esta colección puede cambiar sus páginas.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Anterior", emoji="◀️", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1; self._sync()
        embed, _ = collection_embed(self.target_name, self.rows, self.page, self.filter_name)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Siguiente", emoji="▶️", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1; self._sync()
        embed, _ = collection_embed(self.target_name, self.rows, self.page, self.filter_name)
        await interaction.response.edit_message(embed=embed, view=self)


async def purchase_listing(guild_id: int, user_id: int, listing_id: int, quantity: int = 1):
    async with db._pool().acquire() as connection:
        async with connection.transaction():
            listing = await connection.fetchrow("SELECT * FROM card_market_listings WHERE id=$1 AND guild_id=$2 AND status='active' FOR UPDATE", listing_id, guild_id)
            if not listing or listing["remaining"] < quantity:
                return None, "La publicación no existe o no tiene suficientes copias."
            if listing["seller_id"] == user_id:
                return None, "No puedes comprarte tu propia publicación."
            total = listing["price_each"] * quantity
            buyer = await connection.fetchrow("SELECT coins FROM card_wallets WHERE guild_id=$1 AND user_id=$2 FOR UPDATE", guild_id, user_id)
            if not buyer or buyer["coins"] < total:
                return None, f"Necesitas **{coins_text(total)} Abo Coins**."
            await connection.execute("UPDATE card_wallets SET coins=coins-$1,updated_at=NOW() WHERE guild_id=$2 AND user_id=$3", total, guild_id, user_id)
            await connection.execute("INSERT INTO card_wallets (guild_id,user_id) VALUES ($1,$2) ON CONFLICT DO NOTHING", guild_id, listing["seller_id"])
            await connection.execute("UPDATE card_wallets SET coins=coins+$1,updated_at=NOW() WHERE guild_id=$2 AND user_id=$3", total, guild_id, listing["seller_id"])
            await add_card(connection, guild_id, user_id, listing["card_slug"], quantity)
            remaining = listing["remaining"] - quantity
            await connection.execute("UPDATE card_market_listings SET remaining=$1,status=CASE WHEN $1=0 THEN 'sold' ELSE status END WHERE id=$2", remaining, listing_id)
            card = await connection.fetchrow("SELECT name,rarity,emoji_name,emoji_id FROM card_catalog WHERE slug=$1", listing["card_slug"])
    return {"card": card, "quantity": quantity, "total": total, "seller_id": listing["seller_id"]}, None


class CardService:
    """Capa compartida para que slash, prefijo y botones usen las mismas operaciones."""

    collection = staticmethod(collection_rows)
    purchase_listing = staticmethod(purchase_listing)


class MarketView(discord.ui.View):
    def __init__(self, rows):
        super().__init__(timeout=180)
        for row in rows[:10]:
            buy = discord.ui.Button(label=f"Comprar #{row['id']}", emoji="🛒", style=discord.ButtonStyle.success, custom_id=f"market_buy:{row['id']}")
            seller = discord.ui.Button(label="Vendedor", emoji="👤", style=discord.ButtonStyle.secondary, custom_id=f"market_seller:{row['id']}")
            buy.callback = self._buy_callback(row["id"])
            seller.callback = self._seller_callback(row["seller_id"])
            self.add_item(buy); self.add_item(seller)

    def _buy_callback(self, listing_id):
        async def callback(interaction: discord.Interaction):
            result, error = await CardService.purchase_listing(interaction.guild_id, interaction.user.id, listing_id)
            if error:
                return await interaction.response.send_message(embed=notice("Compra no realizada", error, 0xED4245), ephemeral=True)
            await interaction.response.send_message(embed=notice("Compra completada 🛒", f"Compraste **×{result['quantity']} {card_emoji(result['card'])} {result['card']['name']}** por **{coins_text(result['total'])} Abo Coins**."), ephemeral=True)
        return callback

    def _seller_callback(self, seller_id):
        async def callback(interaction: discord.Interaction):
            member = interaction.guild.get_member(seller_id)
            text = member.mention if member else f"Usuario `{seller_id}`"
            await interaction.response.send_message(embed=notice("Vendedor 👤", f"Esta publicación pertenece a {text}."), ephemeral=True, allowed_mentions=discord.AllowedMentions(users=True))
        return callback


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


def level_for_xp(xp: int) -> int:
    return max(1, int(xp // 1000) + 1)


async def card_message(guild_id: int, key: str, **values) -> discord.Embed:
    default = DEFAULT_CARD_MESSAGES.get(key, ("Abo Cards", "", 0x5865F2))
    row = await db.fetchrow("SELECT title,description,color FROM card_message_templates WHERE guild_id=$1 AND message_key=$2", guild_id, key)
    title, description, color = (row["title"], row["description"], row["color"]) if row else default
    try:
        title, description = title.format(**values), description.format(**values)
    except KeyError:
        pass
    return notice(title, description, color)


async def award_xp(guild_id: int, user_id: int, amount: int) -> tuple[int, bool]:
    # Operación atómica: actualiza XP y nivel en un solo UPDATE para evitar que
    # dos llamadas concurrentes detecten el mismo level-up y envíen dos mensajes.
    async with db._pool().acquire() as connection:
        row = await connection.fetchrow(
            """UPDATE card_wallets
               SET xp = xp + $3,
                   level = GREATEST(level, (xp + $3) / 1000 + 1),
                   updated_at = NOW()
               WHERE guild_id = $1 AND user_id = $2
               RETURNING xp, level,
                         (level > (xp - $3) / 1000 + 1) AS just_leveled_up""",
            guild_id, user_id, amount,
        )
        if row is None:
            # Wallet no existe todavía; la creamos con el XP inicial.
            row = await connection.fetchrow(
                """INSERT INTO card_wallets (guild_id, user_id, xp, level)
                   VALUES ($1, $2, $3, $4)
                   ON CONFLICT (guild_id, user_id) DO UPDATE
                   SET xp = card_wallets.xp + $3,
                       level = GREATEST(card_wallets.level, (card_wallets.xp + $3) / 1000 + 1),
                       updated_at = NOW()
                   RETURNING xp, level,
                             (level > (xp - $3) / 1000 + 1) AS just_leveled_up""",
                guild_id, user_id, amount, level_for_xp(amount),
            )
        new_level = level_for_xp(row["xp"])
        return new_level, bool(row["just_leveled_up"])


async def claim_set_reward(guild_id: int, user_id: int, set_slug: str):
    status = await db.fetchrow("""SELECT COUNT(c.slug)::int AS total,COUNT(i.card_slug) FILTER (WHERE COALESCE(i.quantity,0)>0)::int AS owned,
        s.name,s.reward_coins FROM card_sets s LEFT JOIN card_catalog c ON c.set_slug=s.slug AND c.active=TRUE
        LEFT JOIN card_inventory i ON i.card_slug=c.slug AND i.guild_id=$1 AND i.user_id=$2 WHERE s.slug=$3 GROUP BY s.name,s.reward_coins""", guild_id, user_id, set_slug)
    if not status or status["total"] == 0 or status["owned"] < status["total"]:
        return None
    inserted = await db.fetchval("INSERT INTO card_set_claims (guild_id,user_id,set_slug) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING RETURNING set_slug", guild_id, user_id, set_slug)
    if not inserted:
        return None
    reward = status["reward_coins"]
    await ensure_wallet(guild_id, user_id)
    await db.execute("UPDATE card_wallets SET coins=coins+$1,updated_at=NOW() WHERE guild_id=$2 AND user_id=$3", reward, guild_id, user_id)
    await award_xp(guild_id, user_id, 500)
    return status["name"], reward


async def open_card_pack(guild_id: int, user_id: int):
    await ensure_wallet(guild_id, user_id)
    async with db._pool().acquire() as connection:
        async with connection.transaction():
            wallet = await connection.fetchrow("SELECT * FROM card_wallets WHERE guild_id=$1 AND user_id=$2 FOR UPDATE", guild_id, user_id)
            if wallet["coins"] < PACK_PRICE:
                return None, f"El sobre cuesta **{PACK_PRICE} Abo Coins** y tienes **{wallet['coins']}**.", None
            rare_pity = wallet["pity_rare"] + 1 >= PITY_RARE_LIMIT
            epic_pity = wallet["pity_epic"] + 1 >= PITY_EPIC_LIMIT
            drawn = await choose_cards(connection, 3)
            if epic_pity:
                guaranteed = await connection.fetch("SELECT slug FROM card_catalog WHERE active=TRUE AND rarity IN ('Épica','Legendaria')")
                if guaranteed: drawn[0] = random.choice(guaranteed)["slug"]
            elif rare_pity:
                guaranteed = await connection.fetch("SELECT slug FROM card_catalog WHERE active=TRUE AND rarity IN ('Rara','Épica','Legendaria')")
                if guaranteed: drawn[0] = random.choice(guaranteed)["slug"]
            rows = await connection.fetch("SELECT slug,name,rarity,emoji_name,emoji_id FROM card_catalog WHERE slug=ANY($1::text[])", drawn)
            by_slug = {row["slug"]: row for row in rows}
            has_rare = any(by_slug[s]["rarity"] in {"Rara", "Épica", "Legendaria"} for s in drawn)
            has_epic = any(by_slug[s]["rarity"] in {"Épica", "Legendaria"} for s in drawn)
            rare_count = 0 if has_rare else wallet["pity_rare"] + 1
            epic_count = 0 if has_epic else wallet["pity_epic"] + 1
            await connection.execute("UPDATE card_wallets SET coins=coins-$1,pity_rare=$2,pity_epic=$3,packs_opened=packs_opened+1,updated_at=NOW() WHERE guild_id=$4 AND user_id=$5", PACK_PRICE, rare_count, epic_count, guild_id, user_id)
            for slug in drawn:
                await add_card(connection, guild_id, user_id, slug)
            balance = wallet["coins"] - PACK_PRICE
    level, leveled = await award_xp(guild_id, user_id, XP_PER_PACK)
    return {"drawn": drawn, "rows": by_slug, "balance": balance, "rare_pity": rare_count, "epic_pity": epic_count, "level": level, "leveled": leveled, "forced": "epic" if epic_pity else "rare" if rare_pity else ""}, None, None



BATTLE_MAX_HP = 100
BATTLE_MAX_ENERGY = 5
BATTLE_STATES = {"Quemadura", "Veneno", "Aturdimiento", "Escudo", "Regeneración", "Silencio", "Debilitado", "Lento"}

def combat_stats(row):
    value=row.get("stats") or {}
    if isinstance(value,str):
        try: value=json.loads(value)
        except Exception: value={}
    return value if isinstance(value,dict) else {}

def stat_num(stats,key,default=0):
    match=re.search(r"-?\d+(?:\.\d+)?",str(stats.get(key,default)))
    return int(float(match.group(0))) if match else default

def damage_num(value,default=0):
    match=re.search(r"\d+(?:\.\d+)?",str(value or ""))
    return int(float(match.group(0))) if match else default

def battle_line(player):
    states=", ".join(f"{key}({value})" for key,value in player["states"].items()) or "sin estados"
    return f"**{player['mention']}** · {card_emoji(player['card'])} **{player['card']['name']}**\n❤️ {player['hp']}/{player['max_hp']} HP · ⚡ {player['energy']}/5 · {states}"

class BattleChallengeView(discord.ui.View):
    def __init__(self,cog,guild_id,challenger,opponent):
        super().__init__(timeout=60); self.cog=cog; self.guild_id=guild_id; self.challenger=challenger; self.opponent=opponent
    @discord.ui.button(label="Aceptar pelea",emoji="⚔️",style=discord.ButtonStyle.success)
    async def accept(self,interaction,button):
        if interaction.user.id!=self.opponent: return await interaction.response.send_message("Solo el usuario desafiado puede aceptar.",ephemeral=True)
        await interaction.response.defer(); await self.cog.prepare_battle(interaction,self.guild_id,self.challenger,self.opponent); self.stop()
    @discord.ui.button(label="Rechazar",emoji="✖️",style=discord.ButtonStyle.danger)
    async def reject(self,interaction,button):
        if interaction.user.id!=self.opponent: return await interaction.response.send_message("Solo el usuario desafiado puede rechazar.",ephemeral=True)
        await interaction.response.edit_message(embed=notice("Pelea cancelada","El desafío fue rechazado.",0xED4245),view=None); self.stop()

class BattleChoice(discord.ui.Select):
    def __init__(self,cog,key,user_id,rows):
        options=[discord.SelectOption(label=str(row['name'])[:100],value=row['slug'],description=str(row['rarity'])) for row in rows[:25]]
        super().__init__(placeholder="Elige tu personaje...",options=options); self.cog=cog; self.key=key; self.user_id=user_id
    async def callback(self,interaction):
        if interaction.user.id!=self.user_id: return await interaction.response.send_message("Este selector no es para ti.",ephemeral=True)
        session=self.cog.battles.get(self.key)
        if not session: return await interaction.response.send_message("La pelea ya terminó.",ephemeral=True)
        session['selected'][self.user_id]=self.values[0]
        await interaction.response.defer()
        if len(session['selected'])==2:
            await self.cog.begin_battle(interaction,self.key)
        else:
            await interaction.followup.send(f"Elegiste **{self.values[0]}**. Esperando al rival...",ephemeral=True)

class BattleSetupView(discord.ui.View):
    def __init__(self,cog,key,choices):
        super().__init__(timeout=120)
        for user_id,rows in choices: self.add_item(BattleChoice(cog,key,user_id,rows))

class AbilityChoice(discord.ui.Select):
    def __init__(self, cog, key, user_id, stats):
        options=[]
        for number in range(1,4):
            suffix="" if number==1 else f" {number}"
            name=str(stats.get(f"Habilidad{suffix}","")).strip()
            if name:
                options.append(discord.SelectOption(label=f"Habilidad {number}: {name}"[:100], value=str(number), description=f"Daño: {stats.get(f'Daño de habilidad{suffix}', '—')}"[:100]))
        super().__init__(placeholder="Elige una habilidad...", options=options)
        self.cog=cog; self.key=key; self.user_id=user_id
    async def callback(self, interaction):
        session=self.cog.battles.get(self.key)
        if not session or interaction.user.id!=session['turn']:
            return await interaction.response.send_message("No puedes elegir una habilidad en este momento.",ephemeral=True)
        await interaction.response.defer()
        await self.cog.battle_action(interaction,self.key,f"ability:{self.values[0]}")

class AbilityChoiceView(discord.ui.View):
    def __init__(self,cog,key,user_id,stats):
        super().__init__(timeout=30)
        self.add_item(AbilityChoice(cog,key,user_id,stats))

class BattleView(discord.ui.View):
    def __init__(self,cog,key):
        super().__init__(timeout=45); self.cog=cog; self.key=key
    async def act(self,interaction,action):
        session=self.cog.battles.get(self.key)
        if not session: return await interaction.response.send_message("La pelea ya terminó.",ephemeral=True)
        if interaction.user.id!=session['turn']: return await interaction.response.send_message("No es tu turno.",ephemeral=True)
        await interaction.response.defer(); await self.cog.battle_action(interaction,self.key,action)
    @discord.ui.button(label="Ataque",emoji="⚔️",style=discord.ButtonStyle.primary)
    async def attack(self,interaction,button): await self.act(interaction,"attack")
    @discord.ui.button(label="Habilidad",emoji="✨",style=discord.ButtonStyle.success)
    async def ability(self,interaction,button):
        session=self.cog.battles.get(self.key)
        if not session: return await interaction.response.send_message("La pelea ya terminó.",ephemeral=True)
        if interaction.user.id!=session['turn']: return await interaction.response.send_message("No es tu turno.",ephemeral=True)
        stats=combat_stats(session['players'][session['turn']]['card'])
        if not any(str(stats.get("Habilidad" if n == 1 else f"Habilidad {n}", "")).strip() for n in range(1, 4)):
            return await interaction.response.send_message("Esta carta no tiene habilidades configuradas.",ephemeral=True)
        await interaction.response.edit_message(embed=notice("✨ Elige una habilidad","Selecciona qué habilidad quieres utilizar. Esto todavía no consume tu turno."),view=AbilityChoiceView(self.cog,self.key,interaction.user.id,stats))
    @discord.ui.button(label="Defender",emoji="🛡️",style=discord.ButtonStyle.secondary)
    async def defend(self,interaction,button): await self.act(interaction,"defend")
    @discord.ui.button(label="Rendirse",emoji="🏳️",style=discord.ButtonStyle.danger)
    async def surrender(self,interaction,button): await self.act(interaction,"surrender")

class CardsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.trade_sessions: dict[int, dict] = {}
        self.battles: dict[str, dict] = {}

    async def restore_trade_sessions(self):
        rows = await db.fetch("SELECT * FROM card_trade_sessions WHERE status='active' AND channel_id IS NOT NULL")
        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            channel = guild.get_channel(row["channel_id"]) if guild else None
            if not channel:
                continue
            members = [guild.get_member(row["user_a"]) if guild else None, guild.get_member(row["user_b"]) if guild else None]
            users = [row["user_a"], row["user_b"]]
            offers = {users[0]: {}, users[1]: {}}
            for index, key in enumerate(("offer_a", "offer_b")):
                payload = row[key] or {}
                for slug, quantity in payload.items():
                    card = await card_row(slug)
                    if card:
                        offers[users[index]][slug] = {"quantity": int(quantity), "name": card["name"], "emoji": card_emoji(card)}
            self.trade_sessions[row["channel_id"]] = {
                "trade_id": row["id"], "guild_id": row["guild_id"], "channel_id": row["channel_id"],
                "user_a": users[0], "user_b": users[1],
                "name_a": members[0].display_name if members[0] else str(users[0]),
                "name_b": members[1].display_name if members[1] else str(users[1]),
                "offers": offers,
                "confirmed": {users[0]: row["confirmed_a"], users[1]: row["confirmed_b"]},
            }

    @app_commands.command(name="diario_cartas", description="Reclama tus Abo Coins diarios para comprar sobres")
    @app_commands.guild_only()
    async def diario_cartas(self, interaction: discord.Interaction):
        now = datetime.now(timezone.utc)
        await ensure_wallet(interaction.guild_id, interaction.user.id)
        async with db._pool().acquire() as connection:
            async with connection.transaction():
                wallet = await connection.fetchrow(
                    "SELECT coins, daily_claimed_at, daily_streak FROM card_wallets WHERE guild_id=$1 AND user_id=$2 FOR UPDATE",
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
        level, leveled = await award_xp(interaction.guild_id, interaction.user.id, XP_PER_DAILY)
        if leveled:
            await interaction.followup.send(embed=await card_message(interaction.guild_id, "level_up", level=level, xp=level * 1000), ephemeral=True)

    @app_commands.command(name="saldo_cartas", description="Muestra tu saldo de Abo Coins")
    @app_commands.guild_only()
    async def saldo_cartas(self, interaction: discord.Interaction):
        await ensure_wallet(interaction.guild_id, interaction.user.id)
        coins = await db.fetchval("SELECT coins FROM card_wallets WHERE guild_id=$1 AND user_id=$2", interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(embed=notice("Tu saldo 💰", f"Tienes **{coins_text(coins)} Abo Coins**.\nUsa `/sobre` para comprar un sobre de 3 cartas."), ephemeral=True)

    @app_commands.command(name="perfil", description="Muestra tu perfil de coleccionista")
    @app_commands.guild_only()
    @app_commands.describe(usuario="Perfil de otro miembro")
    async def perfil(self, interaction: discord.Interaction, usuario: discord.Member | None = None):
        target = usuario or interaction.user
        await ensure_wallet(interaction.guild_id, target.id)
        wallet = await db.fetchrow("SELECT coins,xp,level,packs_opened,pity_rare,pity_epic FROM card_wallets WHERE guild_id=$1 AND user_id=$2", interaction.guild_id, target.id)
        stats = await db.fetchrow("""SELECT COUNT(*) FILTER (WHERE quantity>0)::int AS unique_cards,
            COALESCE(SUM(quantity),0)::int AS total_cards,COALESCE(SUM(quantity*c.base_value),0)::bigint AS value
            FROM card_inventory i JOIN card_catalog c ON c.slug=i.card_slug WHERE i.guild_id=$1 AND i.user_id=$2""", interaction.guild_id, target.id)
        rank = await db.fetchval("""SELECT COUNT(*)+1 FROM (SELECT i.user_id,SUM(i.quantity*c.base_value) AS value FROM card_inventory i JOIN card_catalog c ON c.slug=i.card_slug WHERE i.guild_id=$1 GROUP BY i.user_id) x WHERE x.value > $2""", interaction.guild_id, stats["value"]) or 1
        embed = notice(f"Perfil de {target.display_name} 🪪", f"Nivel: **{wallet['level']}** · XP: **{wallet['xp']}/ {(wallet['level'])*1000}**\nSaldo: **{coins_text(wallet['coins'])} Abo Coins**\n\nCartas únicas: **{stats['unique_cards']}**\nCartas totales: **{stats['total_cards']}**\nValor de colección: **{coins_text(stats['value'])}**\nPosición: **#{rank}**\n\nSobres abiertos: **{wallet['packs_opened']}**\nPity rara: **{wallet['pity_rare']}/{PITY_RARE_LIMIT}**\nPity épica: **{wallet['pity_epic']}/{PITY_EPIC_LIMIT}**", 0x5865F2)
        if target.display_avatar: embed.set_thumbnail(url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="cartas_regalar", description="Regala cartas a un miembro")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def cartas_regalar(self, interaction: discord.Interaction, usuario: discord.Member, carta: str, cantidad: int = 1):
        row = await card_row(carta)
        if not row or cantidad < 1:
            return await interaction.response.send_message(embed=notice("Datos inválidos", "Indica una carta válida y una cantidad positiva.", 0xED4245), ephemeral=True)
        async with db._pool().acquire() as connection:
            await add_card(connection, interaction.guild_id, usuario.id, row["slug"], cantidad)
            await connection.execute("INSERT INTO card_admin_audit (guild_id,actor_id,action,target_id,card_slug,quantity) VALUES ($1,$2,'grant',$3,$4,$5)", interaction.guild_id, interaction.user.id, usuario.id, row["slug"], cantidad)
        await interaction.response.send_message(embed=notice("Cartas entregadas 🎁", f"Entregaste **×{cantidad} {card_emoji(row)} {row['name']}** a {usuario.mention}."), ephemeral=True)

    @app_commands.command(name="cartas_retirar", description="Retira cartas de un miembro")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def cartas_retirar(self, interaction: discord.Interaction, usuario: discord.Member, carta: str, cantidad: int = 1):
        row = await card_row(carta)
        if not row or cantidad < 1:
            return await interaction.response.send_message(embed=notice("Datos inválidos", "Indica una carta válida y una cantidad positiva.", 0xED4245), ephemeral=True)
        async with db._pool().acquire() as connection:
            result = await connection.execute("UPDATE card_inventory SET quantity=quantity-$1 WHERE guild_id=$2 AND user_id=$3 AND card_slug=$4 AND quantity >= $1", cantidad, interaction.guild_id, usuario.id, row["slug"])
            if result.endswith("0"):
                return await interaction.response.send_message(embed=notice("No se pudo retirar", "El usuario no tiene suficientes copias.", 0xED4245), ephemeral=True)
            await connection.execute("INSERT INTO card_admin_audit (guild_id,actor_id,action,target_id,card_slug,quantity) VALUES ($1,$2,'remove',$3,$4,$5)", interaction.guild_id, interaction.user.id, usuario.id, row["slug"], cantidad)
        await interaction.response.send_message(embed=notice("Cartas retiradas 🧹", f"Retiraste **×{cantidad} {card_emoji(row)} {row['name']}** de {usuario.mention}."), ephemeral=True)

    @app_commands.command(name="cartas_saldo", description="Establece el saldo de Abo Coins de un miembro")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def cartas_saldo(self, interaction: discord.Interaction, usuario: discord.Member, cantidad: int):
        if cantidad < 0:
            return await interaction.response.send_message(embed=notice("Saldo inválido", "La cantidad no puede ser negativa.", 0xED4245), ephemeral=True)
        await ensure_wallet(interaction.guild_id, usuario.id)
        await db.execute("UPDATE card_wallets SET coins=$1,updated_at=NOW() WHERE guild_id=$2 AND user_id=$3", cantidad, interaction.guild_id, usuario.id)
        await db.execute("INSERT INTO card_admin_audit (guild_id,actor_id,action,target_id,coins) VALUES ($1,$2,'set_balance',$3,$4)", interaction.guild_id, interaction.user.id, usuario.id, cantidad)
        await interaction.response.send_message(embed=notice("Saldo actualizado 💰", f"El saldo de {usuario.mention} ahora es **{coins_text(cantidad)} Abo Coins**."), ephemeral=True)

    @app_commands.command(name="cartas_resetear", description="Reinicia la colección y economía de un miembro")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def cartas_resetear(self, interaction: discord.Interaction, usuario: discord.Member):
        async with db._pool().acquire() as connection:
            await connection.execute("DELETE FROM card_inventory WHERE guild_id=$1 AND user_id=$2", interaction.guild_id, usuario.id)
            await connection.execute("UPDATE card_wallets SET coins=500,xp=0,level=1,pity_rare=0,pity_epic=0,packs_opened=0,daily_claimed_at=NULL,daily_streak=0,updated_at=NOW() WHERE guild_id=$1 AND user_id=$2", interaction.guild_id, usuario.id)
            await connection.execute("INSERT INTO card_admin_audit (guild_id,actor_id,action,target_id) VALUES ($1,$2,'reset',$3)", interaction.guild_id, interaction.user.id, usuario.id)
        await interaction.response.send_message(embed=notice("Colección reiniciada ⚠️", f"Se reinició la colección y economía de {usuario.mention}.", 0xFEE75C), ephemeral=True)

    @app_commands.command(name="sobre", description="Compra un sobre de 3 cartas aleatorias")
    @app_commands.guild_only()
    async def sobre(self, interaction: discord.Interaction):
        result, error, _ = await open_card_pack(interaction.guild_id, interaction.user.id)
        if error:
            return await interaction.response.send_message(embed=notice("No alcanzan las monedas 💸", error, 0xED4245), ephemeral=True)
        lines = [f"{card_emoji(result['rows'][s])} {result['rows'][s]['rarity']} · **{result['rows'][s]['name']}**" for s in result["drawn"]]
        embed = await card_message(interaction.guild_id, "pack_opened", cards="\n".join(f"• {line}" for line in lines), balance=coins_text(result["balance"]))
        if result["forced"]:
            pity = await card_message(interaction.guild_id, "pity_epic" if result["forced"] == "epic" else "pity_rare")
            embed.add_field(name=pity.title, value=pity.description, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        if result["leveled"]:
            await interaction.followup.send(embed=await card_message(interaction.guild_id, "level_up", level=result["level"], xp=result["level"] * 1000), ephemeral=True)

    @app_commands.command(name="coleccion", description="Muestra tu colección paginada")
    @app_commands.guild_only()
    @app_commands.describe(usuario="Miembro cuya colección consultar", filtro="todas, faltantes, repetidas o una rareza")
    async def coleccion(self, interaction: discord.Interaction, usuario: discord.Member | None = None, filtro: str | None = None):
        target = usuario or interaction.user
        rows = await collection_rows(interaction.guild_id, target.id, filtro or "")
        embed, pages = collection_embed(target.display_name, rows, 0, filtro or "")
        view = CollectionView(interaction.user.id, target.display_name, rows, filtro or "") if pages > 1 else None
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="sets", description="Muestra los sets de Abo Cards")
    @app_commands.guild_only()
    async def sets(self, interaction: discord.Interaction):
        rows = await db.fetch("""SELECT s.slug,s.name,s.description,COUNT(c.slug)::int AS total,
            COUNT(i.card_slug) FILTER (WHERE COALESCE(i.quantity,0)>0)::int AS owned
            FROM card_sets s LEFT JOIN card_catalog c ON c.set_slug=s.slug AND c.active=TRUE
            LEFT JOIN card_inventory i ON i.card_slug=c.slug AND i.guild_id=$1 AND i.user_id=$2
            WHERE s.active=TRUE GROUP BY s.slug,s.name,s.description ORDER BY s.name""", interaction.guild_id, interaction.user.id)
        description = "\n".join(f"🎴 **{r['name']}** · {r['owned']}/{r['total']} cartas\n{r['description']}" for r in rows) or "Todavía no hay sets disponibles."
        await interaction.response.send_message(embed=notice("Sets de Abo Cards 🗂️", description))

    @app_commands.command(name="set", description="Muestra las cartas de un set")
    @app_commands.guild_only()
    @app_commands.describe(nombre="Slug o nombre del set")
    async def set_cartas(self, interaction: discord.Interaction, nombre: str):
        row = await db.fetchrow("SELECT slug,name,description FROM card_sets WHERE active=TRUE AND (slug=$1 OR name ILIKE $2)", nombre.lower(), nombre)
        if not row:
            return await interaction.response.send_message(embed=notice("Set no encontrado", "Usa `/sets` para ver los sets disponibles.", 0xED4245), ephemeral=True)
        cards = await db.fetch("""SELECT c.name,c.rarity,c.emoji_name,c.emoji_id,COALESCE(i.quantity,0)::int AS quantity
            FROM card_catalog c LEFT JOIN card_inventory i ON i.card_slug=c.slug AND i.guild_id=$1 AND i.user_id=$2
            WHERE c.active=TRUE AND c.set_slug=$3 ORDER BY c.rarity DESC,c.name""", interaction.guild_id, interaction.user.id, row["slug"])
        description = "\n".join(f"{'✅' if c['quantity'] else '❌'} {card_emoji(c)} **{c['name']}** · ×{c['quantity']}" for c in cards) or "Este set no tiene cartas."
        owned = sum(1 for c in cards if c["quantity"] > 0)
        embed = notice(f"{row['name']} 🗂️", f"{row['description']}\n\nProgreso: **{owned}/{len(cards)}**\n\n{description}")
        await interaction.response.send_message(embed=embed)
        reward = await claim_set_reward(interaction.guild_id, interaction.user.id, row["slug"])
        if reward:
            await interaction.followup.send(embed=await card_message(interaction.guild_id, "set_complete", set_name=reward[0], reward=coins_text(reward[1])), ephemeral=True)

    @app_commands.command(name="carta", description="Muestra los detalles de una carta")
    @app_commands.guild_only()
    @app_commands.describe(nombre="Nombre o slug de la carta")
    async def carta(self, interaction: discord.Interaction, nombre: str):
        row = await db.fetchrow("SELECT * FROM card_catalog WHERE active=TRUE AND (slug=$1 OR name ILIKE $2)", nombre.lower(), nombre)
        if not row:
            return await interaction.response.send_message(embed=notice("Carta no encontrada", "Revisa el nombre en `/coleccion` o `/ranking_cartas`.", 0xED4245), ephemeral=True)
        owned = await db.fetchval("SELECT quantity FROM card_inventory WHERE guild_id=$1 AND user_id=$2 AND card_slug=$3", interaction.guild_id, interaction.user.id, row["slug"]) or 0
        description = row.get("description") or "Conoce a este personaje de Abo."
        embed = notice(f"{card_emoji(row)} {row['name']}", description, int(row.get("embed_color") or rarity_color(row["rarity"])))
        embed.add_field(name="Rareza", value=row["rarity"], inline=True)
        embed.add_field(name="Valor", value=f"{coins_text(row['base_value'])} Abo Coins", inline=True)
        embed.add_field(name="Tienes", value=f"×{owned}", inline=True)
        for field_name, field_value, inline in _combat_embed_fields(row):
            embed.add_field(name=field_name, value=field_value, inline=inline)
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

    @app_commands.command(name="tradeo", description="Inicia un intercambio de cartas con otro miembro")
    @app_commands.guild_only()
    @app_commands.describe(usuario="Usuario con quien quieres hacer el tradeo")
    async def tradeo(self, interaction: discord.Interaction, usuario: discord.Member):
        if usuario.bot or usuario.id == interaction.user.id:
            return await interaction.response.send_message(
                embed=notice("Tradeo inválido", "Elige a otro miembro real del servidor.", 0xED4245), ephemeral=True,
            )
        if interaction.channel_id in self.trade_sessions:
            return await interaction.response.send_message(
                embed=notice("Ya hay un Tradeo activo", "Primero termina o cancela el tradeo actual en este canal.", 0xED4245), ephemeral=True,
            )
        session = {
            "guild_id": interaction.guild_id,
            "channel_id": interaction.channel_id,
            "user_a": interaction.user.id,
            "user_b": usuario.id,
            "name_a": interaction.user.display_name,
            "name_b": usuario.display_name,
            "offers": {interaction.user.id: {}, usuario.id: {}},
            "confirmed": {interaction.user.id: False, usuario.id: False},
        }
        session["trade_id"] = await db.fetchval("""INSERT INTO card_trade_sessions (guild_id,user_a,user_b,channel_id,offer_a,offer_b,status)
            VALUES ($1,$2,$3,$4,'{}'::jsonb,'{}'::jsonb,'active') RETURNING id""", interaction.guild_id, interaction.user.id, usuario.id, interaction.channel_id)
        self.trade_sessions[interaction.channel_id] = session
        await interaction.response.send_message(
            embed=self._trade_embed(session, "Tradeo iniciado 🤝", "Escriban sus cartas en este canal. Ejemplo: `2 Mielabo, 1 Abo Pro` o `nada`."),
            allowed_mentions=discord.AllowedMentions(users=True),
        )

    async def handle_card_prefix(self, message: discord.Message) -> bool:
        """Accesos rápidos de entretenimiento; los comandos complejos siguen en slash."""
        if not message.guild or not message.content.startswith("!"):
            return False
        parts = message.content[1:].strip().split(maxsplit=1)
        if not parts:
            return False
        command = parts[0].lower()
        argument = parts[1].strip() if len(parts) > 1 else ""
        aliases = {
            "saldo": "saldo_cartas", "diario": "diario_cartas", "cards": "coleccion",
            "collection": "coleccion", "card": "carta", "pack": "sobre",
            "market": "mercado", "ranking": "ranking_cartas", "colecciones": "sets", "profile": "perfil",
        }
        command = aliases.get(command, command)
        quick = {"sobre", "coleccion", "carta", "saldo_cartas", "diario_cartas", "mercado", "ranking_cartas", "tradeo", "sets", "set", "perfil", "cartas", "ayudacartas"}
        if command not in quick:
            return False
        if command == "ayudacartas":
            await message.channel.send(embed=notice("Comandos rápidos de Abo Cards 🎴", "`!sobre` · `!coleccion` · `!carta <nombre>` · `!saldo` · `!diario` · `!mercado` · `!ranking` · `!tradeo @usuario`\n\nPara publicar, comprar o cancelar en el mercado usa los comandos `/mercado_*` con autocompletado."))
            return True
        if command == "tradeo":
            target = message.mentions[0] if message.mentions else None
            if not target:
                await message.channel.send(embed=notice("Uso de !tradeo", "Menciona al usuario: `!tradeo @usuario`.", 0xFEE75C))
                return True
            if target.bot or target.id == message.author.id or message.channel.id in self.trade_sessions:
                await message.channel.send(embed=notice("Tradeo inválido", "Elige otro usuario y asegúrate de que no haya otro Tradeo activo en este canal.", 0xED4245))
                return True
            self.trade_sessions[message.channel.id] = {
                "guild_id": message.guild.id, "channel_id": message.channel.id,
                "user_a": message.author.id, "user_b": target.id,
                "name_a": message.author.display_name, "name_b": target.display_name,
                "offers": {message.author.id: {}, target.id: {}},
                "confirmed": {message.author.id: False, target.id: False},
            }
            self.trade_sessions[message.channel.id]["trade_id"] = await db.fetchval("""INSERT INTO card_trade_sessions (guild_id,user_a,user_b,channel_id,offer_a,offer_b,status)
                VALUES ($1,$2,$3,$4,'{}'::jsonb,'{}'::jsonb,'active') RETURNING id""", message.guild.id, message.author.id, target.id, message.channel.id)
            await message.channel.send(embed=self._trade_embed(self.trade_sessions[message.channel.id], "Tradeo iniciado 🤝", "Escriban sus cartas, por ejemplo `2 Mielabo, 1 Abo Pro`, o escriban `nada`. Después confirmen con `@Abo !confirmar`."), allowed_mentions=discord.AllowedMentions(users=True))
            return True
        if command == "perfil":
            target = message.mentions[0] if message.mentions else message.author
            await ensure_wallet(message.guild.id, target.id)
            wallet = await db.fetchrow("SELECT coins,xp,level,packs_opened,pity_rare,pity_epic FROM card_wallets WHERE guild_id=$1 AND user_id=$2", message.guild.id, target.id)
            stats = await db.fetchrow("SELECT COUNT(*) FILTER (WHERE quantity>0)::int AS unique_cards,COALESCE(SUM(quantity),0)::int AS total_cards,COALESCE(SUM(quantity*c.base_value),0)::bigint AS value FROM card_inventory i JOIN card_catalog c ON c.slug=i.card_slug WHERE i.guild_id=$1 AND i.user_id=$2", message.guild.id, target.id)
            embed = notice(f"Perfil de {target.display_name} 🪪", f"Nivel: **{wallet['level']}** · XP: **{wallet['xp']}/{wallet['level']*1000}**\nSaldo: **{coins_text(wallet['coins'])} Abo Coins**\n\nCartas únicas: **{stats['unique_cards']}**\nCartas totales: **{stats['total_cards']}**\nValor: **{coins_text(stats['value'])} Abo Coins**\nSobres abiertos: **{wallet['packs_opened']}**\nPity rara: **{wallet['pity_rare']}/{PITY_RARE_LIMIT}**\nPity épica: **{wallet['pity_epic']}/{PITY_EPIC_LIMIT}**")
            await message.channel.send(embed=embed); return True
        if command == "cartas":
            if not message.author.guild_permissions.manage_guild:
                await message.channel.send(embed=notice("Permiso requerido 🔒", "Necesitas gestionar el servidor para usar herramientas administrativas.", 0xED4245)); return True
            args = argument.split()
            sub = args[0].lower() if args else ""
            target = message.mentions[0] if message.mentions else None
            if sub in {"regalar", "retirar", "saldo", "resetear"} and not target:
                await message.channel.send(embed=notice("Uso administrativo", "Ejemplo: `!cartas regalar @usuario Mielabo 2`.", 0xFEE75C)); return True
            if sub == "resetear":
                await db.execute("DELETE FROM card_inventory WHERE guild_id=$1 AND user_id=$2", message.guild.id, target.id)
                await db.execute("UPDATE card_wallets SET coins=500,xp=0,level=1,pity_rare=0,pity_epic=0,packs_opened=0 WHERE guild_id=$1 AND user_id=$2", message.guild.id, target.id)
                await message.channel.send(embed=notice("Colección reiniciada ⚠️", f"Se reinició la colección de {target.mention}.", 0xFEE75C)); return True
            if sub == "saldo" and len(args) >= 3:
                amount = int(args[-1]); await ensure_wallet(message.guild.id, target.id); await db.execute("UPDATE card_wallets SET coins=$1 WHERE guild_id=$2 AND user_id=$3", amount, message.guild.id, target.id)
                await message.channel.send(embed=notice("Saldo actualizado 💰", f"Saldo de {target.mention}: **{coins_text(amount)}**.")); return True
            if sub in {"regalar", "retirar"} and len(args) >= 3:
                card_name = " ".join(args[2:-1]) if args[-1].isdigit() else " ".join(args[2:]); amount = int(args[-1]) if args[-1].isdigit() else 1; row = await card_row(card_name)
                if not row: await message.channel.send(embed=notice("Carta no encontrada", "Indica una carta válida.", 0xED4245)); return True
                async with db._pool().acquire() as connection:
                    if sub == "regalar":
                        await add_card(connection, message.guild.id, target.id, row["slug"], amount)
                    else:
                        result = await connection.execute(
                            "UPDATE card_inventory SET quantity=quantity-$1 WHERE guild_id=$2 AND user_id=$3 AND card_slug=$4 AND quantity >= $1",
                            amount, message.guild.id, target.id, row["slug"],
                        )
                        if result.endswith("0"):
                            await message.channel.send(embed=notice("No se pudo retirar", f"{target.mention} no tiene suficientes copias de **{row['name']}**.", 0xED4245))
                            return True
                    await connection.execute("INSERT INTO card_admin_audit (guild_id,actor_id,action,target_id,card_slug,quantity) VALUES ($1,$2,$3,$4,$5,$6)", message.guild.id, message.author.id, "grant" if sub == "regalar" else "remove", target.id, row["slug"], amount)
                await message.channel.send(embed=notice("Operación completada ✅", f"{sub.title()}: **×{amount} {card_emoji(row)} {row['name']}** a {target.mention}.")); return True
            await message.channel.send(embed=notice("Herramientas de cartas", "`!cartas regalar @usuario <carta> [cantidad]` · `!cartas retirar @usuario <carta> [cantidad]` · `!cartas saldo @usuario <cantidad>` · `!cartas resetear @usuario")); return True
        if command in {"sets", "set"}:
            set_name = argument if command == "set" else ""
            if command == "sets":
                rows = await db.fetch("""SELECT s.slug,s.name,s.description,COUNT(c.slug)::int AS total,COUNT(i.card_slug) FILTER (WHERE COALESCE(i.quantity,0)>0)::int AS owned FROM card_sets s LEFT JOIN card_catalog c ON c.set_slug=s.slug AND c.active=TRUE LEFT JOIN card_inventory i ON i.card_slug=c.slug AND i.guild_id=$1 AND i.user_id=$2 WHERE s.active=TRUE GROUP BY s.slug,s.name,s.description ORDER BY s.name""", message.guild.id, message.author.id)
                text = "\n".join(f"🎴 **{r['name']}** · {r['owned']}/{r['total']} cartas" for r in rows) or "Todavía no hay sets disponibles."
                await message.channel.send(embed=notice("Sets de Abo Cards 🗂️", text)); return True
            row = await db.fetchrow("SELECT slug,name,description FROM card_sets WHERE active=TRUE AND (slug=$1 OR name ILIKE $2)", set_name.lower(), set_name)
            if not row:
                await message.channel.send(embed=notice("Set no encontrado", "Usa `!sets` para ver los sets disponibles.", 0xED4245)); return True
            cards = await db.fetch("SELECT c.name,c.rarity,c.emoji_name,c.emoji_id,COALESCE(i.quantity,0)::int AS quantity FROM card_catalog c LEFT JOIN card_inventory i ON i.card_slug=c.slug AND i.guild_id=$1 AND i.user_id=$2 WHERE c.active=TRUE AND c.set_slug=$3 ORDER BY c.rarity DESC,c.name", message.guild.id, message.author.id, row["slug"])
            text = "\n".join(f"{'✅' if c['quantity'] else '❌'} {card_emoji(c)} **{c['name']}** · ×{c['quantity']}" for c in cards)
            await message.channel.send(embed=notice(f"{row['name']} 🗂️", f"Progreso: **{sum(1 for c in cards if c['quantity']>0)}/{len(cards)}**\n\n{text}"))
            reward = await claim_set_reward(message.guild.id, message.author.id, row["slug"])
            if reward: await message.channel.send(embed=await card_message(message.guild.id, "set_complete", set_name=reward[0], reward=coins_text(reward[1])))
            return True
        if command == "saldo_cartas":
            await ensure_wallet(message.guild.id, message.author.id)
            coins = await db.fetchval("SELECT coins FROM card_wallets WHERE guild_id=$1 AND user_id=$2", message.guild.id, message.author.id)
            await message.channel.send(embed=notice("Tu saldo 💰", f"Tienes **{coins_text(coins)} Abo Coins**. Usa `!sobre` para abrir un sobre."))
            return True
        if command == "diario_cartas":
            now = datetime.now(timezone.utc)
            await ensure_wallet(message.guild.id, message.author.id)
            async with db._pool().acquire() as connection:
                async with connection.transaction():
                    wallet = await connection.fetchrow(
                        "SELECT coins, daily_claimed_at, daily_streak FROM card_wallets WHERE guild_id=$1 AND user_id=$2 FOR UPDATE",
                        message.guild.id, message.author.id)
                    if wallet["daily_claimed_at"] and wallet["daily_claimed_at"].date() == now.date():
                        await message.channel.send(embed=notice("Diario ya reclamado ⏳", "Vuelve mañana para recibir más Abo Coins.", 0xFEE75C)); return True
                    streak = wallet["daily_streak"] + 1 if wallet["daily_claimed_at"] and (now.date() - wallet["daily_claimed_at"].date()) == timedelta(days=1) else 1
                    reward = min(DAILY_BASE + (streak - 1) * 25, 500)
                    await connection.execute("UPDATE card_wallets SET coins=coins+$1,daily_claimed_at=$2,daily_streak=$3,updated_at=NOW() WHERE guild_id=$4 AND user_id=$5", reward, now, streak, message.guild.id, message.author.id)
            await message.channel.send(embed=notice("Recompensa diaria ✨", f"Recibiste **{coins_text(reward)} Abo Coins**. Racha: **{streak} días**." , 0x57F287))
            level, leveled = await award_xp(message.guild.id, message.author.id, XP_PER_DAILY)
            if leveled: await message.channel.send(embed=await card_message(message.guild.id, "level_up", level=level, xp=level * 1000))
            return True
        if command == "sobre":
            result, error, _ = await open_card_pack(message.guild.id, message.author.id)
            if error:
                await message.channel.send(embed=notice("No alcanzan las monedas 💸", error, 0xED4245)); return True
            lines = [f"{card_emoji(result['rows'][s])} {result['rows'][s]['rarity']} · **{result['rows'][s]['name']}**" for s in result["drawn"]]
            embed = await card_message(message.guild.id, "pack_opened", cards="\n".join(f"• {x}" for x in lines), balance=coins_text(result["balance"]))
            if result["forced"]:
                pity = await card_message(message.guild.id, "pity_epic" if result["forced"] == "epic" else "pity_rare")
                embed.add_field(name=pity.title, value=pity.description, inline=False)
            await message.channel.send(embed=embed)
            if result["leveled"]: await message.channel.send(embed=await card_message(message.guild.id, "level_up", level=result["level"], xp=result["level"] * 1000))
            return True
        if command == "coleccion":
            target = message.mentions[0] if message.mentions else message.author
            filter_name = re.sub(r"<@!?\d+>", "", argument).strip()
            rows = await collection_rows(message.guild.id, target.id, filter_name)
            embed, pages = collection_embed(target.display_name, rows, 0, filter_name)
            view = CollectionView(message.author.id, target.display_name, rows, filter_name) if pages > 1 else None
            await message.channel.send(embed=embed, view=view); return True
        if command == "carta":
            if not argument:
                await message.channel.send(embed=notice("Uso de !carta", "Ejemplo: `!carta Mielabo`.", 0xFEE75C)); return True
            row = await card_row(argument)
            if not row:
                await message.channel.send(embed=notice("Carta no encontrada", "Revisa el nombre e inténtalo de nuevo.", 0xED4245)); return True
            owned = await db.fetchval("SELECT quantity FROM card_inventory WHERE guild_id=$1 AND user_id=$2 AND card_slug=$3", message.guild.id, message.author.id, row["slug"]) or 0
            description = row.get("description") or "Conoce a este personaje de Abo."
            embed = notice(f"{card_emoji(row)} {row['name']}", description, int(row.get("embed_color") or rarity_color(row["rarity"])))
            embed.add_field(name="Rareza", value=row["rarity"], inline=True)
            embed.add_field(name="Valor", value=f"{coins_text(row['base_value'])} Abo Coins", inline=True)
            embed.add_field(name="Tu colección", value=f"×{owned}", inline=True)
            for field_name, field_value, inline in _combat_embed_fields(row):
                embed.add_field(name=field_name, value=field_value, inline=inline)
            path = ASSET_DIR / row["image_file"]
            if row.get("image_data"):
                filename = row["image_file"] or f"{row['slug']}.png"; embed.set_image(url=f"attachment://{filename}"); await message.channel.send(embed=embed, file=discord.File(io.BytesIO(bytes(row["image_data"])), filename=filename))
            elif path.is_file():
                embed.set_image(url=f"attachment://{path.name}"); await message.channel.send(embed=embed, file=discord.File(path, filename=path.name))
            else: await message.channel.send(embed=embed)
            return True
        if command == "mercado":
            rows = await db.fetch("SELECT l.id,l.seller_id,c.name,c.rarity,c.emoji_name,c.emoji_id,l.remaining,l.price_each FROM card_market_listings l JOIN card_catalog c ON c.slug=l.card_slug WHERE l.guild_id=$1 AND l.status='active' AND l.remaining>0 ORDER BY l.created_at DESC LIMIT 20", message.guild.id)
            description = "\n".join(f"**#{r['id']}** · {card_emoji(r)} {r['name']} ({r['rarity']}) · ×{r['remaining']} · **{coins_text(r['price_each'])}** c/u · Vendedor: <@{r['seller_id']}>" for r in rows) or "El mercado está vacío."
            await message.channel.send(embed=notice("Mercado de Abo Cards 🏪", description + "\n\nUsa los botones para comprar 1 copia o ver al vendedor."), view=MarketView(rows), allowed_mentions=discord.AllowedMentions(users=True)); return True
        if command == "ranking_cartas":
            rows = await db.fetch("SELECT i.user_id,SUM(i.quantity*c.base_value)::BIGINT AS value,SUM(i.quantity)::BIGINT AS total,COUNT(*)::INT AS unique_cards FROM card_inventory i JOIN card_catalog c ON c.slug=i.card_slug WHERE i.guild_id=$1 AND i.quantity>0 GROUP BY i.user_id ORDER BY value DESC,total DESC LIMIT 10", message.guild.id)
            lines = []
            for index,row in enumerate(rows,1):
                member=message.guild.get_member(row["user_id"]); lines.append(f"**{index}.** {member.display_name if member else row['user_id']} · {coins_text(row['value'])} valor · {row['unique_cards']} únicas")
            await message.channel.send(embed=notice("Ranking de coleccionistas 🏆", "\n".join(lines) or "Todavía no hay coleccionistas.")); return True
        return True

    def _trade_embed(self, session: dict, title: str, extra: str = "") -> discord.Embed:
        def offer_text(user_id: int) -> str:
            offer = session["offers"][user_id]
            if not offer:
                return "Nada"
            return "\n".join(f"• ×{data['quantity']} {data['emoji']} **{data['name']}**" for data in offer.values())
        embed = notice(title, extra, 0x5865F2)
        embed.add_field(name=f"Oferta de {session['name_a']}", value=offer_text(session["user_a"]), inline=True)
        embed.add_field(name=f"Oferta de {session['name_b']}", value=offer_text(session["user_b"]), inline=True)
        status = "✅" if session["confirmed"][session["user_a"]] else "⏳"
        status += "  " + ("✅" if session["confirmed"][session["user_b"]] else "⏳")
        embed.set_footer(text=f"Confirmaciones: {status} · Menciona a Abo con !confirmar o !cancelar")
        return embed

    async def _parse_trade_offer(self, text: str) -> dict:
        text = text.strip()
        if text.lower() in {"nada", "nada.", "ninguna", "ninguna.", "no", "ninguno", "-"}:
            return {}
        parts = [part.strip() for part in re.split(r"[,\n]+", text) if part.strip()]
        offer = {}
        for part in parts:
            match = re.match(r"^(\d+)\s*(?:x|×)?\s+(.+?)$", part, re.IGNORECASE)
            if match:
                quantity, card_name = int(match.group(1)), match.group(2).strip()
            else:
                quantity, card_name = 1, part
            if quantity < 1 or quantity > 999:
                raise ValueError("Las cantidades deben estar entre 1 y 999.")
            row = await card_row(card_name)
            if not row:
                raise ValueError(f"No encontré la carta **{card_name}**.")
            slug = row["slug"]
            if slug in offer:
                offer[slug]["quantity"] += quantity
            else:
                offer[slug] = {"quantity": quantity, "name": row["name"], "emoji": card_emoji(row)}
        return offer

    async def handle_trade_message(self, message: discord.Message) -> bool:
        session = self.trade_sessions.get(message.channel.id)
        if not session or message.author.id not in {session["user_a"], session["user_b"]}:
            return False
        content = re.sub(r"<@!?\d+>", "", message.content).strip()
        lowered = content.lower()
        if lowered in {"!cancelar", "!cancelado"}:
            self.trade_sessions.pop(message.channel.id, None)
            if session.get("trade_id"):
                await db.execute("UPDATE card_trade_sessions SET status='cancelled',completed_at=NOW() WHERE id=$1", session["trade_id"])
            await message.channel.send(embed=notice("Tradeo cancelado ❌", f"{message.author.mention} canceló el intercambio.", 0xED4245), allowed_mentions=discord.AllowedMentions(users=True))
            return True
        if lowered in {"!confirmar", "!confirmad", "!confirmado"}:
            offer = session["offers"][message.author.id]
            if not offer:
                # Nada es una oferta válida, pero se muestra qué debe hacer el usuario.
                session["offers"][message.author.id] = {}
            session["confirmed"][message.author.id] = True
            confirmation_column = "confirmed_a" if message.author.id == session["user_a"] else "confirmed_b"
            if session.get("trade_id"):
                await db.execute(f"UPDATE card_trade_sessions SET {confirmation_column}=TRUE WHERE id=$1", session["trade_id"])
            if all(session["confirmed"].values()):
                result = await self._complete_trade(session)
                if result:
                    self.trade_sessions.pop(message.channel.id, None)
                    await message.channel.send(embed=result, allowed_mentions=discord.AllowedMentions(users=True))
                else:
                    session["confirmed"] = {session["user_a"]: False, session["user_b"]: False}
                    if session.get("trade_id"):
                        await db.execute("UPDATE card_trade_sessions SET confirmed_a=FALSE,confirmed_b=FALSE WHERE id=$1", session["trade_id"])
                    await message.channel.send(embed=notice("Tradeo detenido ⚠️", "Uno de los dos usuarios ya no tiene las cartas ofrecidas. Las confirmaciones se reiniciaron.", 0xFEE75C))
            else:
                await message.channel.send(embed=self._trade_embed(session, "Confirmación recibida ✅", f"{message.author.mention} confirmó. Falta la confirmación del otro usuario."), allowed_mentions=discord.AllowedMentions(users=True))
            return True
        try:
            offer = await self._parse_trade_offer(content)
        except ValueError as error:
            await message.channel.send(embed=notice("Oferta no válida", f"{error}\nUsa `2 Mielabo, 1 Abo Pro`, una carta por línea o `nada`.", 0xED4245))
            return True
        session["offers"][message.author.id] = offer
        session["confirmed"] = {session["user_a"]: False, session["user_b"]: False}
        if session.get("trade_id"):
            offer_column = "offer_a" if message.author.id == session["user_a"] else "offer_b"
            payload = {slug: data["quantity"] for slug, data in offer.items()}
            await db.execute(f"UPDATE card_trade_sessions SET {offer_column}=$1::jsonb,confirmed_a=FALSE,confirmed_b=FALSE WHERE id=$2", __import__("json").dumps(payload), session["trade_id"])
        await message.channel.send(embed=self._trade_embed(session, "Oferta actualizada 🎴", f"Oferta de {message.author.mention} guardada. Las confirmaciones se reiniciaron."), allowed_mentions=discord.AllowedMentions(users=True))
        return True

    async def _complete_trade(self, session: dict):
        offers = session["offers"]
        async with db._pool().acquire() as connection:
            async with connection.transaction():
                checks = []
                for user_id in (session["user_a"], session["user_b"]):
                    for slug, data in offers[user_id].items():
                        checks.append((user_id, slug, data["quantity"]))
                for user_id, slug, quantity in sorted(checks):
                    owned = await connection.fetchval(
                        "SELECT quantity FROM card_inventory WHERE guild_id=$1 AND user_id=$2 AND card_slug=$3 FOR UPDATE",
                        session["guild_id"], user_id, slug,
                    ) or 0
                    if owned < quantity:
                        return None
                for sender, receiver in ((session["user_a"], session["user_b"]), (session["user_b"], session["user_a"])):
                    for slug, data in offers[sender].items():
                        await connection.execute(
                            "UPDATE card_inventory SET quantity=quantity-$1 WHERE guild_id=$2 AND user_id=$3 AND card_slug=$4",
                            data["quantity"], session["guild_id"], sender, slug,
                        )
                        await add_card(connection, session["guild_id"], receiver, slug, data["quantity"])
                if session.get("trade_id"):
                    await connection.execute("UPDATE card_trade_sessions SET status='completed',completed_at=NOW() WHERE id=$1", session["trade_id"])
                else:
                    await connection.execute("""INSERT INTO card_trade_sessions (guild_id,user_a,user_b,channel_id,offer_a,offer_b,status,completed_at)
                       VALUES ($1,$2,$3,$4,$5::jsonb,$6::jsonb,'completed',NOW())""", session["guild_id"], session["user_a"], session["user_b"], session.get("channel_id"), __import__("json").dumps({slug: data["quantity"] for slug, data in offers[session["user_a"]].items()}), __import__("json").dumps({slug: data["quantity"] for slug, data in offers[session["user_b"]].items()}))
        await award_xp(session["guild_id"], session["user_a"], 100)
        await award_xp(session["guild_id"], session["user_b"], 100)
        return notice("¡Tradeo completado! 🎉", f"{session['name_a']} y {session['name_b']} confirmaron el intercambio. Las cartas fueron transferidas correctamente.", 0x57F287)

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
        rows = await db.fetch("""SELECT l.id,l.seller_id,c.name,c.rarity,c.emoji_name,c.emoji_id,l.remaining,l.price_each FROM card_market_listings l JOIN card_catalog c ON c.slug=l.card_slug WHERE l.guild_id=$1 AND l.status='active' AND l.remaining>0 ORDER BY l.created_at DESC LIMIT 20""", interaction.guild_id)
        description = "\n".join(f"**#{r['id']}** · {card_emoji(r)} {r['name']} ({r['rarity']}) · ×{r['remaining']} · **{coins_text(r['price_each'])}** c/u · Vendedor: <@{r['seller_id']}>" for r in rows) or "El mercado está vacío."
        await interaction.response.send_message(embed=notice("Mercado de Abo Cards 🏪", description + "\n\nUsa los botones para comprar 1 copia o ver al vendedor."), view=MarketView(rows), allowed_mentions=discord.AllowedMentions(users=True))

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


    @app_commands.command(name="pelea", description="Desafía a otro usuario a una pelea carta contra carta")
    @app_commands.guild_only()
    async def pelea(self, interaction: discord.Interaction, usuario: discord.Member):
        if usuario.bot or usuario.id == interaction.user.id:
            return await interaction.response.send_message(embed=notice("Desafío inválido","Elige a otro usuario que no sea un bot.",0xED4245),ephemeral=True)
        active=await db.fetchrow("SELECT id FROM card_battles WHERE guild_id=$1 AND status='active' AND (user_a IN ($2,$3) OR user_b IN ($2,$3)) LIMIT 1",interaction.guild_id,interaction.user.id,usuario.id)
        if active: return await interaction.response.send_message(embed=notice("Ya hay una pelea activa","Uno de los usuarios ya está combatiendo.",0xED4245),ephemeral=True)
        await interaction.response.send_message(embed=notice("⚔️ Desafío de pelea",f"{interaction.user.mention} desafió a {usuario.mention}.\n\nAcepten para elegir un personaje de su colección."),view=BattleChallengeView(self,interaction.guild_id,interaction.user.id,usuario.id))

    async def prepare_battle(self,interaction,guild_id,user_a,user_b):
        choices=[]
        for user_id in (user_a,user_b):
            rows=await db.fetch("SELECT c.* FROM card_catalog c JOIN card_inventory i ON i.card_slug=c.slug AND i.guild_id=$1 AND i.user_id=$2 WHERE c.active=TRUE AND i.quantity>0 ORDER BY c.rarity DESC,c.name LIMIT 25",guild_id,user_id)
            if not rows: return await interaction.edit_original_response(embed=notice("No hay personajes disponibles",f"<@{user_id}> necesita una carta en su colección.",0xED4245),view=None)
            choices.append((user_id,rows))
        key=f"{guild_id}:{user_a}:{user_b}:{interaction.id}"
        self.battles[key]={"guild_id":guild_id,"channel_id":interaction.channel_id,"users":(user_a,user_b),"selected":{}}
        await interaction.edit_original_response(embed=notice("⚔️ Elige tu personaje",f"<@{user_a}> y <@{user_b}> deben escoger una carta."),view=BattleSetupView(self,key,choices))

    async def begin_battle(self,interaction,key):
        session=self.battles.get(key)
        if not session or session.get('started'): return
        players={}
        for user_id in session['users']:
            row=await db.fetchrow("SELECT * FROM card_catalog WHERE slug=$1 AND active=TRUE",session['selected'].get(user_id))
            if not row: return
            stats=combat_stats(row); hp=max(1,stat_num(stats,'HP',BATTLE_MAX_HP))
            players[user_id]={"id":user_id,"mention":f"<@{user_id}>","card":row,"max_hp":hp,"hp":hp,"energy":1,"defending":False,"states":{}}
        turn=max(players,key=lambda uid:stat_num(combat_stats(players[uid]['card']),'Speed',0))
        session.update({'started':True,'players':players,'turn':turn,'turns':0})
        rows=[players[x]['card'] for x in session['users']]
        session['db_id']=await db.fetchval("INSERT INTO card_battles (guild_id,channel_id,user_a,user_b,card_a,card_b) VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",session['guild_id'],session['channel_id'],*session['users'],rows[0]['slug'],rows[1]['slug'])
        await interaction.message.edit(embed=self.battle_embed(session,"¡La pelea comienza! ⚔️"),view=BattleView(self,key))

    def battle_embed(self,session,message):
        p1=session['players'][session['users'][0]]; p2=session['players'][session['users'][1]]
        embed=notice("⚔️ Pelea carta contra carta",f"{message}\n\n{battle_line(p1)}\n\n**VS**\n\n{battle_line(p2)}",0xE67E22)
        embed.add_field(name="Turno",value=f"{session['turns']+1} · juega <@{session['turn']}>",inline=False)
        return embed

    async def battle_action(self,interaction,key,action):
        session=self.battles.get(key)
        if not session: return
        actor=session['players'][session['turn']]; enemy_id=next(x for x in session['users'] if x!=session['turn']); enemy=session['players'][enemy_id]; stats=combat_stats(actor['card'])
        if action=='surrender': return await self.end_battle(interaction,key,enemy_id,f"{actor['mention']} se rindió. ¡Victoria para {enemy['mention']}!")
        message=''
        if action=='defend':
            actor['defending']=True; actor['energy']=min(5,actor['energy']+1); message=f"{actor['mention']} levantó la defensa y recuperó 1 ⚡."
        else:
            if action.startswith('ability'):
                try: ability_number=int(action.split(':',1)[1]) if ':' in action else 1
                except (ValueError, IndexError): ability_number=1
                suffix='' if ability_number==1 else f' {ability_number}'
                name=str(stats.get(f'Habilidad{suffix}','')).strip(); damage=damage_num(stats.get(f'Daño de habilidad{suffix}'))
                if not name or not damage: return await interaction.followup.send("Esta habilidad no tiene daño configurado.",ephemeral=True)
                if actor['energy']<2: return await interaction.followup.send("Necesitas 2 ⚡ para usar la habilidad.",ephemeral=True)
                actor['energy']-=2; label=f"✨ Habilidad {ability_number}: {name}"; effect=str(stats.get(f'Estado de habilidad{suffix}','')).strip(); chance=stat_num(stats,f'Probabilidad de efecto de habilidad{suffix}',0); duration=stat_num(stats,f'Duración de efecto de habilidad{suffix}',0)
            else:
                damage=max(1,stat_num(stats,'ATK',10)); label='⚔️ Ataque básico'; effect=''; chance=0; duration=0; actor['energy']=min(5,actor['energy']+1)
            defense=stat_num(combat_stats(enemy['card']),'DEF',0); damage=max(1,damage-defense//2)
            if enemy['defending']: damage=max(1,damage//2); enemy['defending']=False
            enemy['hp']=max(0,enemy['hp']-damage); applied=''
            if effect in BATTLE_STATES and chance and random.randint(1,100)<=chance: enemy['states'][effect]=max(1,duration); applied=effect
            message=f"{actor['mention']} usó **{label}** e hizo **{damage}** de daño"+(f" y aplicó **{applied}**." if applied else ".")
            await db.execute("INSERT INTO card_battle_logs (battle_id,turn_number,actor_id,action,damage,effect) VALUES ($1,$2,$3,$4,$5,$6)",session['db_id'],session['turns']+1,actor['id'],label,damage,applied)
        session['turns']+=1
        if enemy['hp']<=0: return await self.end_battle(interaction,key,actor['id'],message+f"\n💥 {enemy['mention']} quedó fuera de combate.")
        for player in (actor,enemy):
            for state in list(player['states']):
                if state in ('Quemadura','Veneno'): player['hp']=max(0,player['hp']-3)
                player['states'][state]-=1
                if player['states'][state]<=0: del player['states'][state]
        if enemy['hp']<=0: return await self.end_battle(interaction,key,actor['id'],message+"\n☠️ Un estado terminó el combate.")
        session['turn']=enemy_id
        await db.execute("UPDATE card_battles SET turns=$1 WHERE id=$2",session['turns'],session['db_id'])
        await interaction.edit_original_response(embed=self.battle_embed(session,message),view=BattleView(self,key))

    async def end_battle(self,interaction,key,winner_id,message):
        session=self.battles.get(key)
        if not session: return
        loser_id=next(x for x in session['users'] if x!=winner_id)
        await db.execute("UPDATE card_battles SET status='completed',winner_id=$1,loser_id=$2,turns=$3,result=$4::jsonb,completed_at=NOW() WHERE id=$5",winner_id,loser_id,session['turns'],json.dumps({'message':message}),session['db_id'])
        await interaction.edit_original_response(embed=self.battle_embed(session,message+"\n\n🏆 Pelea terminada."),view=None)
        self.battles.pop(key,None)
