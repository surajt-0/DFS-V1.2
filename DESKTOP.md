# Desktop app (Agamya CyberTech - DFS)

The same Django + React app you run on the web, packaged as a native
desktop window -- no browser tab, no visible URL bar, one double-clickable
app. It's the same codebase: `desktop_app.py` boots the exact Django
project (migrations, plan-gated billing, evidence parsing, everything) and
serves the already-built React SPA, just through a native window instead of
a browser.

## How it works

```
desktop_app.py
  1. Points the database, uploaded evidence, and Django's SECRET_KEY at a
     per-user data directory (NOT the app install folder, which may be
     read-only) -- see user_data_dir() below.
  2. Runs `migrate` and `seed_plans` automatically. First launch on a fresh
     machine "just works" with no terminal step.
  3. Starts waitress (a pure-Python production WSGI server -- no C build
     step, which matters for PyInstaller) serving Django on 127.0.0.1 in a
     background thread.
  4. Opens a native OS window via pywebview, pointed at that local server.
     pywebview uses whatever web engine the OS already ships --
     WebView2 on Windows, WKWebView on macOS, WebKitGTK on Linux -- so no
     Chromium gets bundled into your app.
```

Where your data actually lives once installed:

| OS | Location |
|---|---|
| Windows | `%APPDATA%\AgamyaCyberTech\DFS\` |
| macOS | `~/Library/Application Support/AgamyaCyberTech/DFS/` |
| Linux | `~/.local/share/AgamyaCyberTech/DFS/` |

That's the database, uploaded evidence, and the generated secret key.
Uninstalling the app does **not** delete this folder -- your cases stay put
across reinstalls/updates. Delete it yourself for a clean slate.

## Run it in dev mode (no packaging)

```bash
cd frontend && npm install && npm run build && cd ..
pip install -r requirements.txt
python desktop_app.py
```

A native window opens pointed at your local Django instance. Re-run
`npm run build` after any frontend change and restart `desktop_app.py` to
see it (this mode doesn't have Vite's hot-reload -- for active frontend
work, keep using `npm run dev` + `python manage.py runserver` as normal,
and only switch to `python desktop_app.py` to test the packaged experience).

If pywebview can't find a native web-engine backend (e.g. a Linux box with
no WebKitGTK installed), it fails soft: prints a message and leaves the
server running so you can open `http://127.0.0.1:<port>/` in a regular
browser instead of crashing.

## Build a standalone executable

```bash
cd frontend && npm install && npm run build && cd ..
pip install -r requirements.txt
pyinstaller desktop/build.spec
```

Output lands in `dist/Agamya-DFS/` (`dist/Agamya-DFS/Agamya-DFS.exe` on
Windows). Zip that folder and hand it to someone -- no Python or Node
install required on their end, everything's bundled.

**Important: PyInstaller does not cross-compile.** Running the command
above on Linux produces a Linux binary only; you need to run it on Windows
for a `.exe` and on macOS for a `.app`. If you don't have all three
machines, use the GitHub Actions workflow below instead of building by hand.

### Building via GitHub Actions (recommended if you only have one OS)

`.github/workflows/build-desktop.yml` builds Windows, macOS, and Linux in
parallel using GitHub's own runners for each OS -- you don't need to own
any of those machines yourself. Trigger it either by:

- Pushing a tag matching `desktop-v*` (e.g. `git tag desktop-v1.0 && git push --tags`), or
- Going to the repo's **Actions** tab -> "Build desktop app" -> **Run workflow**

Each OS's build appears as a downloadable artifact on the workflow run.

### App icon

`desktop/build.spec`'s `icon=None` is a placeholder -- PyInstaller needs a
real `.ico` (Windows) / `.icns` (macOS) file, not the `.jpg`/`.svg` logo
already in the repo. Generate one from
`frontend/src/assets/agamya-logo.jpg` (e.g. via icoconvert.com, or
`iconutil` on macOS) and point the spec at it:

```python
icon=str(PROJECT_ROOT / "desktop" / "icon.ico")
```

## Automated evidence intake

On a case's Upload Evidence page, **"Scan this computer for browser data"**
finds every installed Chrome/Edge/Brave/Opera/Firefox/Safari profile on
this machine and uploads + parses everything it can read -- no file picker
needed for the common case. This is specifically a desktop-build feature:
it inspects the filesystem of the machine running the app, which only
makes sense because that machine IS the examiner's own workstation here
(unlike the shared web deployment, where this stays off by default).

Requires the org's plan to include it (`feature_local_scan` -- Pro and
Enterprise by default, toggle it per-plan from the Admin Plans screen).
Anything it can't read (a file locked by a still-running browser,
permission denied) or can't recognize is reported per-file and skipped --
manual upload (drag files onto the same page, or the file picker) is
always available right below it as the fallback, with the same
auto-detection applied to whatever you select by hand.

