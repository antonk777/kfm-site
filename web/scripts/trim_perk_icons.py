#!/usr/bin/env python3
"""Trim the transparent padding off the perk icons: crop each PNG to its
alpha bounding box plus a small margin, so the artwork fills its box."""
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parents[1] / "public" / "assets" / "perks"
MARGIN = 4


def main() -> None:
    n = 0
    for png in sorted(OUT.glob("Perk_*.png")):
        im = Image.open(png).convert("RGBA")
        alpha = im.getchannel("A")
        bbox = alpha.getbbox()
        if not bbox:
            print("empty:", png.name)
            continue
        left, top, right, bottom = bbox
        left = max(0, left - MARGIN)
        top = max(0, top - MARGIN)
        right = min(im.width, right + MARGIN)
        bottom = min(im.height, bottom + MARGIN)
        cropped = im.crop((left, top, right, bottom))
        if cropped.size == im.size:
            continue
        cropped.save(png)
        n += 1
        print(f"{png.name}: {im.size} -> {cropped.size}")
    print("trimmed", n, "icons")


if __name__ == "__main__":
    main()
