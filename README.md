# KF-Maniacs site on Caddy

Public download page for **KFM Companion** at [https://kf-maniacs.com/](https://kf-maniacs.com/) (the old https://kfm.manul.lol/ serves the same site).

| Piece | Role |
|-------|------|
| `index.html` | Landing page, EN/RU/ZH/ES/PT, server monitor, changelog |
| `maps/*.jpg` | Map previews for the monitor, from `tools/gen_map_shots.py` in kfm-mut |
| `fetch-companion.mjs` | Pulls latest `.exe` from private `antonk777/KFMLauncher` releases |
| `release.json` | Written at sync time; page reads `tag` / `file` / changelog |
| `Caddyfile` | TLS, static files, forced download headers, JSON access log |
| `/download` | Stable Companion URL |
| `sync-now.sh` | Forced-command entry for release sync |
| GitHub Action on `KFMLauncher` | On every Release → SSH → `sync-now.sh` (instant) |

## Instant release sync

Publishing (or editing) a Release in `antonk777/KFMLauncher` runs
`.github/workflows/sync-download-site.yml`, which SSHs to the VPS and refreshes
the Companion binary. The daily systemd timer remains only as a backup.

One-time wiring (already done on the live host if you used `install-release-hook.sh`):

1. Deploy key with forced command → `/opt/kfm-site/sync-now.sh`
2. Secrets on `KFMLauncher`: `KFM_SITE_HOST`, `KFM_SITE_USER`, `KFM_SITE_DEPLOY_KEY`

Manual sync: `sudo bash /opt/kfm-site/sync-now.sh`

## One-time host setup

DNS (Dynadot): `kf-maniacs.com`, `www.kf-maniacs.com` and `kfm.manul.lol` **A → VPS IP**, no AAAA, no forwarding/parking. Caddy gets the certificates itself.
Until then: `http://SITE_IP/`.

```bash
git clone https://github.com/antonk777/kfm-site.git /opt/kfm-site
cd /opt/kfm-site
cp kfm-site.env.example /etc/kfm-site.env
sudo nano /etc/kfm-site.env && sudo chmod 600 /etc/kfm-site.env
set -a; source /etc/kfm-site.env; set +a
sudo -E INSTALL_CADDY=1 bash deploy.sh
sudo bash install-release-hook.sh   # deploy key + print pubkey / secret hints
sudo cp systemd/kfm-site-sync.service systemd/kfm-site-sync.timer /etc/systemd/system/
sudo systemctl enable --now kfm-site-sync.timer
```

## Server monitor on the landing page

The first block of `index.html` lists the panel servers (Meat Grinder, Bloodbath):
map preview, map name, difficulty, wave, players, a `steam://run/1250//<ip>:<game port>`
button (Steam starts the game with the address on its command line; `steam://connect`
fails for these servers) and a collapsible player list (names and perks, no steam ids). It polls the
public `GET /api/stats/servers` every 10 s; the data is the same live push that feeds
the `/statistics/` live card (`stale` = no push within 45 s, the card dims).

The address line selects only the `ip:port`; a click copies it to the clipboard and
shows a short "Copied" tooltip.

## Steam listing check on /statistics

The live card on `/statistics/` has a "Браузер Steam" line: whether the server is in
the list Steam hands to the in-game and Steam-client browsers (`live.steam.listed`,
also in `liveAll`), what Steam sees (players, map) and when it was checked.
`stats-server.py` asks `IGameServersService/GetServerList` for this host once every
10 minutes (`STEAM_POLL_SEC`), never on request, and keeps the last answer through
errors; it needs `STEAM_WEB_API_KEY` in `/etc/kfm-site.env`, without it the line is
absent. A server that answers on its game port but is "missing" here is the Steam
query port (28852 + game port - 7707) being closed in the host firewall, see
`server-scripts/kf-firewall.sh`. `GET /api/stats/admin/status` returns the raw poll
(`steam.listed`, `steam.error`). The public `/api/stats/servers` does not carry it.

## Discord card on the landing page

Under the server cards the landing page shows the KF-Maniacs Discord
(`discord.gg/MJXsav9DFC`): name and icon, members online and in total, and a join
button. `stats-server.py` asks Discord once a minute (`DISCORD_POLL_SEC`) for everyone
and serves the last answer as the public `/api/stats/discord` (`checked`, `online`,
`members`, `widget`, `onlineMembers`, `stale`); the page polls it every 60 s. The counts
come from the public invite lookup, so no token or bot is needed. The online members'
names, avatars and games appear once the server widget is on in Discord (Server
Settings → Widget → Enable Server Widget); until then `widget.json` answers 403 and the
card shows the counts only. `DISCORD_INVITE` in `/etc/kfm-site.env` changes the invite
code (default `MJXsav9DFC`; empty turns the polling off, the card keeps its join
button). The last poll is in `GET /api/stats/admin/status` (`discord.ok`,
`discord.error`); errors also go to `journalctl -u kfm-stats`.

Map previews are `maps/<map name in lower case>.jpg` (512x288, 16:9), the screenshot each
map's `LevelSummary` names, decoded straight from the `.rom`. Regenerate after new maps
land on the servers (in kfm-mut):

```bash
python -I tools/gen_map_shots.py --remote   # runs on the game server against its Maps, fetches the JPEGs
python -I tools/gen_map_shots.py            # same for the local KF install
```

A map without a file shows the caption on a plain background.

## Download counts

Shown on the secret `/statistics/` dashboard (from Caddy JSON access logs).
CLI still works:

```bash
sudo SITE_LOG=/var/log/caddy/kfm.manul.lol.log node /opt/kfm-site/download-stats.mjs
```

## Secret `/statistics/` dashboard

Player sessions (who / how long / perk / map / win-loss / loss wave) land in SQLite
via `stats-server.py`. Charts mirror Daily Players (peak + unique) and also show
**D1/D7 retention** and **average total playtime per player per day**.

No auth — unlisted URL only (do not link it from the public page).

**Admins:** the live card and a player's own session list (and map clears) include
DB admins. Daily unique, peak, retention, average playtime and the pies skip
players whose `players.admin` is non-zero.

1. `sudo -E SKIP_FETCH=1 bash deploy.sh` (starts `kfm-stats.service`, reloads Caddy)
2. Open `https://kf-maniacs.com/statistics/`

### Game server push (Unreal → site)

In the KF `*.ini` (section for the live package name, e.g. `KFManiacsMod` or `KFManiacsModRevN`):

```ini
[KFManiacsMod.KFMStatsHttpClientNew]
bEnableStatsPush=True
StatsHost=127.0.0.1
StatsPort=8765
StatsPath=/api/stats/ingest
StatsServerName=meatgrinder
```

Same machine as the site: keep `127.0.0.1:8765`. Remote dedicated server (no TLS in
UE TcpLink): `StatsHost=<SITE_IP>`, `StatsPort=80`, path unchanged — uses the
plain-HTTP Caddy site.

## Token

`COMPANION_GITHUB_TOKEN` needs **Contents: Read** on `antonk777/KFMLauncher`.
