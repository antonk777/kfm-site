// Shared Steam login state for the header and the landing statistics block.
import { computed, ref } from "vue";

export interface SteamMe {
  loggedIn: boolean;
  steamId: string;
  vanity: string;
  name: string;
}

export const steamReady = ref(false);
export const steamUser = ref<SteamMe | null>(null);

export const profileTo = computed(() => {
  const user = steamUser.value;
  if (!user?.loggedIn) return "/players";
  return `/players/${user.vanity || user.steamId}`;
});

let loading: Promise<void> | null = null;

export function loadSteamUser(): Promise<void> {
  if (loading) return loading;
  loading = (async () => {
    try {
      const res = await fetch("/api/stats/steam/me");
      if (res.ok) steamUser.value = (await res.json()) as SteamMe;
    } catch {
      // API down: the login link still points at the real endpoint.
    } finally {
      steamReady.value = true;
    }
  })();
  return loading;
}

export async function logoutSteam(): Promise<void> {
  try {
    await fetch("/api/stats/steam/logout", { method: "POST" });
  } catch {
    // Clear local state either way; the cookie expires on its own if this missed.
  }
  steamUser.value = { loggedIn: false, steamId: "", vanity: "", name: "" };
}
