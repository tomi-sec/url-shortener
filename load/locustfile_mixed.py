"""Locust scenario (c): a 95/5 mix of redirects and creations.

95/5 is the spec's stated shape for real-world traffic on a link
shortener - redirects dominate creation by orders of magnitude in
practice, and this scenario is what the Phase 3/5 optimizations are
ultimately justified against, not the single-scenario numbers.
"""

import random
import string
from pathlib import Path

from locust import HttpUser, between, task

CODES = (Path(__file__).parent / "seeded_codes.txt").read_text(encoding="utf-8").split()


def _random_url():
    """Builds a plausible, unique long URL for a create request.

    Returns:
        A URL string, e.g. "https://example.com/load-test/<random slug>".
    """
    slug = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
    return f"https://example.com/load-test/{slug}"


class MixedUser(HttpUser):
    wait_time = between(0, 0)

    @task(95)
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

    @task(5)
    def create_link(self):
        """POSTs a new link and expects a 201."""
        self.client.post("/links", json={"long_url": _random_url()})
