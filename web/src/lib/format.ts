// Shared formatting helpers (browser-safe, no Node imports).

// Thousands separated by spaces ("10 000 000"). Non-breaking spaces keep a
// number from wrapping at the separator inside narrow cells.
export function fmtNum(n: number): string {
  return String(Math.trunc(n)).replace(/\B(?=(\d{3})+(?!\d))/g, "\u00A0");
}

export function fmtDate(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fmtDateOnly(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

// MySQL datetime string "YYYY-MM-DD HH:MM:SS" in UTC -> unix seconds.
export function mysqlTs(s: string | null): number | null {
  if (!s) return null;
  const t = Date.parse(s.replace(" ", "T") + "Z");
  return Number.isFinite(t) ? Math.floor(t / 1000) : null;
}

// Map internal name -> human name, same rules as the landing page monitor.
export function prettyMap(name: string): string {
  let n = name;
  if (/^KF-/i.test(n)) n = n.slice(3);
  n = n.replace(/_KFM$/i, "").replace(/_/g, " ");
  n = n.replace(/([a-z])([A-Z])/g, "$1 $2");
  return n || "—";
}

// The 8.0 difficulty was called Underworld until it was renamed Brutal on
// 29.10.2026 15:13 Moscow time (ChangeLogLocNew "When(67)"). Sessions from
// before that keep the old name on the site.
export const BRUTAL_RENAMED_AT = 1793275980;

// Status titles and flavour text need the scoreboard counters recorded with
// this version (kills, healing, donations, and the rest). Sessions that
// started before 7 Nov 2026 00:00 UTC do not have them.
export const SESSION_STATUS_SINCE = 1_794_009_600;

export function difficultyName(n: number, at?: number): string {
  if (n <= 0) return "";
  if (n >= 8) return at !== undefined && at < BRUTAL_RENAMED_AT ? "Underworld" : "Brutal";
  if (n >= 7) return "Hell on Earth";
  if (n >= 5) return "Suicidal";
  if (n >= 4) return "Hard";
  if (n >= 2) return "Normal";
  return "Beginner";
}

// Same steps as difficultyName, as the stored tier (8 Brutal, 7 HoE, …).
export function difficultyBucket(n: number): number {
  if (n >= 8) return 8;
  if (n >= 7) return 7;
  if (n >= 5) return 5;
  if (n >= 4) return 4;
  if (n >= 2) return 2;
  if (n > 0) return 1;
  return 0;
}
