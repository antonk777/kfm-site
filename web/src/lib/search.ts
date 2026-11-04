// Parse a search query into a player lookup target.
// Accepted: Steam profile URLs (profiles/<64> and id/<vanity>), SteamID64,
// legacy STEAM_0:Y:Z and [U:1:N] forms, and the old KFM account id.
export type SearchResult =
  | { type: "steam"; id: string }
  | { type: "account"; account: number }
  | { type: "vanity"; name: string };

const STEAM64_BASE = 76561197960265728n;

export function parseSearch(raw: string): SearchResult | null {
  const s = raw.trim();
  if (!s) return null;

  // Full or partial profile URLs.
  const prof = s.match(/profiles\/(\d{16,20})/);
  if (prof) return { type: "steam", id: prof[1] };
  const vanity = s.match(/(?:^|\/)(?:id|u)\/([A-Za-z0-9_-]{2,32})(?:[/?#]|$)/);
  if (vanity) return { type: "vanity", name: vanity[1] };

  // Legacy Steam ids.
  const legacy = s.match(/^STEAM_[0-9]+:([0-9]+):([0-9]+)$/i);
  if (legacy) {
    const y = BigInt(legacy[1]);
    const z = BigInt(legacy[2]);
    return { type: "steam", id: (STEAM64_BASE + z * 2n + y).toString() };
  }
  const u32 = s.match(/^\[U:([0-9]+):([0-9]+)\]$/i);
  if (u32) {
    const account = BigInt(u32[2]);
    return { type: "steam", id: (STEAM64_BASE + account * 2n + 1n).toString() };
  }

  // Plain numbers: 16-20 digits = SteamID64, shorter = old KFM account id.
  if (/^\d{16,20}$/.test(s)) return { type: "steam", id: s };
  if (/^\d{1,9}$/.test(s)) return { type: "account", account: Number(s) };

  // Bare Steam custom URL name (resolved through the Web API at search time).
  if (/^[A-Za-z0-9_-]{2,32}$/.test(s)) return { type: "vanity", name: s };

  return null;
}
