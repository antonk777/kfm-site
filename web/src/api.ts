// JSON contract between the web app and the player API.
// The local dev server (vite.config.ts plugin) serves this from the DB
// snapshot; in production the same shape comes from stats-server.py.

export interface PerkStatInfo {
  key: string;
  value: number;
  effective: number;
  lastReq: number;
  req: number;
  progress: number; // 0..1 toward req
}

export interface PerkInfo {
  index: number;
  id: string;
  level: number;
  progress: number; // 0..1 toward next level (1 at level 9)
  prestigeRank: number;
  prestigeSince: string | null;
  stats: PerkStatInfo[];
}

export interface AchievementInfo {
  index: number;
  name: string;
  desc: string;
  den: number;
  progress: number;
  completed: boolean;
}

export interface SessionInfo {
  map: string;
  mapPretty: string;
  hasMapImage: boolean;
  startedAt: number;
  endedAt: number;
  durationSec: number;
  outcome: string;
  wave: number;
  finalWave: number;
  difficulty: number;
  server: string;
  perk: string;
  joinedAt: number;
  maxWave: number;
  joinWave: number;
}

export interface ClearInfo {
  map: string;
  mapPretty: string;
  hasMapImage: boolean;
  count: number;
  lastAt: number;
}

export interface PlayerPayload {
  found: boolean;
  id: number;
  steamId: string;
  vanity: string | null;
  name: string;
  skinName: string;
  hasSkin: boolean;
  clan: { name: string; leader: boolean } | null;
  country: string;
  admin: boolean;
  veteran: boolean;
  steamUser: boolean;
  dateCreated: number | null;
  lastJoined: number | null;
  score: number;
  rank: number | null;
  rankedPlayers: number;
  stats: { key: string; value: number }[];
  perks: PerkInfo[];
  achievements: {
    total: number;
    completed: number;
    list: AchievementInfo[];
  };
  ban: { reason: string; until: string | null; adminName: string } | null;
  sessions: SessionInfo[];
  clears: ClearInfo[];
}

export interface TopPlayerEntry {
  id: number;
  steamId: string;
  name: string;
  skinName: string;
  hasSkin: boolean;
  score: number;
  kills: number;
  rank: number;
  admin: boolean;
  veteran: boolean;
}

export async function fetchPlayer(id: string): Promise<PlayerPayload> {
  const res = await fetch(`/api/stats/player/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as PlayerPayload;
}

// Steam custom URL name -> SteamID64 (official ResolveVanityURL via the API).
export async function resolveVanity(name: string): Promise<string | null> {
  const res = await fetch(`/api/stats/resolve/${encodeURIComponent(name)}`);
  if (!res.ok) return null;
  const data = (await res.json()) as { steamid?: string };
  return data.steamid ?? null;
}

export async function fetchTopPlayers(): Promise<TopPlayerEntry[]> {
  const res = await fetch("/api/stats/top");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as TopPlayerEntry[];
}
