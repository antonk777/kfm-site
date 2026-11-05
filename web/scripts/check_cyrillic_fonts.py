"""Check which Google Fonts families offer a Cyrillic subset (css2 unicode-range)."""
import re
import urllib.request

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
}

CANDIDATES = [
    "D-DIN",
    "D-DIN Condensed",
    "Barlow Condensed",
    "Archivo Narrow",
    "Fira Sans Condensed",
    "IBM Plex Sans Condensed",
    "Saira Condensed",
    "Tektur",
    "Rubik",
    "Oswald",
    "Roboto Condensed",
    "PT Sans Narrow",
    "Golos Text",
    "Onest",
    "Geologica",
]


def subsets(family: str) -> list[str]:
    url = f"https://fonts.googleapis.com/css2?family={family.replace(' ', '+')}&display=swap"
    try:
        css = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read().decode()
    except Exception as exc:  # noqa: BLE001
        return [f"ERR {exc}"]
    return re.findall(r"/\*\s*([\w-]+)\s*\*/", css)


for fam in CANDIDATES:
    names = subsets(fam)
    has_cyr = any("cyrillic" in s for s in names)
    print(f"{fam:26} cyrillic={'YES' if has_cyr else 'no ':3}  subsets={','.join(names[:8])}")
