"""Desktop launcher for Agamya CyberTech - DFS.

Runs the same Django app + React SPA you use on the web, but as a
self-contained native window instead of "open a browser" -- no separate
terminal, no visible URL bar, no manual server start.

How it fits together:
    - Django serves the API (/api/...) and the already-built React SPA
      (frontend/dist/, via dfs_web/spa.py) exactly like the single-origin
      production deployment described in README.md.
    - waitress (a pure-Python production WSGI server -- no C build step,
      which matters for PyInstaller) serves that Django app on
      127.0.0.1:<port> in a background thread.
    - pywebview opens a native OS window (WebView2 on Windows, WKWebView on
      macOS, WebKitGTK on Linux) pointed at that local server. No Chromium
      bundled in your app -- it uses whatever web engine the OS already has.

Run directly for development:
    python desktop_app.py

Build a standalone executable:
    cd frontend && npm install && npm run build && cd ..
    pyinstaller desktop/build.spec
    # → dist/Agamya-DFS/ (or dist/Agamya-DFS.exe on Windows)

See DESKTOP.md for full build/packaging instructions and platform notes.
"""
import os
import secrets
import socket
import sys
import threading
import time
from pathlib import Path


def app_base_dir():
    """Where the app's own files (dfs_web/, frontend/dist/, etc.) live --
    the PyInstaller temp-extraction dir when frozen, this file's folder
    otherwise."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def user_data_dir():
    """A writable, per-user directory for the database, uploaded evidence,
    and the generated secret key -- deliberately NOT inside the app install
    location, which may be read-only (Program Files, /Applications, a
    PyInstaller temp dir that's wiped on exit, etc.)."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home())
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    d = Path(base) / "AgamyaCyberTech" / "DFS"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_or_create_secret_key(data_dir):
    key_file = data_dir / "secret_key.txt"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    key = secrets.token_urlsafe(50)
    key_file.write_text(key, encoding="utf-8")
    return key


def free_port(preferred=8747):
    """Use the preferred port if it's open, otherwise let the OS assign one
    (two copies of the app, or something else already on 8747, shouldn't
    stop it from launching)."""
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("Could not find a free port")


def bootstrap_django():
    """Sets env vars Django reads, points storage at user_data_dir(), then
    runs migrate + seed_plans so a fresh install "just works" with no
    terminal step required."""
    base = app_base_dir()
    data_dir = user_data_dir()

    os.environ.setdefault("DFS_DEBUG", "0")
    os.environ.setdefault("DFS_ALLOWED_HOSTS", "127.0.0.1,localhost")
    os.environ.setdefault("DFS_SECRET_KEY", get_or_create_secret_key(data_dir))
    os.environ.setdefault("DFS_DB_PATH", str(data_dir / "db.sqlite3"))
    os.environ.setdefault("DFS_EVIDENCE_ROOT", str(data_dir / "evidence_store"))
    os.environ.setdefault("DFS_MEDIA_ROOT", str(data_dir / "media"))
    os.environ.setdefault("DFS_STATIC_ROOT", str(data_dir / "staticfiles"))
    # Local-machine browser scanning (evidence/api.py's LocalScanAPI) only
    # makes sense when the examiner's own workstation IS the machine
    # running the server -- which is exactly the desktop app's whole
    # premise, unlike the shared-server web deployment where this defaults
    # off. Still gated per-org by the plan's feature_local_scan flag.
    os.environ.setdefault("DFS_ENABLE_LOCAL_SCAN", "1")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dfs_web.settings")
    (data_dir / "staticfiles").mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(base))
    os.chdir(base)

    import django
    django.setup()

    from django.core.management import call_command
    call_command("migrate", verbosity=0, interactive=False)

    from billing.models import Plan
    if not Plan.objects.exists():
        call_command("seed_plans", verbosity=0)


def run_server(port):
    from waitress import serve
    from dfs_web.wsgi import application
    serve(application, host="127.0.0.1", port=port, threads=8)


def wait_until_up(port, timeout=15):
    import urllib.request
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/"
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def main():
    if "--createsuperuser" in sys.argv:
        bootstrap_django()
        print(f"Using database: {os.environ['DFS_DB_PATH']}\n")
        from django.core.management import call_command
        call_command("createsuperuser")
        return

    bootstrap_django()
    port = free_port()

    server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    server_thread.start()
    wait_until_up(port)

    try:
        import webview
    except ImportError:
        print(
            "pywebview isn't installed. Install desktop dependencies with:\n"
            "    pip install pywebview waitress\n"
            f"Or just open http://127.0.0.1:{port}/ in a browser -- the server is running."
        )
        server_thread.join()
        return

    # pywebview disables file downloads by default on every platform --
    # a deliberate security default, not a bug -- meaning clicking any
    # CSV/XLSX/JSON export or the PDF report inside the app window would
    # otherwise be silently swallowed with no error, no dialog, and
    # nothing landing on disk. Must be set before create_window().
    webview.settings["ALLOW_DOWNLOADS"] = True

    icon_path = app_base_dir() / "frontend" / "src" / "assets" / "agamya-logo.jpg"

    try:
        webview.create_window(
            "Agamya CyberTech - DFS",
            f"http://127.0.0.1:{port}/",
            width=1360,
            height=860,
            min_size=(1024, 680),
        )
        start_kwargs = {}
        if icon_path.exists():
            start_kwargs["icon"] = str(icon_path)
        webview.start(**start_kwargs)
    except Exception as exc:
        # No native web-engine available on this machine (missing
        # WebView2 runtime on Windows, no WebKitGTK/Qt on Linux, etc.) --
        # the backend is still up and perfectly usable from a browser, so
        # fail soft instead of crashing.
        print(
            f"Couldn't open the native app window ({exc}).\n"
            f"The server is still running -- open http://127.0.0.1:{port}/ in your browser instead.\n"
            "(On Linux, installing WebKitGTK -- e.g. `sudo apt install gir1.2-webkit2-4.1` on "
            "Debian/Ubuntu -- usually fixes this.)"
        )
        server_thread.join()


if __name__ == "__main__":
    main()
