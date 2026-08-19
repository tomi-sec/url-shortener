"""Locust scenario (a): pure redirects on random, already-seeded short codes.

Run `python src/seed.py` first - this reads the sample of real codes it
writes to seeded_codes.txt so every request hits a genuinely random
existing row instead of always the same one.
"""

import random
from pathlib import Path

from locust import HttpUser, between, task

CODES = (Path(__file__).parent / "seeded_codes.txt").read_text(encoding="utf-8").split()


class RedirectUser(HttpUser):
    wait_time = between(0, 0)

    @task
    def redirect(self):
        """Requests a random existing short code and expects a 302."""
        code = random.choice(CODES)
        with self.client.get(
            f"/{code}", name="/:code", allow_redirects=False, catch_response=True
        ) as resp:
            if resp.status_code == 302:
                resp.success()
            else:
                resp.failure(f"expected 302, got {resp.status_code}")
