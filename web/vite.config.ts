import { defineConfig, loadEnv, type Plugin } from "vite";
import vue from "@vitejs/plugin-vue";
import type { IncomingMessage, ServerResponse } from "node:http";
import {
  createReadStream,
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { fileURLToPath } from "node:url";
import { join, resolve } from "node:path";

import { buildPlayer, getStore, loadStore, topPlayers } from "./scripts/data";

const ROOT = fileURLToPath(new URL(".", import.meta.url));
const PUBLIC_DIR = join(ROOT, "public");
const AVATAR_DIR = join(ROOT, ".cache", "avatars");
// Map previews are shared with the old site (site/maps) — not copied into public.
const MAPS_DIR = resolve(ROOT, "..", "maps");
const STEAM_WEB_API_KEY = loadEnv("development", ROOT, "").STEAM_WEB_API_KEY?.trim() || "";

// Names saved before the mod's SteamNameFixNew Wire() transport can contain
// control characters (the Linux server's SendText turned every char past
// U+00FF into 0x7F). Such a name is unrecoverable, so the display name falls
// back to the current Steam persona name.
const BROKEN_NAME = /[\u0000-\u001f\u007f]/;
const personaCache = new Map<string, { name: string; vanity: string; ts: number }>();

function stripCtl(s: string): string {
  return s.replace(/[\u0000-\u001f\u007f]/g, "").trim();
}

async function steamPersonas(ids: string[]): Promise<Map<string, string>> {
  const out = new Map<string, string>();
  const now = Date.now();
  const missing: string[] = [];
  for (const id of ids) {
    const hit = personaCache.get(id);
    if (hit && now - hit.ts < 3600_000) out.set(id, hit.name);
    else missing.push(id);
  }
  if (!missing.length || !STEAM_WEB_API_KEY) return out;
  try {
    for (let i = 0; i < missing.length; i += 100) {
      const chunk = missing.slice(i, i + 100);
      const res = await fetch(
        `https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key=${encodeURIComponent(
          STEAM_WEB_API_KEY,
        )}&steamids=${chunk.join(",")}`,
        { signal: AbortSignal.timeout(8000) },
      );
      if (!res.ok) continue;
      const data = (await res.json()) as {
        response?: { players?: { steamid?: string; personaname?: string; profileurl?: string }[] };
      };
      for (const p of data.response?.players ?? []) {
        if (!p.steamid || !p.personaname) continue;
        // /id/<vanity> in profileurl means a custom URL is set up.
        const vanity = /\/id\/([A-Za-z0-9_-]{2,32})\/?$/.exec(p.profileurl ?? "")?.[1] ?? "";
        personaCache.set(p.steamid, { name: p.personaname, vanity, ts: Date.now() });
        out.set(p.steamid, p.personaname);
      }
    }
  } catch {
    // Steam unavailable: keep the stored name.
  }
  return out;
}

// Steam custom URL name of a profile, "" when it has none. Cached 1 h.
async function steamVanity(steam: string): Promise<string> {
  if (!STEAM_WEB_API_KEY || !/^\d{16,20}$/.test(steam)) return "";
  await steamPersonas([steam]);
  return personaCache.get(steam)?.vanity ?? "";
}

async function patchBrokenName(target: { steamId: string; name: string }): Promise<void> {
  if (BROKEN_NAME.test(target.name) && /^\d{16,20}$/.test(target.steamId)) {
    const names = await steamPersonas([target.steamId]);
    const name = names.get(target.steamId);
    if (name) target.name = name;
  }
  target.name = stripCtl(target.name) || "(unknown)";
}

// ---------------------------------------------------------------------------
// Steam avatars. Prefer the official Web API (the same key the production
// server uses for its Steam checks); fall back to the profile XML scrape.
// ---------------------------------------------------------------------------
const avatarInFlight = new Map<string, Promise<Buffer | null>>();

async function fetchAvatar(steam: string): Promise<Buffer | null> {
  const file = join(AVATAR_DIR, `${steam}.jpg`);
  if (existsSync(file)) return readFileSync(file);

  let inflight = avatarInFlight.get(steam);
  if (inflight) return inflight;
  inflight = (async () => {
    try {
      let url = "";
      if (STEAM_WEB_API_KEY) {
        const res = await fetch(
          `https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key=${encodeURIComponent(
            STEAM_WEB_API_KEY,
          )}&steamids=${steam}`,
          { signal: AbortSignal.timeout(8000) },
        );
        if (res.ok) {
          const data = (await res.json()) as {
            response?: { players?: { avatarfull?: string }[] };
          };
          url = data.response?.players?.[0]?.avatarfull ?? "";
        }
      }
      if (!url) {
        const xml = await fetch(`https://steamcommunity.com/profiles/${steam}/?xml=1`, {
          headers: { "User-Agent": "Mozilla/5.0 (compatible; KFMWebAvatar/1.0)" },
          signal: AbortSignal.timeout(8000),
        }).then((r) => (r.ok ? r.text() : ""));
        for (const tag of ["avatarFull", "avatarMedium", "avatarIcon"]) {
          const m = new RegExp(
            `<${tag}>\\s*(?:<!\\[CDATA\\[(.*?)\\]\\]>|([^<]+?))\\s*</${tag}>`,
            "is",
          ).exec(xml);
          if (m) {
            url = (m[1] || m[2] || "").trim();
            break;
          }
        }
      }
      if (!url || !/^https:\/\//i.test(url)) return null;
      const imgRes = await fetch(url, {
        headers: { "User-Agent": "Mozilla/5.0 (compatible; KFMWebAvatar/1.0)" },
        signal: AbortSignal.timeout(8000),
      });
      if (!imgRes.ok) return null;
      const buf = Buffer.from(await imgRes.arrayBuffer());
      mkdirSync(AVATAR_DIR, { recursive: true });
      writeFileSync(file, buf);
      return buf;
    } catch {
      return null;
    } finally {
      avatarInFlight.delete(steam);
    }
  })();
  avatarInFlight.set(steam, inflight);
  return inflight;
}

function sendJson(res: ServerResponse, code: number, body: unknown): void {
  const data = JSON.stringify(body);
  res.statusCode = code;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.end(data);
}

function devApi(): Plugin {
  return {
    name: "kfm-dev-api",
    configureServer(server) {
      loadStore(ROOT, PUBLIC_DIR);
      server.middlewares.use((req: IncomingMessage, res: ServerResponse, next) => {
        const url = new URL(req.url ?? "/", "http://localhost");
        const { pathname } = url;

        // Map previews come straight from site/maps in dev; production serves
        // the same files from SITE_ROOT/maps.
        if (pathname.startsWith("/maps/") && pathname.endsWith(".jpg")) {
          const rel = decodeURIComponent(pathname.slice("/maps/".length));
          const file = resolve(MAPS_DIR, rel);
          if (file.startsWith(MAPS_DIR) && existsSync(file)) {
            res.statusCode = 200;
            res.setHeader("Content-Type", "image/jpeg");
            res.setHeader("Cache-Control", "public, max-age=3600");
            createReadStream(file).pipe(res);
            return;
          }
        }

        if (pathname === "/api/stats/servers" || pathname === "/api/stats/discord") {
          // Live data from the production stats API through the local SSH
          // tunnel (ssh -L 18765:127.0.0.1:8765 root@VPS). The landing shows
          // its usual "unavailable" state when the tunnel is down.
          fetch(`http://127.0.0.1:18765${pathname}`, { signal: AbortSignal.timeout(6000) })
            .then((r) => (r.ok ? (r.json() as Promise<unknown>) : null))
            .then((data) => {
              if (data) sendJson(res, 200, data);
              else sendJson(res, 502, { error: "tunnel unavailable" });
            })
            .catch(() => sendJson(res, 502, { error: "tunnel unavailable" }));
          return;
        }

        if (pathname === "/release.json") {
          // Companion release info from the production site.
          fetch("https://kfm.manul.lol/release.json", { signal: AbortSignal.timeout(8000) })
            .then((r) => (r.ok ? (r.json() as Promise<unknown>) : null))
            .then((data) => {
              if (data) sendJson(res, 200, data);
              else sendJson(res, 502, { error: "release unavailable" });
            })
            .catch(() => sendJson(res, 502, { error: "release unavailable" }));
          return;
        }

        if (pathname === "/api/dev/reload") {
          loadStore(ROOT, PUBLIC_DIR);
          sendJson(res, 200, { ok: true });
          return;
        }

        if (pathname === "/api/stats/top") {
          (async () => {
            try {
              const limit = Math.min(200, Math.max(1, Number(url.searchParams.get("limit")) || 50));
              const list = topPlayers(getStore(), limit);
              const broken = list.filter(
                (r) => BROKEN_NAME.test(r.name) && /^\d{16,20}$/.test(r.steamId),
              );
              if (broken.length) {
                const names = await steamPersonas(broken.map((r) => r.steamId));
                for (const r of broken) {
                  const name = names.get(r.steamId);
                  if (name) r.name = name;
                }
              }
              for (const r of list) r.name = stripCtl(r.name) || "(unknown)";
              sendJson(res, 200, list);
            } catch (err) {
              sendJson(res, 500, { error: String(err) });
            }
          })();
          return;
        }

        let m = pathname.match(/^\/api\/stats\/player\/(.+)$/);
        if (m) {
          (async () => {
            try {
              const payload = buildPlayer(getStore(), decodeURIComponent(m[1]));
              if (payload.found) {
                await patchBrokenName(payload);
                if (payload.steamId) payload.vanity = (await steamVanity(payload.steamId)) || null;
              }
              sendJson(res, 200, payload);
            } catch (err) {
              sendJson(res, 500, { error: String(err) });
            }
          })();
          return;
        }

        m = pathname.match(/^\/api\/stats\/resolve\/([A-Za-z0-9_-]{2,32})$/);
        if (m) {
          if (!STEAM_WEB_API_KEY) {
            sendJson(res, 400, { error: "no steam api key" });
            return;
          }
          fetch(
            `https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/?key=${encodeURIComponent(
              STEAM_WEB_API_KEY,
            )}&vanityurl=${encodeURIComponent(m[1])}`,
            { signal: AbortSignal.timeout(8000) },
          )
            .then((r) =>
              r.ok
                ? (r.json() as Promise<{ response?: { steamid?: string; success?: number } }>)
                : null,
            )
            .then((data) => {
              const steamid = data?.response?.steamid;
              if (data?.response?.success === 1 && steamid) {
                sendJson(res, 200, { steamid: String(steamid) });
              } else {
                sendJson(res, 404, { error: "vanity not found" });
              }
            })
            .catch(() => sendJson(res, 502, { error: "steam unavailable" }));
          return;
        }

        if (pathname === "/api/stats/avatar/full") {
          const steam = ((url.searchParams.get("steam") || "") as string).trim();
          if (!/^[0-9]{16,20}$/.test(steam)) {
            sendJson(res, 400, { error: "steam id required" });
            return;
          }
          fetchAvatar(steam)
            .then((buf) => {
              if (!buf) {
                res.statusCode = 404;
                res.end("no avatar");
                return;
              }
              res.statusCode = 200;
              res.setHeader("Content-Type", "image/jpeg");
              res.setHeader("Cache-Control", "public, max-age=86400");
              res.end(buf);
            })
            .catch(() => {
              res.statusCode = 500;
              res.end("avatar error");
            });
          return;
        }

        m = pathname.match(/^\/api\/avatar\/([0-9]{16,20})$/);
        if (m) {
          fetchAvatar(m[1])
            .then((buf) => {
              if (!buf) {
                res.statusCode = 404;
                res.end("no avatar");
                return;
              }
              res.statusCode = 200;
              res.setHeader("Content-Type", "image/jpeg");
              res.setHeader("Cache-Control", "public, max-age=86400");
              res.end(buf);
            })
            .catch(() => {
              res.statusCode = 500;
              res.end("avatar error");
            });
          return;
        }

        next();
      });
    },
  };
}

export default defineConfig({
  root: ROOT,
  plugins: [vue(), devApi()],
  server: {
    port: 5173,
    strictPort: false,
  },
  build: {
    outDir: "dist",
  },
});
