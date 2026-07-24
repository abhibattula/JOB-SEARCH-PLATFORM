"""013 (FR-012): generate the Job Engine app icon from one source mark into
every format the app's surfaces need — packaging/icon.ico (Windows exe/window/
taskbar + installer), packaging/icon.icns (macOS app), web/static/favicon.ico
(browser tab). One source of truth; run once and commit the outputs.

Design: a deep "scope-screen" tile with a bright scope ring and a green check —
"a match, found" — echoing the app's datasheet/scope themes. Not a full brand
system (that's a non-goal); a clean, recognizable app mark.

Run: python packaging/make_icon.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SIZE = 256

BG = (13, 17, 23, 255)        # #0d1117 scope-screen
TILE = (22, 34, 59, 255)      # #16233b deep blue tile
RING = (88, 166, 255, 255)    # #58a6ff bright scope blue
RING2 = (47, 111, 168, 255)   # #2f6fa8 accent
CHECK = (63, 185, 80, 255)    # #3fb950 green


def _draw(size: int) -> Image.Image:
    # Supersample for crisp edges, then downscale.
    S = size * 4
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = int(S * 0.06)
    radius = int(S * 0.22)
    d.rounded_rectangle([pad, pad, S - pad, S - pad], radius=radius, fill=TILE)

    # scope rings (concentric), centered
    cx = cy = S // 2
    for r, color, w in ((int(S * 0.30), RING2, int(S * 0.045)),
                        (int(S * 0.20), RING, int(S * 0.05))):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=w)

    # a bold check across the lower-right — "matched"
    w = int(S * 0.065)
    p1 = (int(S * 0.36), int(S * 0.54))
    p2 = (int(S * 0.47), int(S * 0.65))
    p3 = (int(S * 0.68), int(S * 0.38))
    d.line([p1, p2], fill=CHECK, width=w, joint="curve")
    d.line([p2, p3], fill=CHECK, width=w, joint="curve")
    for pt in (p1, p2, p3):
        d.ellipse([pt[0] - w // 2, pt[1] - w // 2, pt[0] + w // 2, pt[1] + w // 2],
                  fill=CHECK)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    base = _draw(SIZE)
    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

    ico = ROOT / "packaging" / "icon.ico"
    base.save(ico, format="ICO", sizes=ico_sizes)
    print(f"wrote {ico}")

    favicon = ROOT / "web" / "static" / "favicon.ico"
    base.save(favicon, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    print(f"wrote {favicon}")

    icns = ROOT / "packaging" / "icon.icns"
    try:
        base.save(icns, format="ICNS")
        print(f"wrote {icns}")
    except Exception as exc:  # some Pillow builds lack ICNS write
        print(f"WARNING: could not write {icns}: {exc}")


if __name__ == "__main__":
    main()
