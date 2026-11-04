#!/usr/bin/env python3
"""Vectorize the extracted stat icons: trace the 14 game-art PNGs to SVG
(vtracer, like the skull placeholder), keeping the hand-drawn 7 as they are.

Icons with a real alpha channel are traced as-is (already bone-tinted); opaque
HUD glyphs (art on black) get luminance-as-alpha so the trace has no black
background. Usage:
  python scripts/vectorize_stat_icons.py
"""
import sys
from pathlib import Path

import vtracer
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

OUT = Path(__file__).resolve().parents[1] / "public" / "assets" / "stats"

PNG_ICONS = [
    "heal", "weld", "shotgun", "headshot", "bullpup", "melee", "flame",
    "selfheal", "sole", "cash", "xbow", "stalkexp", "explosives", "zedtime",
]

BONE = (216, 210, 196, 0)


def main() -> None:
    for name in PNG_ICONS:
        png = OUT / (name + ".png")
        im = Image.open(png).convert("RGBA")
        alpha = im.getchannel("A")
        if alpha.getextrema() == (255, 255):
            # Opaque glyph art on black: transparency from luminance.
            lum = im.convert("L")
            prep = Image.new("RGBA", im.size, BONE)
            prep.putalpha(lum)
            tmp = OUT / (name + "_prep.png")
            prep.save(tmp)
        else:
            tmp = png
        svg = OUT / (name + ".svg")
        vtracer.convert_image_to_svg_py(
            str(tmp),
            str(svg),
            colormode="color",
            hierarchical="stacked",
            mode="spline",
            filter_speckle=4,
            color_precision=6,
            layer_difference=16,
            corner_threshold=60,
            length_threshold=4.0,
            max_iterations=10,
            splice_threshold=45,
            path_precision=3,
        )
        if tmp != png:
            tmp.unlink()
        size = svg.stat().st_size
        print(f"{name}: {im.size} -> {name}.svg ({size} bytes)")


if __name__ == "__main__":
    main()
