#!/usr/bin/env python3
"""Extract full-resolution perk icons from MutZombies_T.utx (UE2 package).

Reads the HUD.Perk_* Texture exports (DXT5 with alpha, 256x256 top mip) and
writes RGBA PNGs into web/public/assets/perks/. Decode code mirrors
tools/gen_map_shots.py, extended with DXT3/DXT5 alpha.

Usage:
  python scripts/extract_perk_icons.py
"""
import struct
from pathlib import Path

from PIL import Image

def repo_root() -> Path:
    p = Path(__file__).resolve().parents[1]
    for _ in range(8):
        if (p / "KFManiacsMod").is_dir():
            return p
        p = p.parent
    return p


UTX = repo_root() / "Textures" / "MutZombies_T.utx"
OUT = Path(__file__).resolve().parents[1] / "public" / "assets" / "perks"

PROP_SIZE = {0: 1, 1: 2, 2: 4, 3: 12, 4: 16}
RF_HAS_STACK = 0x02000000
TEXF_P8, TEXF_RGBA7, TEXF_RGB16, TEXF_DXT1, TEXF_RGB8, TEXF_RGBA8, TEXF_NODATA, TEXF_DXT3, TEXF_DXT5, TEXF_L8 = range(10)


def rci(b: bytes, p: int) -> tuple[int, int]:
    b0 = b[p]
    p += 1
    neg = b0 & 0x80
    more = b0 & 0x40
    v = b0 & 0x3F
    sh = 6
    while more:
        x = b[p]
        p += 1
        more = x & 0x80
        v |= (x & 0x7F) << sh
        sh += 7
    return (-v if neg else v), p


class Pkg:
    def __init__(self, path: Path):
        d = path.read_bytes()
        self.d = d
        self.version = struct.unpack_from("<H", d, 4)[0]
        _flags, nc, noff, ec, eoff, ic, ioff = struct.unpack_from("<IIIIIII", d, 8)
        p = noff
        self.names: list[str] = []
        for _ in range(nc):
            ln, p = rci(d, p)
            self.names.append(d[p : p + ln - 1].decode("latin-1"))
            p += ln + 4
        self.imports: list[tuple[str, str, int, str]] = []
        p = ioff
        for _ in range(ic):
            cp, p = rci(d, p)
            cn, p = rci(d, p)
            outer = struct.unpack_from("<i", d, p)[0]
            p += 4
            on, p = rci(d, p)
            self.imports.append((self.names[cp], self.names[cn], outer, self.names[on]))
        self.exports: list[dict] = []
        p = eoff
        for _ in range(ec):
            cls, p = rci(d, p)
            sup, p = rci(d, p)
            outer = struct.unpack_from("<i", d, p)[0]
            p += 4
            on, p = rci(d, p)
            fl = struct.unpack_from("<I", d, p)[0]
            p += 4
            size, p = rci(d, p)
            off = 0
            if size > 0:
                off, p = rci(d, p)
            self.exports.append(dict(cls=cls, sup=sup, outer=outer, name=self.names[on], flags=fl, size=size, off=off))

    def clsname(self, ref: int) -> str:
        if ref == 0:
            return "Class"
        if ref < 0:
            return self.imports[-ref - 1][3]
        return self.exports[ref - 1]["name"]


def tagged_props(k: Pkg, start: int, end: int) -> tuple[list[tuple[str, object]], int]:
    d = k.d
    names = k.names
    none = names.index("None")

    def walk(pos: int, limit: int = 400):
        rows = []
        for _ in range(limit):
            ni, pos = rci(d, pos)
            if ni < 0 or ni >= len(names):
                return None, pos
            if ni == none:
                return rows, pos
            info = d[pos]
            pos += 1
            typ = info & 0x0F
            szb = (info >> 4) & 7
            is_arr = info & 0x80
            if typ == 0:
                return None, pos
            if typ == 10:
                _, pos = rci(d, pos)
            if szb < 5:
                size = PROP_SIZE[szb]
            elif szb == 5:
                size = d[pos]
                pos += 1
            elif szb == 6:
                size = struct.unpack_from("<H", d, pos)[0]
                pos += 2
            else:
                size = struct.unpack_from("<i", d, pos)[0]
                pos += 4
            if size < 0 or pos + size > end:
                return None, pos
            if typ == 3 and size:
                return None, pos
            if is_arr and typ != 3:
                b = d[pos]
                pos += 1 if b < 128 else (2 if b < 192 else 4)
            raw = d[pos : pos + size]
            val = None
            if typ in (5, 8):
                val, _ = rci(raw, 0)
            elif typ == 1 and size == 1:
                val = raw[0]
            elif typ == 2 and size == 4:
                val = struct.unpack_from("<i", raw)[0]
            pos += size
            rows.append((names[ni], val))
        return None, pos

    try:
        rows, p = walk(start)
    except Exception:  # noqa: BLE001
        rows, p = None, start
    return (rows or [], p)


