// Dev data layer: reads the local DB snapshot (web/data/*.json.gz), indexes it
// and builds the same player payload the production stats-server will serve.
import { existsSync, readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { join, resolve } from "node:path";

import type {
  AchievementInfo,
  ClearDifficulty,
  ClearInfo,
  PerkInfo,
  PlayerPayload,
  RecentSessionInfo,
  SessionDetailInfo,
  SessionDetailPlayer,
  SessionInfo,
  TopPlayerEntry,
} from "../src/api";
import {
  BASELINE_SLOT_PERK,
  PERKS,
  STATS,
  effectiveStat,
  levelFromCounters,
  perkProgressAt,
  type PerkDef,
  type PrestigeRow,
} from "../src/lib/perks";
import { ACHIEVEMENTS } from "../src/data/achievements";
import { BRUTAL_RENAMED_AT, difficultyBucket, prettyMap } from "../src/lib/format";
import { SESSIONS_PUBLIC, SESSIONS_VISIBLE_SINCE } from "../src/lib/flags";

type Row = Record<string, unknown>;

const ERA_START = "2026-01-01";

// Players active since the 2026 server relaunch: last_time_joined is set to
// NOW() by perkhost on every join, so this is the reliable "played in the
// current era" signal (the old 2010s accounts have no 2026 join).
function isEraPlayer(p: Row): boolean {
  return str(p.last_time_joined) >= ERA_START;
}

// Retired slot ids from before the rename (same map as stats-server SERVER_ALIASES).
const SERVER_ALIASES: Record<string, string> = {
  normal: "meatgrinder",
  vote: "bloodbath",
  hoe: "bloodbath",
};
const SERVER_LABELS: Record<string, string> = {
  meatgrinder: "Meat Grinder",
  hard: "Hard",
  suicidal: "Suicidal",
  bloodbath: "Bloodbath",
};
// Live slots plus retired ids. Same set stats-server uses for «Все».
const KNOWN_SERVERS = new Set([
  "meatgrinder",
  "hard",
  "suicidal",
  "bloodbath",
  ...Object.keys(SERVER_ALIASES),
]);

function serverLabel(raw: unknown): string {
  const s = str(raw).trim().toLowerCase();
  if (!s) return "";
  const canon = SERVER_ALIASES[s] ?? s;
  return SERVER_LABELS[canon] ?? canon;
}

// Game ports match stats-server SLOT_PORTS. Hard has none.
const SERVER_PORTS: Record<string, number> = {
  meatgrinder: 7717,
  suicidal: 7727,
  bloodbath: 7737,
};
const KF_APP_ID = 1250;

function sessionJoinUrl(raw: unknown, outcome: string, endedAt: number): string {
  if (outcome !== "playing" || endedAt > 0) return "";
  const canon = SERVER_ALIASES[str(raw).trim().toLowerCase()] ?? str(raw).trim().toLowerCase();
  const port = SERVER_PORTS[canon] ?? 0;
  if (port <= 0) return "";
  const host = process.env.KFM_PUBLIC_HOST || process.env.SITE_IP || "85.192.30.108";
  return `steam://run/${KF_APP_ID}//${host}:${port}`;
}

function num(v: unknown, d = 0): number {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : d;
}

function str(v: unknown): string {
  return v == null ? "" : String(v);
}

interface Store {
  publicDir: string;
  mapsDir: string;
  playersBySteam: Map<string, Row>;
  playersById: Map<number, Row>;
  prestigeByAccount: Map<number, Map<number, Row>>;
  achByAccount: Map<number, Map<number, number>>;
  bansByAccount: Map<number, Row[]>;
  sessionsBySteam: Map<string, Row[]>;
  playersBySession: Map<number, Row[]>;
  clearsBySteam: Map<string, Row[]>;
  clearEventsBySteam: Map<string, Row[]>;
  sessionByKey: Map<string, Row>;
  mapSessionById: Map<number, Row>;
  scoreRank: Map<number, number>; // account id -> rank among non-admin players
  rankedCount: number;
}

let store: Store | null = null;

function readTable(dataDir: string, name: string): Row[] {
  const path = join(dataDir, `${name}.json.gz`);
  const raw = gunzipSync(readFileSync(path));
  return JSON.parse(raw.toString("utf8")) as Row[];
}

function readTableMaybe(dataDir: string, name: string): Row[] {
  const path = join(dataDir, `${name}.json.gz`);
  if (!existsSync(path)) return [];
  return readTable(dataDir, name);
}

export function loadStore(rootDir: string, publicDir: string): Store {
  const dataDir = join(rootDir, "data");
  const players = readTable(dataDir, "players");
  const prestige = readTable(dataDir, "prestige");
  const achievements = readTable(dataDir, "achievements");
  const bans = readTable(dataDir, "bans");
  const mapSessions = readTable(dataDir, "site_map_sessions");
  const sessionPlayers = readTable(dataDir, "site_session_players");
  const clears = readTable(dataDir, "site_player_map_clears");
  const clearEvents = readTableMaybe(dataDir, "site_player_map_clear_events");

  const playersBySteam = new Map<string, Row>();
  const playersById = new Map<number, Row>();
  for (const p of players) {
    const id = num(p.id);
    playersById.set(id, p);
    const steam = str(p.steam_id).trim();
    if (steam && !playersBySteam.has(steam)) playersBySteam.set(steam, p);
  }

  const prestigeByAccount = new Map<number, Map<number, Row>>();
  for (const r of prestige) {
    const acc = num(r.account_id);
    if (!prestigeByAccount.has(acc)) prestigeByAccount.set(acc, new Map());
    prestigeByAccount.get(acc)!.set(num(r.perk), r);
  }

  const achByAccount = new Map<number, Map<number, number>>();
  for (const r of achievements) {
    const acc = num(r.account_id);
    if (!achByAccount.has(acc)) achByAccount.set(acc, new Map());
    achByAccount.get(acc)!.set(num(r.ach_index), num(r.progress));
  }

  const bansByAccount = new Map<number, Row[]>();
  for (const r of bans) {
    const acc = num(r.account_id);
    if (!bansByAccount.has(acc)) bansByAccount.set(acc, []);
    bansByAccount.get(acc)!.push(r);
  }

  const mapSessionById = new Map<number, Row>();
  const sessionByKey = new Map<string, Row>();
  for (const s of mapSessions) {
    mapSessionById.set(num(s.id), s);
    const key = str(s.session_key);
    if (key) sessionByKey.set(key, s);
  }

  const sessionsBySteam = new Map<string, Row[]>();
  const playersBySession = new Map<number, Row[]>();
  for (const sp of sessionPlayers) {
    const steam = str(sp.steam_id).trim();
    if (steam) {
      if (!sessionsBySteam.has(steam)) sessionsBySteam.set(steam, []);
      sessionsBySteam.get(steam)!.push(sp);
    }
    const sid = num(sp.session_id);
    if (!playersBySession.has(sid)) playersBySession.set(sid, []);
    playersBySession.get(sid)!.push(sp);
  }

  const clearsBySteam = new Map<string, Row[]>();
  for (const c of clears) {
    const steam = str(c.steam_id).trim();
    if (!steam) continue;
    if (!clearsBySteam.has(steam)) clearsBySteam.set(steam, []);
    clearsBySteam.get(steam)!.push(c);
  }

  const clearEventsBySteam = new Map<string, Row[]>();
  for (const e of clearEvents) {
    const steam = str(e.steam_id).trim();
    if (!steam) continue;
    if (!clearEventsBySteam.has(steam)) clearEventsBySteam.set(steam, []);
    clearEventsBySteam.get(steam)!.push(e);
  }

  // Rank among players who played since the 2026 relaunch (admins included —
  // the leaderboard shows them too).
  const scored = players
    .filter((p) => isEraPlayer(p) && num(p.score) > 0)
    .map((p) => ({ id: num(p.id), score: num(p.score) }))
    .sort((a, b) => b.score - a.score || a.id - b.id);
  const scoreRank = new Map<number, number>();
  scored.forEach((s, i) => scoreRank.set(s.id, i + 1));

  store = {
    publicDir,
    // Map previews live with the old site (site/maps), not in public/.
    mapsDir: resolve(publicDir, "..", "..", "maps"),
    playersBySteam,
    playersById,
    prestigeByAccount,
    achByAccount,
    bansByAccount,
    sessionsBySteam,
    playersBySession,
    clearsBySteam,
    clearEventsBySteam,
    sessionByKey,
    mapSessionById,
    scoreRank,
    rankedCount: scored.length,
  };
  return store;
}

export function getStore(): Store {
  if (!store) throw new Error("data store not loaded");
  return store;
}

function findPlayer(s: Store, id: string): Row | null {
  const trimmed = id.trim();
  if (/^\d{16,20}$/.test(trimmed)) return s.playersBySteam.get(trimmed) ?? null;
  const n = Number(trimmed);
  if (Number.isInteger(n) && n > 0) return s.playersById.get(n) ?? null;
  return null;
}

function prestigesFor(s: Store, accountId: number): (PrestigeRow | undefined)[] {
  const rows = s.prestigeByAccount.get(accountId);
  const out: (PrestigeRow | undefined)[] = new Array(7).fill(undefined);
  if (!rows) return out;
  for (const [perk, r] of rows) {
    if (perk < 0 || perk > 6) continue;
    out[perk] = {
      perk,
      rank: num(r.rank),
      baselineA: num(r.baseline_a),
      baselineB: num(r.baseline_b),
      since: str(r.prestiged_at) || null,
    };
  }
  return out;
}

function baselinesOf(prestiges: (PrestigeRow | undefined)[]): (number | undefined)[] {
  const out: (number | undefined)[] = new Array(9).fill(undefined);
  BASELINE_SLOT_PERK.forEach((slot, idx) => {
    const p = prestiges[slot.perk];
    if (!p) return;
    out[idx] = slot.col === "a" ? p.baselineA : p.baselineB;
  });
  return out;
}

const PERK_INDEX_BY_NAME: Record<string, number> = {
  fieldmedic: 0,
  supportspecialist: 1,
  sharpshooter: 2,
  commando: 3,
  berserker: 4,
  firebug: 5,
  demolition: 6,
  demolitions: 6,
};

// Level of the perk a live player is on, same numbers as their profile.
// perkIdx wins; the name covers a monitor payload that only has the perk text.
export function livePerkStanding(
  steamId: string,
  perkIdx: number,
  perkName: string,
): { level: number; prestigeRank: number } | null {
  if (!/^\d{16,20}$/.test(steamId)) return null;
  const player = getStore().playersBySteam.get(steamId);
  if (!player) return null;
  let idx = perkIdx;
  if (!Number.isInteger(idx) || idx < 0 || idx > 6) {
    idx = PERK_INDEX_BY_NAME[perkName.toLowerCase().replace(/[\s_]+/g, "")] ?? -1;
  }
  if (idx < 0) return null;
  const perk = buildPerks(player, prestigesFor(getStore(), num(player.id))).find((row) => row.index === idx);
  if (!perk) return null;
  return { level: perk.level, prestigeRank: perk.prestigeRank };
}

function buildPerks(player: Row, prestiges: (PrestigeRow | undefined)[]): PerkInfo[] {
  const baselines = baselinesOf(prestiges);
  return PERKS.map((def: PerkDef) => {
    const cur = def.statIdx.map((statIdx, slot) =>
      effectiveStat(def, slot, num(player[STATS[statIdx]?.key ?? ""] ?? 0, 0), prestiges[def.index], baselines),
    );
    const level = levelFromCounters(def, cur);
    const progress = perkProgressAt(def, level, cur);
    const prestige = prestiges[def.index];
    const stats = def.statIdx.map((statIdx, slot) => {
      const key = STATS[statIdx]?.key ?? "";
      const lastReq = def.req[slot][level - 1] ?? 0;
      const req = def.req[slot][level];
      const c = cur[slot];
      let last = lastReq >= c ? 0 : lastReq;
      if (req <= last) last = req;
      const p = req <= 0 ? 1 : Math.max(0, Math.min(1, (c - last) / Math.max(1, req - last)));
      return {
        key,
        value: num(player[key] ?? 0),
        effective: c,
        lastReq,
        req,
        progress: p,
      };
    });
    return {
      index: def.index,
      id: def.id,
      level,
      progress,
      prestigeRank: prestige?.rank ?? 0,
      prestigeSince: prestige?.since ?? null,
      stats,
    };
  });
}

function activeBan(s: Store, accountId: number): Row | null {
  const rows = s.bansByAccount.get(accountId);
  if (!rows || rows.length === 0) return null;
  const now = Math.floor(Date.now() / 1000);
  let best: Row | null = null;
  let bestAt = -1;
  for (const r of rows) {
    if (num(r.active) !== 1) continue;
    const until = str(r.until_at);
    const untilTs = until ? Math.floor(new Date(until.replace(" ", "T") + "Z").getTime() / 1000) : Infinity;
    if (untilTs < now) continue;
    const at = num(r.banned_at ? Math.floor(new Date(str(r.banned_at).replace(" ", "T") + "Z").getTime() / 1000) : 0);
    if (at > bestAt) {
      bestAt = at;
      best = r;
    }
  }
  return best;
}

function clearDifficulties(s: Store, steamId: string, mapKey: string): ClearDifficulty[] {
  const slots = new Map<number, ClearDifficulty>();
  for (const e of s.clearEventsBySteam.get(steamId) ?? []) {
    if (str(e.map_name).toLowerCase() !== mapKey) continue;
    let d = num(e.difficulty);
    if (d <= 0) {
      const ms = s.sessionByKey.get(str(e.session_key));
      if (ms) d = num(ms.difficulty);
    }
    const bucket = difficultyBucket(d);
    if (bucket <= 0) continue;
    const at = num(e.cleared_at);
    // Underworld and Brutal are the same tier; keep the name from the clear date.
    const era = bucket >= 8 && at > 0 && at < BRUTAL_RENAMED_AT ? 0 : 1;
    const slotKey = bucket * 2 + era;
    const slot = slots.get(slotKey) ?? { difficulty: bucket, count: 0, lastAt: 0 };
    slot.count += 1;
    if (at > slot.lastAt) slot.lastAt = at;
    slots.set(slotKey, slot);
  }
  return [...slots.values()].sort((a, b) => b.difficulty - a.difficulty || b.lastAt - a.lastAt);
}

export function buildPlayer(s: Store, id: string): PlayerPayload {
  const p = findPlayer(s, id);
  if (!p) {
    return {
      found: false,
      id: 0,
      steamId: "",
      vanity: null,
      name: "",
      skinName: "",
      hasSkin: false,
      clan: null,
      country: "",
      admin: false,
      veteran: false,
      steamUser: false,
      dateCreated: null,
      lastJoined: null,
      score: 0,
      rank: null,
      rankedPlayers: s.rankedCount,
      stats: [],
      perks: [],
      achievements: { total: ACHIEVEMENTS.length, completed: 0, list: [] },
      ban: null,
      sessions: [],
      clears: [],
    };
  }

  const accountId = num(p.id);
  const steamId = str(p.steam_id).trim();
  const prestiges = prestigesFor(s, accountId);
  const achMap = s.achByAccount.get(accountId);
  const ban = activeBan(s, accountId);

  const skinName = str(p.last_skin_name).trim();
  const hasSkin = skinName !== "" && existsSync(join(s.publicDir, "assets", "skins", `${skinName}.png`));

  const stats = STATS.map(({ key }) => ({ key, value: num(p[key] ?? 0) }));

  const sessionsRaw = (s.sessionsBySteam.get(steamId) ?? [])
    .map((sp) => {
      const ms = s.mapSessionById.get(num(sp.session_id));
      return { sp, ms };
    })
    .filter((x) => x.ms && num(x.ms.debug) === 0 && num(x.ms.started_at) >= SESSIONS_VISIBLE_SINCE)
    .sort((a, b) => num(b.ms!.started_at) - num(a.ms!.started_at))
    .slice(0, 50);

  const sessions: SessionInfo[] = sessionsRaw.map(({ sp, ms }) => {
    const mapName = str(ms!.map_name);
    const m = mapName.toLowerCase();
    // Boss is FinalWave+1 (site shows "Boss"). Old clears stored FinalWave+2.
    const finalWave = num(ms!.final_wave);
    let wave = num(ms!.wave);
    let maxWave = num(sp.max_wave);
    if (finalWave > 0) {
      const cap = finalWave + 1;
      if (wave > cap) wave = cap;
      if (maxWave > cap) maxWave = cap;
    }
    return {
      id: num(ms!.id),
      map: m,
      mapPretty: prettyMap(mapName),
      hasMapImage: existsSync(join(s.mapsDir, `${m}.jpg`)),
      startedAt: num(ms!.started_at),
      endedAt: num(ms!.ended_at),
      durationSec: num(ms!.duration_sec),
      outcome: str(sp.outcome) || str(ms!.outcome),
      wave,
      finalWave,
      difficulty: num(ms!.difficulty),
      server: serverLabel(ms!.server_name),
      perk: str(sp.perk_name),
      joinedAt: num(sp.joined_at),
      maxWave,
      joinWave: num(sp.join_wave),
    };
  });

  const clears: ClearInfo[] = (s.clearsBySteam.get(steamId) ?? [])
    .map((c) => {
      const mapName = str(c.map_name);
      const m = mapName.toLowerCase();
      return {
        map: m,
        mapPretty: prettyMap(mapName),
        hasMapImage: existsSync(join(s.mapsDir, `${m}.jpg`)),
        count: num(c.clear_count),
        lastAt: num(c.last_cleared_at),
        difficulties: clearDifficulties(s, steamId, m),
      };
    })
    .sort((a, b) => b.count - a.count || a.map.localeCompare(b.map));

  const achList: AchievementInfo[] = ACHIEVEMENTS.map((a) => {
    const progress = achMap?.get(a.i) ?? 0;
    return {
      index: a.i,
      name: a.n,
      desc: a.d,
      den: a.den,
      progress,
      completed: a.den > 0 && progress >= a.den,
    };
  });

  const score = num(p.score);
  const dateCreated = str(p.date_created);
  const veteran = dateCreated !== "" && dateCreated < "2026-01-01";

  return {
    found: true,
    id: accountId,
    steamId,
    vanity: null,
    name: str(p.last_player_name).replace(/^_+/, "").trim() || "(nameless)",
    skinName,
    hasSkin,
    clan: str(p.clan_name).trim()
      ? { name: str(p.clan_name).trim(), leader: num(p.clan_leader) === 1 }
      : null,
    country: str(p.country),
    admin: num(p.admin) !== 0,
    veteran,
    steamUser: num(p.is_steam_user) !== 0,
    dateCreated: dateCreated ? Math.floor(new Date(dateCreated.replace(" ", "T") + "Z").getTime() / 1000) : null,
    lastJoined: str(p.last_time_joined)
      ? Math.floor(new Date(str(p.last_time_joined).replace(" ", "T") + "Z").getTime() / 1000)
      : null,
    score,
    rank: score > 0 ? s.scoreRank.get(accountId) ?? null : null,
    rankedPlayers: s.rankedCount,
    stats,
    perks: buildPerks(p, prestiges),
    achievements: {
      total: ACHIEVEMENTS.length,
      completed: achList.filter((a) => a.completed).length,
      list: achList,
    },
    ban: ban
      ? {
          reason: str(ban.reason),
          until: str(ban.until_at) || null,
          adminName: str(ban.admin_name),
        }
      : null,
    sessions: SESSIONS_PUBLIC ? sessions : [],
    clears,
  };
}

function cleanPlayerName(raw: unknown): string {
  const name = str(raw)
    .replace(/[\u0000-\u001f\u007f]/g, "")
    .replace(/^_+/, "")
    .trim();
  return name || "???";
}

function isPublicPlayer(s: Store, steam: string): boolean {
  const p = s.playersBySteam.get(steam);
  return !p || num(p.admin) === 0;
}

// Still-open maps younger than this stay "in progress". Older ones with no
// close are treated as unfinished unknowns (a crash that never sent map close).
const OPEN_SESSION_MAX_SEC = 3 * 3600;

export function recentSessions(s: Store, limit: number): RecentSessionInfo[] {
  if (!SESSIONS_PUBLIC) return [];
  const now = Math.floor(Date.now() / 1000);
  const rows = [...s.mapSessionById.values()]
    .filter((ms) => KNOWN_SERVERS.has(str(ms.server_name).trim().toLowerCase()))
    .filter((ms) => num(ms.debug) === 0)
    .map((ms) => {
      const people = (s.playersBySession.get(num(ms.id)) ?? []).filter((sp) =>
        isPublicPlayer(s, str(sp.steam_id).trim()),
      );
      return { ms, people };
    })
    .filter((row) => num(row.ms.started_at) >= SESSIONS_VISIBLE_SINCE)
    .filter((row) => num(row.ms.player_count) > 0 || row.people.length > 0)
    .sort((a, b) => num(b.ms.started_at) - num(a.ms.started_at));

  const cap = Math.max(1, Math.min(2000, limit));
  const out: RecentSessionInfo[] = [];
  for (const { ms, people } of rows) {
    const mapName = str(ms.map_name);
    const m = mapName.toLowerCase();
    const finalWave = num(ms.final_wave);
    let wave = num(ms.wave);
    if (finalWave > 0 && wave > finalWave + 1) wave = finalWave + 1;
    const startedAt = num(ms.started_at);
    const endedAt = num(ms.ended_at);
    let durationSec = num(ms.duration_sec);
    let outcome = str(ms.outcome) || "unknown";
    if (endedAt <= 0 && (outcome === "unknown" || outcome === "")) {
      const age = startedAt > 0 ? now - startedAt : -1;
      if (age >= 0 && age <= OPEN_SESSION_MAX_SEC) {
        outcome = "playing";
        durationSec = age;
      }
    }
    // A map open that never closed is not a finished session.
    if (endedAt <= 0 && outcome !== "playing") continue;
    out.push({
      id: num(ms.id),
      map: m,
      mapPretty: prettyMap(mapName),
      hasMapImage: existsSync(join(s.mapsDir, `${m}.jpg`)),
      startedAt,
      endedAt,
      durationSec,
      outcome,
      wave,
      finalWave,
      difficulty: num(ms.difficulty),
      server: serverLabel(ms.server_name),
      playerCount: num(ms.player_count) || people.length,
      players: people.map((sp) => ({
        steamId: str(sp.steam_id).trim(),
        name: cleanPlayerName(sp.name),
        perk: str(sp.perk_name),
      })),
    });
    if (out.length >= cap) break;
  }
  return out;
}

function sessionPlayerDetail(s: Store, sp: Row, finalWave: number): SessionDetailPlayer {
  let maxWave = num(sp.max_wave);
  if (finalWave > 0 && maxWave > finalWave + 1) maxWave = finalWave + 1;
  const steam = str(sp.steam_id).trim();
  const account = s.playersBySteam.get(steam);
  const skinName = str(account?.last_skin_name).trim();
  const standing = livePerkStanding(steam, num(sp.perk_index, -1), str(sp.perk_name));
  return {
    steamId: steam,
    name: cleanPlayerName(sp.name),
    perk: str(sp.perk_name),
    perkIndex: num(sp.perk_index, -1),
    perkLevel: standing ? standing.level : null,
    prestigeRank: standing?.prestigeRank ?? 0,
    joinedAt: num(sp.joined_at),
    leftAt: num(sp.left_at),
    durationSec: num(sp.duration_sec),
    joinWave: num(sp.join_wave),
    maxWave,
    outcome: str(sp.outcome) || "unknown",
    kills: num(sp.kills),
    points: num(sp.points),
    scrakes: num(sp.scrakes),
    fps: num(sp.fps),
    cash: num(sp.cash),
    deaths: num(sp.deaths),
    healed: num(sp.healed),
    welded: num(sp.welded),
    bloats: num(sp.bloats),
    sirens: num(sp.sirens),
    husks: num(sp.husks),
    donated: num(sp.donated),
    skinName,
    hasSkin: skinName !== "" && existsSync(join(s.publicDir, "assets", "skins", `${skinName}.png`)),
  };
}

export function sessionDetail(s: Store, sessionId: number): SessionDetailInfo | null {
  if (!SESSIONS_PUBLIC) return null;
  const ms = s.mapSessionById.get(sessionId);
  if (!ms) return null;
  const mapName = str(ms.map_name);
  const m = mapName.toLowerCase();
  const finalWave = num(ms.final_wave);
  let wave = num(ms.wave);
  if (finalWave > 0 && wave > finalWave + 1) wave = finalWave + 1;
  const startedAt = num(ms.started_at);
  const endedAt = num(ms.ended_at);
  let durationSec = num(ms.duration_sec);
  let outcome = str(ms.outcome) || "unknown";
  const now = Math.floor(Date.now() / 1000);
  if (endedAt <= 0 && (outcome === "unknown" || outcome === "")) {
    const age = startedAt > 0 ? now - startedAt : -1;
    if (age >= 0 && age <= OPEN_SESSION_MAX_SEC) {
      outcome = "playing";
      durationSec = age;
    }
  }
  const people = [...(s.playersBySession.get(sessionId) ?? [])].sort(
    (a, b) => num(b.points) - num(a.points) || num(b.kills) - num(a.kills) || str(a.name).localeCompare(str(b.name)),
  );
  const players = people.map((sp) => sessionPlayerDetail(s, sp, finalWave));
  return {
    id: sessionId,
    found: true,
    map: m,
    mapPretty: prettyMap(mapName),
    hasMapImage: existsSync(join(s.mapsDir, `${m}.jpg`)),
    startedAt,
    endedAt,
    durationSec,
    outcome,
    wave,
    finalWave,
    difficulty: num(ms.difficulty),
    server: serverLabel(ms.server_name),
    day: num(ms.day),
    debug: num(ms.debug) !== 0,
    playerCount: num(ms.player_count) || players.length,
    players,
    join: sessionJoinUrl(ms.server_name, outcome, endedAt),
  };
}

export function topPlayers(s: Store, limit: number): TopPlayerEntry[] {
  const out: TopPlayerEntry[] = [];
  const players = [...s.playersById.values()]
    .filter((p) => isEraPlayer(p) && num(p.score) > 0)
    .sort((a, b) => num(b.score) - num(a.score))
    .slice(0, limit);
  for (const p of players) {
    const skinName = str(p.last_skin_name).trim();
    const dateCreated = str(p.date_created);
    out.push({
      id: num(p.id),
      steamId: str(p.steam_id).trim(),
      name: str(p.last_player_name).replace(/^_+/, "").trim() || "(nameless)",
      skinName,
      hasSkin: skinName !== "" && existsSync(join(s.publicDir, "assets", "skins", `${skinName}.png`)),
      score: num(p.score),
      kills: num(p.Kills),
      rank: s.scoreRank.get(num(p.id)) ?? 0,
      admin: num(p.admin) !== 0,
      veteran: dateCreated !== "" && dateCreated < "2026-01-01",
    });
  }
  return out;
}
