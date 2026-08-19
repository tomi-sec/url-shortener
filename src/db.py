"""Postgres access: a connection pool plus the raw SQL for each operation.

Uses asyncpg directly rather than an ORM - the whole point of this
project is measuring what the database is actually doing under load, and
raw SQL keeps that one-to-one with what EXPLAIN ANALYZE sees.
"""

import asyncpg

CREATE_SEQUENCE_SQL = "CREATE SEQUENCE IF NOT EXISTS links_id_seq START 1000;"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS links (
    id BIGINT PRIMARY KEY,
    short_code TEXT NOT NULL,
    long_url TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    click_count BIGINT NOT NULL DEFAULT 0
);
"""

# Deliberately optional (see init_schema's with_index) - the README's
# Phase 3 measurement is the before/after of adding exactly this index on
# the redirect path's only lookup column.
CREATE_INDEX_SQL = "CREATE UNIQUE INDEX IF NOT EXISTS idx_links_short_code ON links (short_code);"


async def create_pool(dsn):
    """Opens a pooled connection to Postgres.

    Args:
        dsn: A postgresql:// connection string.

    Returns:
        An asyncpg.Pool, sized for the concurrency levels used in the
        load tests (see load/).
    """
    return await asyncpg.create_pool(dsn, min_size=5, max_size=20)


async def init_schema(pool, with_index=True):
    """Creates the links table (and its id sequence) if not already present.

    Args:
        pool: The connection pool.
        with_index: Whether to also create the short_code index. False
            reproduces the Phase 1 baseline schema - see main.py's
            SKIP_SHORT_CODE_INDEX.
    """
    async with pool.acquire() as conn:
        await conn.execute(CREATE_SEQUENCE_SQL)
        await conn.execute(CREATE_TABLE_SQL)
        if with_index:
            await conn.execute(CREATE_INDEX_SQL)


async def next_id(pool):
    """Reserves the next link id from the shared sequence.

    A DB sequence is what lets counter+base62 short codes coordinate
    safely across multiple app instances with zero collision handling -
    Postgres itself guarantees no two callers ever get the same value.

    Args:
        pool: The connection pool.

    Returns:
        The next integer id.
    """
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT nextval('links_id_seq')")


async def insert_link(pool, link_id, short_code, long_url):
    """Inserts a new link row.

    Args:
        pool: The connection pool.
        link_id: The id reserved via next_id().
        short_code: The base62-encoded short code for this id.
        long_url: The destination URL.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO links (id, short_code, long_url) VALUES ($1, $2, $3)",
            link_id,
            short_code,
            long_url,
        )


async def get_long_url(pool, short_code):
    """Looks up a link's destination URL by its short code.

    This is the redirect hot path's only query - see the README's
    Baseline and Phase 3 measurements for what happens to it with and
    without an index on short_code.

    Args:
        pool: The connection pool.
        short_code: The short code to look up.

    Returns:
        The long URL, or None if no link has this short code.
    """
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT long_url FROM links WHERE short_code = $1", short_code)


async def increment_click_count(pool, short_code, by):
    """Adds to a link's stored click count.

    Args:
        pool: The connection pool.
        short_code: The short code whose count to update.
        by: The amount to add. click_buffer.py flushes one batched total
            per short code rather than calling this once per click.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE links SET click_count = click_count + $1 WHERE short_code = $2", by, short_code
        )


async def get_stats(pool, short_code):
    """Reads a link's full row for the /stats endpoint.

    Args:
        pool: The connection pool.
        short_code: The short code to look up.

    Returns:
        An asyncpg.Record with short_code/long_url/created_at/click_count
        fields, or None if no link has this short code.
    """
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT short_code, long_url, created_at, click_count FROM links WHERE short_code = $1",
            short_code,
        )
