"""Locust scenario (b): pure link creation."""

import random
import string

from locust import HttpUser, between, task


def _random_url():
    """Builds a plausible, unique long URL for a create request.

    Returns:
        A URL string, e.g. "https://example.com/load-test/<random slug>".
    """
    slug = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
    return f"https://example.com/load-test/{slug}"


class CreateUser(HttpUser):
    wait_time = between(0, 0)

    @task
    def create_link(self):
        """POSTs a new link and expects a 201."""
        self.client.post("/links", json={"long_url": _random_url()})
