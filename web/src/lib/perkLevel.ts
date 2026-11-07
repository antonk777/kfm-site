// HUDKillingFloorExNew draws the perk level as stars on the icon.
// 1–5: that many red stars. 6–8: (level − 5) gold stars. 9: none.

export type PerkStarTone = "red" | "gold";

export function perkStars(level: number): { count: number; tone: PerkStarTone } {
  if (!Number.isFinite(level) || level <= 0 || level >= 9) return { count: 0, tone: "gold" };
  if (level > 5) return { count: level - 5, tone: "gold" };
  return { count: level, tone: "red" };
}

export const PERK_IDS = [
  "Field_Medic",
  "Support_Specialist",
  "Sharpshooter",
  "Commando",
  "Berserker",
  "Firebug",
  "Demolition",
] as const;

const PERK_ICON_BASE: Record<string, string> = {
  Field_Medic: "Medic",
  Support_Specialist: "Support",
  Sharpshooter: "SharpShooter",
  Commando: "Commando",
  Berserker: "Berserker",
  Firebug: "Firebug",
  Demolition: "Demolition",
};

export function canonPerkId(raw: string): string {
  const text = raw.trim();
  if (!text) return "";
  if (PERK_ICON_BASE[text]) return text;
  const underscored = text.replace(/\s+/g, "_");
  if (PERK_ICON_BASE[underscored]) return underscored;
  const lower = text.toLowerCase().replace(/[\s_]+/g, "");
  if (lower === "demolitions") return "Demolition";
  for (const id of Object.keys(PERK_ICON_BASE)) {
    if (id.toLowerCase().replace(/_/g, "") === lower) return id;
  }
  return "";
}

export function perkIconSrc(perk: string, level: number | null, prestiged: boolean): string {
  const id = canonPerkId(perk);
  const base = PERK_ICON_BASE[id];
  if (!base) return "";
  const variant = level === null ? "White" : perkIconVariant(level, prestiged);
  return `/assets/perks/Perk_${base}_${variant}.png`;
}

export type PerkIconVariant = "White" | "Red" | "Gold";

// Stock game textures, not recolors. Red is KillingFloorHUD.Perk_*,
// gold is KillingFloor2HUD.Perk_*_Gold, white is the mod's Perk_*_White.
export function perkIconVariant(level: number, _prestiged: boolean): PerkIconVariant {
  if (level >= 9) return "White";
  if (level > 5) return "Gold";
  return "Red";
}
