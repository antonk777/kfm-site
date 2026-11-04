#!/usr/bin/env python3
"""Dump kfmaniacs MariaDB tables to gzipped JSON for the local Vue preview.

Run on the VPS (it has pymysql):
  python3 dump-db.py /tmp/kfm-dump
"""
import gzip
import json
import os
import sys

import pymysql

ENV_FILE = "/home/kfserver/.kfm-save.env"
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/kfm-dump"

TABLES = [
    "players",
    "prestige",
    "achievements",
    "bans",
    "site_map_sessions",
    "site_session_players",
    "site_player_map_clears",
    "site_player_map_clear_events",
    "site_daily_snapshot",
    "site_play_sessions",
]


def env_cfg(path):
    cfg = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    return cfg


def main():
    cfg = env_cfg(ENV_FILE)
    con = pymysql.connect(
        host=cfg.get("KFM_MYSQL_HOST", "127.0.0.1"),
        port=int(cfg.get("KFM_MYSQL_PORT", "3306")),
        user=cfg.get("KFM_MYSQL_USER", "kfm"),
        password=cfg.get("KFM_MYSQL_PASSWORD", ""),
        database=cfg.get("KFM_MYSQL_DB", "kfmaniacs"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    os.makedirs(OUT, exist_ok=True)
    for table in TABLES:
        cur = con.cursor()
        cur.execute("SELECT * FROM `%s`" % table)
        path = os.path.join(OUT, table + ".json.gz")
        n = 0
        with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
            fh.write("[")
            first = True
            for row in cur:
                if not first:
                    fh.write(",")
                fh.write(json.dumps(row, ensure_ascii=False, default=str))
                first = False
                n += 1
            fh.write("]")
        print("%s: %d rows -> %s" % (table, n, path), flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
