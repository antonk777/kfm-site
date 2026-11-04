#!/usr/bin/env python3
"""Download the Oswald subsets (Latin + Cyrillic + Vietnamese) from Google
Fonts and write a self-hosted oswald.css for web/public/assets/fonts."""
import re
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
CSS_URL = "https://fonts.googleapis.com/css2?family=Oswald:wght@400;600&display=swap"
OUT_DIR = Path(__file__).resolve().parents[1] / "public" / "assets" / "fonts"
OUT_DIR.mkdir(parents=True, exist_ok=True)

css = urllib.request.urlopen(urllib.request.Request(CSS_URL, headers=UA), timeout=30).read().decode("utf-8")

blocks = re.findall(
    r"/\*\s*([\w-]+)\s*\*/\s*@font-face\s*\{(.*?)\}",
    css,
    re.S,
)
print("subsets:", len(blocks))
lines = ["/* Self-hosted Oswald subsets from Google Fonts (OFL). */"]
saved = 0
for subset, body in blocks:
    url = re.search(r"url\((https://[^)]+)\)", body).group(1)
    w = re.search(r"font-weight:\s*(\d+)", body).group(1)
    rng = re.search(r"unicode-range:\s*([^;]+);", body).group(1)
    name = f"oswald-{w}-{subset}.woff2"
    urllib.request.urlretrieve(url, OUT_DIR / name)
    saved += 1
    lines.append(
        f"@font-face {{\n"
        f"  font-family: 'Oswald';\n"
        f"  font-style: normal;\n"
        f"  font-weight: {w};\n"
        f"  font-display: swap;\n"
        f"  src: url('./{name}') format('woff2');\n"
        f"  unicode-range: {rng};\n"
        f"}}"
    )
(OUT_DIR / "oswald.css").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("saved", saved, "fonts ->", OUT_DIR / "oswald.css")
