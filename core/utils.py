"""
Shared, safety-critical helpers used across the suite:
- streamed SHA-256 hashing (chain-of-custody, never loads a whole file into RAM)
- safe read-only SQLite access, always against a COPY of the uploaded file,
  never the original -- so an uploaded evidence file is never opened for
  writing and the original bytes on disk are never touched after upload.
"""
from __future__ import annotations

import hashlib
import shutil
import sqlite3
import uuid
from pathlib import Path

from django.conf import settings

CHUNK_SIZE = 1024 * 1024  # 1 MB


def sha256_of_file(path) -> tuple[str, int]:
    """Stream-hash a file so multi-GB evidence never gets loaded into memory."""
    h = hashlib.sha256()
    total = 0
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
            total += len(chunk)
    return h.hexdigest(), total


def working_copy_dir() -> Path:
    d = Path(settings.EVIDENCE_STORAGE_ROOT) / "_work" / uuid.uuid4().hex
    d.mkdir(parents=True, exist_ok=True)
    return d


def safe_copy_db(original_path) -> Path:
    """Copy a SQLite file (plus -wal/-shm/-journal siblings if present, since
    modern browsers keep uncommitted data there) into a fresh temp folder and
    return the path to the copy. The original evidence file is never opened
    for writing and this copy is what every parser actually reads."""
    original_path = Path(original_path)
    dest_dir = working_copy_dir()
    dest = dest_dir / original_path.name
    shutil.copy2(original_path, dest)
    for suffix in ("-wal", "-shm", "-journal"):
        sibling = Path(str(original_path) + suffix)
        if sibling.exists():
            shutil.copy2(sibling, Path(str(dest) + suffix))
    return dest


def open_readonly(db_path) -> sqlite3.Connection:
    """Open a SQLite connection in strict read-only + immutable mode against
    the safe copy. `immutable=1` tells SQLite the file will not change for the
    lifetime of the connection, which also avoids locking semantics that could
    otherwise touch the file."""
    uri = f"file:{Path(db_path).as_posix()}?mode=ro&immutable=1"
    return sqlite3.connect(uri, uri=True)


def cleanup_dir(path) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


ALLOWED_URL_SCHEMES = ("http", "https")


def is_safe_url(url: str) -> bool:
    """Only http/https may ever be handed back to a browser link -- refuses
    javascript:, file:, data: etc. even if they show up in parsed rows."""
    try:
        from urllib.parse import urlparse
        scheme = urlparse(url).scheme.lower()
        return scheme in ALLOWED_URL_SCHEMES
    except Exception:
        return False
