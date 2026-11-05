"""Reduce every letter-spacing in the web app by 20%."""
import re
from pathlib import Path

ROOT = Path(r"S:\kfm-mut\site\web\src")
PATTERN = re.compile(r"(letter-spacing:\s*)([0-9.]+)(em|px)")


def shrink(m: re.Match) -> str:
    value = float(m.group(2)) * 0.8
    text = ("%.3f" % value).rstrip("0").rstrip(".")
    return m.group(1) + text + m.group(3)


changed = 0
for path in list(ROOT.rglob("*.css")) + list(ROOT.rglob("*.vue")):
    src = path.read_text(encoding="utf-8")
    new, n = PATTERN.subn(shrink, src)
    if n:
        path.write_text(new, encoding="utf-8")
        changed += n
        print(f"{path.name}: {n}")
print("total:", changed)
