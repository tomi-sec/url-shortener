"""Redis cache-aside for the redirect hot path.

On a miss the caller reads Postgres and calls set_cached_long_url to
populate the cache for next time; on a hit, Postgres is never touched.
There's no explicit edit/delete endpoint in this project (see the
README - only the three endpoints the spec asks for), so the
invalidation story is theoretical rather than exercised code: a future
edit/delete would need to call invalidate() itself, and until then, a
cached reader can see a stale long_url for up to CACHE_TTL_SECONDS.
"""

import redis.asyncio as redis

CACHE_TTL_SECONDS = 300
KEY_PREFIX = "link:"


def create_redis(url):
    """Builds an async Redis client.

    Args:
        url: A redis:// connection string.

    Returns:
        A redis.asyncio.Redis client. Connections are opened lazily on
        first use, so this doesn't itself perform I/O.
    """
    return redis.from_url(url)


async def get_cached_long_url(client, short_code):
    """Reads a short code's cached long URL.

    Args:
        client: The Redis client.
        short_code: The short code to look up.

    Returns:
        The cached long URL as a str, or None on a cache miss.
    """
    value = await client.get(KEY_PREFIX + short_code)
    if value is None:
        return None
    return value.decode() if isinstance(value, bytes) else value


async def set_cached_long_url(client, short_code, long_url):
    """Caches a short code's long URL with a fixed TTL.

    Args:
        client: The Redis client.
        short_code: The short code to cache.
        long_url: The destination URL to cache.
    """
    await client.set(KEY_PREFIX + short_code, long_url, ex=CACHE_TTL_SECONDS)


async def invalidate(client, short_code):
    """Evicts a short code's cached entry, e.g. after an edit or delete.

    Args:
        client: The Redis client.
        short_code: The short code to evict.
    """
    await client.delete(KEY_PREFIX + short_code)
