"""
Metadata-only cache archive scan. Uploaded as a .zip of a browser cache
folder; entries are NEVER extracted or opened -- we only read the zip's
central directory (name, size, mtime) and guess a MIME type from the
filename extension.
"""
from __future__ import annotations
import mimetypes
import zipfile
from datetime import datetime


def scan_cache_zip(zip_path, max_files: int = 20000) -> list[dict]:
    rows = []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                if len(rows) >= max_files:
                    break
                if info.is_dir():
                    continue
                name = info.filename
                mime_guess, _ = mimetypes.guess_type(name)
                try:
                    modified = datetime(*info.date_time)
                except Exception:
                    modified = None
                rows.append({
                    "name": name.rsplit("/", 1)[-1],
                    "path": name,
                    "mime_guess": mime_guess or "unknown",
                    "size_bytes": info.file_size,
                    "modified": modified,
                })
    except zipfile.BadZipFile:
        return []
    return rows
