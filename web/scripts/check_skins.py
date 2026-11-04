import gzip
import json
from pathlib import Path
import collections

DATA = Path(__file__).resolve().parents[1] / "data"
players = json.loads(gzip.open(DATA / "players.json.gz", "rt", encoding="utf-8").read())
sp = json.loads(gzip.open(DATA / "site_session_players.json.gz", "rt", encoding="utf-8").read())
by_steam = {p["steam_id"]: p for p in players}
recent = list(dict.fromkeys(r["steam_id"] for r in sp))

print("--- recent-era players: last_skin_name / skins / skins_info columns ---")
shown = 0
for sid in recent:
    p = by_steam.get(sid)
    if not p:
        continue
    skin = p["last_skin_name"].strip()
    owned = p["skins"].strip()
    info = p["skins_info"].strip()
    if shown < 12:
        print(repr(p["last_player_name"]), "skin=", repr(skin), "skins=", repr(owned[:80]), "skins_info=", repr(info[:80]))
        shown += 1
print("---")
skins_col = collections.Counter()
info_col = collections.Counter()
for sid in recent:
    p = by_steam.get(sid)
    if not p:
        continue
    skins_col["nonempty" if p["skins"].strip() else "empty"] += 1
    info_col["nonempty" if p["skins_info"].strip() else "empty"] += 1
print("recent players: skins col nonempty:", skins_col["nonempty"], "empty:", skins_col["empty"])
print("recent players: skins_info col nonempty:", info_col["nonempty"], "empty:", info_col["empty"])
# show some nonempty skins values
shown = 0
for sid in recent:
    p = by_steam.get(sid)
    if not p:
        continue
    if p["skins"].strip() and shown < 6:
        print("skins sample:", repr(p["skins"][:120]), "| info:", repr(p["skins_info"][:120]))
        shown += 1