def rgb565(v: int) -> tuple[int, int, int]:
    r = (v >> 11) & 31
    g = (v >> 5) & 63
    b = v & 31
    return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)


def decode_dxt_colour(data: bytes, w: int, h: int, coff: int) -> bytes:
    """DXT1/DXT3/DXT5 colour part -> RGB bytes (block stride 8 for DXT1, 16 otherwise)."""
    block = 16 if coff else 8
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    out = bytearray(w * h * 3)
    for by in range(bh):
        for bx in range(bw):
            p = (by * bw + bx) * block + coff
            if p + 8 > len(data):
                break
            c0, c1, bits = struct.unpack_from("<HHI", data, p)
            r0, g0, b0 = rgb565(c0)
            r1, g1, b1 = rgb565(c1)
            if c0 > c1 or coff:
                pal = (
                    (r0, g0, b0),
                    (r1, g1, b1),
                    ((2 * r0 + r1) // 3, (2 * g0 + g1) // 3, (2 * b0 + b1) // 3),
                    ((r0 + 2 * r1) // 3, (g0 + 2 * g1) // 3, (b0 + 2 * b1) // 3),
                )
            else:
                pal = ((r0, g0, b0), (r1, g1, b1), ((r0 + r1) // 2, (g0 + g1) // 2, (b0 + b1) // 2), (0, 0, 0))
            for py in range(4):
                y = by * 4 + py
                if y >= h:
                    break
                row = y * w
                for px in range(4):
                    x = bx * 4 + px
                    if x >= w:
                        break
                    c = pal[(bits >> (2 * (py * 4 + px))) & 3]
                    o = (row + x) * 3
                    out[o] = c[0]
                    out[o + 1] = c[1]
                    out[o + 2] = c[2]
    return bytes(out)


def decode_dxt5_alpha(data: bytes, w: int, h: int) -> bytes:
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    out = bytearray(w * h)
    for by in range(bh):
        for bx in range(bw):
            p = (by * bw + bx) * 16
            if p + 8 > len(data):
                break
            a0, a1 = data[p], data[p + 1]
            if a0 > a1:
                alphas = (a0, a1, (6 * a0 + 1 * a1) // 7, (5 * a0 + 2 * a1) // 7, (4 * a0 + 3 * a1) // 7, (3 * a0 + 4 * a1) // 7, (2 * a0 + 5 * a1) // 7, (1 * a0 + 6 * a1) // 7)
            else:
                alphas = (a0, a1, (4 * a0 + 1 * a1) // 5, (3 * a0 + 2 * a1) // 5, (2 * a0 + 3 * a1) // 5, (1 * a0 + 4 * a1) // 5, 0, 255)
            for i in range(16):
                bit = i * 3
                idx = (data[p + 2 + bit // 8] >> (bit % 8)) & 7
                if bit % 8 > 5:
                    idx = ((data[p + 2 + bit // 8] >> (bit % 8)) | (data[p + 3 + bit // 8] << (8 - bit % 8))) & 7
                py, px = i // 4, i % 4
                y, x = by * 4 + py, bx * 4 + px
                if y < h and x < w:
                    out[y * w + x] = alphas[idx]
    return bytes(out)


def decode_dxt3_alpha(data: bytes, w: int, h: int) -> bytes:
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    out = bytearray(w * h)
    for by in range(bh):
        for bx in range(bw):
            p = (by * bw + bx) * 16
            if p + 8 > len(data):
                break
            for i in range(16):
                nib = data[p + i // 2] >> (4 * (i % 2)) & 0xF
                py, px = i // 4, i % 4
                y, x = by * 4 + py, bx * 4 + px
                if y < h and x < w:
                    out[y * w + x] = nib * 17
    return bytes(out)


def palette_rgb(k: Pkg, ref: int) -> bytes | None:
    if not (0 < ref <= len(k.exports)):
        return None
    e = k.exports[ref - 1]
    _, p = tagged_props(k, e["off"], e["off"] + e["size"])
    n, p = rci(k.d, p)
    if n <= 0 or n > 256 or p + n * 4 > e["off"] + e["size"]:
        return None
    pal = bytearray(768)
    for i in range(n):
        b, g, r = k.d[p + i * 4], k.d[p + i * 4 + 1], k.d[p + i * 4 + 2]
        pal[i * 3 : i * 3 + 3] = bytes((r, g, b))
    return bytes(pal)


def decode_texture(k: Pkg, ref: int) -> Image.Image | None:
    e = k.exports[ref - 1]
    start, end = e["off"], e["off"] + e["size"]
    p = start
    if e["flags"] & RF_HAS_STACK:
        node, p = rci(k.d, p)
        _, p = rci(k.d, p)
        p += 12
        if node:
            _, p = rci(k.d, p)
    rows, p = tagged_props(k, p, end)
    props = dict(rows)
    fmt = int(props.get("Format", TEXF_P8) or 0)
    nmips, p = rci(k.d, p)
    if nmips <= 0:
        return None
    if k.version >= 63:
        p += 4
    count, p = rci(k.d, p)
    data = k.d[p : p + count]
    p += count
    w, h = struct.unpack_from("<ii", k.d, p)
    if w <= 0 or h <= 0 or w > 4096 or h > 4096:
        return None
    if fmt == TEXF_P8:
        pal = palette_rgb(k, int(props.get("Palette") or 0))
        if pal is None or len(data) < w * h:
            return None
        im = Image.frombytes("P", (w, h), data[: w * h])
        im.putpalette(pal)
        return im.convert("RGBA")
    if fmt == TEXF_DXT1:
        rgb = decode_dxt_colour(data, w, h, 0)
        return Image.frombytes("RGB", (w, h), rgb).convert("RGBA")
    if fmt in (TEXF_DXT3, TEXF_DXT5):
        rgb = decode_dxt_colour(data, w, h, 8)
        alpha = decode_dxt5_alpha(data, w, h) if fmt == TEXF_DXT5 else decode_dxt3_alpha(data, w, h)
        im = Image.frombytes("RGB", (w, h), rgb)
        im.putalpha(Image.frombytes("L", (w, h), alpha))
        return im
    if fmt == TEXF_RGBA8:
        return Image.frombytes("RGBA", (w, h), data[: w * h * 4], "raw", "BGRA")
    if fmt == TEXF_RGB8:
        return Image.frombytes("RGB", (w, h), data[: w * h * 3], "raw", "BGR").convert("RGBA")
    if fmt == TEXF_L8:
        return Image.frombytes("L", (w, h), data[: w * h]).convert("RGBA")
    if fmt == TEXF_RGBA7:
        return Image.frombytes("RGBA", (w, h), data[: w * h * 4], "raw", "BGRA").point(lambda v: min(255, v * 2))
    return None


def main() -> None:
    utx = UTX.resolve()
    if not utx.exists():
        utx = repo_root() / "Textures" / "MutZombies_T.utx"
    k = Pkg(utx)
    OUT.mkdir(parents=True, exist_ok=True)
    n = 0
    for i, e in enumerate(k.exports):
        if k.clsname(e["cls"]) != "Texture" or not e["name"].startswith("Perk_"):
            continue
        if e["name"].startswith("Perk_") and not any(v in e["name"] for v in ("_White", "_Prestige", "_Gold_Prestige")):
            continue
        im = decode_texture(k, i + 1)
        if im is None:
            print("skip", e["name"])
            continue
        out = OUT / (e["name"] + ".png")
        im.save(out)
        n += 1
        print(f"{e['name']}: {im.size} {im.mode} -> {out.name}")
    print("wrote", n, "icons")


if __name__ == "__main__":
    main()
