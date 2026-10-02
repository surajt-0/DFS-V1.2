# PyInstaller spec for Agamya CyberTech - DFS (desktop build).
#
# Build (run from the project root, i.e. `pyinstaller desktop/build.spec`,
# NOT from inside desktop/ -- paths below are relative to the project root):
#
#   cd frontend && npm install && npm run build && cd ..
#   pip install -r requirements.txt
#   pyinstaller desktop/build.spec
#
# Output: dist/Agamya-DFS/ (dist/Agamya-DFS/Agamya-DFS.exe on Windows,
# dist/Agamya-DFS.app on macOS if you switch BUNDLE on below).
#
# PyInstaller does NOT cross-compile -- build on each OS you want to ship
# for. See DESKTOP.md for the accompanying GitHub Actions workflow that
# builds Windows/macOS/Linux automatically via CI instead of by hand.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

PROJECT_ROOT = Path(SPECPATH).resolve().parent  # desktop/build.spec -> project root

# Django loads these dynamically (INSTALLED_APPS strings, migration modules
# imported by name, etc.) so PyInstaller's static import analysis alone
# won't find them -- collect every submodule of each local app explicitly.
LOCAL_APPS = ["dfs_web", "accounts", "auditlog", "billing", "cases", "core", "dashboard", "evidence", "recovery"]
hidden_imports = []
for app in LOCAL_APPS:
    hidden_imports += collect_submodules(app)

# Third-party packages with their own dynamic-import patterns.
for pkg in ["rest_framework", "corsheaders", "whitenoise", "waitress", "webview"]:
    hidden_imports += collect_submodules(pkg)

datas = [
    (str(PROJECT_ROOT / "frontend" / "dist"), "frontend/dist"),
    (str(PROJECT_ROOT / "static"), "static"),
]
datas += collect_data_files("django.contrib.admin")
datas += collect_data_files("django.contrib.auth")
datas += collect_data_files("rest_framework")

a = Analysis(
    [str(PROJECT_ROOT / "desktop_app.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Agamya-DFS",
    debug=False,
    strip=False,
    upx=False,
    console=False,  # no terminal window behind the app on Windows/macOS
    # PyInstaller's `icon` needs a real .ico (Windows) / .icns (macOS) file,
    # not the .svg/.jpg logo already in the repo. Generate one (e.g. via
    # https://icoconvert.com or `iconutil` on macOS) from
    # frontend/src/assets/agamya-logo.jpg and point this at it, e.g.:
    #   icon=str(PROJECT_ROOT / "desktop" / "icon.ico")
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Agamya-DFS",
)

# Uncomment for a proper double-clickable .app bundle on macOS instead of a
# raw folder (dist/Agamya-DFS.app):
#
# app = BUNDLE(
#     coll,
#     name="Agamya-DFS.app",
#     bundle_identifier="tech.agamyacyber.dfs",
# )
