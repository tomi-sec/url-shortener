"""Buffers click counts in Redis so the redirect path never blocks on Postgres.

record_click is O(1) in Redis and returns immediately; a background loop
(flush_loop) is the only thing that ever touches Postgres for click
counts, on a fixed timer instead of once per request. The honest
consistency story: a click count can be stale by up to FLUSH_INTERVAL_
SECONDS, and any clicks buffered since the last flush are lost if the
process dies before the next one - Redis itself isn't used durably here.
That's the trade this project makes for keeping the redirect's hot path
free of a synchronous write.
"""

import asyncio

import db

FLUSH_INTERVAL_SECONDS = 5
DIRTY_SET_KEY = "clicks:dirty"
COUNT_PREFIX = "clicks:count:"


async def record_click(redis_client, short_code):
    """Buffers one click for a short code, without touching Postgres.

    Args:
        redis_client: The Redis client.
        short_code: The short code that was just redirected.
    """
    await redis_client.incr(COUNT_PREFIX + short_code)
    await redis_client.sadd(DIRTY_SET_KEY, short_code)


async def flush_once(redis_client, pool):
    """Flushes every buffered click count into Postgres, once.

    Args:
        redis_client: The Redis client holding buffered counts.
        pool: The asyncpg pool to flush into.

    Returns:
        The number of short codes flushed.
    """
    dirty_codes = await redis_client.smembers(DIRTY_SET_KEY)
    for raw_code in dirty_codes:
        short_code = raw_code.decode() if isinstance(raw_code, bytes) else raw_code
        pending = await redis_client.getdel(COUNT_PREFIX + short_code)
        if pending:
            await db.increment_click_count(pool, short_code, by=int(pending))
        await redis_client.srem(DIRTY_SET_KEY, short_code)
    return len(dirty_codes)


async def flush_loop(redis_client, pool, interval=FLUSH_INTERVAL_SECONDS):
    """Runs flush_once on a timer for as long as the app is up.

    Args:
        redis_client: The Redis client holding buffered click counts.
        pool: The asyncpg pool to flush into.
        interval: Seconds between flushes - this is also the outer bound
            on how stale a click count can be.
    """
    while True:
        await asyncio.sleep(interval)
        try:
            await flush_once(redis_client, pool)
        except Exception as exc:
            # A flush failure (e.g. a transient DB hiccup under load) must
            # not kill this loop - the buffered counts just wait for the
            # next tick instead of being lost immediately.
            print(f"click_buffer: flush failed, will retry next tick: {exc}")
