"""Erzeugt alle App-Icons (Android, Web, Logo in der App) aus einer Zeichnung.

Aufruf im Ordner app/: python tool/make_icons.py  (braucht Pillow)
Die Zeichnung liegt auf einem 96er-Raster: steigende Balken hinter einem Rennrad.
"""
from pathlib import Path

from PIL import Image, ImageDraw

NAVY = (19, 41, 75)  # #13294B, wie AppColors.brand
ORANGE = (255, 122, 69)  # #FF7A45, wie AppColors.accent
WHITE = (255, 255, 255)
SS = 4  # Supersampling gegen Treppenkanten

BARS = [(12, 62, 30, 84), (39, 44, 57, 84), (66, 22, 84, 84)]
WHEELS = [(26, 58), (70, 58)]
LINES = [
    [(26, 58), (46, 58), (40, 36), (26, 58)],
    [(40, 36), (64, 38), (46, 58)],
    [(64, 38), (70, 58)],
    [(34, 33), (45, 33)],
    [(64, 38), (62, 30), (67, 30)],
]


def render(size: int, grid: float, rounded: bool, background: bool = True) -> Image.Image:
    """grid: Anteil der Kantenlaenge, den das 96er-Raster einnimmt (1.0 = randlos)."""
    n = size * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = n * grid / 96
    o = (n - 96 * s) / 2

    def p(x, y):
        return (o + x * s, o + y * s)

    if background:
        if rounded:
            d.rounded_rectangle((0, 0, n - 1, n - 1), radius=n * 22 / 96, fill=NAVY)
        else:
            d.rectangle((0, 0, n, n), fill=NAVY)
    for x0, y0, x1, y1 in BARS:
        d.rounded_rectangle((*p(x0, y0), *p(x1, y1)), radius=3 * s, fill=ORANGE)
    w = 4.5 * s
    for cx, cy in WHEELS:
        r = 15 * s
        x, y = p(cx, cy)
        d.ellipse((x - r - w / 2, y - r - w / 2, x + r + w / 2, y + r + w / 2), outline=WHITE, width=round(w))
    for line in LINES:
        pts = [p(*q) for q in line]
        d.line(pts, fill=WHITE, width=round(w), joint="curve")
        for x, y in pts:  # runde Enden
            d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=WHITE)
    return img.resize((size, size), Image.LANCZOS)


def main():
    root = Path(__file__).resolve().parent.parent
    res = root / "android/app/src/main/res"
    densities = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}
    for name, f in densities.items():
        render(round(48 * f), 1.0, True).save(res / f"mipmap-{name}/ic_launcher.png")
        # Adaptives Icon: Inhalt muss in den sicheren Kreis (66 von 108 dp) passen
        render(round(108 * f), 0.574, False, background=False).save(res / f"mipmap-{name}/ic_launcher_foreground.png")
    web = root / "web"
    render(32, 1.0, True).save(web / "favicon.png")
    for px in (192, 512):
        render(px, 1.0, True).save(web / f"icons/Icon-{px}.png")
        render(px, 0.74, False).save(web / f"icons/Icon-maskable-{px}.png")
    (root / "assets").mkdir(exist_ok=True)
    render(256, 1.0, True).save(root / "assets/logo.png")


if __name__ == "__main__":
    main()
