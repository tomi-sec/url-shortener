"""Seeds the database with ~1M links so load tests hit a realistic data volume.

Also writes load/seeded_codes.txt, a flat list of the codes it created -
the Locust redirect/mixed scenarios sample random codes from that file
so they're testing the same "read a random existing row" access pattern
production traffic would have, not always hitting the same hot row.
"""

import asyncio
import os
import random
import string
from pathlib import Path

import db
import shortcode

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/urlshortener"
)
SEED_COUNT = int(os.environ.get("SEED_COUNT", "1000000"))
# Matches main.py's flag of the same name, so seeding reproduces whichever
# phase's schema you're currently measuring instead of always adding the
# index.
SKIP_SHORT_CODE_INDEX = os.environ.get("SKIP_SHORT_CODE_INDEX") == "1"
BATCH_SIZE = 5000
CODES_SAMPLE_SIZE = 50000
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CODES_OUTPUT_PATH = PROJECT_ROOT / "load" / "seeded_codes.txt"


def _random_url():
    """Builds a plausible, unique long URL for seed data.

    Returns:
        A URL string, e.g. "https://example.com/articles/<random slug>".
    """
    slug = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
    return f"https://example.com/articles/{slug}"


async def seed(count=SEED_COUNT):
    """Bulk-inserts `count` links directly via Postgres's COPY protocol.

    Going through the HTTP API one request at a time would make seeding
    itself the bottleneck long before the database is, so this uses
    asyncpg's copy_records_to_table to talk the bulk-load protocol
    directly instead.

    Args:
        count: How many links to seed.
    """
    pool = await db.create_pool(DATABASE_URL)
    await db.init_schema(pool, with_index=not SKIP_SHORT_CODE_INDEX)

    async with pool.acquire() as conn:
        first_id = await conn.fetchval("SELECT nextval('links_id_seq')")
        await conn.execute("SELECT setval('links_id_seq', $1, false)", first_id + count)

        all_codes = []
        records = []
        for offset in range(count):
            link_id = first_id + offset
            code = shortcode.encode(link_id)
            all_codes.append(code)
            records.append((link_id, code, _random_url()))
            if len(records) >= BATCH_SIZE:
                await conn.copy_records_to_table(
                    "links", records=records, columns=["id", "short_code", "long_url"]
                )
                records.clear()
                if (offset + 1) % 100000 < BATCH_SIZE:
                    print(f"seeded {offset + 1}/{count}")
        if records:
            await conn.copy_records_to_table(
                "links", records=records, columns=["id", "short_code", "long_url"]
            )

    await pool.close()

    sample = random.sample(all_codes, k=min(CODES_SAMPLE_SIZE, len(all_codes)))
    CODES_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CODES_OUTPUT_PATH.write_text("\n".join(sample), encoding="utf-8")

    print(f"seeded {count} links, wrote a {len(sample)}-code sample to {CODES_OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(seed())