## Where your data lives

Two different things, two different places:

- **Uploaded evidence files + the database** (cases, parsed history/logins/
  cookies/downloads/cache rows, users, audit log): the per-user data
  directory from the table above (`~/.local/share/AgamyaCyberTech/DFS/` on
  Linux, etc.) -- `evidence_store/` for the raw uploaded files,
  `db.sqlite3` for everything else.
- **Exported CSV/XLSX/JSON files and PDF reports**: these are generated
  on the fly and are never written to disk by the app itself -- clicking
  Export/PDF report triggers a normal browser/webview file download, same
  as downloading anything from any website. It lands wherever your OS's
  default downloads location is (typically `~/Downloads`, or
  `%USERPROFILE%\Downloads` on Windows), same as any other file your
  browser saves. The app has no way to know or control where the OS puts
  it -- check your downloads folder, or your browser/webview's download
  history, if you're not sure a download went through.

## Accessing the superuser / Django admin

The app auto-creates its database and seeds the billing plans on first
launch, but it can't auto-create a superuser -- that needs a username and
password from you. Create one with:

```bash
python desktop_app.py --createsuperuser
```

This runs the normal interactive Django prompt (username, email, password),
against the **exact same database** the desktop app itself uses (the
per-user data directory from the table above) -- not the project-folder
`db.sqlite3` a plain `python manage.py createsuperuser` would use, which is
a different, unrelated database as far as the desktop app is concerned.

Once created, reach the admin two ways:

- **In the app window itself** -- there's no URL bar, but you're logged in
  to the same session either way, so navigating to `/admin/` isn't
  necessary unless you specifically want Django's admin UI rather than the
  in-app "Admin Plans" screen (Nav bar, superusers only).
- **In a regular browser** -- the desktop app is just a local web server
  under the hood, reachable from any browser while it's running. With the
  app open, visit `http://127.0.0.1:8747/admin/` (8747 is the default port;
  if that was already taken, check the app's terminal output on launch for
  whichever port it actually bound to) and log in with the superuser
  account you just created.

If you've packaged this into a standalone executable (`pyinstaller
desktop/build.spec`), the same `--createsuperuser` flag works on the built
binary too -- run it from a terminal:
```bash
./dist/Agamya-DFS/Agamya-DFS --createsuperuser        # macOS/Linux
dist\Agamya-DFS\Agamya-DFS.exe --createsuperuser       # Windows
```
One catch on Windows: `desktop/build.spec` builds with `console=False` (no
terminal window for the normal app) -- on Windows specifically, that's a
genuine subsystem-level flag, not just "hide the window": a `console=False`
`.exe` has no stdin/stdout attached at all, even if you launch it from an
existing Command Prompt/PowerShell window, so the interactive prompts have
nowhere to go. (macOS and Linux don't have this restriction -- running the
built binary from a Terminal works fine there regardless of the flag.) For
Windows, either:
- Do superuser creation from source instead (`python desktop_app.py
  --createsuperuser`, which is a normal console Python process) and let the
  packaged `.exe` just read the resulting database, or
- Temporarily flip `console=True` in `desktop/build.spec`, rebuild, run
  `Agamya-DFS.exe --createsuperuser` from Command Prompt, then flip it back
  to `console=False` and rebuild again for the version you actually ship.

## Troubleshooting

**Exports/PDF report do nothing -- no save dialog, no error, nothing on
disk** -- this was a real bug fixed in `desktop_app.py`: pywebview disables
all file downloads by default, on every platform, as a security default
(`webview.settings['ALLOW_DOWNLOADS']` starts `False`). `desktop_app.py`
sets it to `True` before creating the window. If you're seeing this on a
build from before that fix, rebuild from current source.

**"Couldn't open the native app window" on Linux** -- install WebKitGTK:
```bash
sudo apt install gir1.2-webkit2-4.1 python3-gi python3-gi-cairo gir1.2-gtk-3.0   # Debian/Ubuntu
```

**PyInstaller build is missing something at runtime (e.g. a
`ModuleNotFoundError` for a Django app)** -- `desktop/build.spec` collects
hidden imports per local app via `collect_submodules(...)`; if you add a
new top-level Django app, add its name to the `LOCAL_APPS` list near the
top of the spec.

**Rebuilding after a code change** -- always `npm run build` first if you
touched anything in `frontend/`, then re-run `pyinstaller desktop/build.spec`.
The bundled SPA is a snapshot from whenever you last built it, same as the
single-origin web deployment described in the main README.

**Windows SmartScreen / macOS Gatekeeper warnings** -- expected for an
unsigned executable. Code-signing (a paid Apple Developer / Microsoft
certificate) is what removes these warnings; out of scope for this build
setup but straightforward to bolt on later if you get a certificate.
