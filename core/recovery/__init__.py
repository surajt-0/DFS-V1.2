"""Deleted-data / browser-state recovery engines.

Pure-Python, Django-free (same convention as core/parsers/*): everything
here works on plain file paths / bytes and returns plain dataclasses, so it
can be unit-tested and reused without the web app. The Django layer that
stores results lives in the `recovery` app.

Design rules shared by every engine in this package:
  * Only ever read a COPY of the evidence (callers pass the safe working
    copy made by core.utils.safe_copy_db) -- nothing here opens a file for
    writing.
  * Passwords and cookie values are NEVER read, decoded or returned. The
    carver only extracts an explicit whitelist of metadata columns (see
    sqlite_carver.KNOWN_TABLES); `password_value`, `value` and
    `encrypted_value` are not on it, so they cannot leak by accident.
"""
