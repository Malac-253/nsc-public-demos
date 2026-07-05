"""Strip white/checkerboard backgrounds from PNG icons and normalize size."""
from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
ICON_SIZE = 64
PAD = 6


def is_background(r: int, g: int, b: int, a: int) -> bool:
    if a < 20:
        return True
    spread = max(r, g, b) - min(r, g, b)
    avg = (r + g + b) / 3
    # pure/near white
    if avg > 248 and spread < 12:
        return True
    # light grey checkerboard fringe
    if spread < 28 and avg > 185:
        return True
    return False


def flood_clear(im: Image.Image) -> Image.Image:
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    seen = [[False] * h for _ in range(w)]
    q: deque[tuple[int, int]] = deque()

    def seed(x: int, y: int) -> None:
        if 0 <= x < w and 0 <= y < h and not seen[x][y]:
            r, g, b, a = px[x, y]
            if is_background(r, g, b, a):
                seen[x][y] = True
                q.append((x, y))

    for x in range(w):
        seed(x, 0)
        seed(x, h - 1)
    for y in range(h):
        seed(0, y)
        seed(w - 1, y)

    while q:
        x, y = q.popleft()
        px[x, y] = (0, 0, 0, 0)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not seen[nx][ny]:
                r, g, b, a = px[nx, ny]
                if is_background(r, g, b, a):
                    seen[nx][ny] = True
                    q.append((nx, ny))
    return im


def trim_and_pad(im: Image.Image, size: int) -> Image.Image:
    bbox = im.getbbox()
    if not bbox:
        return Image.new("RGBA", (size, size), (0, 0, 0, 0))
    cropped = im.crop(bbox)
    cw, ch = cropped.size
    inner = size - PAD * 2
    scale = min(inner / cw, inner / ch)
    nw, nh = max(1, int(cw * scale)), max(1, int(ch * scale))
    resized = cropped.resize((nw, nh), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(resized, ((size - nw) // 2, (size - nh) // 2), resized)
    return out


def process(path: Path, size: int) -> None:
    im = flood_clear(Image.open(path))
    im = trim_and_pad(im, size)
    im.save(path, optimize=True)
    print(f"  {path.name} -> {size}x{size}")


def main() -> None:
    icons = ROOT / "icons"
    for p in sorted(icons.glob("*.png")):
        process(p, ICON_SIZE)
    for name, size in (("px-tree.png", 200), ("px-trip-badge.png", 120)):
        p = ROOT / name
        if p.exists():
            im = flood_clear(Image.open(p))
            im = trim_and_pad(im, size)
            im.save(p, optimize=True)
            print(f"  {name} -> {size}x{size}")


if __name__ == "__main__":
    main()
