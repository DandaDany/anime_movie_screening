"""Derive transparent brand icons from the approved logo without changing its artwork.

This script runs in the Pages build workspace, not in the browser. The original
logo-256.png is preserved as the source of truth. Only the corner-connected
near-cream matte is removed; enclosed white popcorn details are retained.
"""
from collections import deque
from pathlib import Path

from PIL import Image


def render_brand_assets(web_dir: Path) -> None:
    brand = web_dir / "assets" / "brand"
    source = brand / "logo-256.png"
    image = Image.open(source).convert("RGBA")
    width, height = image.size
    pixels = image.load()
    corners = [pixels[0, 0][:3], pixels[width - 1, 0][:3],
               pixels[0, height - 1][:3], pixels[width - 1, height - 1][:3]]
    matte = tuple(round(sum(v[channel] for v in corners) / 4) for channel in range(3))

    # Flood-fill only the connected background; white popcorn inside the logo
    # should never be erased merely because it has a pale color.
    visited = bytearray(width * height)
    queue = deque([(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)])
    while queue:
        x, y = queue.popleft()
        index = y * width + x
        if visited[index]:
            continue
        visited[index] = 1
        r, g, b, _ = pixels[x, y]
        difference = max(abs(r - matte[0]), abs(g - matte[1]), abs(b - matte[2]))
        if difference > 27:
            continue
        opacity = min(255, max(0, round((difference - 8) * 255 / 19)))
        pixels[x, y] = (r, g, b, opacity)
        if x > 0: queue.append((x - 1, y))
        if x + 1 < width: queue.append((x + 1, y))
        if y > 0: queue.append((x, y - 1))
        if y + 1 < height: queue.append((x, y + 1))

    image.save(brand / "logo-transparent.png", optimize=True)
    image.resize((48, 48), Image.Resampling.LANCZOS).save(
        brand / "favicon-48.png", optimize=True
    )
    image.resize((180, 180), Image.Resampling.LANCZOS).save(
        brand / "apple-touch-icon.png", optimize=True
    )
    if Image.open(brand / "logo-transparent.png").getpixel((0, 0))[3] != 0:
        raise RuntimeError("Transparent logo matte removal failed")


if __name__ == "__main__":
    render_brand_assets(Path(__file__).resolve().parents[1] / "web")
