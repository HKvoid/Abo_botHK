"""Abo Cards: colección social, sobres, economía, intercambio y mercado."""
from __future__ import annotations

import io
import json
import random
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from core import db, TU_ID

ASSET_DIR = Path(__file__).resolve().parent.parent / "assets" / "cards"
PACK_PRICE = 175
DAILY_BASE = 150
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

# Fusión: cuántas copias se necesitan para obtener la rareza superior
FUSION_RULES = {
    "Común":     {"copies": 3, "cost": 50,  "result": "Rara"},
    "Rara":      {"copies": 3, "cost": 150, "result": "Épica"},
    "Épica":     {"copies": 3, "cost": 300, "result": "Legendaria"},
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
    "glotonabo": ("GLOTONABO", "1560743838690054234"),
    "sueterabo": ("SUTERABO",  "1560743813142679683"),
    "tacosabo": ("TACOSABO", "1560743787309965393"),
    "starabo": ("STARABO", "1560743769433841665"),
    "sopabo": ("SOPABO", "1560743747933704192"),
    "abomaid": ("MAIDABO", "1560743731051630773"),
    "abosaurio": ("ABOSAURIO", "1560743712521199758"),
    "abojama": ("ABOJAMA", "1560743687561027624"),
    "encebollabo": ("ENCEBOLLABO", "1564292065678856374"),
    "abocado": ("ABOCADO", "1564292138915594260"),
    "sandiabo": ("SANDIABO", "1564292200597159997"),
    "abo_jedi": ("ABOJEDI", "1564292246432514199"),
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
    ("abojama", "Abojama", "Común", "abojama.png", 42, 100),
    ("abomaid", "Abomaid", "Rara", "abomaid.png", 22, 250),
    ("abosaurio", "Abosaurio", "Épica", "abosaurio.png", 10, 500),
    ("encebollabo", "Encebollabo", "Común", "encebollabo.png", 42, 100),
    ("abocado", "Abocado", "Común", "abocado.png", 42, 100),
    ("sandiabo", "Sandiabo", "Rara", "sandiabo.png", 22, 250),
    ("abo_jedi", "Abo Jedi", "Legendaria", "abo_jedi.png", 4, 1000),
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
    "Costo de energía de habilidad",
    "Costo de energía de habilidad 2",
    "Costo de energía de habilidad 3",
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
        energy_cost = value(f"Costo de energía de habilidad{suffix}", "2")

        lines = []
        # Primera línea: daño + tipo + costo de energía
        dmg_parts = []
        if dmg != "—": dmg_parts.append(f"💥 **{dmg}**")
        if dmg_type != "—": dmg_parts.append(f"{TYPE_ICONS.get(dmg_type, '')} {dmg_type}")
        dmg_parts.append(f"⚡ {energy_cost}")
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
           ON CONFLICT (slug) DO NOTHING""",
        __import__("json").dumps(rows),
    )
    migrated = await db.fetchval("SELECT migration_key FROM schema_migrations WHERE migration_key='character_pixel_assets_v1'")
    if not migrated:
        await db.execute("UPDATE card_catalog SET image_data=NULL,image_mime=''" )
        await db.execute("INSERT INTO schema_migrations (migration_key) VALUES ('character_pixel_assets_v1') ON CONFLICT DO NOTHING")


def card_emoji(row) -> str:
    name = (row.get("emoji_name") or "").strip()
    eid  = (row.get("emoji_id")   or "").strip()
    if name and eid:
        return f"<:{name}:{eid}>"
    # Fallback: buscar en el dict hardcodeado por slug
    slug = (row.get("slug") or "").strip()
    if slug and slug in EMOJI_BY_SLUG:
        fallback_name, fallback_id = EMOJI_BY_SLUG[slug]
        return f"<:{fallback_name}:{fallback_id}>"
    return RARITY_EMOJI.get(row.get("rarity"), "🎴")


async def collection_rows(guild_id: int, user_id: int, filter_name: str = ""):
    """Obtiene la colección global del usuario; guild_id se conserva por compatibilidad."""
    filter_name = (filter_name or "").strip().lower()
    if filter_name in {"faltantes", "faltante"}:
        return await db.fetch("""SELECT c.name,c.rarity,c.emoji_name,c.emoji_id,0::int AS quantity,c.base_value
            FROM card_catalog c WHERE c.active=TRUE AND NOT EXISTS
            (SELECT 1 FROM card_inventory_global i WHERE i.user_id=$1 AND i.card_slug=c.slug AND i.quantity>0)
            ORDER BY c.rarity DESC,c.name""", user_id)
    extra = ""
    args = [user_id]
    if filter_name in {"comun", "común", "rara", "epica", "épica", "legendaria"}:
        extra = " AND c.rarity=$2"
        args.append({"comun":"Común","común":"Común","rara":"Rara","epica":"Épica","épica":"Épica","legendaria":"Legendaria"}[filter_name])
    elif filter_name in {"repetidas", "repetida"}:
        extra = " AND i.quantity>1"
    return await db.fetch(f"""SELECT c.name,c.rarity,c.emoji_name,c.emoji_id,i.quantity,c.base_value
        FROM card_inventory_global i JOIN card_catalog c ON c.slug=i.card_slug
        WHERE i.user_id=$1 AND i.quantity>0{extra}
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
            buyer = await connection.fetchrow("SELECT coins FROM card_wallets_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 FOR UPDATE", guild_id, user_id)
            if not buyer or buyer["coins"] < total:
                return None, f"Necesitas **{coins_text(total)} Abo Coins**."
            await connection.execute("UPDATE card_wallets_global SET coins=coins-$1,updated_at=NOW() WHERE ($2::BIGINT IS NOT NULL) AND user_id=$3", total, guild_id, user_id)
            await connection.execute("INSERT INTO card_wallets_global (guild_id,user_id) VALUES ($1,$2) ON CONFLICT DO NOTHING", guild_id, listing["seller_id"])
            await connection.execute("UPDATE card_wallets_global SET coins=coins+$1,updated_at=NOW() WHERE ($2::BIGINT IS NOT NULL) AND user_id=$3", total, guild_id, listing["seller_id"])
            await add_card(connection, guild_id, user_id, listing["card_slug"], quantity)
            remaining = listing["remaining"] - quantity
            await connection.execute("UPDATE card_market_listings SET remaining=$1,status=CASE WHEN $1=0 THEN 'sold' ELSE status END WHERE id=$2", remaining, listing_id)
            card = await connection.fetchrow("SELECT name,rarity,emoji_name,emoji_id FROM card_catalog WHERE slug=$1", listing["card_slug"])
    return {"card": card, "quantity": quantity, "total": total, "seller_id": listing["seller_id"]}, None


async def cancel_listing(guild_id: int, user_id: int, listing_id: int):
    async with db._pool().acquire() as connection:
        async with connection.transaction():
            listing = await connection.fetchrow(
                "SELECT * FROM card_market_listings WHERE id=$1 AND guild_id=$2 AND seller_id=$3 AND status='active' FOR UPDATE",
                listing_id, guild_id, user_id,
            )
            if not listing:
                return None, "La publicación no existe, no es tuya o ya terminó."
            if listing["remaining"] > 0:
                await add_card(connection, guild_id, user_id, listing["card_slug"], listing["remaining"])
            await connection.execute(
                "UPDATE card_market_listings SET remaining=0,status='cancelled' WHERE id=$1", listing_id
            )
            return int(listing["remaining"]), None


class CardService:
    """Capa compartida para que slash, prefijo y botones usen las mismas operaciones."""

    collection = staticmethod(collection_rows)
    purchase_listing = staticmethod(purchase_listing)


MARKET_PAGE_SIZE = 5


def _market_header(rows, page: int) -> str:
    total_pages = max(1, (len(rows) + MARKET_PAGE_SIZE - 1) // MARKET_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    return (
        "## Mercado de Abo Cards 🏪\n"
        "Compra cada publicación con el botón que aparece dentro de su propia tarjeta.\n"
        f"Página **{page + 1}/{total_pages}**"
    )


async def _market_seller_names(rows, guild):
    """Añade nombres legibles sin crear menciones en el mensaje del mercado."""
    for index, row in enumerate(rows):
        # asyncpg.Record no permite asignaciones directas; usamos un dict para
        # conservar la fila y añadir el nombre legible del vendedor.
        row = dict(row)
        rows[index] = row
        member = guild.get_member(row["seller_id"]) if guild else None
        if member is None and guild:
            try:
                member = await guild.fetch_member(row["seller_id"])
            except (discord.NotFound, discord.HTTPException):
                member = None
        row["seller_name"] = member.display_name if member else "Vendedor"
    return rows


class MarketView(discord.ui.LayoutView):
    """Mercado en Components V2: cada botón es accesorio de su propia sección."""

    def __init__(self, rows, page: int = 0):
        super().__init__(timeout=180)
        self.rows = rows
        self.page = page
        self._build()

    def _build(self):
        self.clear_items()
        total_pages = max(1, (len(self.rows) + MARKET_PAGE_SIZE - 1) // MARKET_PAGE_SIZE)
        chunk = self.rows[self.page * MARKET_PAGE_SIZE:(self.page + 1) * MARKET_PAGE_SIZE]
        children = [discord.ui.TextDisplay(_market_header(self.rows, self.page))]
        if not chunk:
            children.append(discord.ui.TextDisplay("El mercado está vacío."))
        for index, row in enumerate(chunk, 1):
            buy = discord.ui.Button(
                label="Comprar", emoji="🛒", style=discord.ButtonStyle.success,
                custom_id=f"market_buy:{row['id']}",
            )
            buy.callback = self._buy_callback(row["id"])
            details = discord.ui.TextDisplay(
                f"### {card_emoji(row)} {index}. {row['name']}\n"
                f"**{row['rarity']}** · **×{row['remaining']}** disponibles\n"
                f"🪙 **{coins_text(row['price_each'])}** c/u · Vendedor: **{row.get('seller_name', 'Vendedor')}**"
            )
            children.append(discord.ui.Section(details, accessory=buy))
            if index < len(chunk):
                children.append(discord.ui.Separator())
        prev_btn = discord.ui.Button(
            label="Anterior", emoji="◀️", style=discord.ButtonStyle.secondary,
            disabled=self.page <= 0, custom_id="market_prev",
        )
        next_btn = discord.ui.Button(
            label="Siguiente", emoji="▶️", style=discord.ButtonStyle.primary,
            disabled=self.page >= total_pages - 1, custom_id="market_next",
        )
        prev_btn.callback = self._prev_callback()
        next_btn.callback = self._next_callback()
        children.extend((discord.ui.Separator(), discord.ui.ActionRow(prev_btn, next_btn)))
        self.add_item(discord.ui.Container(*children, accent_color=0x5865F2))

    def _buy_callback(self, listing_id):
        async def callback(interaction: discord.Interaction):
            result, error = await CardService.purchase_listing(
                interaction.guild_id, interaction.user.id, listing_id
            )
            if error:
                return await interaction.response.send_message(
                    embed=notice("Compra no realizada", error, 0xED4245), ephemeral=True
                )
            await interaction.response.send_message(
                embed=notice(
                    "Compra completada 🛒",
                    f"Compraste **×{result['quantity']} {card_emoji(result['card'])} "
                    f"{result['card']['name']}** por **{coins_text(result['total'])} Abo Coins**.",
                ),
                ephemeral=True,
            )
        return callback

    def _prev_callback(self):
        async def callback(interaction: discord.Interaction):
            self.page = max(0, self.page - 1)
            self._build()
            await interaction.response.edit_message(view=self)
        return callback

    def _next_callback(self):
        async def callback(interaction: discord.Interaction):
            total_pages = max(1, (len(self.rows) + MARKET_PAGE_SIZE - 1) // MARKET_PAGE_SIZE)
            self.page = min(total_pages - 1, self.page + 1)
            self._build()
            await interaction.response.edit_message(view=self)
        return callback


async def ensure_wallet(guild_id: int, user_id: int) -> None:
    await db.execute(
        "INSERT INTO card_wallets_global (guild_id, user_id) VALUES ($1,$2) ON CONFLICT DO NOTHING",
        guild_id, user_id,
    )


async def card_row(slug: str):
    value = slug.strip()
    return await db.fetchrow("SELECT * FROM card_catalog WHERE active=TRUE AND (slug=$1 OR name ILIKE $2)", value.lower(), value)


async def add_card(connection, guild_id: int, user_id: int, slug: str, quantity: int = 1) -> None:
    await connection.execute(
        """INSERT INTO card_inventory_global (guild_id,user_id,card_slug,quantity)
           VALUES ($1,$2,$3,$4) ON CONFLICT (user_id,card_slug) DO UPDATE
           SET quantity=card_inventory_global.quantity+EXCLUDED.quantity""",
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
            """UPDATE card_wallets_global
               SET xp = xp + $3,
                   level = GREATEST(level, (xp + $3) / 1000 + 1),
                   updated_at = NOW()
               WHERE ($1::BIGINT IS NOT NULL) AND user_id = $2
               RETURNING xp, level,
                         (level > (xp - $3) / 1000 + 1) AS just_leveled_up""",
            guild_id, user_id, amount,
        )
        if row is None:
            # Wallet no existe todavía; la creamos con el XP inicial.
            row = await connection.fetchrow(
                """INSERT INTO card_wallets_global (guild_id, user_id, xp, level)
                   VALUES ($1, $2, $3, $4)
                   ON CONFLICT (user_id) DO UPDATE
                   SET xp = card_wallets_global.xp + $3,
                       level = GREATEST(card_wallets_global.level, (card_wallets_global.xp + $3) / 1000 + 1),
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
        LEFT JOIN card_inventory_global i ON i.card_slug=c.slug AND ($1::BIGINT IS NOT NULL) AND i.user_id=$2 WHERE s.slug=$3 GROUP BY s.name,s.reward_coins""", guild_id, user_id, set_slug)
    if not status or status["total"] == 0 or status["owned"] < status["total"]:
        return None
    inserted = await db.fetchval("INSERT INTO card_set_claims_global (guild_id,user_id,set_slug) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING RETURNING set_slug", guild_id, user_id, set_slug)
    if not inserted:
        return None
    reward = status["reward_coins"]
    await ensure_wallet(guild_id, user_id)
    await db.execute("UPDATE card_wallets_global SET coins=coins+$1,updated_at=NOW() WHERE ($2::BIGINT IS NOT NULL) AND user_id=$3", reward, guild_id, user_id)
    await award_xp(guild_id, user_id, 500)
    return status["name"], reward


async def open_card_pack(guild_id: int, user_id: int):
    await ensure_wallet(guild_id, user_id)
    async with db._pool().acquire() as connection:
        async with connection.transaction():
            wallet = await connection.fetchrow("SELECT * FROM card_wallets_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 FOR UPDATE", guild_id, user_id)
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
            await connection.execute("UPDATE card_wallets_global SET coins=coins-$1,pity_rare=$2,pity_epic=$3,packs_opened=packs_opened+1,updated_at=NOW() WHERE ($4::BIGINT IS NOT NULL) AND user_id=$5", PACK_PRICE, rare_count, epic_count, guild_id, user_id)
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
    s=str(value or "")
    rng=re.search(r"(\d+)\s*[-–]\s*(\d+)",s)
    if rng: return random.randint(int(rng.group(1)),int(rng.group(2)))
    match=re.search(r"\d+(?:\.\d+)?",s)
    return int(float(match.group(0))) if match else default

def battle_line(player):
    states=", ".join(f"{key}({value})" for key,value in player["states"].items()) or "sin estados"
    line=f"**{player['mention']}** · {card_emoji(player['card'])} **{player['card']['name']}**\n❤️ {player['hp']}/{player['max_hp']} HP · ⚡ {player['energy']}/5 · {states}"
    bench=[f for f in (player.get('team') or []) if f is not player]
    if bench:
        line+="\n🪑 Banca: "+" · ".join(f"{f['card']['name']} "+("💀" if f['hp']<=0 else f"{f['hp']}/{f['max_hp']}") for f in bench)
    return line

class BattleChallengeView(discord.ui.View):
    def __init__(self,cog,guild_id,challenger,opponent,mode="1v1"):
        super().__init__(timeout=360); self.cog=cog; self.guild_id=guild_id; self.challenger=challenger; self.opponent=opponent; self.mode=mode
    @discord.ui.button(label="Aceptar pelea",emoji="⚔️",style=discord.ButtonStyle.success)
    async def accept(self,interaction,button):
        if interaction.user.id!=self.opponent: return await interaction.response.send_message("Solo el usuario desafiado puede aceptar.",ephemeral=True)
        await interaction.response.defer()
        await self.cog.prepare_battle(interaction,self.guild_id,self.challenger,self.opponent,self.mode)
        self.stop()
    @discord.ui.button(label="Rechazar",emoji="✖️",style=discord.ButtonStyle.danger)
    async def reject(self,interaction,button):
        if interaction.user.id!=self.opponent: return await interaction.response.send_message("Solo el usuario desafiado puede rechazar.",ephemeral=True)
        await interaction.response.edit_message(embed=notice("Pelea cancelada","El desafío fue rechazado.",0xED4245),view=None); self.stop()


BATTLE_TEAM_SIZE = 3

class BattleChoice(discord.ui.Select):
    def __init__(self,cog,key,user_id,rows,team_size):
        options=[]
        for row in rows[:25]:
            quantity = int(row.get('owned_quantity') or 0)
            label = f"{row['name']} · {row['rarity']}"[:100]
            description = f"Tienes ×{quantity} · Seleccionable para este combate"[:100]
            options.append(discord.SelectOption(label=label, value=row['slug'], description=description))
        size=min(team_size,len(options))
        label = "carta" if size == 1 else "cartas"
        super().__init__(placeholder=f"Elige {size} {label}...",min_values=size,max_values=size,options=options); self.cog=cog; self.key=key; self.user_id=user_id
    async def callback(self,interaction):
        if interaction.user.id!=self.user_id: return await interaction.response.send_message("Este selector no es para ti.",ephemeral=True)
        session=self.cog.battles.get(self.key)
        if not session: return await interaction.response.send_message("La pelea ya terminó.",ephemeral=True)
        session['selected'][self.user_id]=list(self.values)
        await interaction.response.defer()
        if len(session['selected'])==2:
            await self.cog.begin_battle(interaction,self.key)
        else:
            await interaction.followup.send(f"Equipo elegido: **{', '.join(self.values)}**. Esperando al rival...",ephemeral=True)

class BattleSetupView(discord.ui.View):
    def __init__(self,cog,key,choices):
        super().__init__(timeout=360)
        for user_id,rows,team_size in choices: self.add_item(BattleChoice(cog,key,user_id,rows,team_size))

class AbilityChoice(discord.ui.Select):
    def __init__(self, cog, key, user_id, stats):
        options=[]
        for number in range(1,4):
            suffix="" if number==1 else f" {number}"
            name=str(stats.get(f"Habilidad{suffix}","")).strip()
            if name:
                skill_cost_display = max(1, int(stats.get(f'Costo de energía de habilidad{suffix}') or 2))
                options.append(discord.SelectOption(label=f"Habilidad {number}: {name}"[:100], value=str(number), description=f"Daño: {stats.get(f'Daño de habilidad{suffix}', '—')} · ⚡ {skill_cost_display}"[:100]))
        super().__init__(placeholder="Elige una habilidad...", options=options)
        self.cog=cog; self.key=key; self.user_id=user_id
    async def callback(self, interaction):
        session=self.cog.battles.get(self.key)
        if not session or interaction.user.id!=session['turn']:
            return await interaction.response.send_message("No puedes elegir una habilidad en este momento.",ephemeral=True)
        await interaction.response.defer()
        await self.cog.battle_action(interaction,self.key,f"ability:{self.values[0]}")

class AbilityChoiceView(discord.ui.View):
    def __init__(self,cog,key,user_id,stats,message=None):
        super().__init__(timeout=30)
        self.cog, self.key, self.message = cog, key, message
        self.add_item(AbilityChoice(cog,key,user_id,stats))

    async def on_timeout(self):
        session = self.cog.battles.get(self.key)
        if not session or not self.message:
            return
        try:
            await self.message.edit(embed=self.cog.battle_embed(session, "El menú expiró; elige otra acción."), view=BattleView(self.cog, self.key))
        except (discord.NotFound, discord.HTTPException):
            pass

class SwitchChoice(discord.ui.Select):
    def __init__(self, cog, key, user_id, bench):
        options=[discord.SelectOption(label=str(f['card']['name'])[:100], value=str(i), description=f"❤️ {f['hp']}/{f['max_hp']} HP · {f['card']['rarity']}"[:100]) for i,f in bench]
        super().__init__(placeholder="Elige la carta que entra...", options=options)
        self.cog=cog; self.key=key; self.user_id=user_id
    async def callback(self, interaction):
        session=self.cog.battles.get(self.key)
        if not session or interaction.user.id!=session['turn']:
            return await interaction.response.send_message("No puedes cambiar de carta en este momento.",ephemeral=True)
        await interaction.response.defer()
        await self.cog.battle_action(interaction,self.key,f"switch:{self.values[0]}")

class SwitchChoiceView(discord.ui.View):
    def __init__(self, cog, key, user_id, bench, message):
        super().__init__(timeout=120)
        self.cog=cog; self.key=key; self.message=message
        self.add_item(SwitchChoice(cog,key,user_id,bench))
    @discord.ui.button(label="Volver",emoji="↩️",style=discord.ButtonStyle.secondary)
    async def back(self, interaction, button):
        session=self.cog.battles.get(self.key)
        if not session: return await interaction.response.send_message("La pelea ya terminó.",ephemeral=True)
        if interaction.user.id!=session['turn']: return await interaction.response.send_message("No es tu turno.",ephemeral=True)
        await interaction.response.edit_message(embed=self.cog.battle_embed(session,"Elige tu acción."),view=BattleView(self.cog,self.key))
        self.stop()
    async def on_timeout(self):
        session=self.cog.battles.get(self.key)
        if not session: return
        try: await self.message.edit(embed=self.cog.battle_embed(session,"Elige tu acción."),view=BattleView(self.cog,self.key))
        except Exception: pass

BATTLE_TURN_TIMEOUT = 360  # 6 min sin acción; no limita la duración total
BATTLE_REWARD = 50        # Abo Coins que gana el vencedor


class RematchView(discord.ui.View):
    """Botón de revancha que aparece al terminar una pelea."""

    def __init__(self, cog, finished_session: dict, winner_id: int, loser_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild_id    = finished_session['guild_id']
        self.channel_id  = finished_session['channel_id']
        self.winner_id   = winner_id
        self.loser_id    = loser_id
        # Guardamos las cartas usadas para la revancha
        self.cards_used  = {uid: [f['card']['slug'] for f in finished_session['teams'][uid]]
                            for uid in finished_session['users']}
        self.users       = finished_session['users']
        self.mode        = finished_session.get('mode', '1v1')
        self.is_rematch  = True
        self.accepted    = set()
        self._message_id: int | None = None  # se rellena al enviar el embed final

    @discord.ui.button(label="⚔️ Revancha", style=discord.ButtonStyle.danger)
    async def rematch(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.users:
            return await interaction.response.send_message("Solo los participantes pueden pedir revancha.", ephemeral=True)
        self.accepted.add(interaction.user.id)
        if len(self.accepted) < 2:
            other_id = next(x for x in self.users if x != interaction.user.id)
            await interaction.response.send_message(
                f"Revancha solicitada. Esperando a <@{other_id}>…", ephemeral=True
            )
            return
        # Ambos aceptaron — iniciar nueva sesión con las mismas cartas
        self.stop()
        # Usar un key único (igual que prepare_battle usa interaction.id) para evitar colisiones
        key = f"{self.guild_id}:{self.users[0]}:{self.users[1]}:{interaction.id}"
        self.cog.battles[key] = {
            'guild_id':   self.guild_id,
            'channel_id': self.channel_id,
            'users':      self.users,
            'selected':   dict(self.cards_used),
            'mode':       getattr(self, 'mode', '1v1'),
            'started':    False,
            '_rematch_message_id': self._message_id,  # usado por begin_battle
        }
        await interaction.response.defer()
        await self.cog.begin_battle_rematch(interaction, key)

    async def on_timeout(self):
        # Deshabilitar el botón cuando expira
        for item in self.children:
            item.disabled = True
        self.stop()

class BattleView(discord.ui.View):
    def __init__(self,cog,key):
        session = cog.battles.get(key)
        idle = time.monotonic() - session.get("last_action_at", time.monotonic()) if session else BATTLE_TURN_TIMEOUT
        super().__init__(timeout=max(1, BATTLE_TURN_TIMEOUT - idle)); self.cog=cog; self.key=key
    async def on_timeout(self):
        session=self.cog.battles.get(self.key)
        if not session: return
        # Las vistas antiguas pueden expirar después de que se haya creado otra.
        # Solo se cancela si han pasado seis minutos desde la última acción real.
        if time.monotonic() - session.get("last_action_at", time.monotonic()) < BATTLE_TURN_TIMEOUT:
            return
        self.cog.battles.pop(self.key,None)
        turn_mention=f"<@{session['turn']}>"
        if session.get('db_id'):
            try: await db.execute("UPDATE card_battles SET status='cancelled',completed_at=NOW() WHERE id=$1",session['db_id'])
            except Exception: pass
        try:
            guild=self.cog.bot.get_guild(session['guild_id'])
            channel=guild.get_channel(session['channel_id']) if guild else None
            msg_id=session.get('battle_message_id')
            if channel and msg_id:
                p1=session['players'][session['users'][0]]; p2=session['players'][session['users'][1]]
                embed=notice("⚔️ Pelea " + ("3v3 · equipos de cartas" if session.get('mode') == '3v3' else "1v1 · carta contra carta"),
                    f"⏰ Pelea anulada por inactividad.\n{turn_mention} no actuó a tiempo.\n\n{battle_line(p1)}\n\n**VS**\n\n{battle_line(p2)}",
                    0x95A5A6)
                embed.add_field(name="Resultado",value="Anulada · Sin ganador",inline=False)
                msg=channel.get_partial_message(msg_id)
                await msg.edit(embed=embed,view=None)
        except Exception: pass
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
        actor=session['players'][session['turn']]
        if 'Silencio' in actor['states']: return await interaction.response.send_message("🔇 Estás en **Silencio** y no puedes usar habilidades este turno.",ephemeral=True)
        stats=combat_stats(actor['card'])
        available=[n for n in range(1,4) if str(stats.get("Habilidad" if n==1 else f"Habilidad {n}","")).strip()]
        if not available: return await interaction.response.send_message("Esta carta no tiene habilidades configuradas.",ephemeral=True)
        if len(available)==1:
            await interaction.response.defer(); await self.cog.battle_action(interaction,self.key,f"ability:{available[0]}")
        else:
            await interaction.response.edit_message(embed=notice("✨ Elige una habilidad","Selecciona qué habilidad quieres utilizar. Esto todavía no consume tu turno."),view=AbilityChoiceView(self.cog,self.key,interaction.user.id,stats,interaction.message))
    @discord.ui.button(label="Defender",emoji="🛡️",style=discord.ButtonStyle.secondary)
    async def defend(self,interaction,button): await self.act(interaction,"defend")
    @discord.ui.button(label="Cambiar",emoji="🔄",style=discord.ButtonStyle.secondary)
    async def switch(self,interaction,button):
        session=self.cog.battles.get(self.key)
        if not session: return await interaction.response.send_message("La pelea ya terminó.",ephemeral=True)
        if interaction.user.id!=session['turn']: return await interaction.response.send_message("No es tu turno.",ephemeral=True)
        actor=session['players'][session['turn']]
        bench=[(i,f) for i,f in enumerate(session['teams'][session['turn']]) if f is not actor and f['hp']>0]
        if not bench: return await interaction.response.send_message("No tienes más cartas disponibles para cambiar.",ephemeral=True)
        await interaction.response.edit_message(embed=notice("🔄 Cambiar de carta","Elige qué carta entra al combate. Cambiar es **gratis** y no consume tu turno; la energía se conserva."),view=SwitchChoiceView(self.cog,self.key,interaction.user.id,bench,interaction.message))
    @discord.ui.button(label="Rendirse",emoji="🏳️",style=discord.ButtonStyle.danger)
    async def surrender(self,interaction,button): await self.act(interaction,"surrender")

# ─────────────────────────────────────────────────────────────────────────────
# COMPARAR COLECCIONES
# ─────────────────────────────────────────────────────────────────────────────

def _comparison_stats(rows, side):
    quantity_key = "qty_a" if side == "a" else "qty_b"
    return len(rows), sum(r[quantity_key] for r in rows), sum(r[quantity_key] * r.get("base_value", 0) for r in rows)


def comparison_embed(owner_name, other_name, solo_a, solo_b, ambos, section="solo_a", page=0):
    sections = {
        "solo_a": (f"Solo {owner_name}", solo_a),
        "solo_b": (f"Solo {other_name}", solo_b),
        "ambos": ("En común", ambos),
    }
    title, rows = sections[section]
    per_page = 8
    total_pages = max(1, (len(rows) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    chunk = rows[page * per_page:(page + 1) * per_page]

    if section == "solo_a":
        lines = [f"{card_emoji(r)} **{r['name']}** · {r['rarity']} · ×{r['qty_a']}" for r in chunk]
    elif section == "solo_b":
        lines = [f"{card_emoji(r)} **{r['name']}** · {r['rarity']} · ×{r['qty_b']}" for r in chunk]
    else:
        lines = [f"{card_emoji(r)} **{r['name']}** · {r['rarity']} · {owner_name}: ×{r['qty_a']} · {other_name}: ×{r['qty_b']}" for r in chunk]
    description = "\n".join(lines) or "No hay cartas en esta sección."
    embed = notice(f"Comparación de colecciones 🔍 · {title}", description, 0x5865F2)

    unique_a, copies_a, value_a = _comparison_stats(solo_a + ambos, "a")
    unique_b, copies_b, value_b = _comparison_stats(solo_b + ambos, "b")
    embed.add_field(name=f"{owner_name}", value=f"Únicas: **{unique_a}**\nCopias: **{copies_a}**\nValor: **{coins_text(value_a)}**", inline=True)
    embed.add_field(name=f"{other_name}", value=f"Únicas: **{unique_b}**\nCopias: **{copies_b}**\nValor: **{coins_text(value_b)}**", inline=True)
    embed.add_field(name="Resumen", value=f"Solo {owner_name}: **{len(solo_a)}**\nSolo {other_name}: **{len(solo_b)}**\nEn común: **{len(ambos)}**", inline=True)
    embed.set_footer(text=f"Página {page + 1}/{total_pages} · Sección: {title}")
    return embed, total_pages


class ComparisonView(discord.ui.View):
    def __init__(self, owner_id, owner_name, other_name, solo_a, solo_b, ambos):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.owner_name = owner_name
        self.other_name = other_name
        self.sections = {"solo_a": solo_a, "solo_b": solo_b, "ambos": ambos}
        self.section = "solo_a"
        self.page = 0
        self._sync()

    def _sync(self):
        total_pages = max(1, (len(self.sections[self.section]) + 7) // 8)
        self.previous.disabled = self.page <= 0
        self.next.disabled = self.page >= total_pages - 1
        self.only_a.style = discord.ButtonStyle.primary if self.section == "solo_a" else discord.ButtonStyle.secondary
        self.only_b.style = discord.ButtonStyle.primary if self.section == "solo_b" else discord.ButtonStyle.secondary
        self.shared.style = discord.ButtonStyle.primary if self.section == "ambos" else discord.ButtonStyle.secondary

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Solo quien inició la comparación puede usar estos botones.", ephemeral=True)
            return False
        return True

    async def _change_section(self, interaction, section):
        self.section = section
        self.page = 0
        self._sync()
        embed, _ = comparison_embed(self.owner_name, self.other_name, self.sections["solo_a"], self.sections["solo_b"], self.sections["ambos"], self.section, self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Solo tú", style=discord.ButtonStyle.primary, row=0)
    async def only_a(self, interaction, button):
        await self._change_section(interaction, "solo_a")

    @discord.ui.button(label="Solo el otro", style=discord.ButtonStyle.secondary, row=0)
    async def only_b(self, interaction, button):
        await self._change_section(interaction, "solo_b")

    @discord.ui.button(label="En común", style=discord.ButtonStyle.secondary, row=0)
    async def shared(self, interaction, button):
        await self._change_section(interaction, "ambos")

    @discord.ui.button(label="Anterior", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def previous(self, interaction, button):
        self.page -= 1
        self._sync()
        embed, _ = comparison_embed(self.owner_name, self.other_name, self.sections["solo_a"], self.sections["solo_b"], self.sections["ambos"], self.section, self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Siguiente", emoji="▶️", style=discord.ButtonStyle.primary, row=1)
    async def next(self, interaction, button):
        self.page += 1
        self._sync()
        embed, _ = comparison_embed(self.owner_name, self.other_name, self.sections["solo_a"], self.sections["solo_b"], self.sections["ambos"], self.section, self.page)
        await interaction.response.edit_message(embed=embed, view=self)


async def compare_collections(guild_id: int, user_a: int, user_b: int):
    """Devuelve (solo_a, solo_b, ambos) con cantidades y valor base."""
    rows = await db.fetch(
        """SELECT c.slug, c.name, c.rarity, c.emoji_name, c.emoji_id, c.base_value,
                  COALESCE(a.quantity, 0)::int AS qty_a,
                  COALESCE(b.quantity, 0)::int AS qty_b
           FROM card_catalog c
           LEFT JOIN card_inventory_global a ON a.card_slug=c.slug AND a.user_id=$1 AND a.quantity>0
           LEFT JOIN card_inventory_global b ON b.card_slug=c.slug AND b.user_id=$2 AND b.quantity>0
           WHERE c.active=TRUE
           ORDER BY c.rarity DESC, c.name""",
        user_a, user_b,
    )
    solo_a = [r for r in rows if r["qty_a"] > 0 and r["qty_b"] == 0]
    solo_b = [r for r in rows if r["qty_b"] > 0 and r["qty_a"] == 0]
    ambos = [r for r in rows if r["qty_a"] > 0 and r["qty_b"] > 0]
    return solo_a, solo_b, ambos


# ─────────────────────────────────────────────────────────────────────────────
# FUSIÓN
# ─────────────────────────────────────────────────────────────────────────────

class FusionConfirmView(discord.ui.View):
    """Botones de confirmación para la fusión."""

    def __init__(self, guild_id: int, user_id: int, card_row_data, result_slug: str,
                 result_row, copies: int, cost: int):
        super().__init__(timeout=60)
        self.guild_id = guild_id
        self.user_id = user_id
        self.card_row_data = card_row_data
        self.result_slug = result_slug
        self.result_row = result_row
        self.copies = copies
        self.cost = cost
        self.done = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Solo tú puedes confirmar esta fusión.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Fusionar ✨", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.done:
            return
        self.done = True
        self.stop()

        async with db._pool().acquire() as conn:
            async with conn.transaction():
                inv = await conn.fetchrow(
                    "SELECT quantity FROM card_inventory_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 AND card_slug=$3 FOR UPDATE",
                    self.guild_id, self.user_id, self.card_row_data["slug"],
                )
                wallet = await conn.fetchrow(
                    "SELECT coins FROM card_wallets_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 FOR UPDATE",
                    self.guild_id, self.user_id,
                )
                if not inv or inv["quantity"] < self.copies:
                    return await interaction.response.edit_message(
                        embed=notice("Fusión cancelada ❌", f"Ya no tienes suficientes copias de **{self.card_row_data['name']}**.", 0xED4245),
                        view=None,
                    )
                if not wallet or wallet["coins"] < self.cost:
                    return await interaction.response.edit_message(
                        embed=notice("Fusión cancelada ❌", f"No tienes suficientes Abo Coins (necesitas **{coins_text(self.cost)}**).", 0xED4245),
                        view=None,
                    )
                await conn.execute(
                    "UPDATE card_inventory_global SET quantity=quantity-$1 WHERE ($2::BIGINT IS NOT NULL) AND user_id=$3 AND card_slug=$4",
                    self.copies, self.guild_id, self.user_id, self.card_row_data["slug"],
                )
                await conn.execute(
                    "UPDATE card_wallets_global SET coins=coins-$1,updated_at=NOW() WHERE ($2::BIGINT IS NOT NULL) AND user_id=$3",
                    self.cost, self.guild_id, self.user_id,
                )
                await add_card(conn, self.guild_id, self.user_id, self.result_slug)

        await interaction.response.edit_message(
            embed=notice(
                "¡Fusión exitosa! ✨",
                f"Combinaste **×{self.copies} {card_emoji(self.card_row_data)} {self.card_row_data['name']}** "
                f"y gastaste **{coins_text(self.cost)} Abo Coins**.\n\n"
                f"¡Obtuviste {card_emoji(self.result_row)} **{self.result_row['name']}**! ({self.result_row['rarity']})",
                rarity_color(self.result_row["rarity"]),
            ),
            view=None,
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.done = True
        self.stop()
        await interaction.response.edit_message(
            embed=notice("Fusión cancelada", "No se realizó ningún cambio.", 0x95A5A6),
            view=None,
        )


# ─────────────────────────────────────────────────────────────────────────────
# EVOLUCIÓN
# ─────────────────────────────────────────────────────────────────────────────

def _apply_boost(stats: dict, boost_pct: int) -> dict:
    """Devuelve una copia de stats con HP, ATK, DEF y Speed subidos en boost_pct %."""
    NUMERIC_KEYS = {"HP", "ATK", "DEF", "Speed"}
    result = dict(stats)
    for key in NUMERIC_KEYS:
        raw = str(result.get(key, "")).strip()
        if raw:
            try:
                result[key] = str(round(int(raw) * (1 + boost_pct / 100)))
            except ValueError:
                pass
    return result


def _boosted_stats_preview(base_stats: dict, boost_pct: int) -> str:
    """Texto comparativo de stats antes → después del boost."""
    NUMERIC_KEYS = [("HP", "❤️"), ("ATK", "⚔️"), ("DEF", "🛡️"), ("Speed", "⚡")]
    lines = []
    for key, emoji in NUMERIC_KEYS:
        raw = str(base_stats.get(key, "")).strip()
        if raw:
            try:
                after = round(int(raw) * (1 + boost_pct / 100))
                lines.append(f"{emoji} **{key}**: {raw} → **{after}**")
            except ValueError:
                pass
    return "\n".join(lines) if lines else "—"


class EvolveConfirmView(discord.ui.View):
    """Sube el nivel de evolución de una carta del usuario, mejorando sus stats."""

    def __init__(self, guild_id: int, user_id: int, card_row_data, evo_row,
                 current_level: int, current_boost: int):
        super().__init__(timeout=60)
        self.guild_id = guild_id
        self.user_id = user_id
        self.card_row_data = card_row_data
        self.evo_row = evo_row          # fila de card_evolutions
        self.current_level = current_level
        self.current_boost = current_boost
        self.done = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Solo tú puedes confirmar esta evolución.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Evolucionar 🌟", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.done:
            return
        self.done = True
        self.stop()

        slug       = self.card_row_data["slug"]
        async with db._pool().acquire() as conn:
            async with conn.transaction():
                current = await conn.fetchrow(
                    "SELECT evo_level, stat_boost_pct FROM card_inventory_evo_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 AND card_slug=$3 FOR UPDATE",
                    self.guild_id, self.user_id, slug,
                )
                rule = await conn.fetchrow(
                    "SELECT cost_copies, cost_coins, stat_boost_pct, max_level FROM card_evolutions WHERE base_slug=$1 FOR UPDATE", slug
                )
                if not rule:
                    return await interaction.response.edit_message(embed=notice("Evolución cancelada", "La regla de evolución ya no existe.", 0xED4245), view=None)
                live_level = int(current["evo_level"]) if current else 0
                live_boost = int(current["stat_boost_pct"]) if current else 0
                if live_level >= int(rule["max_level"]):
                    return await interaction.response.edit_message(embed=notice("Nivel máximo alcanzado", "Esta carta ya no puede evolucionar más.", 0xFEE75C), view=None)
                cost_cop = int(rule["cost_copies"])
                cost_coins = int(rule["cost_coins"])
                new_level = live_level + 1
                new_boost = live_boost + int(rule["stat_boost_pct"])
                inv = await conn.fetchrow(
                    "SELECT quantity FROM card_inventory_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 AND card_slug=$3 FOR UPDATE",
                    self.guild_id, self.user_id, slug,
                )
                wallet = await conn.fetchrow(
                    "SELECT coins FROM card_wallets_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 FOR UPDATE",
                    self.guild_id, self.user_id,
                )
                if not inv or inv["quantity"] < cost_cop:
                    return await interaction.response.edit_message(
                        embed=notice("Evolución cancelada ❌",
                                     f"Ya no tienes **×{cost_cop}** copias de **{self.card_row_data['name']}**.", 0xED4245),
                        view=None,
                    )
                if not wallet or wallet["coins"] < cost_coins:
                    return await interaction.response.edit_message(
                        embed=notice("Evolución cancelada ❌",
                                     f"No tienes suficientes Abo Coins (necesitas **{coins_text(cost_coins)}**).", 0xED4245),
                        view=None,
                    )
                # Consumir copias y monedas
                await conn.execute(
                    "UPDATE card_inventory_global SET quantity=quantity-$1 WHERE ($2::BIGINT IS NOT NULL) AND user_id=$3 AND card_slug=$4",
                    cost_cop, self.guild_id, self.user_id, slug,
                )
                await conn.execute(
                    "UPDATE card_wallets_global SET coins=coins-$1,updated_at=NOW() WHERE ($2::BIGINT IS NOT NULL) AND user_id=$3",
                    cost_coins, self.guild_id, self.user_id,
                )
                # Guardar / actualizar nivel de evolución personal
                await conn.execute(
                    """INSERT INTO card_inventory_evo_global (guild_id,user_id,card_slug,evo_level,stat_boost_pct)
                       VALUES ($1,$2,$3,$4,$5)
                       ON CONFLICT (user_id,card_slug) DO UPDATE SET
                         evo_level      = EXCLUDED.evo_level,
                         stat_boost_pct = EXCLUDED.stat_boost_pct""",
                    self.guild_id, self.user_id, slug, new_level, new_boost,
                )

        base_stats = self.card_row_data.get("stats") or {}
        if isinstance(base_stats, str):
            import json as _json
            try: base_stats = _json.loads(base_stats)
            except Exception: base_stats = {}
        preview = _boosted_stats_preview(base_stats, new_boost)

        await interaction.response.edit_message(
            embed=notice(
                f"¡Evolución completada! 🌟 (Nivel {new_level})",
                f"{card_emoji(self.card_row_data)} **{self.card_row_data['name']}** subió al nivel de evolución **{new_level}**.\n"
                f"Sus stats ahora tienen un **+{new_boost}%** respecto al original.\n\n"
                f"{preview}\n\n"
                f"Se consumieron **×{cost_cop}** copias y **{coins_text(cost_coins)} Abo Coins**.",
                rarity_color(self.card_row_data["rarity"]),
            ),
            view=None,
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.done = True
        self.stop()
        await interaction.response.edit_message(
            embed=notice("Evolución cancelada", "No se realizó ningún cambio.", 0x95A5A6),
            view=None,
        )


class TradeQuantityModal(discord.ui.Modal, title="Cantidad para el tradeo"):
    cantidad = discord.ui.TextInput(label="Cantidad", placeholder="Ejemplo: 2", min_length=1, max_length=3)
    def __init__(self, cog, channel_id, user_id, slug):
        super().__init__(); self.cog=cog; self.channel_id=channel_id; self.user_id=user_id; self.slug=slug
    async def on_submit(self, interaction):
        try: quantity=int(str(self.cantidad.value).strip())
        except ValueError: return await interaction.response.send_message("Indica una cantidad numérica válida.", ephemeral=True)
        await self.cog._add_trade_card(interaction, self.channel_id, self.user_id, self.slug, quantity)

class TradeCardSelect(discord.ui.Select):
    def __init__(self, cog, channel_id, user_id, rows):
        super().__init__(placeholder="Selecciona una carta para ofrecer…", options=[
            discord.SelectOption(label=f"{r['name']} · {r['rarity']}"[:100], description=f"Tienes ×{r['quantity']} · Elige la cantidad después"[:100], value=r['slug']) for r in rows[:25]
        ])
        self.cog=cog; self.channel_id=channel_id; self.user_id=user_id
    async def callback(self, interaction):
        await interaction.response.send_modal(TradeQuantityModal(self.cog, self.channel_id, self.user_id, self.values[0]))

class TradeCardPickerView(discord.ui.View):
    def __init__(self, cog, channel_id, user_id, rows):
        super().__init__(timeout=120); self.add_item(TradeCardSelect(cog, channel_id, user_id, rows))

class TradeView(discord.ui.View):
    def __init__(self, cog, channel_id):
        session = cog.trade_sessions.get(channel_id)
        idle = time.monotonic() - session.get("last_activity_at", time.monotonic()) if session else 900
        super().__init__(timeout=max(1, 900 - idle)); self.cog=cog; self.channel_id=channel_id
    async def on_timeout(self):
        session = self.cog.trade_sessions.get(self.channel_id)
        if not session or time.monotonic() - session.get("last_activity_at", time.monotonic()) < 900:
            return
        await self.cog._expire_trade(self.channel_id)
    async def interaction_check(self, interaction):
        session=self.cog.trade_sessions.get(self.channel_id)
        if not session or interaction.user.id not in {session['user_a'],session['user_b']}:
            await interaction.response.send_message("Este tradeo no está disponible para ti.", ephemeral=True); return False
        return True
    @discord.ui.button(label="Añadir carta", emoji="🎴", style=discord.ButtonStyle.primary)
    async def add_card(self, interaction, button):
        rows=await db.fetch("""SELECT c.slug,c.name,c.rarity,i.quantity FROM card_catalog c JOIN card_inventory_global i ON i.card_slug=c.slug WHERE c.active=TRUE AND ($1::BIGINT IS NOT NULL) AND i.user_id=$2 AND i.quantity>0 ORDER BY c.rarity DESC,c.name LIMIT 25""", interaction.guild_id, interaction.user.id)
        if not rows: return await interaction.response.send_message("No tienes cartas disponibles para ofrecer.", ephemeral=True)
        await interaction.response.send_message("Elige una carta y después indica la cantidad:", view=TradeCardPickerView(self.cog,self.channel_id,interaction.user.id,rows), ephemeral=True)
    @discord.ui.button(label="Confirmar oferta", emoji="✅", style=discord.ButtonStyle.success)
    async def confirm(self, interaction, button): await self.cog._confirm_trade(interaction,self.channel_id)
    @discord.ui.button(label="Cancelar tradeo", emoji="❌", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction, button): await self.cog._cancel_trade(interaction,self.channel_id)

class CardsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.trade_sessions: dict[int, dict] = {}
        self.battles: dict[str, dict] = {}
        self._rate_limits: dict[tuple[str, int, int], float] = {}

    def _rate_limit(self, action: str, guild_id: int, user_id: int, seconds: float) -> float:
        now = time.monotonic()
        key = (action, guild_id, user_id)
        remaining = self._rate_limits.get(key, 0.0) - now
        if remaining > 0:
            return remaining
        self._rate_limits[key] = now + seconds
        return 0.0

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
                "message_id": row.get("message_id"),
                "user_a": users[0], "user_b": users[1],
                "name_a": members[0].display_name if members[0] else str(users[0]),
                "name_b": members[1].display_name if members[1] else str(users[1]),
                "offers": offers,
                "confirmed": {users[0]: row["confirmed_a"], users[1]: row["confirmed_b"]},
                "last_activity_at": time.monotonic() - max(0, (datetime.now(timezone.utc) - (row.get("last_activity_at") or row.get("created_at") or datetime.now(timezone.utc))).total_seconds()),
            }
            message = None
            message_id = self.trade_sessions[row["channel_id"]].get("message_id")
            try:
                if message_id:
                    message = await channel.fetch_message(message_id)
                else:
                    # Compatibilidad con sesiones creadas antes de persistir message_id.
                    async for candidate in channel.history(limit=100):
                        title = candidate.embeds[0].title if candidate.embeds else ""
                        if candidate.author == self.bot.user and title and title.startswith("Tradeo"):
                            message = candidate
                            break
                if message:
                    self.trade_sessions[row["channel_id"]]["message_id"] = message.id
                    if row["id"]:
                        await db.execute("UPDATE card_trade_sessions SET message_id=$1 WHERE id=$2", message.id, row["id"])
                    await message.edit(view=TradeView(self, row["channel_id"]))
            except (discord.NotFound, discord.HTTPException):
                pass

    @app_commands.command(name="cguia", description="Guía breve de comandos de Abo Cards (! y /)")
    @app_commands.guild_only()
    async def cguia(self, interaction: discord.Interaction):
        nl = chr(10)
        embed = discord.Embed(
            title="Guía de Abo Cards 🎴",
            description="Consulta rápida de los comandos de cartas con prefijo `!` y slash `/`.",
            color=0x5865F2,
        )
        embed.add_field(name="Colección", value=nl.join([
            "`/sobre` · `!sobre` — Abre un sobre.",
            "`/coleccion` · `!coleccion` — Consulta tu colección.",
            "`/carta <nombre>` · `!carta <nombre>` — Detalles de una carta.",
            "`/sets` · `!sets` — Lista los sets.",
            "`/set <nombre>` · `!set <nombre>` — Progreso de un set.",
            "`/perfil [usuario]` · `!perfil [@usuario]` — Perfil de cartas.",
        ]), inline=False)
        embed.add_field(name="Economía y mejoras", value=nl.join([
            "`/diario_cartas` · `!diario` — Recompensa diaria.",
            "`/saldo_cartas` · `!saldo` — Consulta tus Abo Coins.",
            "`/fusionar <carta>` — Fusiona copias.",
            "`/evolucionar <carta>` — Evoluciona una carta.",
            "`/favorita <carta>` — Marca una favorita.",
            "`/mercado` · `!mercado` — Abre el mercado.",
            "`/mercado_publicar <carta> <cantidad> <precio>` — Publica cartas.",
        ]), inline=False)
        embed.add_field(name="Interacción", value=nl.join([
            "`/comparar usuario` · `!comparar @usuario` — Compara colecciones.",
            "`/tradeo usuario` · `!tradeo @usuario` — Inicia un intercambio.",
            "`/pelea usuario modalidad` — Desafía en 1v1 o 3v3.",
            "`/ranking_cartas` · `!ranking` — Ranking del servidor.",
        ]), inline=False)
        embed.set_footer(text="Abo Cards · Usa /help para el resto de funciones del bot")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="diario_cartas", description="Reclama tus Abo Coins diarios para comprar sobres")
    @app_commands.guild_only()
    async def diario_cartas(self, interaction: discord.Interaction):
        if (wait := self._rate_limit("daily", interaction.guild_id, interaction.user.id, 5)):
            return await interaction.response.send_message(f"Espera {wait:.1f}s antes de volver a reclamar el diario.", ephemeral=True)
        now = datetime.now(timezone.utc)
        await ensure_wallet(interaction.guild_id, interaction.user.id)
        async with db._pool().acquire() as connection:
            async with connection.transaction():
                wallet = await connection.fetchrow(
                    "SELECT coins, daily_claimed_at, daily_streak FROM card_wallets_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 FOR UPDATE",
                    interaction.guild_id, interaction.user.id,
                )
                last = wallet["daily_claimed_at"]
                if last and last.date() == now.date():
                    return await interaction.response.send_message(
                        embed=notice("Diario ya reclamado ⏳", "Vuelve mañana para recibir más Abo Coins.", 0xFEE75C), ephemeral=True,
                    )
                streak = wallet["daily_streak"] + 1 if last and (now.date() - last.date()) == timedelta(days=1) else 1
                reward = min(DAILY_BASE + (streak - 1) * 25, 350)
                await connection.execute(
                    "UPDATE card_wallets_global SET coins=coins+$1, daily_claimed_at=$2, daily_streak=$3, updated_at=NOW() WHERE ($4::BIGINT IS NOT NULL) AND user_id=$5",
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
        coins = await db.fetchval("SELECT coins FROM card_wallets_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2", interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(embed=notice("Tu saldo 💰", f"Tienes **{coins_text(coins)} Abo Coins**.\nUsa `/sobre` para comprar un sobre de 3 cartas."), ephemeral=True)

    @app_commands.command(name="perfil", description="Muestra tu perfil de coleccionista")
    @app_commands.guild_only()
    @app_commands.describe(usuario="Perfil de otro miembro")
    async def perfil(self, interaction: discord.Interaction, usuario: discord.Member | None = None):
        target = usuario or interaction.user
        await ensure_wallet(interaction.guild_id, target.id)
        wallet = await db.fetchrow("SELECT coins,xp,level,packs_opened,pity_rare,pity_epic FROM card_wallets_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2", interaction.guild_id, target.id)
        stats = await db.fetchrow("""SELECT COUNT(*) FILTER (WHERE quantity>0)::int AS unique_cards,
            COALESCE(SUM(quantity),0)::int AS total_cards,COALESCE(SUM(quantity*c.base_value),0)::bigint AS value
            FROM card_inventory_global i JOIN card_catalog c ON c.slug=i.card_slug WHERE ($1::BIGINT IS NOT NULL) AND i.user_id=$2""", interaction.guild_id, target.id)
        rank = await db.fetchval("""SELECT COUNT(*)+1 FROM (SELECT i.user_id,SUM(i.quantity*c.base_value) AS value FROM card_inventory_global i JOIN card_catalog c ON c.slug=i.card_slug WHERE ($1::BIGINT IS NOT NULL) GROUP BY i.user_id) x WHERE x.value > $2""", interaction.guild_id, stats["value"]) or 1
        fav = await db.fetchrow(
            """SELECT c.name,c.rarity,c.emoji_name,c.emoji_id FROM card_inventory_global i
               JOIN card_catalog c ON c.slug=i.card_slug
               WHERE ($1::BIGINT IS NOT NULL) AND i.user_id=$2 AND i.is_favorite=TRUE LIMIT 1""",
            interaction.guild_id, target.id
        )
        fav_line = f"\n\n⭐ Favorita: {card_emoji(fav)} **{fav['name']}** ({fav['rarity']})" if fav else ""
        embed = notice(f"Perfil de {target.display_name} 🪪", f"Nivel: **{wallet['level']}** · XP: **{wallet['xp']}/ {(wallet['level'])*1000}**\nSaldo: **{coins_text(wallet['coins'])} Abo Coins**\n\nCartas únicas: **{stats['unique_cards']}**\nCartas totales: **{stats['total_cards']}**\nValor de colección: **{coins_text(stats['value'])}**\nPosición: **#{rank}**\n\nSobres abiertos: **{wallet['packs_opened']}**\nPity rara: **{wallet['pity_rare']}/{PITY_RARE_LIMIT}**\nPity épica: **{wallet['pity_epic']}/{PITY_EPIC_LIMIT}**{fav_line}", 0x5865F2)
        if target.display_avatar: embed.set_thumbnail(url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    # ── FAVORITA ──────────────────────────────────────────────────────────────

    @app_commands.command(name="favorita", description="Marca una carta de tu colección como favorita")
    @app_commands.guild_only()
    @app_commands.describe(carta="Nombre o slug de la carta que quieres marcar")
    async def favorita_cmd(self, interaction: discord.Interaction, carta: str):
        gid, uid = interaction.guild_id, interaction.user.id
        row = await card_row(carta)
        if not row:
            return await interaction.response.send_message(
                embed=notice("Carta no encontrada", "Revisa el nombre e inténtalo de nuevo.", 0xED4245),
                ephemeral=True,
            )
        owned = await db.fetchval(
            "SELECT quantity FROM card_inventory_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 AND card_slug=$3",
            gid, uid, row["slug"]
        )
        if not owned or owned < 1:
            return await interaction.response.send_message(
                embed=notice("No tienes esta carta", f"Necesitas tener al menos una copia de **{row['name']}** para marcarla como favorita.", 0xED4245),
                ephemeral=True,
            )
        # Quitar favorita anterior y poner la nueva
        await db.execute("UPDATE card_inventory_global SET is_favorite=FALSE WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 AND is_favorite=TRUE", gid, uid)
        await db.execute("UPDATE card_inventory_global SET is_favorite=TRUE WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 AND card_slug=$3", gid, uid, row["slug"])
        await interaction.response.send_message(
            embed=notice("Favorita actualizada ⭐", f"{card_emoji(row)} **{row['name']}** es ahora tu carta favorita. Aparecerá en tu `/perfil`."),
            ephemeral=True,
        )

    @favorita_cmd.autocomplete("carta")
    async def favorita_carta_autocomplete(self, interaction: discord.Interaction, current: str):
        query = f"%{(current or '').strip()}%"
        rows = await db.fetch(
            """SELECT c.slug,c.name,c.rarity,i.quantity
               FROM card_catalog c JOIN card_inventory_global i ON i.card_slug=c.slug
               WHERE c.active=TRUE AND ($1::BIGINT IS NOT NULL) AND i.user_id=$2 AND i.quantity>0
                 AND (c.name ILIKE $3 OR c.slug ILIKE $3)
               ORDER BY CASE WHEN c.name ILIKE $4 THEN 0 ELSE 1 END, c.rarity DESC, c.name LIMIT 25""",
            interaction.guild_id, interaction.user.id, query, f"{(current or '').strip()}%",
        )
        return [app_commands.Choice(name=f"{r['name']} · {r['rarity']} · ×{r['quantity']}"[:100], value=r['slug']) for r in rows]

    # ── COMPARAR ──────────────────────────────────────────────────────────────

    @app_commands.command(name="comparar", description="Compara tu colección con la de otro miembro")
    @app_commands.guild_only()
    @app_commands.describe(usuario="Miembro con quien comparar")
    async def comparar_cmd(self, interaction: discord.Interaction, usuario: discord.Member):
        if usuario.bot or usuario.id == interaction.user.id:
            return await interaction.response.send_message(
                embed=notice("Comparación inválida", "Elige a otro miembro del servidor.", 0xED4245),
                ephemeral=True,
            )
        gid = interaction.guild_id
        solo_yo, solo_el, ambos = await compare_collections(gid, interaction.user.id, usuario.id)
        embed, _ = comparison_embed(
            interaction.user.display_name, usuario.display_name,
            solo_yo, solo_el, ambos, "solo_a", 0,
        )
        await interaction.response.send_message(
            embed=embed,
            view=ComparisonView(
                interaction.user.id, interaction.user.display_name, usuario.display_name,
                solo_yo, solo_el, ambos,
            ),
        )

    # ── FUSIÓN ────────────────────────────────────────────────────────────────

    @app_commands.command(name="fusionar", description="Fusiona 3 copias de una carta para obtener una de mayor rareza")
    @app_commands.guild_only()
    @app_commands.describe(carta="Carta que quieres fusionar (necesitas ×3 copias)")
    async def fusion_cmd(self, interaction: discord.Interaction, carta: str):
        if (wait := self._rate_limit("fusion", interaction.guild_id, interaction.user.id, 3)):
            return await interaction.response.send_message(f"Espera {wait:.1f}s antes de fusionar otra carta.", ephemeral=True)
        gid, uid = interaction.guild_id, interaction.user.id
        row = await card_row(carta)
        if not row:
            return await interaction.response.send_message(
                embed=notice("Carta no encontrada", "Revisa el nombre e inténtalo de nuevo.", 0xED4245),
                ephemeral=True,
            )

        rule = FUSION_RULES.get(row["rarity"])
        if not rule:
            return await interaction.response.send_message(
                embed=notice("Fusión no disponible", "Las cartas **Legendarias** no pueden fusionarse.", 0xED4245),
                ephemeral=True,
            )

        copies, cost, result_rarity = rule["copies"], rule["cost"], rule["result"]

        owned = await db.fetchval(
            "SELECT quantity FROM card_inventory_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 AND card_slug=$3",
            gid, uid, row["slug"],
        ) or 0
        if owned < copies:
            return await interaction.response.send_message(
                embed=notice("Copias insuficientes",
                             f"Necesitas **×{copies}** copias de **{row['name']}** y tienes **×{owned}**.", 0xED4245),
                ephemeral=True,
            )

        await ensure_wallet(gid, uid)
        wallet = await db.fetchrow("SELECT coins FROM card_wallets_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2", gid, uid)
        if not wallet or wallet["coins"] < cost:
            return await interaction.response.send_message(
                embed=notice("Monedas insuficientes",
                             f"La fusión cuesta **{coins_text(cost)} Abo Coins** y tienes **{coins_text(wallet['coins'] if wallet else 0)}**.", 0xED4245),
                ephemeral=True,
            )

        # Elige aleatoriamente una carta de la rareza resultado
        candidates = await db.fetch(
            "SELECT * FROM card_catalog WHERE active=TRUE AND rarity=$1", result_rarity
        )
        if not candidates:
            return await interaction.response.send_message(
                embed=notice("Sin cartas disponibles", f"No hay cartas de rareza **{result_rarity}** en el catálogo.", 0xED4245),
                ephemeral=True,
            )
        result_row = random.choice(candidates)

        embed = notice(
            "Confirmar fusión ✨",
            f"Vas a combinar **×{copies} {card_emoji(row)} {row['name']}** ({row['rarity']})\n"
            f"y gastar **{coins_text(cost)} Abo Coins**\n\n"
            f"A cambio recibirás una carta aleatoria de rareza **{result_rarity}**.\n"
            f"*(En este caso: {card_emoji(result_row)} **{result_row['name']}**)*\n\n"
            f"⚠️ Esta acción no se puede deshacer.",
            rarity_color(result_rarity),
        )
        view = FusionConfirmView(gid, uid, row, result_row["slug"], result_row, copies, cost)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @fusion_cmd.autocomplete("carta")
    async def fusion_carta_autocomplete(self, interaction: discord.Interaction, current: str):
        query = f"%{(current or '').strip()}%"
        rows = await db.fetch(
            """SELECT c.slug,c.name,c.rarity,i.quantity
               FROM card_catalog c JOIN card_inventory_global i ON i.card_slug=c.slug
               WHERE c.active=TRUE AND ($1::BIGINT IS NOT NULL) AND i.user_id=$2 AND i.quantity>=3
                 AND c.rarity IN ('Común','Rara','Épica')
                 AND (c.name ILIKE $3 OR c.slug ILIKE $3)
               ORDER BY CASE WHEN c.name ILIKE $4 THEN 0 ELSE 1 END, c.rarity DESC, c.name
               LIMIT 25""",
            interaction.guild_id, interaction.user.id, query, f"{(current or '').strip()}%",
        )
        fusion_costs = {"Común": 50, "Rara": 150, "Épica": 300}
        return [
            app_commands.Choice(
                name=f"{row['name']} · {row['rarity']} · ×{row['quantity']} · cuesta {coins_text(fusion_costs[row['rarity']])}"[:100],
                value=row['slug'],
            )
            for row in rows
        ]

    # ── EVOLUCIÓN ─────────────────────────────────────────────────────────────

    @app_commands.command(name="evolucionar", description="Sube el nivel de evolución de una carta mejorando sus stats")
    @app_commands.guild_only()
    @app_commands.describe(carta="Carta que quieres evolucionar")
    async def evolucionar_cmd(self, interaction: discord.Interaction, carta: str):
        if (wait := self._rate_limit("evolve", interaction.guild_id, interaction.user.id, 3)):
            return await interaction.response.send_message(f"Espera {wait:.1f}s antes de evolucionar otra carta.", ephemeral=True)
        gid, uid = interaction.guild_id, interaction.user.id
        row = await card_row(carta)
        if not row:
            return await interaction.response.send_message(
                embed=notice("Carta no encontrada", "Revisa el nombre e inténtalo de nuevo.", 0xED4245),
                ephemeral=True,
            )

        evo = await db.fetchrow(
            "SELECT * FROM card_evolutions WHERE base_slug=$1", row["slug"]
        )
        if not evo:
            return await interaction.response.send_message(
                embed=notice("Sin evolución", f"**{row['name']}** no tiene evolución configurada.", 0xFEE75C),
                ephemeral=True,
            )

        # Nivel actual del usuario para esta carta
        evo_data = await db.fetchrow(
            "SELECT evo_level, stat_boost_pct FROM card_inventory_evo_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 AND card_slug=$3",
            gid, uid, row["slug"],
        )
        current_level = evo_data["evo_level"] if evo_data else 0
        current_boost = evo_data["stat_boost_pct"] if evo_data else 0

        if current_level >= evo["max_level"]:
            return await interaction.response.send_message(
                embed=notice("Nivel máximo alcanzado ✨",
                             f"Tu **{row['name']}** ya está al nivel máximo de evolución (**{evo['max_level']}**) "
                             f"con **+{current_boost}%** en stats.", 0xF1C40F),
                ephemeral=True,
            )

        copies_needed = evo["cost_copies"]
        cost = evo["cost_coins"]
        owned = await db.fetchval(
            "SELECT quantity FROM card_inventory_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 AND card_slug=$3",
            gid, uid, row["slug"],
        ) or 0
        if owned < copies_needed:
            return await interaction.response.send_message(
                embed=notice("Copias insuficientes",
                             f"Necesitas **×{copies_needed}** copias de **{row['name']}** y tienes **×{owned}**.", 0xED4245),
                ephemeral=True,
            )

        await ensure_wallet(gid, uid)
        wallet = await db.fetchrow("SELECT coins FROM card_wallets_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2", gid, uid)
        if not wallet or wallet["coins"] < cost:
            return await interaction.response.send_message(
                embed=notice("Monedas insuficientes",
                             f"Necesitas **{coins_text(cost)} Abo Coins** y tienes **{coins_text(wallet['coins'] if wallet else 0)}**.", 0xED4245),
                ephemeral=True,
            )

        # Preview de stats tras el boost
        import json as _json
        base_stats = row.get("stats") or {}
        if isinstance(base_stats, str):
            try: base_stats = _json.loads(base_stats)
            except Exception: base_stats = {}
        next_boost = current_boost + evo["stat_boost_pct"]
        preview = _boosted_stats_preview(base_stats, next_boost)

        embed = notice(
            f"Confirmar evolución 🌟 → Nivel {current_level + 1}/{evo['max_level']}",
            f"{card_emoji(row)} **{row['name']}** mejorará sus stats un **+{next_boost}%** acumulado.\n\n"
            f"{preview}\n\n"
            f"Costo: **×{copies_needed}** copias + **{coins_text(cost)} Abo Coins**\n"
            f"⚠️ Esta acción no se puede deshacer.",
            rarity_color(row["rarity"]),
        )
        view = EvolveConfirmView(gid, uid, row, evo, current_level, current_boost)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @evolucionar_cmd.autocomplete("carta")
    async def evolucionar_carta_autocomplete(self, interaction: discord.Interaction, current: str):
        query = f"%{(current or '').strip()}%"
        rows = await db.fetch(
            """SELECT c.slug,c.name,c.rarity,i.quantity,e.cost_copies,e.max_level,
                      COALESCE(ie.evo_level,0)::int AS evo_level
               FROM card_catalog c
               JOIN card_inventory_global i ON i.card_slug=c.slug
                    AND ($1::BIGINT IS NOT NULL) AND i.user_id=$2 AND i.quantity>0
               JOIN card_evolutions e ON e.base_slug=c.slug
               LEFT JOIN card_inventory_evo_global ie ON ($1::BIGINT IS NOT NULL) AND ie.user_id=$2 AND ie.card_slug=c.slug
               WHERE c.active=TRUE
                 AND COALESCE(ie.evo_level,0) < e.max_level
                 AND i.quantity >= e.cost_copies
                 AND (c.name ILIKE $3 OR c.slug ILIKE $3)
               ORDER BY CASE WHEN c.name ILIKE $4 THEN 0 ELSE 1 END, c.rarity DESC, c.name
               LIMIT 25""",
            interaction.guild_id, interaction.user.id, query, f"{(current or '').strip()}%",
        )
        return [
            app_commands.Choice(
                name=f"{row['name']} · Nv. {row['evo_level']}/{row['max_level']} · ×{row['quantity']}"[:100],
                value=row['slug'],
            )
            for row in rows
        ]

    @app_commands.command(name="evolucion_configurar", description="Configura la evolución de una carta (admin)")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        carta_base="Carta que puede evolucionar",
        boost_por_nivel="% de mejora en stats por nivel (ej: 25)",
        nivel_maximo="Niveles máximos de evolución (ej: 5)",
        costo_monedas="Abo Coins por nivel",
        costo_copias="Copias necesarias por nivel",
    )
    async def evolucion_configurar(self, interaction: discord.Interaction,
                                   carta_base: str,
                                   boost_por_nivel: int = 25,
                                   nivel_maximo: int = 5,
                                   costo_monedas: int = 100,
                                   costo_copias: int = 2):
        if interaction.user.id != TU_ID:
            return await interaction.response.send_message("Esta configuración global solo puede modificarla el propietario del bot.", ephemeral=True)
        if costo_monedas < 1 or costo_copias < 1:
            return await interaction.response.send_message("Los costos deben ser mayores que 0.", ephemeral=True)
        base = await card_row(carta_base)
        if not base:
            return await interaction.response.send_message(
                embed=notice("Carta no encontrada", "Revisa el nombre.", 0xED4245), ephemeral=True,
            )
        if not 1 <= boost_por_nivel <= 200:
            return await interaction.response.send_message(
                embed=notice("Boost inválido", "El boost debe estar entre 1 y 200 %.", 0xED4245), ephemeral=True,
            )
        if not 1 <= nivel_maximo <= 20:
            return await interaction.response.send_message(
                embed=notice("Nivel inválido", "El nivel máximo debe estar entre 1 y 20.", 0xED4245), ephemeral=True,
            )
        await db.execute(
            """INSERT INTO card_evolutions (base_slug,cost_coins,cost_copies,stat_boost_pct,max_level)
               VALUES ($1,$2,$3,$4,$5)
               ON CONFLICT (base_slug) DO UPDATE SET
                 cost_coins     = EXCLUDED.cost_coins,
                 cost_copies    = EXCLUDED.cost_copies,
                 stat_boost_pct = EXCLUDED.stat_boost_pct,
                 max_level      = EXCLUDED.max_level""",
            base["slug"], costo_monedas, costo_copias, boost_por_nivel, nivel_maximo,
        )
        await interaction.response.send_message(
            embed=notice(
                "Evolución configurada ✅",
                f"{card_emoji(base)} **{base['name']}**\n"
                f"Boost por nivel: **+{boost_por_nivel}%** · Máximo: **{nivel_maximo} niveles** "
                f"(hasta **+{boost_por_nivel * nivel_maximo}%**)\n"
                f"Costo por nivel: **×{costo_copias}** copias + **{coins_text(costo_monedas)} Abo Coins**",
                0x57F287,
            ),
            ephemeral=True,
        )

    @app_commands.command(name="evolucion_ver", description="Muestra las evoluciones configuradas")
    @app_commands.guild_only()
    async def evolucion_ver(self, interaction: discord.Interaction):
        rows = await db.fetch(
            """SELECT e.base_slug, e.cost_coins, e.cost_copies, e.stat_boost_pct, e.max_level,
                      b.name AS base_name, b.rarity AS base_rarity, b.emoji_name AS b_ename, b.emoji_id AS b_eid
               FROM card_evolutions e
               JOIN card_catalog b ON b.slug = e.base_slug
               ORDER BY b.rarity, b.name"""
        )
        if not rows:
            return await interaction.response.send_message(
                embed=notice("Sin evoluciones", "Aún no hay evoluciones configuradas. Usa `/evolucion_configurar`.", 0xFEE75C),
                ephemeral=True,
            )
        lines = []
        for r in rows:
            b_emoji = card_emoji({"emoji_name": r["b_ename"], "emoji_id": r["b_eid"], "rarity": r["base_rarity"]})
            max_total = r["stat_boost_pct"] * r["max_level"]
            lines.append(
                f"{b_emoji} **{r['base_name']}** · "
                f"+{r['stat_boost_pct']}% por nivel · máx {r['max_level']} niveles "
                f"(hasta **+{max_total}%**) · "
                f"×{r['cost_copies']} copias + {coins_text(r['cost_coins'])} AC/nivel"
            )
        await interaction.response.send_message(
            embed=notice("Evoluciones disponibles 🌟", "\n".join(lines)),
            ephemeral=True,
        )

    # ── ADMIN: CARTAS ─────────────────────────────────────────────────────────

    @app_commands.command(name="sobre", description="Compra un sobre de 3 cartas aleatorias")
    @app_commands.guild_only()
    async def sobre(self, interaction: discord.Interaction):
        if (wait := self._rate_limit("pack", interaction.guild_id, interaction.user.id, 5)):
            return await interaction.response.send_message(f"Espera {wait:.1f}s antes de abrir otro sobre.", ephemeral=True)
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
            LEFT JOIN card_inventory_global i ON i.card_slug=c.slug AND ($1::BIGINT IS NOT NULL) AND i.user_id=$2
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
            FROM card_catalog c LEFT JOIN card_inventory_global i ON i.card_slug=c.slug AND ($1::BIGINT IS NOT NULL) AND i.user_id=$2
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
        owned = await db.fetchval("SELECT quantity FROM card_inventory_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 AND card_slug=$3", interaction.guild_id, interaction.user.id, row["slug"]) or 0
        evo_data = await db.fetchrow("SELECT evo_level, stat_boost_pct FROM card_inventory_evo_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 AND card_slug=$3", interaction.guild_id, interaction.user.id, row["slug"])
        evo_level = evo_data["evo_level"] if evo_data else 0
        evo_boost = evo_data["stat_boost_pct"] if evo_data else 0
        description = row.get("description") or "Conoce a este personaje de Abo."
        embed = notice(f"{card_emoji(row)} {row['name']}", description, int(row.get("embed_color") or rarity_color(row["rarity"])))
        embed.add_field(name="Rareza", value=row["rarity"], inline=True)
        embed.add_field(name="Valor", value=f"{coins_text(row['base_value'])} Abo Coins", inline=True)
        evo_label = f"×{owned}" + (f"  🌟 Nv.{evo_level} (+{evo_boost}%)" if evo_level > 0 else "")
        embed.add_field(name="Tienes", value=evo_label, inline=True)
        # Aplicar boost a los stats si el usuario tiene esta carta evolucionada
        display_row = dict(row)
        if evo_boost > 0:
            import json as _json
            base_stats = row.get("stats") or {}
            if isinstance(base_stats, str):
                try: base_stats = _json.loads(base_stats)
                except Exception: base_stats = {}
            boosted = _apply_boost(base_stats, evo_boost)
            display_row["stats"] = _json.dumps(boosted, ensure_ascii=False)
        for field_name, field_value, inline in _combat_embed_fields(display_row):
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
        if (wait := self._rate_limit("trade", interaction.guild_id, interaction.user.id, 10)):
            return await interaction.response.send_message(f"Espera {wait:.1f}s antes de iniciar otro tradeo.", ephemeral=True)
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
            "last_activity_at": time.monotonic(),
        }
        session["trade_id"] = await db.fetchval("""INSERT INTO card_trade_sessions (guild_id,user_a,user_b,channel_id,offer_a,offer_b,status)
            VALUES ($1,$2,$3,$4,'{}'::jsonb,'{}'::jsonb,'active') RETURNING id""", interaction.guild_id, interaction.user.id, usuario.id, interaction.channel_id)
        self.trade_sessions[interaction.channel_id] = session
        await interaction.response.send_message(
            embed=self._trade_embed(session, "Tradeo iniciado 🤝", "Usen **Añadir carta** para seleccionar una carta y su cantidad. El intercambio por texto sigue disponible como alternativa."),
            view=TradeView(self, interaction.channel_id), allowed_mentions=discord.AllowedMentions(users=True),
        )
        session["message_id"]=(await interaction.original_response()).id
        if session.get("trade_id"):
            await db.execute("UPDATE card_trade_sessions SET message_id=$1,last_activity_at=NOW() WHERE id=$2", session["message_id"], session["trade_id"])

    async def _refresh_trade_message(self, channel_id, title="Tradeo actualizado 🤝", extra=""):
        session=self.trade_sessions.get(channel_id)
        if not session or not session.get("message_id"): return
        channel=self.bot.get_channel(channel_id)
        if not channel: return
        try:
            message=await channel.fetch_message(session["message_id"])
            await message.edit(embed=self._trade_embed(session,title,extra), view=TradeView(self,channel_id))
        except (discord.NotFound,discord.HTTPException): pass

    async def _add_trade_card(self, interaction, channel_id, user_id, slug, quantity):
        session=self.trade_sessions.get(channel_id)
        if not session or user_id not in {session["user_a"],session["user_b"]}: return await interaction.response.send_message("Este tradeo ya no está activo.",ephemeral=True)
        if quantity<1 or quantity>999: return await interaction.response.send_message("La cantidad debe estar entre 1 y 999.",ephemeral=True)
        owned=await db.fetchval("SELECT quantity FROM card_inventory_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 AND card_slug=$3",session["guild_id"],user_id,slug) or 0
        current=session["offers"][user_id].get(slug,{}).get("quantity",0)
        if current+quantity>owned: return await interaction.response.send_message(f"No puedes ofrecer ×{current+quantity}; solo tienes ×{owned}.",ephemeral=True)
        row=await card_row(slug)
        if not row: return await interaction.response.send_message("La carta ya no está disponible.",ephemeral=True)
        session["offers"][user_id][slug]={"quantity":current+quantity,"name":row["name"],"emoji":card_emoji(row)}
        session["last_activity_at"] = time.monotonic()
        session["confirmed"]={session["user_a"]:False,session["user_b"]:False}
        if session.get("trade_id"):
            col="offer_a" if user_id==session["user_a"] else "offer_b"; payload={k:v["quantity"] for k,v in session["offers"][user_id].items()}
            await db.execute(f"UPDATE card_trade_sessions SET {col}=$1::jsonb,confirmed_a=FALSE,confirmed_b=FALSE,last_activity_at=NOW() WHERE id=$2",__import__("json").dumps(payload),session["trade_id"])
        await interaction.response.send_message(embed=notice("Carta añadida ✅",f"Ofreciste **×{quantity} {card_emoji(row)} {row['name']}**."),ephemeral=True)
        await self._refresh_trade_message(channel_id)

    async def _confirm_trade(self, interaction, channel_id):
        session=self.trade_sessions.get(channel_id)
        if not session: return await interaction.response.send_message("Este tradeo ya no está activo.",ephemeral=True)
        uid=interaction.user.id; session["last_activity_at"] = time.monotonic(); session["confirmed"][uid]=True; col="confirmed_a" if uid==session["user_a"] else "confirmed_b"
        if session.get("trade_id"): await db.execute(f"UPDATE card_trade_sessions SET {col}=TRUE,last_activity_at=NOW() WHERE id=$1",session["trade_id"])
        if all(session["confirmed"].values()):
            if session.get("completing"):
                return await interaction.response.send_message("El tradeo ya se está procesando.", ephemeral=True)
            if not any(session["offers"][uid] for uid in session["users"]):
                session["confirmed"]={session["user_a"]:False,session["user_b"]:False}
                return await interaction.response.send_message("No puedes completar un tradeo sin ofrecer cartas.", ephemeral=True)
            session["completing"] = True
            result=await self._complete_trade(session)
            if result:
                self.trade_sessions.pop(channel_id,None); await interaction.response.edit_message(embed=result,view=None); return
            session.pop("completing", None)
            session["confirmed"]={session["user_a"]:False,session["user_b"]:False}; msg="Uno de los dos usuarios ya no tiene las cartas ofrecidas. Las confirmaciones se reiniciaron."
            if session.get("trade_id"): await db.execute("UPDATE card_trade_sessions SET confirmed_a=FALSE,confirmed_b=FALSE WHERE id=$1",session["trade_id"])
        else: msg=f"{interaction.user.mention} confirmó su oferta. Falta la confirmación del otro usuario."
        await interaction.response.send_message("Oferta confirmada. Revisa el panel del tradeo.",ephemeral=True)
        await self._refresh_trade_message(channel_id,"Confirmación actualizada ✅",msg)

    async def _expire_trade(self, channel_id):
        session = self.trade_sessions.pop(channel_id, None)
        if not session:
            return
        if session.get("trade_id"):
            await db.execute("UPDATE card_trade_sessions SET status='cancelled',completed_at=NOW() WHERE id=$1", session["trade_id"])
        channel = self.bot.get_channel(channel_id)
        if channel and session.get("message_id"):
            try:
                message = await channel.fetch_message(session["message_id"])
                await message.edit(embed=notice("Tradeo expirado ⏰", "El intercambio se canceló por 15 minutos sin actividad.", 0x95A5A6), view=None)
            except (discord.NotFound, discord.HTTPException):
                pass

    async def _cancel_trade(self, interaction, channel_id):
        session=self.trade_sessions.pop(channel_id,None)
        if not session: return await interaction.response.send_message("Este tradeo ya no está activo.",ephemeral=True)
        if session.get("trade_id"): await db.execute("UPDATE card_trade_sessions SET status='cancelled',completed_at=NOW() WHERE id=$1",session["trade_id"])
        await interaction.response.edit_message(embed=notice("Tradeo cancelado ❌",f"{interaction.user.mention} canceló el intercambio.",0xED4245),view=None)

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
            "favorita": "favorita", "tienda": "tienda", "ayudacartas": "cguia",
        }
        command = aliases.get(command, command)
        quick = {"sobre", "coleccion", "carta", "saldo_cartas", "diario_cartas", "mercado", "ranking_cartas", "tradeo", "sets", "set", "perfil", "cguia", "comparar"}
        if command not in quick:
            return False
        if command == "cguia":
            nl = "\n"
            embed = notice("Guía de Abo Cards 🎴", "Consulta rápida de comandos con `!` y `/`.")
            embed.add_field(name="Colección", value=nl.join([
                "`/sobre` · `!sobre` — Abre un sobre.",
                "`/coleccion` · `!coleccion` — Consulta tu colección.",
                "`/carta <nombre>` · `!carta <nombre>` — Detalles.",
                "`/sets` · `!sets` — Lista los sets.",
                "`/set <nombre>` · `!set <nombre>` — Progreso de un set.",
                "`/perfil [usuario]` · `!perfil [@usuario]` — Perfil.",
            ]), inline=False)
            embed.add_field(name="Economía", value=nl.join([
                "`/diario_cartas` · `!diario` — Recompensa diaria.",
                "`/saldo_cartas` · `!saldo` — Abo Coins.",
                "`/fusionar`, `/evolucionar`, `/favorita` — Mejoras.",
                "`/mercado` · `!mercado` — Mercado.",
                "`/mercado_publicar` — Publicar cartas.",
            ]), inline=False)
            embed.add_field(name="Interacción", value=nl.join([
                "`/comparar usuario` · `!comparar @usuario` — Comparar.",
                "`/tradeo usuario` · `!tradeo @usuario` — Intercambiar.",
                "`/pelea usuario modalidad` — Pelea 1v1 o 3v3.",
                "`/ranking_cartas` · `!ranking` — Ranking del servidor.",
            ]), inline=False)
            await message.channel.send(embed=embed)
            return True
        if command == "comparar":
            target = message.mentions[0] if message.mentions else None
            if target is None and argument:
                token = argument.strip()
                id_match = re.fullmatch(r"<@!?(\d+)>|\d+", token)
                target_id = int(id_match.group(1) or token) if id_match else None
                if target_id:
                    target = message.guild.get_member(target_id)
                else:
                    target = discord.utils.find(
                        lambda member: member.display_name.casefold() == argument.casefold()
                        or member.name.casefold() == argument.casefold(),
                        message.guild.members,
                    )
            if not target or target.bot or target.id == message.author.id:
                await message.channel.send(embed=notice("Uso de !comparar", "Menciona a otro miembro o usa su ID: `!comparar @usuario`.", 0xFEE75C))
                return True
            gid = message.guild.id
            solo_yo, solo_el, ambos = await compare_collections(gid, message.author.id, target.id)
            def fmt(rows, limit=15):
                if not rows: return "—"
                lines = [f"{card_emoji(r)} **{r['name']}** · {r['rarity']}" for r in rows[:limit]]
                if len(rows) > limit: lines.append(f"*…y {len(rows) - limit} más*")
                return "\n".join(lines)
            embed = notice(
                f"Comparación: {message.author.display_name} vs {target.display_name} 🔍",
                f"Únicas tuyas: **{len(solo_yo)}** · Únicas de {target.display_name}: **{len(solo_el)}** · En común: **{len(ambos)}**",
                0x5865F2,
            )
            embed.add_field(name=f"Solo tú tienes ({len(solo_yo)})", value=fmt(solo_yo), inline=False)
            embed.add_field(name=f"Solo {target.display_name} tiene ({len(solo_el)})", value=fmt(solo_el), inline=False)
            embed.add_field(name=f"Ambos tienen ({len(ambos)})", value=fmt(ambos), inline=False)
            await message.channel.send(embed=embed)
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
                "last_activity_at": time.monotonic(),
            }
            self.trade_sessions[message.channel.id]["trade_id"] = await db.fetchval("""INSERT INTO card_trade_sessions (guild_id,user_a,user_b,channel_id,offer_a,offer_b,status)
                VALUES ($1,$2,$3,$4,'{}'::jsonb,'{}'::jsonb,'active') RETURNING id""", message.guild.id, message.author.id, target.id, message.channel.id)
            sent=await message.channel.send(embed=self._trade_embed(self.trade_sessions[message.channel.id], "Tradeo iniciado 🤝", "Usen los botones para añadir cartas, confirmar o cancelar. El formato por texto sigue disponible."), view=TradeView(self,message.channel.id), allowed_mentions=discord.AllowedMentions(users=True))
            self.trade_sessions[message.channel.id]["message_id"]=sent.id
            await db.execute("UPDATE card_trade_sessions SET message_id=$1,last_activity_at=NOW() WHERE id=$2", sent.id, self.trade_sessions[message.channel.id]["trade_id"])
            return True
        if command == "perfil":
            target = message.mentions[0] if message.mentions else message.author
            await ensure_wallet(message.guild.id, target.id)
            wallet = await db.fetchrow("SELECT coins,xp,level,packs_opened,pity_rare,pity_epic FROM card_wallets_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2", message.guild.id, target.id)
            stats = await db.fetchrow("SELECT COUNT(*) FILTER (WHERE quantity>0)::int AS unique_cards,COALESCE(SUM(quantity),0)::int AS total_cards,COALESCE(SUM(quantity*c.base_value),0)::bigint AS value FROM card_inventory_global i JOIN card_catalog c ON c.slug=i.card_slug WHERE ($1::BIGINT IS NOT NULL) AND i.user_id=$2", message.guild.id, target.id)
            embed = notice(f"Perfil de {target.display_name} 🪪", f"Nivel: **{wallet['level']}** · XP: **{wallet['xp']}/{wallet['level']*1000}**\nSaldo: **{coins_text(wallet['coins'])} Abo Coins**\n\nCartas únicas: **{stats['unique_cards']}**\nCartas totales: **{stats['total_cards']}**\nValor: **{coins_text(stats['value'])} Abo Coins**\nSobres abiertos: **{wallet['packs_opened']}**\nPity rara: **{wallet['pity_rare']}/{PITY_RARE_LIMIT}**\nPity épica: **{wallet['pity_epic']}/{PITY_EPIC_LIMIT}**")
            await message.channel.send(embed=embed); return True
        if command in {"sets", "set"}:
            set_name = argument if command == "set" else ""
            if command == "sets":
                rows = await db.fetch("""SELECT s.slug,s.name,s.description,COUNT(c.slug)::int AS total,COUNT(i.card_slug) FILTER (WHERE COALESCE(i.quantity,0)>0)::int AS owned FROM card_sets s LEFT JOIN card_catalog c ON c.set_slug=s.slug AND c.active=TRUE LEFT JOIN card_inventory_global i ON i.card_slug=c.slug AND ($1::BIGINT IS NOT NULL) AND i.user_id=$2 WHERE s.active=TRUE GROUP BY s.slug,s.name,s.description ORDER BY s.name""", message.guild.id, message.author.id)
                text = "\n".join(f"🎴 **{r['name']}** · {r['owned']}/{r['total']} cartas" for r in rows) or "Todavía no hay sets disponibles."
                await message.channel.send(embed=notice("Sets de Abo Cards 🗂️", text)); return True
            row = await db.fetchrow("SELECT slug,name,description FROM card_sets WHERE active=TRUE AND (slug=$1 OR name ILIKE $2)", set_name.lower(), set_name)
            if not row:
                await message.channel.send(embed=notice("Set no encontrado", "Usa `!sets` para ver los sets disponibles.", 0xED4245)); return True
            cards = await db.fetch("SELECT c.name,c.rarity,c.emoji_name,c.emoji_id,COALESCE(i.quantity,0)::int AS quantity FROM card_catalog c LEFT JOIN card_inventory_global i ON i.card_slug=c.slug AND ($1::BIGINT IS NOT NULL) AND i.user_id=$2 WHERE c.active=TRUE AND c.set_slug=$3 ORDER BY c.rarity DESC,c.name", message.guild.id, message.author.id, row["slug"])
            text = "\n".join(f"{'✅' if c['quantity'] else '❌'} {card_emoji(c)} **{c['name']}** · ×{c['quantity']}" for c in cards)
            await message.channel.send(embed=notice(f"{row['name']} 🗂️", f"Progreso: **{sum(1 for c in cards if c['quantity']>0)}/{len(cards)}**\n\n{text}"))
            reward = await claim_set_reward(message.guild.id, message.author.id, row["slug"])
            if reward: await message.channel.send(embed=await card_message(message.guild.id, "set_complete", set_name=reward[0], reward=coins_text(reward[1])))
            return True
        if command == "saldo_cartas":
            await ensure_wallet(message.guild.id, message.author.id)
            coins = await db.fetchval("SELECT coins FROM card_wallets_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2", message.guild.id, message.author.id)
            await message.channel.send(embed=notice("Tu saldo 💰", f"Tienes **{coins_text(coins)} Abo Coins**. Usa `!sobre` para abrir un sobre."))
            return True
        if command == "diario_cartas":
            now = datetime.now(timezone.utc)
            await ensure_wallet(message.guild.id, message.author.id)
            async with db._pool().acquire() as connection:
                async with connection.transaction():
                    wallet = await connection.fetchrow(
                        "SELECT coins, daily_claimed_at, daily_streak FROM card_wallets_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 FOR UPDATE",
                        message.guild.id, message.author.id)
                    if wallet["daily_claimed_at"] and wallet["daily_claimed_at"].date() == now.date():
                        await message.channel.send(embed=notice("Diario ya reclamado ⏳", "Vuelve mañana para recibir más Abo Coins.", 0xFEE75C)); return True
                    streak = wallet["daily_streak"] + 1 if wallet["daily_claimed_at"] and (now.date() - wallet["daily_claimed_at"].date()) == timedelta(days=1) else 1
                    reward = min(DAILY_BASE + (streak - 1) * 25, 350)
                    await connection.execute("UPDATE card_wallets_global SET coins=coins+$1,daily_claimed_at=$2,daily_streak=$3,updated_at=NOW() WHERE ($4::BIGINT IS NOT NULL) AND user_id=$5", reward, now, streak, message.guild.id, message.author.id)
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
            owned = await db.fetchval("SELECT quantity FROM card_inventory_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 AND card_slug=$3", message.guild.id, message.author.id, row["slug"]) or 0
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
            rows = await db.fetch("SELECT l.id,l.seller_id,c.name,c.rarity,c.emoji_name,c.emoji_id,l.remaining,l.price_each FROM card_market_listings l JOIN card_catalog c ON c.slug=l.card_slug WHERE l.guild_id=$1 AND l.status='active' AND l.remaining>0 ORDER BY l.created_at DESC LIMIT 50", message.guild.id)
            await _market_seller_names(rows, message.guild)
            await message.channel.send(view=MarketView(rows, 0), allowed_mentions=discord.AllowedMentions(users=True)); return True
        if command == "ranking_cartas":
            rows = await db.fetch("SELECT i.user_id,SUM(i.quantity*c.base_value)::BIGINT AS value,SUM(i.quantity)::BIGINT AS total,COUNT(*)::INT AS unique_cards FROM card_inventory_global i JOIN card_catalog c ON c.slug=i.card_slug WHERE i.quantity>0 GROUP BY i.user_id ORDER BY value DESC,total DESC")
            members = {member.id: member for member in message.guild.members if not member.bot}
            rows = [row for row in rows if row["user_id"] in members][:10]
            lines = []
            for index,row in enumerate(rows,1):
                member=members[row["user_id"]]; lines.append(f"**{index}.** {member.display_name} · {coins_text(row['value'])} valor · {row['unique_cards']} únicas")
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
        embed.set_footer(text=f"Confirmaciones: {status} · Usa los botones para añadir, confirmar o cancelar")
        return embed

    async def _parse_trade_offer(self, text: str) -> dict:
        text = text.strip()
        if text.lower() in {"nada", "nada.", "ninguna", "ninguna.", "ninguno", "-"}:
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
        # Los comandos ! deben seguir llegando a handle_card_prefix; solo los
        # comandos propios del tradeo se procesan aquí.
        if lowered.startswith("!") and lowered not in {"!cancelar", "!cancelado", "!confirmar", "!confirmad", "!confirmado"}:
            return False
        if lowered in {"!cancelar", "!cancelado"}:
            self.trade_sessions.pop(message.channel.id, None)
            if session.get("trade_id"):
                await db.execute("UPDATE card_trade_sessions SET status='cancelled',completed_at=NOW() WHERE id=$1", session["trade_id"])
            await message.channel.send(embed=notice("Tradeo cancelado ❌", f"{message.author.mention} canceló el intercambio.", 0xED4245), allowed_mentions=discord.AllowedMentions(users=True))
            return True
        if lowered in {"!confirmar", "!confirmad", "!confirmado"}:
            session["last_activity_at"] = time.monotonic()
            offer = session["offers"][message.author.id]
            if not offer:
                # Nada es una oferta válida, pero se muestra qué debe hacer el usuario.
                session["offers"][message.author.id] = {}
            session["confirmed"][message.author.id] = True
            confirmation_column = "confirmed_a" if message.author.id == session["user_a"] else "confirmed_b"
            if session.get("trade_id"):
                await db.execute(f"UPDATE card_trade_sessions SET {confirmation_column}=TRUE WHERE id=$1", session["trade_id"])
            if all(session["confirmed"].values()):
                if session.get("completing"):
                    return True
                if not any(session["offers"][uid] for uid in session["users"]):
                    session["confirmed"] = {session["user_a"]: False, session["user_b"]: False}
                    await message.channel.send(embed=notice("Tradeo detenido", "No puedes completar un tradeo sin ofrecer cartas.", 0xFEE75C))
                    return True
                session["completing"] = True
                result = await self._complete_trade(session)
                if result:
                    self.trade_sessions.pop(message.channel.id, None)
                    await message.channel.send(embed=result, allowed_mentions=discord.AllowedMentions(users=True))
                else:
                    session.pop("completing", None)
                    session["confirmed"] = {session["user_a"]: False, session["user_b"]: False}
                    if session.get("trade_id"):
                        await db.execute("UPDATE card_trade_sessions SET confirmed_a=FALSE,confirmed_b=FALSE WHERE id=$1", session["trade_id"])
                    await message.channel.send(embed=notice("Tradeo detenido ⚠️", "Uno de los dos usuarios ya no tiene las cartas ofrecidas. Las confirmaciones se reiniciaron.", 0xFEE75C))
            else:
                await message.channel.send(embed=self._trade_embed(session, "Confirmación recibida ✅", f"{message.author.mention} confirmó. Falta la confirmación del otro usuario."), allowed_mentions=discord.AllowedMentions(users=True))
            return True
        looks_like_offer = bool(re.match(r"^\d+\s*(?:x|×)?\s+", content)) or "," in content or "\n" in content
        if not looks_like_offer and await card_row(content) is None and content.lower() not in {"nada", "nada.", "ninguna", "ninguna.", "ninguno", "-"}:
            return False
        try:
            offer = await self._parse_trade_offer(content)
        except ValueError as error:
            await message.channel.send(embed=notice("Oferta no válida", f"{error}\nUsa `2 Mielabo, 1 Abo Pro`, una carta por línea o `nada`.", 0xED4245))
            return True
        session["offers"][message.author.id] = offer
        session["last_activity_at"] = time.monotonic()
        session["confirmed"] = {session["user_a"]: False, session["user_b"]: False}
        if session.get("trade_id"):
            offer_column = "offer_a" if message.author.id == session["user_a"] else "offer_b"
            payload = {slug: data["quantity"] for slug, data in offer.items()}
            await db.execute(f"UPDATE card_trade_sessions SET {offer_column}=$1::jsonb,confirmed_a=FALSE,confirmed_b=FALSE,last_activity_at=NOW() WHERE id=$2", __import__("json").dumps(payload), session["trade_id"])
        await message.channel.send(embed=self._trade_embed(session, "Oferta actualizada 🎴", f"Oferta de {message.author.mention} guardada. Las confirmaciones se reiniciaron."), allowed_mentions=discord.AllowedMentions(users=True))
        return True

    async def _complete_trade(self, session: dict):
        offers = session["offers"]
        if not any(offers.get(user_id) for user_id in (session["user_a"], session["user_b"])):
            return None
        async with db._pool().acquire() as connection:
            async with connection.transaction():
                checks = []
                for user_id in (session["user_a"], session["user_b"]):
                    for slug, data in offers[user_id].items():
                        checks.append((user_id, slug, data["quantity"]))
                for user_id, slug, quantity in sorted(checks):
                    owned = await connection.fetchval(
                        "SELECT quantity FROM card_inventory_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 AND card_slug=$3 FOR UPDATE",
                        session["guild_id"], user_id, slug,
                    ) or 0
                    if owned < quantity:
                        return None
                for sender, receiver in ((session["user_a"], session["user_b"]), (session["user_b"], session["user_a"])):
                    for slug, data in offers[sender].items():
                        await connection.execute(
                            "UPDATE card_inventory_global SET quantity=quantity-$1 WHERE ($2::BIGINT IS NOT NULL) AND user_id=$3 AND card_slug=$4",
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

    # ── TIENDA NPC ────────────────────────────────────────────────────────────

    @app_commands.command(name="tienda", description="Tienda del NPC Abo — 4 cartas rotan cada 24 horas")
    @app_commands.guild_only()
    async def tienda_cmd(self, interaction: discord.Interaction):
        import hashlib, datetime as _dt
        seed_str = str(interaction.guild_id) + _dt.datetime.utcnow().strftime("%Y-%m-%d")
        seed = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
        rng = __import__("random").Random(seed)

        catalog = await db.fetch(
            "SELECT slug,name,rarity,emoji_name,emoji_id,base_value,image_file FROM card_catalog WHERE active=TRUE ORDER BY slug",
        )
        if not catalog:
            return await interaction.response.send_message(
                embed=notice("Tienda cerrada", "Todavía no hay cartas en el catálogo."), ephemeral=True
            )

        pool = list(catalog)
        rng.shuffle(pool)
        rare_plus = [r for r in pool if r["rarity"] in ("Rara", "Épica", "Legendaria")]
        if rare_plus:
            guaranteed = rng.choice(rare_plus)
            rest = [r for r in pool if r["slug"] != guaranteed["slug"]]
            rng.shuffle(rest)
            shop_cards = [guaranteed] + rest[:3]
        else:
            shop_cards = pool[:4]

        NPC_MARKUP = 2

        await ensure_wallet(interaction.guild_id, interaction.user.id)
        wallet_coins = await db.fetchval(
            "SELECT coins FROM card_wallets_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2",
            interaction.guild_id, interaction.user.id,
        ) or 0

        now_utc = _dt.datetime.utcnow()
        next_rotation = now_utc.replace(hour=0, minute=0, second=0, microsecond=0) + _dt.timedelta(days=1)
        secs_left = int((next_rotation - now_utc).total_seconds())
        hours_left, mins_left = secs_left // 3600, (secs_left % 3600) // 60

        class ShopView(discord.ui.LayoutView):
            def __init__(self):
                super().__init__(timeout=900)
                self._build()

            def _build(self):
                self.clear_items()
                children = [discord.ui.TextDisplay("## 🏬 Tienda de Abo")]
                for index, card in enumerate(shop_cards, 1):
                    price = card["base_value"] * NPC_MARKUP
                    button = discord.ui.Button(
                        label="Comprar",
                        emoji="🛍️",
                        style=discord.ButtonStyle.success,
                        custom_id=f"shop_buy:{card['slug']}",
                    )
                    button.callback = self._make_callback(card, price)
                    details = discord.ui.TextDisplay(
                        f"### {card_emoji(card)} {index}. {card['name']}\n"
                        f"**{card['rarity']}**\n"
                        f"🪙 **{coins_text(price)} Abo Coins**"
                    )
                    children.append(discord.ui.Section(details, accessory=button))
                    if index < len(shop_cards):
                        children.append(discord.ui.Separator())
                children.append(
                    discord.ui.TextDisplay(
                        f"💰 Saldo: **{coins_text(wallet_coins)} Abo Coins** · "
                        f"🔄 Rota en **{hours_left}h {mins_left}m**"
                    )
                )
                self.add_item(discord.ui.Container(*children, accent_color=0xF1C40F))

            def _make_callback(self, card, price):
                async def callback(inter: discord.Interaction):
                    # Confirmar inmediatamente la interacción para no superar
                    # el límite de 3 segundos mientras se completa la compra.
                    await inter.response.defer(ephemeral=True)
                    async with db._pool().acquire() as conn:
                        async with conn.transaction():
                            wallet = await conn.fetchrow(
                                "SELECT coins FROM card_wallets_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 FOR UPDATE",
                                inter.guild_id, inter.user.id,
                            )
                            if not wallet or wallet["coins"] < price:
                                return await inter.followup.send(
                                    embed=notice(
                                        "Saldo insuficiente",
                                        f"Necesitas **{coins_text(price)} Abo Coins** y tienes **{coins_text(wallet['coins'] if wallet else 0)}**.",
                                        0xED4245,
                                    ),
                                    ephemeral=True,
                                )
                            await conn.execute(
                                "UPDATE card_wallets_global SET coins=coins-$1,updated_at=NOW() WHERE ($2::BIGINT IS NOT NULL) AND user_id=$3",
                                price, inter.guild_id, inter.user.id,
                            )
                            await add_card(conn, inter.guild_id, inter.user.id, card["slug"])
                    await inter.followup.send(
                        embed=notice(
                            "¡Compra realizada! 🛍️",
                            f"Compraste {card_emoji(card)} **{card['name']}** por **{coins_text(price)} Abo Coins**.",
                        ),
                        ephemeral=True,
                    )
                return callback

        await interaction.response.send_message(view=ShopView())


    # ── MERCADO ───────────────────────────────────────────────────────────────

    @app_commands.command(name="mercado_publicar", description="Publica copias de una carta en el mercado")
    @app_commands.guild_only()
    @app_commands.describe(carta="Carta propia a vender", cantidad="Copias", precio="Precio por copia")
    async def mercado_publicar(self, interaction: discord.Interaction, carta: str, cantidad: int, precio: int):
        if (wait := self._rate_limit("market_publish", interaction.guild_id, interaction.user.id, 3)):
            return await interaction.response.send_message(f"Espera {wait:.1f}s antes de publicar otra carta.", ephemeral=True)
        row = await card_row(carta)
        if not row or cantidad < 1 or precio < 1:
            return await interaction.response.send_message(embed=notice("Publicación inválida", "Carta, cantidad y precio deben ser válidos.", 0xED4245), ephemeral=True)
        async with db._pool().acquire() as connection:
            async with connection.transaction():
                owned = await connection.fetchval("SELECT quantity FROM card_inventory_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 AND card_slug=$3 FOR UPDATE", interaction.guild_id, interaction.user.id, row["slug"]) or 0
                if owned < cantidad:
                    return await interaction.response.send_message(embed=notice("No tienes suficientes copias", f"Posees **×{owned}** de {row['name']}.", 0xED4245), ephemeral=True)
                await connection.execute("UPDATE card_inventory_global SET quantity=quantity-$1 WHERE ($2::BIGINT IS NOT NULL) AND user_id=$3 AND card_slug=$4", cantidad, interaction.guild_id, interaction.user.id, row["slug"])
                await connection.execute("INSERT INTO card_market_listings (guild_id,seller_id,card_slug,quantity,remaining,price_each) VALUES ($1,$2,$3,$4,$4,$5)", interaction.guild_id, interaction.user.id, row["slug"], cantidad, precio)
        await interaction.response.send_message(embed=notice("Carta publicada 🏪", f"Publicaste **×{cantidad} {card_emoji(row)} {row['name']}** a **{coins_text(precio)} Abo Coins** cada una."), ephemeral=True)

    @mercado_publicar.autocomplete("carta")
    async def mercado_publicar_carta_autocomplete(self, interaction: discord.Interaction, current: str):
        query = f"%{(current or '').strip()}%"
        rows = await db.fetch(
            """SELECT c.slug,c.name,c.rarity,i.quantity
               FROM card_catalog c JOIN card_inventory_global i ON i.card_slug=c.slug
               WHERE c.active=TRUE AND ($1::BIGINT IS NOT NULL) AND i.user_id=$2 AND i.quantity>0
                 AND (c.name ILIKE $3 OR c.slug ILIKE $3)
               ORDER BY CASE WHEN c.name ILIKE $4 THEN 0 ELSE 1 END, c.rarity DESC, c.name
               LIMIT 25""",
            interaction.guild_id, interaction.user.id, query, f"{(current or '').strip()}%",
        )
        return [
            app_commands.Choice(
                name=f"{row['name']} · {row['rarity']} · ×{row['quantity']}"[:100],
                value=row['slug'],
            )
            for row in rows
        ]

    @app_commands.command(name="mercado_cancelar", description="Cancela una publicación tuya y devuelve las cartas")
    @app_commands.guild_only()
    async def mercado_cancelar(self, interaction: discord.Interaction, publicacion: int):
        if publicacion < 1:
            return await interaction.response.send_message("Indica un ID de publicación válido.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        restored, error = await cancel_listing(interaction.guild_id, interaction.user.id, publicacion)
        if error:
            return await interaction.followup.send(embed=notice("No se pudo cancelar", error, 0xED4245), ephemeral=True)
        await interaction.followup.send(embed=notice("Publicación cancelada ✅", f"Se devolvieron **×{restored}** cartas a tu colección."), ephemeral=True)

    @app_commands.command(name="mercado", description="Muestra las cartas disponibles en el mercado")
    @app_commands.guild_only()
    async def mercado(self, interaction: discord.Interaction):
        await interaction.response.defer()
        rows = await db.fetch("""SELECT l.id,l.seller_id,c.name,c.rarity,c.emoji_name,c.emoji_id,l.remaining,l.price_each FROM card_market_listings l JOIN card_catalog c ON c.slug=l.card_slug WHERE l.guild_id=$1 AND l.status='active' AND l.remaining>0 ORDER BY l.created_at DESC LIMIT 50""", interaction.guild_id)
        await _market_seller_names(rows, interaction.guild)
        await interaction.edit_original_response(view=MarketView(rows, 0), allowed_mentions=discord.AllowedMentions(users=True))

    @app_commands.command(name="ranking_cartas", description="Ranking de coleccionistas por valor de cartas")
    @app_commands.guild_only()
    async def ranking_cartas(self, interaction: discord.Interaction):
        rows = await db.fetch("""SELECT i.user_id,SUM(i.quantity*c.base_value)::BIGINT AS value,SUM(i.quantity)::BIGINT AS total,COUNT(*)::INT AS unique_cards FROM card_inventory_global i JOIN card_catalog c ON c.slug=i.card_slug WHERE i.quantity>0 GROUP BY i.user_id ORDER BY value DESC,total DESC""")
        members = {member.id: member for member in interaction.guild.members if not member.bot}
        rows = [row for row in rows if row["user_id"] in members][:10]
        lines = []
        for index, row in enumerate(rows, 1):
            name = members[row["user_id"]].display_name
            lines.append(f"**{index}.** {name} · {coins_text(row['value'])} valor · {row['unique_cards']} únicas")
        await interaction.response.send_message(embed=notice("Ranking de coleccionistas 🏆", "\n".join(lines) or "Todavía no hay coleccionistas."))


    @app_commands.command(name="pelea", description="Desafía a otro usuario en combate 1v1 o 3v3")
    @app_commands.guild_only()
    @app_commands.choices(modalidad=[
        app_commands.Choice(name="1v1 · Una carta", value="1v1"),
        app_commands.Choice(name="3v3 · Tres cartas", value="3v3"),
    ])
    async def pelea(self, interaction: discord.Interaction, usuario: discord.Member, modalidad: str):
        if (wait := self._rate_limit("challenge", interaction.guild_id, interaction.user.id, 10)):
            return await interaction.response.send_message(f"Espera {wait:.1f}s antes de enviar otro desafío.", ephemeral=True)
        if usuario.bot or usuario.id == interaction.user.id:
            return await interaction.response.send_message(embed=notice("Desafío inválido","Elige a otro usuario que no sea un bot.",0xED4245),ephemeral=True)
        active=await db.fetchrow("SELECT id FROM card_battles WHERE guild_id=$1 AND status='active' AND (user_a IN ($2,$3) OR user_b IN ($2,$3)) LIMIT 1",interaction.guild_id,interaction.user.id,usuario.id)
        if active:
            # Si la batalla activa no tiene BattleView vivo en memoria, está huérfana → limpiarla automáticamente
            live_keys=[k for k,s in self.battles.items() if s.get('db_id')==active['id']]
            if not live_keys:
                await db.execute("UPDATE card_battles SET status='cancelled',completed_at=NOW() WHERE id=$1",active['id'])
            else:
                return await interaction.response.send_message(embed=notice("Ya hay una pelea activa","Uno de los usuarios ya está combatiendo. Espera a que termine o expire por inactividad.",0xED4245),ephemeral=True)
        modalidad = modalidad if modalidad in {"1v1", "3v3"} else "1v1"
        if modalidad == "1v1":
            modo_texto = "**1v1 · Una carta**"
        else:
            modo_texto = "**3v3 · Tres cartas por equipo**"
        await interaction.response.send_message(
            embed=notice("⚔️ Desafío de pelea", f"{interaction.user.mention} desafió a {usuario.mention} en modalidad {modo_texto}.\n\nEl usuario desafiado debe aceptar para comenzar."),
            view=BattleChallengeView(self, interaction.guild_id, interaction.user.id, usuario.id, modalidad),
        )

    async def prepare_battle(self,interaction,guild_id,user_a,user_b,mode="1v1"):
        team_size = 1 if mode == "1v1" else BATTLE_TEAM_SIZE
        choices=[]
        for user_id in (user_a,user_b):
            rows=await db.fetch("SELECT c.*, i.quantity AS owned_quantity FROM card_catalog c JOIN card_inventory_global i ON i.card_slug=c.slug AND ($1::BIGINT IS NOT NULL) AND i.user_id=$2 WHERE c.active=TRUE AND i.quantity>0 ORDER BY c.rarity DESC,c.name LIMIT 25",guild_id,user_id)
            if not rows:
                return await interaction.edit_original_response(embed=notice("No hay personajes disponibles",f"<@{user_id}> necesita una carta en su colección.",0xED4245),view=None)
            if mode == "3v3" and len(rows) < BATTLE_TEAM_SIZE:
                return await interaction.edit_original_response(embed=notice("No se puede iniciar 3v3",f"<@{user_id}> necesita al menos **3 cartas distintas** en su colección para este modo.",0xED4245),view=None)
            choices.append((user_id,rows,team_size))
        key=f"{guild_id}:{user_a}:{user_b}:{interaction.id}"
        self.battles[key]={"guild_id":guild_id,"channel_id":interaction.channel_id,"users":(user_a,user_b),"selected":{},"mode":mode}
        if mode == "3v3":
            title, text = "⚔️ Elige tu equipo 3v3", f"<@{user_a}> y <@{user_b}> deben escoger **3 cartas distintas**. La más rápida sale primero y las demás entran cuando una carta cae."
        else:
            title, text = "⚔️ Elige tu carta 1v1", f"<@{user_a}> y <@{user_b}> deben escoger una carta."
        await interaction.edit_original_response(embed=notice(title,text),view=BattleSetupView(self,key,choices))

    async def _build_battle(self,session):
        """Crea los equipos, la carta activa de cada jugador, el turno inicial y el registro en la DB."""
        teams={}
        for user_id in session['users']:
            slugs=session['selected'].get(user_id) or []
            if isinstance(slugs,str): slugs=[slugs]
            expected = 1 if session.get('mode', '1v1') == '1v1' else BATTLE_TEAM_SIZE
            if len(slugs) != expected:
                return False
            rows=await db.fetch("SELECT * FROM card_catalog WHERE slug=ANY($1::text[]) AND active=TRUE",list(slugs))
            by_slug={r['slug']:r for r in rows}
            team=[]
            for slug in slugs:
                row=by_slug.get(slug)
                if not row: continue
                evo = await db.fetchrow("SELECT stat_boost_pct FROM card_inventory_evo_global WHERE ($1::BIGINT IS NOT NULL) AND user_id=$2 AND card_slug=$3", session['guild_id'], user_id, slug)
                if evo and int(evo.get('stat_boost_pct') or 0) > 0:
                    row = dict(row)
                    base_stats = combat_stats(row)
                    row['stats'] = _apply_boost(base_stats, int(evo['stat_boost_pct']))
                hp=max(1,stat_num(combat_stats(row),'HP',BATTLE_MAX_HP))
                team.append({"id":user_id,"mention":f"<@{user_id}>","card":row,"max_hp":hp,"hp":hp,"energy":1,"defending":False,"states":{},"last_breath_used":False})
            if not team: return False
            # La más rápida sale primero y define el orden de reemplazo
            team.sort(key=lambda f:-stat_num(combat_stats(f['card']),'Speed',0))
            for f in team: f['team']=team
            teams[user_id]=team
        players={uid:team[0] for uid,team in teams.items()}
        # El jugador con mayor Speed empieza con 2 de energía en lugar de 1
        speeds={uid:stat_num(combat_stats(players[uid]['card']),'Speed',0) for uid in players}
        turn=max(speeds,key=lambda uid:speeds[uid])
        if speeds[session['users'][0]]!=speeds[session['users'][1]]:
            players[turn]['energy']=2
        session.update({'started':True,'teams':teams,'players':players,'turn':turn,'turns':0,'last_action_at':time.monotonic()})
        leads=[players[x]['card'] for x in session['users']]
        session['db_id']=await db.fetchval("INSERT INTO card_battles (guild_id,channel_id,user_a,user_b,card_a,card_b,mode) VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id",session['guild_id'],session['channel_id'],*session['users'],leads[0]['slug'],leads[1]['slug'],session.get('mode','1v1'))
        return True

    async def begin_battle(self,interaction,key):
        session=self.battles.get(key)
        if not session or session.get('started'): return
        if not await self._build_battle(session): return
        await interaction.message.edit(embed=self.battle_embed(session,"¡La pelea comienza! El más rápido empieza con 2 ⚡."),view=BattleView(self,key))
        session['battle_message_id']=interaction.message.id

    async def begin_battle_rematch(self, interaction, key):
        """Como begin_battle pero edita el mensaje existente del canal en lugar de interaction.message."""
        session = self.battles.get(key)
        if not session or session.get('started'): return
        if not await self._build_battle(session): return
        # Editar el mensaje original del canal (guardado en _rematch_message_id por end_battle)
        guild   = self.bot.get_guild(session['guild_id'])
        channel = guild.get_channel(session['channel_id']) if guild else None
        msg_id  = session.get('_rematch_message_id')
        if channel and msg_id:
            msg = await channel.get_partial_message(msg_id).edit(
                embed=self.battle_embed(session, "¡Revancha! El más rápido empieza con 2 ⚡."),
                view=BattleView(self, key)
            )
            session['battle_message_id'] = msg.id
        else:
            # Fallback: usar followup si no tenemos el canal/mensaje
            msg = await interaction.followup.send(
                embed=self.battle_embed(session, "¡Revancha! El más rápido empieza con 2 ⚡."),
                view=BattleView(self, key)
            )
            session['battle_message_id'] = msg.id

    def _replace_fallen(self,session,user_id):
        """Si la carta activa cayó, entra la siguiente viva del equipo. Devuelve (quedan_cartas, texto)."""
        fallen=session['players'][user_id]
        if fallen['hp']>0: return True,""
        nxt=next((f for f in session['teams'][user_id] if f['hp']>0),None)
        if nxt is None: return False,""
        nxt['energy']=fallen['energy']  # la energía es del jugador, no de la carta
        fallen['defending']=False
        session['players'][user_id]=nxt
        return True,f"\n💀 {fallen['card']['name']} cayó. ¡Entra {card_emoji(nxt['card'])} **{nxt['card']['name']}** de {nxt['mention']}!"

    def battle_embed(self,session,message):
        p1=session['players'][session['users'][0]]; p2=session['players'][session['users'][1]]
        title = "⚔️ Pelea 3v3 · equipos de cartas" if session.get('mode') == '3v3' else "⚔️ Pelea 1v1 · carta contra carta"
        embed=notice(title,f"{message}\n\n{battle_line(p1)}\n\n**VS**\n\n{battle_line(p2)}",0xE67E22)
        embed.add_field(name="Turno",value=f"{session['turns']+1} · juega <@{session['turn']}>",inline=False)
        return embed

    async def battle_action(self,interaction,key,action):
        session=self.battles.get(key)
        if not session: return
        if (wait := self._rate_limit("battle_action", session["guild_id"], interaction.user.id, 0.8)):
            return await interaction.followup.send(f"Espera {wait:.1f}s antes de realizar otra acción.", ephemeral=True)
        session["last_action_at"] = time.monotonic()
        actor=session['players'][session['turn']]; enemy_id=next(x for x in session['users'] if x!=session['turn']); enemy=session['players'][enemy_id]; stats=combat_stats(actor['card'])
        if action=='surrender': return await self.end_battle(interaction,key,enemy_id,f"{actor['mention']} se rindió. ¡Victoria para {enemy['mention']}!")
        message=''

        if 'Lento' in actor['states']:
            actor['states']['Lento'] -= 1
            if actor['states']['Lento'] <= 0: del actor['states']['Lento']
            session['turns'] += 1; session['turn'] = enemy_id
            await db.execute("UPDATE card_battles SET turns=$1 WHERE id=$2", session['turns'], session['db_id'])
            msg = await interaction.edit_original_response(embed=self.battle_embed(session, f"🐢 {actor['mention']} está **Lento** y pierde el turno sin gastar energía."), view=BattleView(self,key))
            session['battle_message_id'] = msg.id; return

        # ── Aturdimiento: pierde el turno sin ganar energía ────────────────────
        if 'Aturdimiento' in actor['states']:
            actor['states']['Aturdimiento']-=1
            if actor['states']['Aturdimiento']<=0: del actor['states']['Aturdimiento']
            session['turns']+=1; session['turn']=enemy_id
            await db.execute("UPDATE card_battles SET turns=$1 WHERE id=$2",session['turns'],session['db_id'])
            stun_msg=f"⚡ {actor['mention']} está **Aturdido** y pierde el turno sin ganar energía."
            msg=await interaction.edit_original_response(embed=self.battle_embed(session,stun_msg),view=BattleView(self,key))
            session['battle_message_id']=msg.id; return

        if action=='defend':
            actor['defending']=True; actor['energy']=min(5,actor['energy']+1); message=f"{actor['mention']} levantó la defensa y recuperó 1 ⚡."
        elif action.startswith('switch:'):
            try: idx=int(action.split(':',1)[1])
            except (ValueError, IndexError): idx=-1
            team=session['teams'][session['turn']]
            if not 0<=idx<len(team) or team[idx] is actor or team[idx]['hp']<=0:
                return await interaction.followup.send("Esa carta no está disponible.",ephemeral=True)
            new=team[idx]; new['energy']=actor['energy']; actor['defending']=False
            session['players'][session['turn']]=new
            message=f"🔄 {actor['mention']} cambió a {card_emoji(new['card'])} **{new['card']['name']}**. ✅ Cambio gratuito: sigues jugando tú."
            await db.execute("INSERT INTO card_battle_logs (battle_id,turn_number,actor_id,action,damage,effect) VALUES ($1,$2,$3,$4,$5,$6)",session['db_id'],session['turns']+1,actor['id'],f"🔄 Cambio gratuito a {new['card']['name']}",0,'')
            # Cambiar de carta no consume el turno: no se procesan estados, no
            # aumenta el contador y el mismo jugador puede actuar con la nueva carta.
            msg=await interaction.edit_original_response(embed=self.battle_embed(session,message),view=BattleView(self,key))
            session['battle_message_id']=msg.id
            return
        else:
            # ── Silencio: solo puede atacar o defender, no usar habilidades ─────
            if action.startswith('ability') and 'Silencio' in actor['states']:
                msg=await interaction.edit_original_response(embed=self.battle_embed(session,"🔇 No puedes usar habilidades bajo **Silencio**."),view=BattleView(self,key))
                session['battle_message_id']=msg.id; return
            if action.startswith('ability'):
                try: ability_number=int(action.split(':',1)[1]) if ':' in action else 1
                except (ValueError, IndexError): ability_number=1
                suffix='' if ability_number==1 else f' {ability_number}'
                name=str(stats.get(f'Habilidad{suffix}','')).strip(); damage=damage_num(stats.get(f'Daño de habilidad{suffix}'))
                if not name or not damage: return await interaction.followup.send("Esta habilidad no tiene daño configurado.",ephemeral=True)
                skill_cost=max(1,int(stats.get(f'Costo de energía de habilidad{suffix}') or 2))
                if actor['energy']<skill_cost:
                    await interaction.followup.send(f"Necesitas {skill_cost} ⚡ para usar **{name}**. Tienes {actor['energy']} ⚡ — ataca, defiéndete o ríndate.",ephemeral=True)
                    msg=await interaction.edit_original_response(embed=self.battle_embed(session,"⚡ Energía insuficiente para la habilidad."),view=BattleView(self,key))
                    session['battle_message_id']=msg.id; return
                actor['energy']-=skill_cost; label=f"✨ Habilidad {ability_number}: {name}"; effect=str(stats.get(f'Estado de habilidad{suffix}','')).strip(); chance=stat_num(stats,f'Probabilidad de efecto de habilidad{suffix}',0); duration=stat_num(stats,f'Duración de efecto de habilidad{suffix}',0)
                damage_type=str(stats.get(f'Tipo de daño de habilidad{suffix}',stats.get('Tipo de daño','Físico'))).strip()
            else:
                damage=max(1,stat_num(stats,'ATK',10)); label='⚔️ Ataque básico'; effect=''; chance=0; duration=0; actor['energy']=min(5,actor['energy']+1)
                damage_type=str(stats.get('Tipo de daño','Físico')).strip()
            # ── Debilitado: reduce el ATK del actor un 30% ─────────────────────
            if 'Debilitado' in actor['states']:
                damage=max(1,int(damage*0.7))
            # ── Aplicar fórmula según tipo de daño ─────────────────────────────
            enemy_stats=combat_stats(enemy['card']); defense=stat_num(enemy_stats,'DEF',0)
            blocked=enemy['defending']
            if damage_type=='Porcentual':
                raw=max(1,round(enemy['max_hp']*damage/100))
                damage=raw; blocked=False
            elif damage_type=='Verdadero':
                damage=max(1,damage); blocked=False
            elif damage_type=='Mágico':
                damage=max(1,damage)
                if blocked: damage=max(1,damage//2); enemy['defending']=False; blocked=False
            else:
                damage=max(1,damage-defense//2)
                if blocked: damage=max(1,damage//2); enemy['defending']=False; blocked=False
            if blocked: enemy['defending']=False
            # ── Escudo: anula el 99% del daño final, sin importar su tipo ──────
            if 'Escudo' in enemy['states']:
                damage=max(1,(damage+99)//100)
                enemy['states']['Escudo']-=1
                if enemy['states']['Escudo']<=0: del enemy['states']['Escudo']
            enemy['hp']=max(0,enemy['hp']-damage); applied=''
            if effect in BATTLE_STATES and chance and random.randint(1,100)<=chance:
                _target=actor if effect in ('Escudo','Regeneración') else enemy
                _target['states'][effect]=max(1,duration); applied=effect
            # ── Pasiva del actor: se activa al atacar ──────────────────────────
            p_stats=stats; p_name=str(p_stats.get('Pasiva','')).strip()
            if p_name and p_name!='—':
                p_dmg=damage_num(p_stats.get('Daño de pasiva')); p_type=str(p_stats.get('Tipo de daño de pasiva',p_stats.get('Tipo de daño','Físico'))).strip()
                p_effect=str(p_stats.get('Estado de pasiva','')).strip(); p_chance=stat_num(p_stats,'Probabilidad de efecto de pasiva',0); p_dur=stat_num(p_stats,'Duración de efecto de pasiva',0)
                passive_msg_parts=[]
                if p_dmg:
                    p_def=defense if p_type not in ('Verdadero','Porcentual','Mágico') else 0
                    p_real=max(1,round(enemy['max_hp']*p_dmg/100)) if p_type=='Porcentual' else max(1,p_dmg-p_def//2)
                    enemy['hp']=max(0,enemy['hp']-p_real)
                    passive_msg_parts.append(f"+{p_real} daño de pasiva")
                if p_effect in BATTLE_STATES and p_chance and random.randint(1,100)<=p_chance:
                    _p_target=actor if p_effect in ('Escudo','Regeneración') else enemy
                    _p_target['states'][p_effect]=max(1,p_dur); passive_msg_parts.append(f"aplicó {p_effect}")
                if passive_msg_parts:
                    message_suffix=f" *(Pasiva — {p_name}: {', '.join(passive_msg_parts)})*"
                else:
                    message_suffix=''
            else:
                message_suffix=''
            dmg_label={'Físico':'💢','Mágico':'✨','Verdadero':'⚡','Porcentual':'📊'}.get(damage_type,'')
            message=f"{actor['mention']} usó **{label}** e hizo **{damage}** de daño {dmg_label}"+(f" y aplicó **{applied}**." if applied else ".")+message_suffix
            await db.execute("INSERT INTO card_battle_logs (battle_id,turn_number,actor_id,action,damage,effect) VALUES ($1,$2,$3,$4,$5,$6)",session['db_id'],session['turns']+1,actor['id'],label,damage,applied)
        session['turns']+=1

        # ── Último aliento: 20% de sobrevivir con 1 HP (una sola vez) ──────────
        if enemy['hp']<=0 and not enemy.get('last_breath_used') and random.randint(1,100)<=20:
            enemy['hp']=1; enemy['last_breath_used']=True
            message+=f"\n💫 **¡Último aliento!** {enemy['mention']} sobrevivió con 1 HP."
        if enemy['hp']<=0:
            message+=f"\n💥 {enemy['card']['name']} de {enemy['mention']} quedó fuera de combate."
            alive,txt=self._replace_fallen(session,enemy_id)
            if not alive: return await self.end_battle(interaction,key,actor['id'],message+f"\n☠️ ¡Todo el equipo de {enemy['mention']} cayó!")
            message+=txt; enemy=session['players'][enemy_id]

        # ── Efectos de estado al final del turno ───────────────────────────────
        state_msgs=[]
        for player in (actor,enemy):
            for state in list(player['states']):
                if state in ('Quemadura','Veneno'):
                    player['hp']=max(0,player['hp']-3); state_msgs.append(f"{player['mention']} recibió 3 de daño por {state}.")
                elif state=='Regeneración':
                    player['hp']=min(player['max_hp'],player['hp']+5); state_msgs.append(f"{player['mention']} regeneró 5 HP.")
                # Escudo y Lento ya se decrementan inline al aplicarse; no volver a decrementar aquí
                # Aturdimiento se decrementa al inicio del turno del afectado
                if state not in ('Escudo','Lento'):
                    player['states'][state]-=1
                    if player['states'][state]<=0: del player['states'][state]
            # ── Último aliento post-estados ────────────────────────────────────
            if player['hp']<=0 and not player.get('last_breath_used') and random.randint(1,100)<=20:
                player['hp']=1; player['last_breath_used']=True
                state_msgs.append(f"💫 **¡Último aliento!** {player['mention']} sobrevivió con 1 HP.")
        if state_msgs: message+=f"\n{'  '.join(state_msgs)}"
        if enemy['hp']<=0:
            message+=f"\n☠️ {enemy['card']['name']} cayó por un estado."
            alive,txt=self._replace_fallen(session,enemy_id)
            if not alive: return await self.end_battle(interaction,key,actor['id'],message+f"\n☠️ ¡Todo el equipo de {enemy['mention']} cayó!")
            message+=txt
        if actor['hp']<=0:
            message+=f"\n☠️ {actor['card']['name']} cayó por un estado."
            alive,txt=self._replace_fallen(session,actor['id'])
            if not alive: return await self.end_battle(interaction,key,enemy_id,message+f"\n☠️ ¡Todo el equipo de {actor['mention']} cayó!")
            message+=txt
        session['turn']=enemy_id
        await db.execute("UPDATE card_battles SET turns=$1 WHERE id=$2",session['turns'],session['db_id'])
        msg=await interaction.edit_original_response(embed=self.battle_embed(session,message),view=BattleView(self,key))
        session['battle_message_id']=msg.id

    async def end_battle(self,interaction,key,winner_id,message):
        session=self.battles.get(key)
        if not session: return
        loser_id=next(x for x in session['users'] if x!=winner_id)
        await db.execute("UPDATE card_battles SET status='completed',winner_id=$1,loser_id=$2,turns=$3,result=$4::jsonb,completed_at=NOW() WHERE id=$5",winner_id,loser_id,session['turns'],json.dumps({'message':message,'teams':{str(u):[f['card']['slug'] for f in t] for u,t in session.get('teams',{}).items()}}),session['db_id'])
        # Las revanchas reutilizan cartas y no generan monedas para evitar farming.
        reward_msg = "\n\n🏆 Pelea terminada."
        if not session.get('is_rematch'):
            await ensure_wallet(session['guild_id'],winner_id)
            await db.execute("UPDATE card_wallets_global SET coins=coins+$1,updated_at=NOW() WHERE ($2::BIGINT IS NOT NULL) AND user_id=$3",BATTLE_REWARD,session['guild_id'],winner_id)
            reward_msg=f"\n\n🏆 Pelea terminada. <@{winner_id}> gana **+{coins_text(BATTLE_REWARD)} Abo Coins**."
        final_embed=self.battle_embed(session,message+reward_msg)
        rematch_view=RematchView(self,session,winner_id,loser_id)
        self.battles.pop(key,None)  # borrar ANTES del await para evitar reuso, session ya está en local
        msg=await interaction.edit_original_response(embed=final_embed,view=rematch_view)
        rematch_view._message_id=msg.id  # guardar para que begin_battle_rematch pueda editar el mismo mensaje
