"""Generate the app icon (build-time): dark rounded square + green ring/dot.

Outputs to build/: icon_1024.png, icon.iconset/* (macOS), icon.ico (Windows).
Requires Pillow (build-time only).
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "build"
GREEN = (47, 191, 113, 255)
BG = (28, 28, 36, 255)


def render(size: int) -> Image.Image:
    # Render at 4x then downscale for antialiasing.
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=BG)
    c, r = s // 2, int(s * 0.30)
    d.ellipse([c - r, c - r, c + r, c + r], outline=GREEN, width=max(2, int(s * 0.055)))
    r2 = int(s * 0.15)
    d.ellipse([c - r2, c - r2, c + r2, c + r2], fill=GREEN)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    render(1024).save(OUT / "icon_1024.png")

    iconset = OUT / "icon.iconset"
    iconset.mkdir(exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        render(size).save(iconset / f"icon_{size}x{size}.png")
        render(size * 2).save(iconset / f"icon_{size}x{size}@2x.png")

    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    render(256).save(OUT / "icon.ico", sizes=[(s, s) for s in ico_sizes])
    print(f"Icons written to {OUT}")


if __name__ == "__main__":
    main()
