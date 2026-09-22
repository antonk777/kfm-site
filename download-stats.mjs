// Count Companion downloads from Caddy JSON access logs.
// Usage:
//   SITE_LOG=/var/log/caddy/kfm.manul.lol.log node download-stats.mjs
//   node download-stats.mjs /var/log/caddy/kfm.manul.lol.log

import { createReadStream } from "node:fs";
import { createInterface } from "node:readline";

const logPath =
  process.argv[2] ||
  process.env.SITE_LOG ||
  "/var/log/caddy/kfm.manul.lol.log";

const counts = new Map();
let total = 0;
let lines = 0;
let bad = 0;

const rl = createInterface({
  input: createReadStream(logPath, { encoding: "utf8" }),
  crlfDelay: Infinity,
});

for await (const line of rl) {
  if (!line.trim()) continue;
  lines++;
  let row;
  try {
    row = JSON.parse(line);
  } catch {
    bad++;
    continue;
  }
  const status = Number(row.status ?? row.status_code ?? 0);
  if (status < 200 || status >= 400) continue;
  const uri =
    row.request?.uri ||
    row.request?.url ||
    row.uri ||
    row.url ||
    "";
  const path = String(uri).split("?")[0];
  if (!/^\/(download|KFM-Companion[^/]*\.exe)$/i.test(path)) continue;
  total++;
  counts.set(path, (counts.get(path) || 0) + 1);
}

const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]);
console.log(JSON.stringify({ log: logPath, lines, parseErrors: bad, total, byPath: Object.fromEntries(sorted) }, null, 2));
