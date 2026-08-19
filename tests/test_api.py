"""Integration tests against the real API - real Postgres, real Redis.

Requires `docker compose up postgres redis` (or the full stack) already
running locally on the default ports. These hit the actual database and
cache rather than mocking either one, matching how every optimization in
this project was actually measured instead of assumed.
"""

import time

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    """A TestClient that runs the app's real lifespan (real Postgres + Redis)."""
    with TestClient(app) as c:
        yield c


def test_create_link_returns_a_short_code(client):
    resp = client.post("/links", json={"long_url": "https://example.com/hello"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["long_url"] == "https://example.com/hello"
    assert len(body["short_code"]) > 0


def test_redirect_follows_to_the_long_url(client):
    created = client.post("/links", json={"long_url": "https://example.com/world"}).json()
    resp = client.get(f"/{created['short_code']}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://example.com/world"


def test_redirect_on_unknown_code_is_a_404(client):
    resp = client.get("/does-not-exist-xyz", follow_redirects=False)
    assert resp.status_code == 404


def test_stats_on_unknown_code_is_a_404(client):
    resp = client.get("/stats/does-not-exist-xyz")
    assert resp.status_code == 404


def test_stats_reports_click_count_once_the_buffer_flushes(client):
    """Click counting is buffered (see click_buffer.py) - this waits out a real flush cycle."""
    created = client.post("/links", json={"long_url": "https://example.com/stats-me"}).json()
    code = created["short_code"]
    for _ in range(3):
        client.get(f"/{code}", follow_redirects=False)

    time.sleep(6)  # the flush loop runs every 5s (click_buffer.FLUSH_INTERVAL_SECONDS)

    resp = client.get(f"/stats/{code}")
    assert resp.status_code == 200
    assert resp.json()["click_count"] == 3
