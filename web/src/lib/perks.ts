// Perk levels 0-9 and progress, mirrored from KFStatsNew.uc (KF-Maniacs).
// LevelFromCounters / GetPerkProgressEx with the exact thresholds from
// GetMedicReq / GetSupportReq / GetSharpshooterReq / GetCommandoReq /
// GetBerserkerReq / GetFirebugReq / GetDemolitionsReq.

export const MAX_LEVEL = 9;

// 21 stat columns, same order as perkhost STATS / StatsObjectNew.GetSaveData.
export const STATS: { key: string; label: string }[] = [
  { key: "DamageHealed", label: "Damage Healed" },
  { key: "WeldingPoints", label: "Welding Points" },
  { key: "ShotgunDamage", label: "Shotgun Damage" },
  { key: "HeadshotKills", label: "Headshot Kills" },
  { key: "StalkerKills", label: "Stalker Kills" },
  { key: "BullpupDamage", label: "Bullpup Damage" },
  { key: "MeleeDamage", label: "Melee Damage" },
  { key: "FlameThrowerDamage", label: "Flamethrower Damage" },
  { key: "SelfHeals", label: "Self Heals" },
  { key: "SoleSurvivorWaves", label: "Sole Survivor Waves" },
  { key: "CashDonated", label: "Cash Donated" },
  { key: "FeedingKills", label: "Feeding Kills" },
  { key: "BurningCrossbowKills", label: "Burning Crossbow Kills" },
  { key: "GibbedFleshpounds", label: "Gibbed Fleshpounds" },
  { key: "StalkersKilledWithExplosives", label: "Stalkers Killed With Explosives" },
  { key: "GibbedEnemies", label: "Gibbed Enemies" },
  { key: "BloatKills", label: "Bloat Kills" },
  { key: "SirenKills", label: "Siren Kills" },
  { key: "Kills", label: "Kills" },
  { key: "ExplosivesDamage", label: "Explosives Damage" },
  { key: "TotalZedTime", label: "Total Zed Time" },
];

export const STATS_BY_KEY: Record<string, number> = Object.fromEntries(
  STATS.map((s, i) => [s.key, i]),
);

export interface PerkDef {
  index: number;
  id: string;
  // stat column indices in STATS, one or two
  statIdx: number[];
  // thresholds[statSlot][level 0..9]
  req: number[][];
}

const SHOTGUN: number[] = [
  25000, 100000, 200000, 500000, 3500000, 5500000, 10000000, 15000000, 25000000, 25000000,
];

export const PERKS: PerkDef[] = [
  {
    index: 0,
    id: "Field_Medic",
    statIdx: [0],
    req: [[200, 1000, 2000, 4000, 25000, 100000, 200000, 300000, 400000, 400000]],
  },
  {
    index: 1,
    id: "Support_Specialist",
    statIdx: [1, 2],
    req: [
      [2000, 7000, 15000, 30000, 250000, 370000, 500000, 750000, 1000000, 1000000],
      [...SHOTGUN],
    ],
  },
  {
    index: 2,
    id: "Sharpshooter",
    statIdx: [3],
    req: [[30, 100, 500, 1000, 5500, 8500, 15000, 25000, 40000, 40000]],
  },
  {
    index: 3,
    id: "Commando",
    statIdx: [4, 5],
    req: [
      [30, 100, 200, 350, 2400, 3600, 5000, 7000, 10000, 10000],
      [...SHOTGUN],
    ],
  },
  {
    index: 4,
    id: "Berserker",
    statIdx: [6],
    req: [[...SHOTGUN]],
  },
  {
    index: 5,
    id: "Firebug",
    statIdx: [7],
    req: [[...SHOTGUN]],
  },
  {
    index: 6,
    id: "Demolition",
    statIdx: [19],
    req: [[...SHOTGUN]],
  },
];

// PrestigeStoreNew.BaselineSlot(perk, statSlot) -> prestige baseline slot 0..8.
export function baselineSlot(perk: number, statSlot: number): number {
  switch (perk) {
    case 0: return 0;
    case 1: return 1 + statSlot;
    case 2: return 3;
    case 3: return 4 + statSlot;
    case 4: return 6;
    case 5: return 7;
    case 6: return 8;
    default: return 0;
  }
}

// perkhost PERK_BASELINE_SLOTS: slot -> which perk row holds it (a or b).
export const BASELINE_SLOT_PERK: { perk: number; col: "a" | "b" }[] = [
  { perk: 0, col: "a" },
  { perk: 1, col: "a" },
  { perk: 1, col: "b" },
  { perk: 2, col: "a" },
  { perk: 3, col: "a" },
  { perk: 3, col: "b" },
  { perk: 4, col: "a" },
  { perk: 5, col: "a" },
  { perk: 6, col: "a" },
];

export interface PrestigeRow {
  perk: number;
  rank: number;
  baselineA: number;
  baselineB: number;
  since: string | null;
}

// Effective stat for one perk/statSlot: raw minus the prestige baseline when
// the perk is prestiged (KFStatsNew.GetEffectiveStat).
export function effectiveStat(
  perk: PerkDef,
  statSlot: number,
  raw: number,
  prestige: PrestigeRow | undefined,
  baselines: (number | undefined)[],
): number {
  if (!prestige || prestige.rank <= 0) return raw;
  const slot = baselineSlot(perk.index, statSlot);
  if (slot < 0 || slot > 8) return raw;
  const base = baselines[slot] ?? 0;
  return raw <= base ? 0 : raw - base;
}

// KFStatsNew.LevelFromCounters: level implied by the counters.
export function levelFromCounters(perk: PerkDef, cur: number[]): number {
  const n = perk.req.length;
  for (let lvl = 0; lvl < MAX_LEVEL; lvl++) {
    let total = 0;
    for (let i = 0; i < n; i++) {
      const c = cur[i];
      let last = perk.req[i][lvl - 1] ?? 0;
      const req = perk.req[i][lvl];
      if (last >= c) last = 0;
      if (req <= last) {
        if (c >= req) total += 1;
        continue;
      }
      let p = (c - last) / (req - last);
      if (p > 1) p = 1;
      if (p < 0) p = 0;
      total += p;
    }
    if (total / n < 1) return lvl;
  }
  return MAX_LEVEL;
}

// KFStatsNew.GetPerkProgressEx at the given level: average fraction to the
// next level threshold.
export function perkProgressAt(perk: PerkDef, level: number, cur: number[]): number {
  if (level >= MAX_LEVEL) return 1;
  const n = perk.req.length;
  let total = 0;
  for (let i = 0; i < n; i++) {
    const c = cur[i];
    let last = perk.req[i][level - 1] ?? 0;
    const req = perk.req[i][level];
    if (last >= c) last = 0;
    if (req <= last) {
      total += 1;
      continue;
    }
    let p = (c - last) / (req - last);
    if (p > 1) p = 1;
    if (p < 0) p = 0;
    total += p;
  }
  return total / n;
}
