#!/usr/bin/env python3
"""Convert the old hub's PHP country name arrays (EN/RU) into a TS module."""
import re
from pathlib import Path

SRC_EN = Path(r"D:\_kfm_proj\hub\first_include\country_en.php")
SRC_RU = Path(r"D:\_kfm_proj\hub\first_include\country.php")
OUT = Path(__file__).resolve().parents[1] / "src" / "data" / "countries.ts"


def parse(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    out: dict[str, str] = {}
    for m in re.finditer(r'"([A-Z]{2})"\s*=>\s*"((?:[^"\\]|\\.)*)"', text):
        out[m.group(1)] = m.group(2).replace('\\"', '"').replace("\\\\", "\\")
    return out


def ts_block(entries: dict[str, str]) -> str:
    rows = ",\n  ".join(f"{k!r}: {v!r}" for k, v in sorted(entries.items()))
    return "{\n  " + rows + ",\n}"


en = parse(SRC_EN)
ru = parse(SRC_RU)
print("en:", len(en), "ru:", len(ru))
OUT.write_text(
    "// Country names from the old hub (first_include/country*.php).\n"
    "// Missing codes fall back to English, then to the code itself.\n\n"
    f"export const COUNTRIES_EN: Record<string, string> = {ts_block(en)};\n\n"
    f"export const COUNTRIES_RU: Record<string, string> = {ts_block(ru)};\n\n"
    "export function countryName(code: string, locale: string): string {\n"
    "  const c = String(code || \"\").toUpperCase();\n"
    "  if (!c) return \"\";\n"
    "  const map = locale === \"ru\" ? COUNTRIES_RU : COUNTRIES_EN;\n"
    "  return map[c] ?? COUNTRIES_EN[c] ?? c;\n"
    "}\n",
    encoding="utf-8",
)
print("written", OUT)
