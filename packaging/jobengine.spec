# PyInstaller spec — build from the repo root:
#   pyinstaller packaging/jobengine.spec
# Produces dist/JobEngine/ (onedir). On macOS also produces "Job Engine.app".
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(ROOT, "web", "templates"), "web/templates"),
    (os.path.join(ROOT, "web", "static"), "web/static"),
    (os.path.join(ROOT, "companies.yml"), "."),
    (os.path.join(ROOT, "assets", "uscis"), "assets/uscis"),
]

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
]

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
            "CFBundleShortVersionString": "0.3.0",
        },
    )
