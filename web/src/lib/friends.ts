// Steam friends of the signed-in player, and who among them is on a KFM server.
// The header polls this while the player is logged in. Alerts fire only when
// the account-menu toggle is on, and a friend already announced this tab
// session is not announced again until they leave.
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
}

export type FriendsStatus =
  | "idle"
  | "loading"
  | "ok"
  | "private"
  | "unavailable"
  | "noconfig"
  | "login";

const NOTIFY_KEY = "kfm-friend-notify";
const SEEN_KEY = "kfm-friend-seen";
const POLL_MS = 45_000;

export const friends = ref<Friend[] | null>(null);
export const friendsStatus = ref<FriendsStatus>("idle");

function readNotify(): boolean {
  if (import.meta.server) return false;
  try {
    return localStorage.getItem(NOTIFY_KEY) === "1";
  } catch {
    return false;
  }
}

export const friendNotify = ref(readNotify());

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

let onAlert: ((friend: Friend) => void) | null = null;
let timer = 0;
let running = false;
let generation = 0;
let alerted = loadAlerted();
export const friendDemo = ref(false);

export function setFriendAlertHandler(fn: ((friend: Friend) => void) | null): void {
  onAlert = fn;
}

export function emitFriendAlert(friend: Friend): void {
  try {
    onAlert?.(friend);
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
  };
}

function notePlaying(list: Friend[]): void {
  const current = new Set<string>();
  for (const friend of list) {
    if (friend.playing && friend.serverId) current.add(presenceKey(friend));
  }
  if (friendNotify.value) {
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

export async function setFriendNotify(on: boolean): Promise<void> {
  friendNotify.value = on;
  try {
    localStorage.setItem(NOTIFY_KEY, on ? "1" : "0");
  } catch {
    // The toggle still applies until the next reload.
  }
  if (on && friends.value) notePlaying(friends.value);
  if (!friendDemo.value) await syncDevicePush(on);
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
