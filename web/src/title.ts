import { computed, ref, watch } from "vue";
import { i18n, t } from "./i18n";

const BRAND = "KF-Maniacs";

// Section pages use the nav label. A player or session page replaces it with
// that record's name once the page has loaded it.
const TITLE_KEY: Record<string, string> = {
  index: "nav.landing",
  home: "nav.landing",
  changelog: "nav.changelog",
  sessions: "nav.sessions",
  "sessions-id": "nav.sessions",
  session: "nav.sessions",
  players: "nav.home",
  "players-id": "nav.home",
  player: "nav.home",
  friends: "nav.friends",
  "demo-friends": "demo.title",
  "friend-demo": "demo.title",
};

/** A string is shown as-is. A key is translated and follows the language. */
const pageName = ref<{ path: string; name: string | { key: string } } | null>(null);

export function setPageTitle(name: string | { key: string } | null): void {
  const path = import.meta.client ? window.location.pathname + window.location.search : "";
  try {
    const route = useRoute();
    pageName.value = name ? { path: route.fullPath, name } : null;
  } catch {
    pageName.value = name ? { path, name } : null;
  }
}

function pageLabel(routeName: string | symbol | null | undefined, fullPath: string): string {
  const current = pageName.value;
  if (current && current.path === fullPath) {
    return typeof current.name === "string" ? current.name : t(current.name.key);
  }
  const key = TITLE_KEY[String(routeName ?? "")] ?? "nav.landing";
  return t(key);
}

/** Call once from a client plugin / layout so document title tracks the route. */
export function usePageTitle(): void {
  const route = useRoute();
  const title = computed(
    () => `${BRAND} · ${pageLabel(route.name, route.fullPath)}`,
  );
  useHead({ title });
  // Keep a direct write as well for pages that set a name after load.
  if (import.meta.client) {
    watch(
      [() => route.fullPath, () => i18n.locale, pageName, title],
      () => {
        document.title = title.value;
      },
      { immediate: true },
    );
  }
}
