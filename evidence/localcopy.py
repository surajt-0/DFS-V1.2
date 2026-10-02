"""Copy a local file that a running browser may still hold open.

Used by the automatic local scan (evidence/api.py's LocalScanAPI). A plain
`open(path, "rb")` routinely fails on Windows while Chrome/Edge/Brave is
running, because those browsers keep History / Cookies / Login Data open
with sharing modes Python's `open()` isn't compatible with. Strategies,
tried in order, first success wins:

  1. "direct"                -- ordinary buffered copy (works when the
                                browser is closed, and on macOS/Linux).
  2. "windows-shared-read"   -- Windows only: reopen with CreateFileW and
                                FILE_SHARE_READ|WRITE|DELETE, which is
                                compatible with the handle the browser holds.
  3. "sqlite-snapshot"       -- SQLite online-backup API against a
                                read-only, non-locking (immutable) connection.
                                Caveat: immutable ignores a -wal file, so
                                the very newest, not-yet-checkpointed rows
                                may be missing from this snapshot.

The method used is returned so the caller can record it on the evidence
item -- for a forensic tool, how a copy was obtained matters, and an
incomplete-by-design snapshot must never be silently indistinguishable
from a clean copy.
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

METHOD_DIRECT = "direct"
METHOD_WINDOWS_SHARED = "windows-shared-read"
METHOD_SQLITE_SNAPSHOT = "sqlite-snapshot"


def _direct_copy(src: Path, dest: Path) -> None:
    with open(src, "rb") as fin, open(dest, "wb") as out:
        shutil.copyfileobj(fin, out)


def _windows_shared_copy(src: Path, dest: Path) -> None:
    import ctypes
    from ctypes import wintypes

    GENERIC_READ = 0x80000000
    FILE_SHARE_ALL = 0x1 | 0x2 | 0x4  # READ | WRITE | DELETE
    OPEN_EXISTING = 3
    FILE_ATTRIBUTE_NORMAL = 0x80

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.ReadFile.argtypes = [
        wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
    ]
    k32.ReadFile.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    invalid = ctypes.c_void_p(-1).value
    handle = k32.CreateFileW(
        str(src), GENERIC_READ, FILE_SHARE_ALL, None, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None
    )
    if handle is None or handle == invalid:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        buf = ctypes.create_string_buffer(1024 * 1024)
        read = wintypes.DWORD(0)
        with open(dest, "wb") as out:
            while True:
                if not k32.ReadFile(handle, buf, len(buf), ctypes.byref(read), None):
                    raise ctypes.WinError(ctypes.get_last_error())
                if read.value == 0:
                    break
                out.write(buf.raw[: read.value])
    finally:
        k32.CloseHandle(handle)


def _sqlite_snapshot(src: Path, dest: Path) -> None:
    uri = src.resolve().as_uri() + "?mode=ro&immutable=1"
    source = sqlite3.connect(uri, uri=True)
    try:
        target = sqlite3.connect(str(dest))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def copy_local_file(src: Path, dest: Path) -> str:
    """Copies src -> dest, returning which METHOD_* succeeded. Raises the
    first (most informative) OSError if every strategy fails."""
    try:
        _direct_copy(src, dest)
        return METHOD_DIRECT
    except OSError as first_error:
        strategies = []
        if sys.platform == "win32":
            strategies.append((METHOD_WINDOWS_SHARED, _windows_shared_copy))
        strategies.append((METHOD_SQLITE_SNAPSHOT, _sqlite_snapshot))

        for method, fn in strategies:
            try:
                dest.unlink(missing_ok=True)  # discard any partial output
                fn(src, dest)
                return method
            except (OSError, sqlite3.Error):
                continue
        dest.unlink(missing_ok=True)
        raise first_error
