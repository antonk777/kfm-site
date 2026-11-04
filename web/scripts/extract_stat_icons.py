#!/usr/bin/env python3
"""Build combat-stat icons for the web app.

Game icons are decoded from the KF1 HUD packages (full-res, alpha kept) and
tinted to the theme's bone-white where they have an alpha channel; zed-specific
stats get hand-drawn bone-white SVG glyphs in the same style.

Usage:
  python scripts/extract_stat_icons.py
"""
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_perk_icons import Pkg, decode_texture  # noqa: E402

KF = Path(r"F:\SteamLibrary\steamapps\common\KillingFloor\Textures")
OUT = Path(__file__).resolve().parents[1] / "public" / "assets" / "stats"

BONE = (216, 210, 196)

# (package file, texture path, output name)
ICONS = [
    ("KillingFloorHUD.utx", "Trader_Weapon_Images.Trader_First_Aid", "heal"),
    ("KillingFloorHUD.utx", "WeaponSelect.Welder", "weld"),
    ("KillingFloorHUD.utx", "WeaponSelect.combat_shotgun", "shotgun"),
    ("KF_IJC_HUD.utx", "WeaponSelect.sniper", "headshot"),
    ("KillingFloorHUD.utx", "WeaponSelect.Bullpup", "bullpup"),
    ("KillingFloorHUD.utx", "WeaponSelect.Axe", "melee"),
    ("KillingFloorHUD.utx", "WeaponSelect.FlameThrower", "flame"),
    ("KillingFloorHUD.utx", "HUD.Hud_Syringe", "selfheal"),
    ("KillingFloorHUD.utx", "HUD.Hud_Perk_Star", "sole"),
    ("KillingFloorHUD.utx", "Generic.HUDCoins", "cash"),
    ("KillingFloorHUD.utx", "WeaponSelect.Crossbow", "xbow"),
    ("KillingFloorHUD.utx", "WeaponSelect.Frag", "stalkexp"),
    ("KillingFloorHUD.utx", "HUD.Hud_Grenade", "explosives"),
    ("KillingFloorHUD.utx", "HUD.Hud_Bio_Clock_Circle", "zedtime"),
]

# Hand-drawn bone-white glyphs for zed-specific stats (64x64 viewBox).
SVGS = {
    "kills": """<g fill="#d8d2c4"><path d="M32 6 C20 6 12 14 12 24 C12 32 16 36 16 40 L16 48 C16 52 20 56 24 56 L40 56 C44 56 48 52 48 48 L48 40 C48 36 52 32 52 24 C52 14 44 6 32 6 Z"/><circle cx="24" cy="24" r="5" fill="#0a0a0c"/><circle cx="40" cy="24" r="5" fill="#0a0a0c"/><rect x="29" y="38" width="6" height="8" rx="1" fill="#0a0a0c"/></g>""",
    "stalker": """<g fill="none" stroke="#d8d2c4" stroke-width="5" stroke-linecap="round"><path d="M16 14 L30 38"/><path d="M28 10 L42 34"/><path d="M40 6 L54 30"/></g>""",
    "feeding": """<g fill="#d8d2c4"><path d="M10 24 h5 v-8 h6 v8 h5 v-8 h6 v8 h5 v-8 h6 v8 h5 v6 H10 Z"/><path d="M10 34 Q32 52 54 34 L54 42 Q32 56 10 42 Z"/></g>""",
    "gibfp": """<g fill="none" stroke="#d8d2c4" stroke-width="4" stroke-linecap="round"><rect x="20" y="28" width="24" height="20" rx="6" fill="#d8d2c4" stroke="none"/><path d="M26 12 l4 8"/><path d="M32 8 v12"/><path d="M38 12 l-4 8"/><path d="M8 8 l6 6"/><path d="M56 8 l-6 6"/><path d="M8 44 l6 -6"/><path d="M56 44 l-6 -6"/><path d="M4 26 h8"/><path d="M52 26 h8"/></g>""",
    "gibbed": """<g fill="#d8d2c4"><circle cx="19" cy="15" r="6"/><circle cx="19" cy="49" r="6"/><circle cx="45" cy="15" r="6"/><circle cx="45" cy="49" r="6"/><rect x="16" y="15" width="32" height="34" rx="2"/></g>""",
    "bloat": """<g fill="#d8d2c4"><path d="M14 24 Q14 8 32 8 Q50 8 50 24 Q50 38 32 38 Q14 38 14 24 Z"/><path d="M24 22 Q32 30 40 22 Q32 26 24 22 Z" fill="#0a0a0c"/><circle cx="42" cy="46" r="4"/><path d="M39 53 L45 53 L42 59 Z"/></g>""",
    "siren": """<g fill="#d8d2c4"><path d="M23 22 Q32 30 41 22 Q41 36 32 40 Q23 36 23 22 Z"/><path d="M10 30 q-6 -10 0 -18 q6 8 0 18 z"/><path d="M54 30 q6 -10 0 -18 q-6 8 0 18 z"/><circle cx="27" cy="13" r="3"/><circle cx="37" cy="13" r="3"/></g>""",
}

SVG_TMPL = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">{body}</svg>\n'


def export_path(k: Pkg, ref: int) -> str:
    parts = []
    while ref != 0:
        if ref < 0:
            imp = k.imports[-ref - 1]
            parts.append(imp[3])
            ref = imp[2]
        else:
            e = k.exports[ref - 1]
            parts.append(e["name"])
            ref = e["outer"]
    return ".".join(reversed(parts))


def bone_tint(im: Image.Image) -> Image.Image:
    im = im.convert("RGBA")
    alpha = im.getchannel("A")
    if alpha.getextrema() == (255, 255):
        # Opaque (HUD glyph art on black): keep the art as it is.
        return im
    out = Image.new("RGBA", im.size, BONE + (0,))
    out.putalpha(alpha)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cache: dict[str, Pkg] = {}
    n = 0
    for pkg_name, tex_path, out_name in ICONS:
        try:
            k = cache.get(pkg_name)
            if k is None:
                k = Pkg(KF / pkg_name)
                cache[pkg_name] = k
            want = tex_path.lower().split(".")
            ref = 0
            for i, e in enumerate(k.exports):
                if k.clsname(e["cls"]) != "Texture":
                    continue
                parts = export_path(k, i + 1).lower().split(".")
                if parts[-len(want) :] == want:
                    ref = i + 1
                    break
            if not ref:
                print("NOT FOUND:", pkg_name, tex_path)
                continue
            im = decode_texture(k, ref)
            if im is None:
                print("DECODE FAIL:", pkg_name, tex_path)
                continue
            im = bone_tint(im)
            out = OUT / (out_name + ".png")
            im.save(out)
            n += 1
            print(f"{pkg_name} {tex_path} ({im.size}) -> {out.name}")
        except Exception as exc:  # noqa: BLE001
            print("ERROR:", pkg_name, tex_path, exc)
    for name, body in SVGS.items():
        (OUT / (name + ".svg")).write_text(SVG_TMPL.format(body=body), encoding="utf-8")
        n += 1
        print("svg ->", name + ".svg")
    print("wrote", n, "stat icons")


if __name__ == "__main__":
    main()
