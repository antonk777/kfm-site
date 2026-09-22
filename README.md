# KF-Maniacs site on Caddy

Public download page for **KFM Companion** at [https://kfm.manul.lol/](https://kfm.manul.lol/).

| Piece | Role |
|-------|------|
| `index.html` | Landing page, EN/RU/ZH/ES/PT, changelog |
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

DNS: `kfm.manul.lol` **A → VPS IP**, Cloudflare **DNS only** (grey cloud) for Let's Encrypt.
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

1. `sudo -E SKIP_FETCH=1 bash deploy.sh` (starts `kfm-stats.service`, reloads Caddy)
2. Open `https://kfm.manul.lol/statistics/`

### Game server push (Unreal → site)

In the KF `*.ini` (section for the live package name, e.g. `KFManiacsMod` or `KFManiacsModRevN`):

```ini
[KFManiacsMod.KFMStatsHttpClientNew]
bEnableStatsPush=True
StatsHost=127.0.0.1
StatsPort=8765
StatsPath=/api/stats/ingest
StatsServerName=main
```

Same machine as the site: keep `127.0.0.1:8765`. Remote dedicated server (no TLS in
UE TcpLink): `StatsHost=<SITE_IP>`, `StatsPort=80`, path unchanged — uses the
plain-HTTP Caddy site.

## Token

`COMPANION_GITHUB_TOKEN` needs **Contents: Read** on `antonk777/KFMLauncher`.
