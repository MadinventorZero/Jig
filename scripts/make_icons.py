#!/usr/bin/env python3
"""
Generate all required icon assets from a single 1024x1024 source PNG.

Usage:
    # Generate placeholder icons (no source image needed):
    python scripts/make_icons.py --placeholder

    # Generate from your own 1024x1024 PNG:
    python scripts/make_icons.py --source path/to/icon.png

Outputs (all written to ui/assets/):
    app.icns          — macOS app bundle icon (requires iconutil, Mac only)
    app.ico           — Windows app icon
    menubar_icon.png  — macOS status bar 22x22
    menubar_icon@2x.png — macOS status bar 44x44 (retina)
    menubar_running.png — status bar icon, "running" state
    menubar_error.png   — status bar icon, "error" state
    tray_icon.png     — Windows system tray 64x64
"""
import argparse
import os
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise SystemExit("Pillow required: pip install Pillow")

ROOT   = Path(__file__).parent.parent
ASSETS = ROOT / "ui" / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

# Brand colours
BG     = (18,  18,  18)   # near-black background
ACCENT = (99,  102, 241)  # indigo — "M" glyph
RUN_C  = (34,  197, 94)   # green  — running state
ERR_C  = (239, 68,  68)   # red    — error state


def _draw_icon(size: int, bg: tuple, accent: tuple) -> Image.Image:
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    r    = size // 8
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=(*bg, 255))
    # Simple "M" glyph centred
    m   = size // 2
    pad = size // 5
    lw  = max(2, size // 16)
    pts = [
        (pad,         size - pad),
        (pad,         pad),
        (m,           size // 2),
        (size - pad,  pad),
        (size - pad,  size - pad),
    ]
    draw.line(pts, fill=(*accent, 255), width=lw)
    return img


def _make_placeholder(source_size: int = 1024) -> Image.Image:
    return _draw_icon(source_size, BG, ACCENT)


def _make_icns(source: Image.Image) -> None:
    """Build app.icns using iconutil (macOS only)."""
    if os.uname().sysname != "Darwin":
        print("  skip app.icns — iconutil only available on macOS")
        return

    sizes = [16, 32, 64, 128, 256, 512, 1024]
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "AppIcon.iconset"
        iconset.mkdir()
        for s in sizes:
            img = source.resize((s, s), Image.LANCZOS)
            img.save(iconset / f"icon_{s}x{s}.png")
            if s <= 512:
                img2x = source.resize((s * 2, s * 2), Image.LANCZOS)
                img2x.save(iconset / f"icon_{s}x{s}@2x.png")
        dest = ASSETS / "app.icns"
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(dest)], check=True)
        print(f"  wrote {dest}")


def _make_ico(source: Image.Image) -> None:
    dest  = ASSETS / "app.ico"
    sizes = [(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)]
    imgs  = [source.resize(s, Image.LANCZOS) for s in sizes]
    imgs[0].save(dest, format="ICO", sizes=sizes, append_images=imgs[1:])
    print(f"  wrote {dest}")


def _make_menubar(source: Image.Image) -> None:
    for name, size, state_accent in [
        ("menubar_icon.png",    22, ACCENT),
        ("menubar_icon@2x.png", 44, ACCENT),
        ("menubar_running.png", 22, RUN_C),
        ("menubar_error.png",   22, ERR_C),
    ]:
        img  = _draw_icon(size, BG, state_accent)
        dest = ASSETS / name
        img.save(dest)
        print(f"  wrote {dest}")


def _make_tray(source: Image.Image) -> None:
    img  = source.resize((64, 64), Image.LANCZOS)
    dest = ASSETS / "tray_icon.png"
    img.save(dest)
    print(f"  wrote {dest}")


def main() -> None:
    p = argparse.ArgumentParser(description="Generate Mad Automation Platform icon assets")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--placeholder", action="store_true",
                   help="Generate programmatic placeholder icons")
    g.add_argument("--source", metavar="PNG",
                   help="Path to a 1024x1024 source PNG")
    args = p.parse_args()

    print("Generating icon assets...")
    if args.placeholder:
        src = _make_placeholder(1024)
    else:
        src = Image.open(args.source).convert("RGBA")
        if src.size != (1024, 1024):
            print(f"  warning: source is {src.size}, expected (1024, 1024) — resizing")
            src = src.resize((1024, 1024), Image.LANCZOS)

    _make_icns(src)
    _make_ico(src)
    _make_menubar(src)
    _make_tray(src)
    print("Done. Assets written to ui/assets/")


if __name__ == "__main__":
    main()
