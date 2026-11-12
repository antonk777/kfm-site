// Steam friends of the signed-in player, and who among them is on a KFM server.
// The header polls this while the player is logged in. A friend is announced
// only when a site or desktop checkbox is on, and someone already announced
// this tab session is not announced again until they leave.
import { computed, ref } from "vue";
import { syncDevicePush } from "./push";

export interface Friend {
  steamId: string;
  name: string;
  profile: string;
  avatar: string;
  playing: boolean;
  played: boolean;
  serverId: string;
  server: string;
  map: string;
  perk: string;
  join: string;
  full: boolean;
  difficulty: number;
}

export type FriendsStatus =
  | "idle"
  | "loading"
  | "ok"
  | "private"
  | "unavailable"
  | "noconfig"
  | "login";

const SITE_KEY = "kfm-friend-notify-site";
const DESKTOP_KEY = "kfm-friend-notify-desktop";
const LEGACY_KEY = "kfm-friend-notify";
const SEEN_KEY = "kfm-friend-seen";
const POLL_MS = 45_000;

export const friends = ref<Friend[] | null>(null);
export const friendsStatus = ref<FriendsStatus>("idle");

function storedFlag(key: string): boolean | null {
  try {
    const value = localStorage.getItem(key);
    if (value === "1") return true;
    if (value === "0") return false;
    return null;
  } catch {
    return null;
  }
}

function writeFlag(key: string, on: boolean): void {
  try {
    localStorage.setItem(key, on ? "1" : "0");
  } catch {
    // The choice still applies until the next reload.
  }
}

function readNotifyPrefs(): { site: boolean; desktop: boolean } {
  if (import.meta.server) return { site: false, desktop: false };
  const site = storedFlag(SITE_KEY);
  const desktop = storedFlag(DESKTOP_KEY);
  if (site !== null || desktop !== null) {
    return { site: site === true, desktop: desktop === true };
  }
  // The old single switch turned both on. Desktop stays off until the browser
  // has already allowed it, so opening the site does not ask again.
  if (storedFlag(LEGACY_KEY) !== true) return { site: false, desktop: false };
  const granted = typeof Notification !== "undefined" && Notification.permission === "granted";
  writeFlag(SITE_KEY, true);
  writeFlag(DESKTOP_KEY, granted);
  return { site: true, desktop: granted };
}

const initialNotify = readNotifyPrefs();
export const friendNotify = ref(initialNotify.site);
export const friendDesktopNotify = ref(initialNotify.desktop);
export const friendsPrivacyPrompt = ref(false);

function promptFriendsPrivacy(otherOn: boolean): void {
  if (otherOn || friendDemo.value) return;
  friendsPrivacyPrompt.value = true;
}

export const playingFriends = computed(() => (friends.value ?? []).filter((f) => f.playing));

export const friendsById = computed(() => {
  const map = new Map<string, Friend>();
  for (const friend of friends.value ?? []) {
    if (friend.steamId) map.set(friend.steamId, friend);
  }
  return map;
});

export function steamFriendsPrivacy(steamId: string): string {
  if (/^\d{16,20}$/.test(steamId)) return `https://steamcommunity.com/profiles/${steamId}/edit/settings`;
  return "https://steamcommunity.com/my/edit/settings";
}

let onAlert: ((friend: Friend, preview?: boolean) => void) | null = null;
let timer = 0;
let running = false;
let generation = 0;
let alerted = loadAlerted();
export const friendDemo = ref(false);

export function setFriendAlertHandler(fn: ((friend: Friend, preview?: boolean) => void) | null): void {
  onAlert = fn;
}

export function emitFriendAlert(friend: Friend, preview = false): void {
  try {
    onAlert?.(friend, preview);
  } catch {
    // The list itself is still updated.
  }
}

export function beginFriendDemo(list: Friend[]): () => void {
  const prevFriends = friends.value;
  const prevStatus = friendsStatus.value;
  generation += 1;
  friendDemo.value = true;
  friends.value = list;
  friendsStatus.value = "ok";
  return () => {
    generation += 1;
    friendDemo.value = false;
    friends.value = prevFriends;
    friendsStatus.value = prevStatus;
  };
}

function loadAlerted(): Set<string> {
  if (import.meta.server) return new Set();
  try {
    const raw = sessionStorage.getItem(SEEN_KEY);
    const arr = raw ? (JSON.parse(raw) as unknown) : [];
    if (!Array.isArray(arr)) return new Set();
    return new Set(arr.filter((x): x is string => typeof x === "string"));
  } catch {
    return new Set();
  }
}

