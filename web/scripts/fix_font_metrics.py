"""Add CSS Fonts 4 metric overrides to the self-hosted font faces so text
sits tight in its line box (Bebas Neue reserves 30% descent, Oswald 29% with
a 1.19 ascent — both leave dead space under the glyphs)."""
import re
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "src" / "styles" / "fonts.css"
CSS = P.read_text(encoding="utf-8")

OVER = {
    "Bebas Neue": "  ascent-override: 88%;\n  descent-override: 12%;\n  line-gap-override: 0%;\n",
    "Oswald": "  ascent-override: 100%;\n  descent-override: 24%;\n  line-gap-override: 0%;\n",
}

BLOCK = re.compile(r"@font-face \{\n  font-family: '([^']+)';(.*?)\n\}", re.S)


def inject(m: re.Match) -> str:
    family = m.group(1)
    body = m.group(0)
    if "ascent-override" in body:
        return body
    extra = OVER.get(family, "")
    if not extra:
        return body
    return body.replace("  font-display: swap;\n", "  font-display: swap;\n" + extra, 1)


new = BLOCK.sub(inject, CSS)
P.write_text(new, encoding="utf-8")
print("font faces with overrides:", new.count("ascent-override"))
