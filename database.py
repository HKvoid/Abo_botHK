"""Persistencia PostgreSQL/Neon para Abo, con migración conservadora de SQLite."""
from __future__ import annotations

import asyncio
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import asyncpg


_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_memory_user_channel_created
    ON memory (user_id, channel_id, created_at DESC);

CREATE TABLE IF NOT EXISTS warns (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    moderator_id BIGINT NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_warns_guild_user_created
    ON warns (guild_id, user_id, created_at);

CREATE TABLE IF NOT EXISTS color_roles (
    guild_id BIGINT NOT NULL,
    categoria TEXT NOT NULL,
    clave TEXT NOT NULL,
    role_id BIGINT NOT NULL,
    PRIMARY KEY (guild_id, categoria, clave)
);

CREATE TABLE IF NOT EXISTS purge_exceptions (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    razon TEXT NOT NULL,
    added_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS purge_scans (
    guild_id BIGINT PRIMARY KEY,
    candidate_user_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
    scanned_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id BIGINT NOT NULL,
    setting_key TEXT NOT NULL,
    setting_value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (guild_id, setting_key)
);

CREATE TABLE IF NOT EXISTS tickets (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL UNIQUE,
    opener_id BIGINT NOT NULL,
    title TEXT NOT NULL,
    details TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    claimed_by BIGINT,
    closed_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    transcript_message_id BIGINT,
    transcript_url TEXT,
    transcript_html BYTEA
);
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS transcript_html BYTEA;
CREATE INDEX IF NOT EXISTS idx_tickets_guild_opener_status
    ON tickets (guild_id, opener_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tickets_one_open_per_user
    ON tickets (guild_id, opener_id) WHERE status = 'open';

CREATE TABLE IF NOT EXISTS ticket_panels (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    image_url TEXT NOT NULL DEFAULT '',
    buttons TEXT NOT NULL DEFAULT '[{"emoji":"🎫","label":"Crear ticket"}]',
    channel_id BIGINT,
    message_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (guild_id, name)
);
ALTER TABLE ticket_panels ADD COLUMN IF NOT EXISTS image_url TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_ticket_panels_guild ON ticket_panels (guild_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS card_catalog (
    slug TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    rarity TEXT NOT NULL,
    image_file TEXT NOT NULL,
    drop_weight INTEGER NOT NULL DEFAULT 100,
    base_value INTEGER NOT NULL DEFAULT 100,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    emoji_name TEXT NOT NULL DEFAULT '',
    emoji_id TEXT NOT NULL DEFAULT '',
    image_mime TEXT NOT NULL DEFAULT '',
    image_data BYTEA,
    set_slug TEXT NOT NULL DEFAULT 'original',
    description TEXT NOT NULL DEFAULT '',
    stats JSONB NOT NULL DEFAULT '{}'::jsonb,
    tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    embed_color INTEGER NOT NULL DEFAULT 5793266,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE card_catalog ADD COLUMN IF NOT EXISTS set_slug TEXT NOT NULL DEFAULT 'original';
ALTER TABLE card_catalog ADD COLUMN IF NOT EXISTS emoji_name TEXT NOT NULL DEFAULT '';
ALTER TABLE card_catalog ADD COLUMN IF NOT EXISTS emoji_id TEXT NOT NULL DEFAULT '';
ALTER TABLE card_catalog ADD COLUMN IF NOT EXISTS image_mime TEXT NOT NULL DEFAULT '';
ALTER TABLE card_catalog ADD COLUMN IF NOT EXISTS image_data BYTEA;
ALTER TABLE card_catalog ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '';
ALTER TABLE card_catalog ADD COLUMN IF NOT EXISTS stats JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE card_catalog ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];
ALTER TABLE card_catalog ADD COLUMN IF NOT EXISTS embed_color INTEGER NOT NULL DEFAULT 5793266;


CREATE TABLE IF NOT EXISTS card_sets (
    slug TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    reward_coins INTEGER NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO card_sets (slug,name,description,reward_coins)
VALUES ('original','Colección Original','Las primeras cartas de Abo Cards.',250)
ON CONFLICT (slug) DO NOTHING;

CREATE TABLE IF NOT EXISTS card_wallets (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    coins BIGINT NOT NULL DEFAULT 500 CHECK (coins >= 0),
    daily_claimed_at TIMESTAMPTZ,
    daily_streak INTEGER NOT NULL DEFAULT 0,
    xp BIGINT NOT NULL DEFAULT 0,
    level INTEGER NOT NULL DEFAULT 1,
    pity_rare INTEGER NOT NULL DEFAULT 0,
    pity_epic INTEGER NOT NULL DEFAULT 0,
    packs_opened INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (guild_id, user_id)
);

ALTER TABLE card_wallets ADD COLUMN IF NOT EXISTS xp BIGINT NOT NULL DEFAULT 0;
ALTER TABLE card_wallets ADD COLUMN IF NOT EXISTS level INTEGER NOT NULL DEFAULT 1;
ALTER TABLE card_wallets ADD COLUMN IF NOT EXISTS pity_rare INTEGER NOT NULL DEFAULT 0;
ALTER TABLE card_wallets ADD COLUMN IF NOT EXISTS pity_epic INTEGER NOT NULL DEFAULT 0;
ALTER TABLE card_wallets ADD COLUMN IF NOT EXISTS packs_opened INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS card_set_claims (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    set_slug TEXT NOT NULL,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (guild_id,user_id,set_slug)
);

CREATE TABLE IF NOT EXISTS card_message_templates (
    guild_id BIGINT NOT NULL,
    message_key TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    color INTEGER NOT NULL DEFAULT 5793266,
    updated_by BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (guild_id, message_key)
);

CREATE TABLE IF NOT EXISTS card_admin_audit (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    actor_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    target_id BIGINT,
    card_slug TEXT,
    quantity INTEGER,
    coins BIGINT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS card_inventory (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    card_slug TEXT NOT NULL REFERENCES card_catalog(slug),
    quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    first_obtained_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (guild_id, user_id, card_slug)
);
CREATE INDEX IF NOT EXISTS idx_card_inventory_user ON card_inventory (guild_id, user_id, quantity DESC);
ALTER TABLE card_inventory ADD COLUMN IF NOT EXISTS is_favorite BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_card_inventory_fav ON card_inventory (guild_id, user_id, is_favorite) WHERE is_favorite = TRUE;

CREATE TABLE IF NOT EXISTS card_market_listings (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    seller_id BIGINT NOT NULL,
    card_slug TEXT NOT NULL REFERENCES card_catalog(slug),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    remaining INTEGER NOT NULL CHECK (remaining >= 0),
    price_each BIGINT NOT NULL CHECK (price_each > 0),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','sold','cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_card_market_active ON card_market_listings (guild_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS card_trades (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    sender_id BIGINT NOT NULL,
    receiver_id BIGINT NOT NULL,
    offered_slug TEXT NOT NULL REFERENCES card_catalog(slug),
    offered_quantity INTEGER NOT NULL CHECK (offered_quantity > 0),
    requested_slug TEXT NOT NULL REFERENCES card_catalog(slug),
    requested_quantity INTEGER NOT NULL CHECK (requested_quantity > 0),
    status TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('completed','cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS card_trade_sessions (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_a BIGINT NOT NULL,
    user_b BIGINT NOT NULL,
    channel_id BIGINT,
    offer_a JSONB NOT NULL DEFAULT '{}'::jsonb,
    offer_b JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('active','completed','cancelled')),
    confirmed_a BOOLEAN NOT NULL DEFAULT FALSE,
    confirmed_b BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
ALTER TABLE card_trade_sessions DROP CONSTRAINT IF EXISTS card_trade_sessions_status_check;
ALTER TABLE card_trade_sessions ADD CONSTRAINT card_trade_sessions_status_check CHECK (status IN ('active','completed','cancelled'));
ALTER TABLE card_trade_sessions ADD COLUMN IF NOT EXISTS channel_id BIGINT;
ALTER TABLE card_trade_sessions ADD COLUMN IF NOT EXISTS confirmed_a BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE card_trade_sessions ADD COLUMN IF NOT EXISTS confirmed_b BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_card_trade_sessions_active ON card_trade_sessions (guild_id, channel_id) WHERE status='active';
CREATE INDEX IF NOT EXISTS idx_card_trade_sessions_guild ON card_trade_sessions (guild_id, created_at DESC);

CREATE TABLE IF NOT EXISTS card_battles (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    user_a BIGINT NOT NULL,
    user_b BIGINT NOT NULL,
    card_a TEXT NOT NULL REFERENCES card_catalog(slug),
    card_b TEXT NOT NULL REFERENCES card_catalog(slug),
    winner_id BIGINT,
    loser_id BIGINT,
    turns INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','cancelled')),
    result JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_card_battles_guild_created ON card_battles (guild_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_card_battles_users ON card_battles (guild_id, user_a, user_b, created_at DESC);
ALTER TABLE card_battles ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT '1v1';

CREATE TABLE IF NOT EXISTS card_battle_logs (
    id BIGSERIAL PRIMARY KEY,
    battle_id BIGINT NOT NULL REFERENCES card_battles(id) ON DELETE CASCADE,
    turn_number INTEGER NOT NULL,
    actor_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    damage INTEGER NOT NULL DEFAULT 0,
    effect TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_key TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Evoluciones: vincula una carta base con su forma evolucionada
CREATE TABLE IF NOT EXISTS card_evolutions (
    base_slug      TEXT PRIMARY KEY REFERENCES card_catalog(slug),
    cost_coins     INTEGER NOT NULL DEFAULT 100,
    cost_copies    INTEGER NOT NULL DEFAULT 2,
    stat_boost_pct INTEGER NOT NULL DEFAULT 25,
    max_level      INTEGER NOT NULL DEFAULT 5,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Migración: quitar columna evolved_slug si existía de versión anterior
-- (se ejecuta sin error aunque ya no exista)

CREATE TABLE IF NOT EXISTS card_inventory_evo (
    guild_id       BIGINT NOT NULL,
    user_id        BIGINT NOT NULL,
    card_slug      TEXT NOT NULL REFERENCES card_catalog(slug),
    evo_level      INTEGER NOT NULL DEFAULT 0,
    stat_boost_pct INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, card_slug)
);

-- Progreso global por usuario: no contiene guild_id a propósito.
CREATE TABLE IF NOT EXISTS card_wallets_global (
    guild_id BIGINT NOT NULL DEFAULT 0,
    user_id BIGINT PRIMARY KEY,
    coins BIGINT NOT NULL DEFAULT 500 CHECK (coins >= 0),
    daily_claimed_at TIMESTAMPTZ,
    daily_streak INTEGER NOT NULL DEFAULT 0,
    xp BIGINT NOT NULL DEFAULT 0,
    level INTEGER NOT NULL DEFAULT 1,
    pity_rare INTEGER NOT NULL DEFAULT 0,
    pity_epic INTEGER NOT NULL DEFAULT 0,
    packs_opened INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS card_inventory_global (
    guild_id BIGINT NOT NULL DEFAULT 0,
    user_id BIGINT NOT NULL,
    card_slug TEXT NOT NULL REFERENCES card_catalog(slug),
    quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    first_obtained_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_favorite BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (user_id, card_slug)
);
CREATE INDEX IF NOT EXISTS idx_card_inventory_global_user
    ON card_inventory_global (user_id, quantity DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_card_inventory_global_legacy
    ON card_inventory_global (guild_id, user_id, card_slug);

CREATE TABLE IF NOT EXISTS card_inventory_evo_global (
    guild_id BIGINT NOT NULL DEFAULT 0,
    user_id BIGINT NOT NULL,
    card_slug TEXT NOT NULL REFERENCES card_catalog(slug),
    evo_level INTEGER NOT NULL DEFAULT 0,
    stat_boost_pct INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, card_slug)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_card_inventory_evo_global_legacy
    ON card_inventory_evo_global (guild_id, user_id, card_slug);

CREATE TABLE IF NOT EXISTS card_set_claims_global (
    guild_id BIGINT NOT NULL DEFAULT 0,
    user_id BIGINT NOT NULL,
    set_slug TEXT NOT NULL,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, set_slug)
);

-- La columna legacy se conserva solo para que helpers antiguos puedan seguir
-- recibiendo guild_id; el trigger la normaliza y nunca participa en la identidad.
CREATE OR REPLACE FUNCTION normalize_card_global_guild() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.guild_id := 0; RETURN NEW; END $$;
DROP TRIGGER IF EXISTS card_wallets_global_guild ON card_wallets_global;
CREATE TRIGGER card_wallets_global_guild BEFORE INSERT OR UPDATE ON card_wallets_global
FOR EACH ROW EXECUTE FUNCTION normalize_card_global_guild();
DROP TRIGGER IF EXISTS card_inventory_global_guild ON card_inventory_global;
CREATE TRIGGER card_inventory_global_guild BEFORE INSERT OR UPDATE ON card_inventory_global
FOR EACH ROW EXECUTE FUNCTION normalize_card_global_guild();
DROP TRIGGER IF EXISTS card_inventory_evo_global_guild ON card_inventory_evo_global;
CREATE TRIGGER card_inventory_evo_global_guild BEFORE INSERT OR UPDATE ON card_inventory_evo_global
FOR EACH ROW EXECUTE FUNCTION normalize_card_global_guild();
DROP TRIGGER IF EXISTS card_set_claims_global_guild ON card_set_claims_global;
CREATE TRIGGER card_set_claims_global_guild BEFORE INSERT OR UPDATE ON card_set_claims_global
FOR EACH ROW EXECUTE FUNCTION normalize_card_global_guild();
"""


class Database:
    def __init__(self) -> None:
        self.pool: asyncpg.Pool | None = None

    @staticmethod
    def _normalize_dsn(dsn: str) -> str:
        """Keep Neon TLS requirements and discard libpq-only channel binding options."""
        parsed = urlsplit(dsn)
        query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                 if key.lower() != "channel_binding"]
        if not any(key.lower() == "sslmode" for key, _ in query):
            query.append(("sslmode", "require"))
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))

    async def connect(self) -> None:
        if self.pool is not None:
            return
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            raise RuntimeError(
                "Falta DATABASE_URL. Configura la cadena de conexión PostgreSQL de Neon "
                "como secreto/variable de entorno del servicio."
            )
        self.pool = await asyncpg.create_pool(
            dsn=self._normalize_dsn(dsn),
            ssl="require",
            min_size=1,
            max_size=8,
            command_timeout=30,
            statement_cache_size=0,
            server_settings={"application_name": "abo-discord-bot"},
        )
        async with self.pool.acquire() as connection:
            await connection.execute(_SCHEMA)
        await self.migrate_card_progress_global()
        await self.migrate_sqlite_if_present()

    async def migrate_card_progress_global(self) -> None:
        """Consolida una vez el progreso histórico de todos los servidores por usuario.

        La migración no modifica ni elimina las tablas antiguas. Los valores aditivos se
        suman; nivel/evolución/favorita se combinan conservadoramente; los claims son
        distintos. El advisory lock evita carreras entre arranques concurrentes.
        """
        marker = "card_progress_global_v1"
        async with self._pool().acquire() as connection:
            async with connection.transaction():
                await connection.execute("SELECT pg_advisory_xact_lock(hashtext($1)::bigint)", marker)
                if await connection.fetchval("SELECT 1 FROM schema_migrations WHERE migration_key=$1", marker):
                    return
                await connection.execute("""
                    INSERT INTO card_wallets_global
                        (user_id, coins, daily_claimed_at, daily_streak, xp, level,
                         pity_rare, pity_epic, packs_opened, created_at, updated_at)
                    SELECT user_id, SUM(coins), MAX(daily_claimed_at), MAX(daily_streak),
                           SUM(xp), MAX(level), MAX(pity_rare), MAX(pity_epic),
                           SUM(packs_opened), MIN(created_at), MAX(updated_at)
                    FROM card_wallets GROUP BY user_id
                    ON CONFLICT (user_id) DO NOTHING
                """)
                await connection.execute("""
                    INSERT INTO card_inventory_global
                        (user_id, card_slug, quantity, first_obtained_at, is_favorite)
                    SELECT user_id, card_slug, SUM(quantity), MIN(first_obtained_at), BOOL_OR(is_favorite)
                    FROM card_inventory GROUP BY user_id, card_slug
                    ON CONFLICT (user_id, card_slug) DO NOTHING
                """)
                await connection.execute("""
                    INSERT INTO card_inventory_evo_global (user_id, card_slug, evo_level, stat_boost_pct)
                    SELECT user_id, card_slug, MAX(evo_level), MAX(stat_boost_pct)
                    FROM card_inventory_evo GROUP BY user_id, card_slug
                    ON CONFLICT (user_id, card_slug) DO NOTHING
                """)
                await connection.execute("""
                    INSERT INTO card_set_claims_global (user_id, set_slug, claimed_at)
                    SELECT user_id, set_slug, MIN(claimed_at)
                    FROM card_set_claims GROUP BY user_id, set_slug
                    ON CONFLICT (user_id, set_slug) DO NOTHING
                """)
                await connection.execute(
                    "INSERT INTO schema_migrations (migration_key) VALUES ($1) ON CONFLICT DO NOTHING", marker
                )

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    def _pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("La base de datos no está conectada; inicializa Neon al iniciar el bot.")
        return self.pool

    async def execute(self, query: str, *args):
        async with self._pool().acquire() as connection:
            return await connection.execute(query, *args)

    async def fetch(self, query: str, *args):
        async with self._pool().acquire() as connection:
            return await connection.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        async with self._pool().acquire() as connection:
            return await connection.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        async with self._pool().acquire() as connection:
            return await connection.fetchval(query, *args)

    async def set_setting(self, guild_id: int, key: str, value: str) -> None:
        await self.execute(
            """INSERT INTO guild_settings (guild_id, setting_key, setting_value)
               VALUES ($1, $2, $3)
               ON CONFLICT (guild_id, setting_key) DO UPDATE
               SET setting_value = EXCLUDED.setting_value, updated_at = NOW()""",
            guild_id, key, value,
        )

    async def set_settings(self, guild_id: int, values: dict[str, str]) -> None:
        if not values:
            return
        async with self._pool().acquire() as connection:
            async with connection.transaction():
                await connection.executemany(
                    """INSERT INTO guild_settings (guild_id, setting_key, setting_value)
                       VALUES ($1, $2, $3)
                       ON CONFLICT (guild_id, setting_key) DO UPDATE
                       SET setting_value = EXCLUDED.setting_value, updated_at = NOW()""",
                    [(guild_id, key, value) for key, value in values.items()],
                )

    async def get_setting(self, guild_id: int, key: str, default: str | None = None) -> str | None:
        value = await self.fetchval(
            "SELECT setting_value FROM guild_settings WHERE guild_id = $1 AND setting_key = $2",
            guild_id, key,
        )
        return default if value is None else value

    async def get_settings(self, guild_id: int) -> dict[str, str]:
        rows = await self.fetch(
            "SELECT setting_key, setting_value FROM guild_settings WHERE guild_id = $1",
            guild_id,
        )
        return {row["setting_key"]: row["setting_value"] for row in rows}

    async def save_purge_scan(self, guild_id: int, candidate_user_ids: list[int]) -> None:
        await self.execute(
            """INSERT INTO purge_scans (guild_id, candidate_user_ids, scanned_at)
               VALUES ($1, $2, NOW())
               ON CONFLICT (guild_id) DO UPDATE
               SET candidate_user_ids = EXCLUDED.candidate_user_ids, scanned_at = NOW()""",
            guild_id, candidate_user_ids,
        )

    async def get_purge_scan(self, guild_id: int) -> list[int]:
        rows = await self.fetchval(
            "SELECT candidate_user_ids FROM purge_scans WHERE guild_id = $1",
            guild_id,
        )
        return list(rows or [])

    async def migrate_sqlite_if_present(self, path: str = "abo_memoria.db") -> None:
        """Import the old local database once; never delete or modify its source file."""
        source = Path(path)
        if not source.is_file():
            return
        marker = "sqlite_abo_memoria_v1"
        if await self.fetchval("SELECT 1 FROM schema_migrations WHERE migration_key = $1", marker):
            return

        payload = await asyncio.to_thread(self._read_sqlite, source)
        async with self._pool().acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1)::bigint)", marker,
                )
                if await connection.fetchval(
                    "SELECT 1 FROM schema_migrations WHERE migration_key = $1", marker,
                ):
                    return
                if payload["memoria"]:
                    await connection.executemany(
                        """INSERT INTO memory (user_id, channel_id, role, content, created_at)
                           VALUES ($1, $2, $3, $4, $5)""",
                        payload["memoria"],
                    )
                if payload["warns"]:
                    await connection.executemany(
                        """INSERT INTO warns (id, guild_id, user_id, moderator_id, reason, created_at)
                           VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (id) DO NOTHING""",
                        payload["warns"],
                    )
                    await connection.execute(
                        """SELECT setval(pg_get_serial_sequence('warns', 'id'),
                           GREATEST((SELECT COALESCE(MAX(id), 1) FROM warns), 1), TRUE)"""
                    )
                if payload["color_roles"]:
                    await connection.executemany(
                        """INSERT INTO color_roles (guild_id, categoria, clave, role_id)
                           VALUES ($1, $2, $3, $4)
                           ON CONFLICT (guild_id, categoria, clave) DO UPDATE
                           SET role_id = EXCLUDED.role_id""",
                        payload["color_roles"],
                    )
                if payload["purge_exceptions"]:
                    await connection.executemany(
                        """INSERT INTO purge_exceptions (guild_id, user_id, razon, added_by, created_at)
                           VALUES ($1, $2, $3, $4, $5)
                           ON CONFLICT (guild_id, user_id) DO UPDATE
                           SET razon = EXCLUDED.razon, added_by = EXCLUDED.added_by,
                               created_at = EXCLUDED.created_at""",
                        payload["purge_exceptions"],
                    )
                await connection.execute(
                    "INSERT INTO schema_migrations (migration_key) VALUES ($1) ON CONFLICT DO NOTHING",
                    marker,
                )

    @staticmethod
    def _read_sqlite(path: Path) -> dict[str, list]:
        connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            tables = {row["name"] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )}

            def timestamp(value):
                if not value:
                    return datetime.now(timezone.utc)
                try:
                    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                except ValueError:
                    return datetime.now(timezone.utc)
                return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed

            result = {"memoria": [], "warns": [], "color_roles": [], "purge_exceptions": []}
            if "memoria" in tables:
                for row in connection.execute("SELECT user_id, canal_id, rol, contenido, timestamp FROM memoria"):
                    result["memoria"].append((row["user_id"], row["canal_id"], row["rol"], row["contenido"], timestamp(row["timestamp"])))
            if "warns" in tables:
                for row in connection.execute("SELECT id, guild_id, user_id, moderator_id, reason, timestamp FROM warns"):
                    result["warns"].append((row["id"], row["guild_id"], row["user_id"], row["moderator_id"], row["reason"], timestamp(row["timestamp"])))
            if "color_roles" in tables:
                result["color_roles"] = [tuple(row) for row in connection.execute(
                    "SELECT guild_id, categoria, clave, role_id FROM color_roles"
                )]
            if "purga_exceptions" in tables:
                for row in connection.execute("SELECT guild_id, user_id, razon, added_by, timestamp FROM purga_exceptions"):
                    result["purge_exceptions"].append((row["guild_id"], row["user_id"], row["razon"], row["added_by"], timestamp(row["timestamp"])))
            return result
        finally:
            connection.close()


db = Database()
