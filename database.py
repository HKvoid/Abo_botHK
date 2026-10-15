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

CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_key TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
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
        await self.migrate_sqlite_if_present()

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
