"""013 (FR-012): the app-icon assets exist and are wired into every surface."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_icon_assets_exist():
    assert (ROOT / "packaging" / "icon.ico").exists()
    assert (ROOT / "packaging" / "icon.icns").exists()
    assert (ROOT / "web" / "static" / "favicon.ico").exists()


def test_windows_installer_references_icon():
    iss = (ROOT / "packaging" / "windows.iss").read_text(encoding="utf-8")
    assert "SetupIconFile=icon.ico" in iss
    assert "UninstallDisplayIcon=" in iss


def test_pyinstaller_spec_sets_exe_icon():
    spec = (ROOT / "packaging" / "jobengine.spec").read_text(encoding="utf-8")
    assert "icon.ico" in spec and "icon=_ICON_ICO" in spec
    assert "icon=_ICON_ICNS" in spec   # macOS bundle icon


def test_base_template_links_favicon():
    base = (ROOT / "web" / "templates" / "base.html").read_text(encoding="utf-8")
    assert 'rel="icon"' in base and "favicon.ico" in base


def test_icon_ico_is_a_valid_multisize_image():
    from PIL import Image

    with Image.open(ROOT / "packaging" / "icon.ico") as img:
        assert img.size[0] >= 256   # the largest embedded size
