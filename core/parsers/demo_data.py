"""
Synthetic, entirely made-up sample data for every module, so the whole
suite (and every table/search/export/report feature) can be exercised
safely with no real browser evidence present -- a classroom walkthrough
or a UI smoke-test never touches real data.
"""
from __future__ import annotations
from datetime import datetime, timedelta
import random

_SITES = [
    "github.com", "stackoverflow.com", "wikipedia.org", "python.org",
    "docs.djangoproject.com", "reddit.com", "news.ycombinator.com", "nist.gov",
    "sans.org", "owasp.org", "arxiv.org", "pypi.org",
]


def demo_history(n: int = 80) -> list[dict]:
    rows = []
    now = datetime.now()
    for i in range(n):
        site = random.choice(_SITES)
        rows.append({
            "url": f"https://{site}/page-{i}",
            "title": f"{site.split('.')[0].title()} - sample page {i}",
            "visit_count": random.randint(1, 40),
            "last_visit_time": now - timedelta(hours=random.randint(0, 400)),
        })
    return rows


def demo_logins(n: int = 12) -> list[dict]:
    rows = []
    now = datetime.now()
    for i, site in enumerate(_SITES[:n]):
        rows.append({
            "site": f"https://{site}",
            "username": f"demo.user{i}@example.com",
            "password_value": "Protected",
            "date_created": now - timedelta(days=random.randint(5, 300)),
        })
    return rows


def demo_cookies(n: int = 60) -> list[dict]:
    rows = []
    now = datetime.now()
    for i in range(n):
        site = random.choice(_SITES)
        rows.append({
            "host": f".{site}",
            "name": random.choice(["session_id", "_ga", "csrftoken", "auth_token", "locale"]),
            "path": "/",
            "expires_utc": now + timedelta(days=random.randint(1, 365)),
            "is_secure": random.choice([True, False]),
            "is_httponly": random.choice([True, False]),
            "last_access_utc": now - timedelta(hours=random.randint(0, 200)),
            "value": "Protected",
        })
    return rows


def demo_downloads(n: int = 25) -> list[dict]:
    rows = []
    now = datetime.now()
    states = ["Complete", "Interrupted", "Cancelled", "In progress"]
    dangers = ["Not dangerous", "Potentially unwanted", "Dangerous host"]
    for i in range(n):
        site = random.choice(_SITES)
        rows.append({
            "target_path": f"/home/demo/Downloads/sample_file_{i}.pdf",
            "source_url": f"https://{site}/downloads/file-{i}.pdf",
            "referrer": f"https://{site}/",
            "total_bytes": random.randint(1_000, 50_000_000),
            "state": random.choice(states),
            "danger_type": random.choice(dangers),
            "start_time": now - timedelta(days=random.randint(0, 60)),
        })
    return rows


def demo_cache(n: int = 45) -> list[dict]:
    rows = []
    now = datetime.now()
    exts = [("jpg", "image/jpeg"), ("png", "image/png"), ("js", "application/javascript"),
            ("css", "text/css"), ("woff2", "font/woff2"), ("json", "application/json")]
    for i in range(n):
        ext, mime = random.choice(exts)
        rows.append({
            "name": f"asset_{i}.{ext}",
            "path": f"cache/f_{i:03d}.{ext}",
            "mime_guess": mime,
            "size_bytes": random.randint(500, 2_000_000),
            "modified": now - timedelta(hours=random.randint(0, 500)),
        })
    return rows
