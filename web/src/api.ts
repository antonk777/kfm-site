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
  id: number;
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

// One map play on any server, for the landing page. `playing` means the map
// is still open. Players are the non-admin humans who joined it.
export interface RecentSessionPlayer {
  steamId: string;
  name: string;
  perk: string;
}

export interface RecentSessionInfo {
  id: number;
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
  playerCount: number;
  players: RecentSessionPlayer[];
}

// Full per-player row for a session detail page (Tab scoreboard + leave fields).
export interface SessionDetailPlayer {
  steamId: string;
  name: string;
  perk: string;
  perkIndex: number;
  perkLevel: number | null;
  prestigeRank: number;
  joinedAt: number;
  leftAt: number;
  durationSec: number;
  joinWave: number;
  maxWave: number;
  outcome: string;
  kills: number;
  points: number;
  scrakes: number;
  fps: number;
  cash: number;
  deaths: number;
  healed: number;
  welded: number;
  bloats: number;
  sirens: number;
  husks: number;
  donated: number;
  skinName: string;
  hasSkin: boolean;
}

export interface SessionDetailInfo {
  id: number;
  found: boolean;
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
  day: number;
  debug: boolean;
  playerCount: number;
  players: SessionDetailPlayer[];
  // steam:// link while the map is still open. Empty once it has ended.
  join: string;
}

export interface ClearDifficulty {
  difficulty: number;
  count: number;
  lastAt: number;
}

