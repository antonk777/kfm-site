# KF-Maniacs site on Caddy

Public download page for **KFM Companion** at [https://kf-maniacs.com/](https://kf-maniacs.com/) (the old https://kfm.manul.lol/ serves the same site).

| Piece | Role |
|-------|------|
| `web/` | Vue 3 SPA (landing, `/players`, profiles); `npm run build` → `web/dist` |
| `web/dist` | Public document root (gitignored); shipped by `deploy-site.py` / built by `deploy.sh` |
| `maps/*.jpg` | Map previews for the monitor, from `tools/gen_map_shots.py` in kfm-mut |
| `fetch-companion.mjs` | Pulls latest `.exe` from private `antonk777/KFMLauncher` releases |
| `release.json` | Written at sync time; page reads `tag` / `file` / changelog |
| `Caddyfile` | TLS, SPA fallback, forced download headers, JSON access log |
| `/download` | Stable Companion URL |
| `sync-now.sh` | Forced-command entry for release sync |
| GitHub Action on `KFMLauncher` | On every Release → SSH → `sync-now.sh` (instant) |

## Daily change log summaries

The website change log shows one short editorial summary per Moscow calendar
day, with all detailed notes inside a native expandable section. The homepage
previews the three most recent days with highlights. Days with only fixes or
removals, and older unsummarized days, keep their full log without summary text.

Summaries are maintained by the changelog skill in
`tools/changelog_summaries.json` in the parent repository. The initial backfill
starts on 8 November 2026. `python tools/changelog.py summarize <file.json>`
replaces a day's summary in all site languages; `check` detects missing or stale
reviews. `deploy.bat` publishes summaries with the existing notes in
`/mod-changelog.json`. They are not bundled into the site build.

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

The first block of the Vue landing (`web/src/views/LandingPage.vue`) lists the panel
servers (Meat Grinder, Bloodbath): map preview, map name, difficulty, wave, players,
a `steam://run/1250//<ip>:<game port>` button (Steam starts the game with the address
on its command line; `steam://connect` fails for these servers) and a collapsible
player list (names and perks, no steam ids). It polls the public `GET /api/stats/servers`
every 10 s; the data is the same live push that feeds the `/statistics/` live card
(`stale` = no push within 45 s, the card dims).

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

The shareable URL [https://kf-maniacs.com/discord](https://kf-maniacs.com/discord)
redirects to `https://discord.gg/MJXsav9DFC`. Caddy handles `/discord` and
`/discord/` with HTTP 302 so the destination can be updated without a cached
permanent redirect. Update the destination in `Caddyfile` if the invite changes.

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

Maps without embedded previews have manually supplied screenshots in `maps/`:

| Map | Preview source |
| --- | --- |
| Atlas | [Steam Workshop preview](https://steamcommunity.com/sharedfiles/filedetails/?id=98493090) |
| High Rise | [Steam Workshop preview](https://steamcommunity.com/sharedfiles/filedetails/?id=115212469) |
| Defence Snow KFM | Local in-game capture of `KF-Defence-Snow_KFM`, without HUD (17 Nov 2026) |
| Meow Night | Local in-game capture of `KF-Meow_Night`, without HUD (17 Nov 2026) |

Keep both `kf-highrise[beta1].jpg` (live map filename) and
`kf-highrise_beta1_.jpg` (older session records). Retain previews of removed maps,
including `kf-prison_extended.jpg`, because past sessions still display them.
The generator leaves manually supplied images alone when a map has no embedded
preview. Overrun's embedded screenshots are named `lvlprev1` through `lvlprev4`;
`tools/gen_map_shots.py` recognizes that prefix so it does not choose a wall texture.

## Steam login in the header

The Vue header has a Steam button (`GET /api/stats/steam/login`). It is Steam
OpenID: the player approves on steamcommunity.com, `stats-server.py` checks the
assertion, sets an HttpOnly `kfm_player` cookie (14 days), and redirects to
`/players/<custom URL or SteamID64>`. While that cookie is valid the header
shows **My profile** (from `GET /api/stats/steam/me`) and a logout
(`POST /api/stats/steam/logout`). Accounts with `players.admin` set also gain
access to `/statistics` and `/admin/bans`; ordinary Steam accounts do not.

`SITE_PUBLIC_URL` (default `https://kf-maniacs.com`, no trailing path) is the
OpenID realm and return URL. The cookie is signed with `STATS_ADMIN_SECRET`, or
with `STEAM_WEB_API_KEY` when that secret is unset. If neither is set, the login
route answers 503. Persona name and custom URL reuse the existing Web API
lookup, so a missing key still logs the player in and sends them to
`/players/<SteamID64>`.

## Ban management for DB admins

Steam accounts with `players.admin` set see **Ban management** in the account
menu at `/admin/bans`. The page searches by player name, SteamID64 or account ID,
filters active/expired/unbanned records, and supports timed or permanent bans,
editing the reason/expiry, and unbanning with confirmation. Banned player profiles
show DB admins an active-ban panel with a link to that player's filtered list.
English and Russian are provided; other site languages use the English fallback.

The API uses the same `bans` table as perkhost. Existing history is retained;
website changes additionally record the authenticated admin and before/after values
in `site_ban_audit`, created on stats-server startup. Writes are transactional and
reject stale edits, duplicate active bans, and bans against DB admins. Each request
checks the signed Steam cookie and current database admin flag; writes also require
JSON and the `X-KFM-Admin` header. No additional credentials are configured.

A website ban does not kick an already connected player. It takes effect when
the game next checks their account. Dates entered on the page use the browser's
local time zone and are stored in UTC. Deploy both the Nuxt app and stats-server
with `python deploy-site.py` so the new routes and audit table are available.

Regression checks: `python -B -m unittest discover -s site/tests -v` from the
parent repository, and `npm run build` in `site/web`. The test database is an
isolated SQLite adapter; MariaDB row-lock semantics are not covered by that suite.

## Visits (Umami)

Page views stay on this machine. Umami and its Postgres run in Docker and listen
on `127.0.0.1:9477` only. Caddy proxies two public paths to it, `/kf.js` and
`/api/kf`. The dashboard is not on the public site.

`deploy.sh` and `deploy-site.py` start it (`umami/up.sh`). The first run writes
`/etc/kfm-umami.env` (mode 600) with the database password. Keep that file: a
later change to `POSTGRES_PASSWORD` does not update the existing volume.

Open the dashboard through an SSH tunnel:

```bash
ssh -L 9477:127.0.0.1:9477 root@85.192.30.108
```

Then http://127.0.0.1:9477. The first login is **admin** / **umami**. Change
that password, add a website for `kf-maniacs.com`, and put the website UUID in
`/etc/kfm-site.env`:

```bash
UMAMI_WEBSITE_ID=<uuid from the dashboard>
```

The next site deploy writes it to `SITE_ROOT/umami-website-id`. The Vue app
loads the tracker only when that file is a UUID, and only on `kf-maniacs.com`
and `kfm.manul.lol`. Client-side moves (`/players/…`, `/sessions/…`) are
recorded by the tracker. Paths are stored, including `/players/<steam id>`.
Query strings are not. An empty `UMAMI_WEBSITE_ID` removes the file and the
tracker stays off.

Umami is started with telemetry, the update check, and its favicon lookups
turned off (`PRIVATE_MODE`, `DISABLE_TELEMETRY`, `DISABLE_UPDATES`).

## Download counts

`/download` and `KFM-Companion*.exe` are served by `stats-server.py`. Each GET
that starts the file inserts a row in `site_companion_downloads`. The
`/statistics/` dashboard reads that table.

## Server Management

Player sessions (who / how long / perk / map / win-loss / loss wave) land in SQLite
via `stats-server.py`. Charts mirror Daily Players (peak + unique) and also show
**D1/D7 retention** and **average total playtime per player per day**.

Server Management at `/statistics/` requires Steam login and `players.admin` in
the database. DB admins see its link in the account menu. The data APIs check
the same authorization.

**Admins:** DB admins count in every public stat the same as players (unique,
peak, retention, playtime, pies, session names, `player_count`).

1. `sudo -E SKIP_FETCH=1 bash deploy.sh` (starts `kfm-stats.service`, reloads Caddy)
2. Open `https://kf-maniacs.com/statistics/`

### Staging

`deploy.bat staging` builds the current workspace and deploys it to **Staging**
at `193.5.64.167:7727` on the German VPS. Revisions use their own sequence
(`R1S`, `R2S`, etc.) and FastDL. The deployment restarts only Staging.

Staging starts with a copy of Condemned's maps and settings and uses the same
perkhost and MariaDB for player progression. It has a separate local game tree.
Find its card in Server Management. Join by entering `open 193.5.64.167:7727`
in the Killing Floor console. Staging uses direct-IP access without a password.
Its launcher disables Steam master-server advertising while retaining Steam
authentication for player progression.
The mod adds a Staging favorite after perkhost confirms the player's DB admin flag.
Debug mode is always on. Staging sends live status to Server Management only,
and its matches, player sessions, and daily counts are excluded from site stats.

To provision Staging on the German VPS, run `server-scripts/install-staging.sh`
as root with the sibling scripts present. Register its panel row on the hub and
restart `kfm-stats.service` to load it.

```text
staging|Staging|193.5.64.167|7727|7728|staging|kfserver@10.10.0.3|DE|DE
```

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