function saveAlerted(): void {
  try {
    sessionStorage.setItem(SEEN_KEY, JSON.stringify([...alerted]));
  } catch {
    // Private mode: alerts still work until the next reload.
  }
}

function presenceKey(friend: Friend): string {
  return `${friend.steamId}:${friend.serverId}`;
}

function asFriend(raw: Partial<Friend>): Friend {
  const steamId = String(raw.steamId || "");
  return {
    steamId,
    name: String(raw.name || steamId),
    profile: String(raw.profile || steamId),
    avatar: String(raw.avatar || ""),
    playing: Boolean(raw.playing),
    played: Boolean(raw.played) || Boolean(raw.playing),
    serverId: String(raw.serverId || ""),
    server: String(raw.server || ""),
    map: String(raw.map || ""),
    perk: String(raw.perk || ""),
    join: String(raw.join || ""),
    full: Boolean(raw.full),
    difficulty: Number(raw.difficulty) || 0,
  };
}

function notePlaying(list: Friend[]): void {
  const current = new Set<string>();
  for (const friend of list) {
    if (friend.playing && friend.serverId) current.add(presenceKey(friend));
  }
  if (friendNotify.value || friendDesktopNotify.value) {
    for (const friend of list) {
      if (!friend.playing || !friend.serverId) continue;
      const key = presenceKey(friend);
      if (alerted.has(key)) continue;
      alerted.add(key);
      try {
        onAlert?.(friend);
      } catch {
        // The list itself is still updated.
      }
    }
  }
  for (const key of [...alerted]) {
    if (!current.has(key)) alerted.delete(key);
  }
  saveAlerted();
}

export function setFriendNotify(on: boolean): void {
  const other = friendDesktopNotify.value;
  friendNotify.value = on;
  writeFlag(SITE_KEY, on);
  if (on) promptFriendsPrivacy(other);
  if (on && friends.value) notePlaying(friends.value);
}

export async function setFriendDesktopNotify(on: boolean): Promise<boolean> {
  if (on && (typeof Notification === "undefined" || Notification.permission !== "granted")) {
    friendDesktopNotify.value = false;
    writeFlag(DESKTOP_KEY, false);
    return false;
  }
  const other = friendNotify.value;
  friendDesktopNotify.value = on;
  writeFlag(DESKTOP_KEY, on);
  if (on) promptFriendsPrivacy(other);
  if (on && friends.value) notePlaying(friends.value);
  if (!friendDemo.value) await syncDevicePush(on);
  return on;
}

export async function refreshFriends(fresh = false): Promise<void> {
  if (friendDemo.value) return;
  const gen = generation;
  if (!friends.value) friendsStatus.value = "loading";
  try {
    const res = await fetch(`/api/stats/steam/friends${fresh ? "?fresh=1" : ""}`);
    if (friendDemo.value || gen !== generation) return;
    if (res.status === 401) {
      friends.value = [];
      friendsStatus.value = "login";
      return;
    }
    if (!res.ok) {
      if (!friends.value) friendsStatus.value = "unavailable";
      return;
    }
    const data = (await res.json()) as { status?: FriendsStatus; friends?: Partial<Friend>[] };
    if (friendDemo.value || gen !== generation) return;
    const status = data.status ?? "unavailable";
    if (status === "ok") {
      const list = (data.friends ?? []).map(asFriend);
      friends.value = list;
      friendsStatus.value = "ok";
      notePlaying(list);
      return;
    }
    if (status === "private" || status === "noconfig" || status === "login") {
      friends.value = [];
      friendsStatus.value = status;
      return;
    }
    if (!friends.value) friendsStatus.value = "unavailable";
  } catch {
    if (friendDemo.value || gen !== generation) return;
    if (!friends.value) friendsStatus.value = "unavailable";
  }
}

export function startFriendWatch(): void {
  if (running) return;
  running = true;
  void refreshFriends(false);
  timer = window.setInterval(() => {
    void refreshFriends(false);
  }, POLL_MS);
}

export function stopFriendWatch(): void {
  running = false;
  generation += 1;
  if (timer) window.clearInterval(timer);
  timer = 0;
  friends.value = null;
  friendsStatus.value = "idle";
  alerted = new Set();
  try {
    sessionStorage.removeItem(SEEN_KEY);
  } catch {
    // Already gone.
  }
}
