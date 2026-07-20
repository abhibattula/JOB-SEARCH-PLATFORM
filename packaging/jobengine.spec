# PyInstaller spec — build from the repo root:
#   pyinstaller packaging/jobengine.spec
# Produces dist/JobEngine/ (onedir). On macOS also produces "Job Engine.app".
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
# collect_submodules imports the package at build time; the repo root is not on
# sys.path during spec execution, so add it or the collection silently yields [].
sys.path.insert(0, ROOT)

datas = [
    (os.path.join(ROOT, "web", "templates"), "web/templates"),
    (os.path.join(ROOT, "web", "static"), "web/static"),
    (os.path.join(ROOT, "companies.yml"), "."),
    (os.path.join(ROOT, "assets", "uscis"), "assets/uscis"),
]

# jobspy's tls_client dependency loads a native dll/so/dylib via ctypes at a
# path computed from its own package location — invisible to PyInstaller's
# static import analysis, so it's silently dropped without this. Confirmed
# live: every jobspy search failed frozen with "the specified module could
# not be found" (WinError / FileNotFoundError loading tls-client-64.dll)
# until this was added.
_tls_client_data = collect_data_files("tls_client")
assert any(src.lower().endswith((".dll", ".so", ".dylib")) for src, _ in _tls_client_data), (
    f"tls_client native libs not found: {_tls_client_data}"
)
datas += _tls_client_data

# The engine loads sources via importlib with string names, and imports pandas/
# jobspy/matcher lazily inside functions — all invisible to static analysis, so
# everything engine-adjacent must be declared explicitly.
_engine_modules = collect_submodules("engine")
assert any("ingest.greenhouse" in m for m in _engine_modules), (
    f"engine submodule collection failed: {_engine_modules}"
)

hiddenimports = (
    _engine_modules
    + [
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        "jobspy",
        "pandas",
        "openpyxl",
        "openai",
        "apscheduler.schedulers.background",
        "apscheduler.triggers.cron",
    ]
    # plyer resolves its notification backend dynamically per platform
    + (["plyer.platforms.win.notification"] if sys.platform == "win32" else [])
    + (["plyer.platforms.macosx.notification"] if sys.platform == "darwin" else [])
)

a = Analysis(
    [os.path.join(ROOT, "desktop.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="JobEngine",
    # JE_DEBUG_CONSOLE=1 at build time produces a console build for diagnosing
    # frozen-only failures (windowed builds swallow tracebacks).
    console=os.environ.get("JE_DEBUG_CONSOLE") == "1",
    icon=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="JobEngine",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Job Engine.app",
        bundle_identifier="dev.abhinav.jobengine",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": "0.4.1",
        },
    )
