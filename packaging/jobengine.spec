# PyInstaller spec — build from the repo root:
#   pyinstaller packaging/jobengine.spec
# Produces dist/JobEngine/ (onedir). On macOS also produces "Job Engine.app".
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

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
binaries = []

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

# llama-cpp-python (feature 005, local LLM tier) loads its compiled llama.cpp
# core via ctypes at a path relative to its own package location — the exact
# same invisible-to-static-analysis shape as tls_client above. Without this,
# the app would import fine but every local-model chat() call would fail
# with a missing-DLL error, silently, in production only — precisely the
# v0.4.0 tls_client incident repeating itself. collect_dynamic_libs (not
# collect_data_files) is correct here since these are genuine compiled
# binaries, not package data.
_llama_cpp_libs = collect_dynamic_libs("llama_cpp")
assert any(src.lower().endswith((".dll", ".so", ".dylib")) for src, _ in _llama_cpp_libs), (
    f"llama_cpp native libs not found: {_llama_cpp_libs}"
)
binaries += _llama_cpp_libs

# The bundled local model (feature 005) — fetched by packaging/fetch_model.py
# before this spec runs; never committed to git (see .gitignore). Build-time
# assertion here means a missing/incomplete fetch fails the build loudly
# instead of shipping an installer with no offline AI tier.
_model_path = os.path.join(ROOT, "models", "qwen2.5-1.5b-instruct-q4_k_m.gguf")
assert os.path.exists(_model_path) and os.path.getsize(_model_path) > 500_000_000, (
    f"bundled model missing or too small at {_model_path} — run"
    " packaging/fetch_model.py first"
)
datas.append((_model_path, "models"))

# Playwright (feature 005, Apply Assist) loads its Node.js-based driver at
# runtime from a path relative to its own package's __file__ — package data,
# not a Python import, so invisible to static analysis. Playwright's own
# PyInstaller hook is documented as unreliable on recent PyInstaller for
# macOS, so this is bundled explicitly rather than trusted to "just work" —
# the same defensive posture as tls_client and llama_cpp above.
_playwright_data = collect_data_files("playwright")
assert any(
    src.lower().endswith(("node.exe", os.path.sep + "node")) for src, _ in _playwright_data
), f"playwright driver executable not found: {[s for s, _ in _playwright_data][:5]}"
datas += _playwright_data

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
        "llama_cpp",
        "diskcache",
        "playwright.sync_api",
    ]
    # plyer resolves its notification backend dynamically per platform
    + (["plyer.platforms.win.notification"] if sys.platform == "win32" else [])
    + (["plyer.platforms.macosx.notification"] if sys.platform == "darwin" else [])
    # keyring (feature 005, credential vault) does not reliably auto-detect
    # its backend inside a frozen app — engine/credentials.py calls
    # keyring.set_keyring() explicitly when frozen, so the concrete backend
    # module must be declared here or that call fails with ImportError.
    + (["keyring.backends.Windows"] if sys.platform == "win32" else [])
    + (["keyring.backends.macOS"] if sys.platform == "darwin" else [])
)

a = Analysis(
    [os.path.join(ROOT, "desktop.py")],
    pathex=[ROOT],
    datas=datas,
    binaries=binaries,
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
            "CFBundleShortVersionString": "0.5.6",
        },
    )