export interface ClearInfo {
  map: string;
  mapPretty: string;
  hasMapImage: boolean;
  count: number;
  lastAt: number;
  difficulties: ClearDifficulty[];
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

// Homepage preview. The history page asks for SESSION_HISTORY_LIMIT.
export const SESSION_PREVIEW_LIMIT = 5;
// Whole public list, clamped again by the stats server.
export const SESSION_HISTORY_LIMIT = 2000;

export async function fetchRecentSessions(limit = SESSION_PREVIEW_LIMIT): Promise<RecentSessionInfo[]> {
  const res = await fetch(`/api/stats/sessions?limit=${limit}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as RecentSessionInfo[];
}

/** Full fake session for layout previews at /sessions/demo. */
export function mockSessionDetail(): SessionDetailInfo {
  const startedAt = 1_793_820_000;
  const players: SessionDetailPlayer[] = [
    {
      steamId: "76561198007392654",
      name: "VectorM",
      perk: "Sharpshooter",
      perkIndex: 2,
      perkLevel: 5,
      prestigeRank: 0,
      joinedAt: startedAt,
      leftAt: startedAt + 2650,
      durationSec: 2650,
      joinWave: 1,
      maxWave: 8,
      outcome: "win",
      kills: 318,
      points: 1910,
      scrakes: 14,
      fps: 3,
      cash: 2450,
      deaths: 1,
      healed: 0,
      welded: 0,
      bloats: 6,
      sirens: 9,
      husks: 8,
      donated: 0,
      skinName: "FosterWhite",
      hasSkin: true,
    },
    {
      steamId: "76561198027703145",
      name: "Doc",
      perk: "Field_Medic",
      perkIndex: 0,
      perkLevel: 9,
      prestigeRank: 0,
      joinedAt: startedAt,
      leftAt: startedAt + 2650,
      durationSec: 2650,
      joinWave: 1,
      maxWave: 8,
      outcome: "win",
      kills: 112,
      points: 1380,
      scrakes: 1,
      fps: 0,
      cash: 890,
      deaths: 1,
      healed: 18450,
      welded: 40,
      bloats: 7,
      sirens: 4,
      husks: 3,
      donated: 150,
      skinName: "Mr_Foster",
      hasSkin: true,
    },
    {
      steamId: "76561198052468918",
      name: "YEBBEKER",
      perk: "Berserker",
      perkIndex: 4,
      perkLevel: 7,
      prestigeRank: 0,
      joinedAt: startedAt + 40,
      leftAt: startedAt + 2650,
      durationSec: 2610,
      joinWave: 1,
      maxWave: 8,
      outcome: "win",
      kills: 446,
      points: 1760,
      scrakes: 6,
      fps: 2,
      cash: 1320,
      deaths: 2,
      healed: 200,
      welded: 0,
      bloats: 21,
      sirens: 7,
      husks: 4,
      donated: 0,
      skinName: "Samuel_Avalon",
      hasSkin: true,
    },
    {
      steamId: "76561197985926491",
      name: "TUM",
      perk: "Support_Specialist",
      perkIndex: 1,
      perkLevel: 4,
      prestigeRank: 0,
      joinedAt: startedAt,
      leftAt: startedAt + 2650,
      durationSec: 2650,
      joinWave: 1,
      maxWave: 8,
      outcome: "win",
      kills: 289,
      points: 1520,
      scrakes: 4,
      fps: 1,
      cash: 640,
      deaths: 1,
      healed: 0,
      welded: 8200,
      bloats: 15,
      sirens: 5,
      husks: 6,
      donated: 1200,
      skinName: "Reverend_Alberts",
      hasSkin: true,
    },
    {
      steamId: "76561200437956380",
      name: "kazak",
      perk: "Commando",
      perkIndex: 3,
      perkLevel: 6,
      prestigeRank: 0,
      joinedAt: startedAt + 120,
      leftAt: startedAt + 2650,
      durationSec: 2530,
      joinWave: 2,
      maxWave: 8,
      outcome: "win",
      kills: 301,
      points: 1490,
      scrakes: 2,
      fps: 0,
      cash: 1100,
      deaths: 0,
      healed: 0,
      welded: 60,
      bloats: 12,
      sirens: 17,
      husks: 5,
      donated: 0,
      skinName: "Captian_Wiggins",
      hasSkin: true,
    },
    {
      steamId: "76561201006168774",
      name: "Ah1n1",
      perk: "Firebug",
      perkIndex: 5,
      perkLevel: 3,
      prestigeRank: 0,
      joinedAt: startedAt,
      leftAt: startedAt + 2100,
      durationSec: 2100,
      joinWave: 1,
      maxWave: 6,
      outcome: "leave",
      kills: 174,
      points: 760,
      scrakes: 1,
      fps: 0,
      cash: 420,
      deaths: 3,
      healed: 0,
      welded: 0,
      bloats: 9,
      sirens: 2,
      husks: 4,
      donated: 100,
      skinName: "Reverend_Alberts",
      hasSkin: true,
    },
    {
      steamId: "76561198006804047",
      name: "Boomstick",
      perk: "Demolition",
      perkIndex: 6,
      perkLevel: 8,
      prestigeRank: 0,
      joinedAt: startedAt + 80,
      leftAt: startedAt + 2650,
      durationSec: 2570,
      joinWave: 1,
      maxWave: 8,
      outcome: "win",
      kills: 226,
      points: 1450,
      scrakes: 5,
      fps: 7,
      cash: 1580,
      deaths: 2,
      healed: 0,
      welded: 15,
      bloats: 10,
      sirens: 3,
      husks: 13,
      donated: 300,
      skinName: "Chopper_Harris",
      hasSkin: true,
    },
  ];
  return {
    id: 0,
    found: true,
    map: "kf-foundry",
    mapPretty: "Foundry",
    hasMapImage: true,
    startedAt,
    endedAt: startedAt + 2650,
    durationSec: 2650,
    outcome: "win",
    wave: 8,
    finalWave: 7,
    difficulty: 7,
    server: "Bloodbath",
    day: 20261106,
    debug: false,
    playerCount: players.length,
    players,
    join: "",
  };
}

export async function fetchSession(id: number | string): Promise<SessionDetailInfo> {
  if (String(id) === "demo") return mockSessionDetail();
  const res = await fetch(`/api/stats/sessions/${encodeURIComponent(String(id))}`);
  if (res.status === 404) {
    return {
      id: Number(id) || 0,
      found: false,
      map: "",
      mapPretty: "",
      hasMapImage: false,
      startedAt: 0,
      endedAt: 0,
      durationSec: 0,
      outcome: "",
      wave: 0,
      finalWave: 0,
      difficulty: 0,
      server: "",
      day: 0,
      debug: false,
      playerCount: 0,
      players: [],
      join: "",
    };
  }
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as SessionDetailInfo;
}
