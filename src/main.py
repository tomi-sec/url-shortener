"""FastAPI app: create a short link, redirect on visit, report click stats.

Three env flags reproduce each measurement phase from the README on
demand, rather than that history only existing as a claim: SKIP_SHORT_
CODE_INDEX=1 recreates the un-indexed Phase 1 schema, DISABLE_CACHE=1
skips the Redis cache-aside layer, and SYNC_CLICKS=1 writes click counts
inline instead of through click_buffer's background flush. All three
default to off, i.e. the app runs in its final, optimized configuration
unless you're deliberately reproducing an earlier phase.
"""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse

import cache
import click_buffer
import db
import shortcode
from models import CreateLinkRequest, CreateLinkResponse, StatsResponse

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/urlshortener"
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
SKIP_SHORT_CODE_INDEX = os.environ.get("SKIP_SHORT_CODE_INDEX") == "1"
DISABLE_CACHE = os.environ.get("DISABLE_CACHE") == "1"
SYNC_CLICKS = os.environ.get("SYNC_CLICKS") == "1"


@asynccontextmanager
async def lifespan(app):
    """Opens the DB pool and Redis client on startup, closes them on shutdown.

    Args:
        app: The FastAPI application instance.
    """
    app.state.pool = await db.create_pool(DATABASE_URL)
    await db.init_schema(app.state.pool, with_index=not SKIP_SHORT_CODE_INDEX)
    app.state.redis = cache.create_redis(REDIS_URL)

    app.state.flush_task = None
    if not SYNC_CLICKS:
        app.state.flush_task = asyncio.create_task(
            click_buffer.flush_loop(app.state.redis, app.state.pool)
        )

    yield

    if app.state.flush_task:
        app.state.flush_task.cancel()
    await app.state.pool.close()
    await app.state.redis.aclose()


app = FastAPI(lifespan=lifespan)


@app.post("/links", response_model=CreateLinkResponse, status_code=201)
async def create_link(payload: CreateLinkRequest):
    """Creates a short link for a long URL.

    Args:
        payload: The request body, holding the long URL to shorten.

    Returns:
        The new short code paired with the (pydantic-normalized) long
        URL.
    """
    pool = app.state.pool
    link_id = await db.next_id(pool)
    code = shortcode.encode(link_id)
    long_url = str(payload.long_url)
    await db.insert_link(pool, link_id, code, long_url)
    return CreateLinkResponse(short_code=code, long_url=long_url)


@app.get("/stats/{short_code}", response_model=StatsResponse)
async def get_stats(short_code):
    """Reports a link's destination and click count.

    Args:
        short_code: The short code to look up.

    Returns:
        The link's short code, long URL, click count, and creation time.

    Raises:
        HTTPException: 404 if no link has this short code.
    """
    row = await db.get_stats(app.state.pool, short_code)
    if row is None:
        raise HTTPException(status_code=404, detail="short code not found")
    return StatsResponse(
        short_code=row["short_code"],
        long_url=row["long_url"],
        click_count=row["click_count"],
        created_at=row["created_at"].isoformat(),
    )


@app.get("/{short_code}")
async def redirect(short_code):
    """Redirects a short code to its long URL and records a click.

    302, not 301: a 301 gets cached permanently by the visiting browser,
    which would both freeze in a stale long_url after any future edit
    and starve click counting of repeat-visit hits.

    Args:
        short_code: The short code to redirect.

    Returns:
        A 302 RedirectResponse to the long URL.

    Raises:
        HTTPException: 404 if no link has this short code.
    """
    long_url = None
    if not DISABLE_CACHE:
        long_url = await cache.get_cached_long_url(app.state.redis, short_code)

    if long_url is None:
        long_url = await db.get_long_url(app.state.pool, short_code)
        if long_url is None:
            raise HTTPException(status_code=404, detail="short code not found")
        if not DISABLE_CACHE:
            await cache.set_cached_long_url(app.state.redis, short_code, long_url)

    if SYNC_CLICKS:
        await db.increment_click_count(app.state.pool, short_code, by=1)
    else:
        await click_buffer.record_click(app.state.redis, short_code)

    return RedirectResponse(url=long_url, status_code=302)
