<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { LANG_LABEL, LOCALES, i18n, setLocale, t, type Locale } from "~/i18n";
import { SESSIONS_PUBLIC } from "~/lib/flags";
import { prettyMap, noticePlace } from "~/lib/format";
import {
  friendNotify,
  playingFriends,
  setFriendAlertHandler,
  setFriendNotify,
  startFriendWatch,
  stopFriendWatch,
  type Friend,
} from "~/lib/friends";
import { pushReady, syncDevicePush } from "~/lib/push";
import { parseSearch } from "~/lib/search";
import { loadSteamUser, logoutSteam, profileTo, steamReady, steamUser } from "~/lib/steam";
import SteamMark from "~/components/SteamMark.vue";
import AccountMenu from "~/components/AccountMenu.vue";
import FriendToast from "~/components/FriendToast.vue";

const router = useRouter();
const route = useRoute();
const query = ref("");
const searchError = ref("");
const resolving = ref(false);
const menuOpen = ref(false);
const accountOpen = ref(false);
const accountMenu = ref<{ contains: (node: Node) => boolean } | null>(null);
const headerInner = ref<HTMLElement | null>(null);
const notifyPerm = ref<NotificationPermission | "unsupported">("unsupported");

interface FriendToastItem {
  id: number;
  name: string;
  server: string;
  map: string;
  profile: string;
  join: string;
  full: boolean;
  difficulty: number;
}
const toasts = ref<FriendToastItem[]>([]);
let toastSeq = 0;
// The desktop row gives up and uses the burger when the search can no longer
// stay at full width. Below 900px the burger is mandatory either way.
const cramped = ref(false);
let neededWidth = 0;
let headerObserver: ResizeObserver | null = null;
let narrowQuery: MediaQueryList | null = null;

// The burger menu closes whenever the view changes.
watch(
  () => route.fullPath,
  () => {
    menuOpen.value = false;
    accountOpen.value = false;
  },
);

watch(
  () => steamUser.value?.loggedIn === true,
  (on) => {
    if (on) startFriendWatch();
    else stopFriendWatch();
  },
);

// Language and login width change without a viewport resize. Remeasure from
// the open row, otherwise a previous "needed" width keeps the burger forever.
watch([() => i18n.locale, () => steamUser.value?.loggedIn, () => playingFriends.value.length], () => {
  if (import.meta.server || narrowQuery?.matches) return;
  cramped.value = false;
  neededWidth = 0;
  requestAnimationFrame(fitHeader);
});

function fitHeader(): void {
  const inner = headerInner.value;
  if (!inner || !narrowQuery) return;
  if (narrowQuery.matches) {
    cramped.value = true;
    neededWidth = Number.POSITIVE_INFINITY;
    return;
  }
  if (neededWidth === Number.POSITIVE_INFINITY) {
    cramped.value = false;
    neededWidth = 0;
  }
  const available = inner.parentElement?.clientWidth ?? inner.clientWidth;
  // A few pixels of slack so a subpixel remainder doesn't flap the burger.
  const slack = 4;
  if (cramped.value) {
    if (available >= neededWidth + slack) {
      cramped.value = false;
      neededWidth = 0;
      requestAnimationFrame(fitHeader);
    }
    return;
  }
  if (inner.scrollWidth > inner.clientWidth + slack) {
    neededWidth = inner.scrollWidth;
    cramped.value = true;
  }
}

function onLangChange(event: Event): void {
  const value = (event.target as HTMLSelectElement).value as Locale;
  if (LOCALES.includes(value)) setLocale(value);
}

function onDocPointer(event: Event): void {
  if (!accountOpen.value) return;
  if (event.target instanceof Node && accountMenu.value?.contains(event.target)) return;
  accountOpen.value = false;
}

function onDocKey(event: KeyboardEvent): void {
  if (event.key === "Escape") accountOpen.value = false;
}

function pushFriendToast(friend: Friend): void {
  const id = ++toastSeq;
  toasts.value = [
    ...toasts.value,
    {
      id,
      name: friend.name,
      server: friend.server,
      map: friend.map ? prettyMap(friend.map) : "",
      profile: friend.profile,
      join: friend.join,
      full: friend.full,
      difficulty: friend.difficulty,
    },
  ].slice(-4);
  window.setTimeout(() => {
    toasts.value = toasts.value.filter((toast) => toast.id !== id);
  }, 20000);
}

function showFriendAlert(friend: Friend): void {
  pushFriendToast(friend);
  // A saved subscription is delivered by the service worker, including after
  // this tab is closed. Without one, the browser still notifies this device
  // for as long as the site is open.
  if (pushReady.value) return;
  if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
  const place = noticePlace(friend.map ? prettyMap(friend.map) : "", friend.difficulty, friend.server);
  const title = friend.name;
  const body = t("friends.noticeBody", { place });
  try {
    const note = new Notification(title, {
      body,
      tag: `kfm-friend-${friend.steamId}`,
      icon: friend.avatar.startsWith("https://") ? friend.avatar : undefined,
    });
    note.onclick = () => {
      window.focus();
      void router.push(`/players/${friend.profile}`);
      note.close();
    };
  } catch {
    // The toast is already on the page.
  }
}

async function onToggleNotify(): Promise<void> {
  const next = !friendNotify.value;
  if (next && typeof Notification !== "undefined" && Notification.permission === "default") {
    try {
      notifyPerm.value = await Notification.requestPermission();
    } catch {
      notifyPerm.value = "denied";
    }
  } else if (typeof Notification !== "undefined") {
    notifyPerm.value = Notification.permission;
  }
  await setFriendNotify(next);
}

onMounted(() => {
  notifyPerm.value =
    typeof Notification === "undefined" ? "unsupported" : Notification.permission;
  narrowQuery = window.matchMedia("(max-width: 900px)");
  cramped.value = narrowQuery.matches;
  neededWidth = cramped.value ? Number.POSITIVE_INFINITY : 0;

  setFriendAlertHandler(showFriendAlert);
  document.addEventListener("pointerdown", onDocPointer);
  document.addEventListener("keydown", onDocKey);
  void loadSteamUser().then(() => {
    if (friendNotify.value && steamUser.value?.loggedIn) void syncDevicePush(true);
  });
  const inner = headerInner.value;
  if (inner) {
    headerObserver = new ResizeObserver(() => fitHeader());
    headerObserver.observe(inner);
    if (inner.parentElement) headerObserver.observe(inner.parentElement);
  }
  narrowQuery.addEventListener("change", fitHeader);
  fitHeader();
});

onBeforeUnmount(() => {
  setFriendAlertHandler(null);
  document.removeEventListener("pointerdown", onDocPointer);
  document.removeEventListener("keydown", onDocKey);
  headerObserver?.disconnect();
  narrowQuery?.removeEventListener("change", fitHeader);
});

function onLogout(): void {
  void logoutSteam();
}

async function onSearch(): Promise<void> {
  searchError.value = "";
  const q = query.value.trim();
  if (!q) return;
  const parsed = parseSearch(q);
  if (!parsed) {
    searchError.value = t("search.error");
    return;
  }
  if (parsed.type === "vanity") {
    resolving.value = true;
    try {
      const res = await fetch(`/api/stats/resolve/${encodeURIComponent(parsed.name)}`);
      if (!res.ok) {
        searchError.value = t("search.notFound");
        return;
      }
      const data = (await res.json()) as { steamid?: string };
      if (data.steamid) router.push(`/players/${parsed.name}`);
      else searchError.value = t("search.notFound");
    } catch {
      searchError.value = t("search.error");
    } finally {
      resolving.value = false;
    }
    return;
  }
  router.push(`/players/${parsed.type === "steam" ? parsed.id : parsed.account}`);
}
</script>

<template>
  <header class="site-header" :class="{ wide: route.name === 'index' || route.path === '/', cramped }">
    <div ref="headerInner" class="header-inner">
      <a class="header-logo" href="/">
        <img src="/assets/kf-maniacs-logo.svg" alt="KF-Maniacs" />
      </a>
      <button
        class="burger"
        type="button"
        :aria-expanded="menuOpen"
        aria-label="Menu"
        @click="menuOpen = !menuOpen"
      >
        <span :class="{ open: menuOpen }"></span>
      </button>
      <div class="header-tools" :class="{ open: menuOpen }">
        <nav class="header-nav">
          <NuxtLink to="/">{{ t("nav.landing") }}</NuxtLink>
          <NuxtLink v-if="SESSIONS_PUBLIC" to="/sessions">{{ t("nav.sessions") }}</NuxtLink>
          <NuxtLink to="/players">{{ t("nav.home") }}</NuxtLink>
          <NuxtLink to="/changelog">{{ t("nav.changelog") }}</NuxtLink>
        </nav>
        <form class="search" @submit.prevent="onSearch">
          <input
            v-model="query"
            type="text"
            :placeholder="t('search.placeholder')"
            :aria-label="t('search.placeholder')"
            spellcheck="false"
            autocomplete="off"
            @input="searchError = ''"
          />
          <button type="submit" :disabled="resolving" :title="t('search.placeholder')">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
              <circle cx="10.5" cy="10.5" r="6.5" />
              <path d="M15.5 15.5 L21 21" />
            </svg>
          </button>
        </form>
        <div class="header-actions">
          <template v-if="steamReady">
            <a v-if="!steamUser?.loggedIn" class="header-steam" href="/api/stats/steam/login">
              <SteamMark />
              {{ t("nav.login") }}
            </a>
            <AccountMenu
              v-else
              ref="accountMenu"
              :open="accountOpen"
              :inline="cramped"
              :profile-to="profileTo"
              :playing="playingFriends.length"
              :notify="friendNotify"
              :denied="friendNotify && notifyPerm === 'denied'"
              @toggle="accountOpen = !accountOpen"
              @logout="onLogout"
              @toggle-notify="onToggleNotify"
            />
          </template>
          <a
            class="header-discord"
            href="https://discord.gg/MJXsav9DFC"
            target="_blank"
            rel="noopener"
            :title="t('srv.discord')"
            aria-label="Discord"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
              <path d="M20.317 4.3698a19.7913 19.7913 0 00-4.8851-1.5152.0741.0741 0 00-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495-1.8447-.2762-3.68-.2762-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 00-.0785-.037 19.7363 19.7363 0 00-4.8852 1.515.0699.0699 0 00-.0321.0277C.5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 00.0312.0561c2.0528 1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 00.0842-.0276c.4616-.6304.8731-1.2952 1.226-1.9942a.076.076 0 00-.0416-.1057c-.6528-.2476-1.2743-.5495-1.8722-.8923a.077.077 0 01-.0076-.1277c.1258-.0943.2517-.1923.3718-.2914a.0743.0743 0 01.0776-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a.0739.0739 0 01.0785.0095c.1202.099.246.1981.3728.2924a.077.077 0 01-.0066.1276 12.2986 12.2986 0 01-1.873.8914.0766.0766 0 00-.0407.1067c.3604.698.7719 1.3628 1.225 1.9932a.076.076 0 00.0842.0286c1.961-.6067 3.9495-1.5219 6.0023-3.0294a.077.077 0 00.0313-.0552c.5004-5.177-.8382-9.6739-3.5485-13.6604a.061.061 0 00-.0312-.0286zM8.02 15.3312c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9555-2.4189 2.157-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 2.4189zm7.9748 0c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9554-2.4189 2.1569-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.946 2.4189-2.1568 2.4189Z" />
            </svg>
          </a>
          <div class="lang-switch" :title="t('lang.title')">
            <span class="lang-sizer" aria-hidden="true">{{ LANG_LABEL[i18n.locale] }}</span>
            <svg class="lang-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="9" />
              <path d="M3 12h18" />
              <path d="M12 3c2.2 2.6 3.5 5.6 3.5 9s-1.3 6.4-3.5 9c-2.2-2.6-3.5-5.6-3.5-9s1.3-6.4 3.5-9z" />
            </svg>
            <select :value="i18n.locale" :aria-label="t('lang.title')" @change="onLangChange">
              <option v-for="loc in LOCALES" :key="loc" :value="loc">
                {{ LANG_LABEL[loc] }}
              </option>
            </select>
          </div>
        </div>
      </div>
    </div>
    <p v-if="searchError" class="search-error">{{ searchError }}</p>
  </header>

  <div class="friend-toasts" aria-live="polite">
    <FriendToast
      v-for="toast in toasts"
      :key="toast.id"
      :name="toast.name"
      :server="toast.server"
      :map="toast.map"
      :profile="toast.profile"
      :join="toast.join"
      :full="toast.full"
      :difficulty="toast.difficulty"
    />
  </div>

  <slot />

  <footer class="footer">{{ t("footer.made") }} · kf-maniacs.com</footer>
</template>

<style scoped>
.site-header {
  position: sticky;
  top: 0;
  z-index: 20;
  background: linear-gradient(rgba(10, 10, 12, 0.97), rgba(10, 10, 12, 0.92));
  border-bottom: 1px solid var(--border);
}
.site-header::after {
  content: "";
  display: block;
  height: 2px;
  background: linear-gradient(90deg, var(--accent-deep), var(--accent) 20%, var(--accent-deep) 80%, transparent);
}
.header-inner {
  /* As wide as the links plus a full search field, but never past the viewport
     and never narrower than the page column when there is room. */
  width: max-content;
  min-width: min(100%, var(--page));
  max-width: 100%;
  margin: 0 auto;
  padding: 10px 20px;
  display: flex;
  align-items: center;
  gap: 22px;
  flex-wrap: nowrap;
  box-sizing: border-box;
}
.header-logo { flex: none; }
.header-logo img { height: 34px; display: block; }

/* Burger: narrow windows, and any width where the search would be clipped. */
.burger {
  display: none;
  width: 38px;
  height: 32px;
  margin-left: auto;
  flex: none;
  appearance: none;
  background: var(--panel-2);
  border: 1px solid var(--border-bright);
  border-radius: 4px;
  cursor: pointer;
  align-items: center;
  justify-content: center;
  padding: 0;
}
.burger span {
  position: relative;
  display: block;
  width: 16px;
  height: 2px;
  background: var(--text-dim);
}
.burger span::before,
.burger span::after {
  content: "";
  position: absolute;
  left: 0;
  width: 16px;
  height: 2px;
  background: var(--text-dim);
}
.burger span::before { top: -5px; }
.burger span::after { top: 5px; }
.burger span.open { background: transparent; }
.burger span.open::before { top: 0; transform: rotate(45deg); }
.burger span.open::after { top: 0; transform: rotate(-45deg); }

.header-tools {
  display: flex;
  align-items: center;
  gap: 22px;
  flex: 1 0 auto;
  min-width: max-content;
}
.header-nav { display: flex; gap: 4px; flex: 1 0 auto; }
.header-nav a {
  font-family: var(--font-display);
  font-size: 19px;
  letter-spacing: 0.064em;
  text-transform: uppercase;
  color: var(--text-dim);
  padding: 4px 12px;
  border: 1px solid transparent;
  white-space: nowrap;
}
.header-nav a:hover { color: var(--text); text-decoration: none; }
.header-nav a.router-link-active,
.header-nav a.router-link-exact-active {
  color: #fff;
  background: rgba(198, 18, 23, 0.16);
  border-color: var(--accent-deep);
}
.header-actions { display: flex; align-items: center; gap: 8px; flex: none; }

.lang-switch {
  position: relative;
  display: inline-flex;
  align-items: center;
  flex: none;
  color: var(--text-dim);
}
/* The closed control is only as wide as the selected language. A native
   select would otherwise reserve room for the longest name in the list. */
.lang-sizer {
  visibility: hidden;
  white-space: nowrap;
  font: 13px var(--font-body);
  line-height: 30px;
  padding: 0 28px;
  height: 32px;
  border: 1px solid transparent;
  box-sizing: border-box;
}
.lang-switch .lang-icon {
  position: absolute;
  left: 9px;
  z-index: 1;
  pointer-events: none;
}
.lang-switch select {
  position: absolute;
  inset: 0;
  width: 100%;
  appearance: none;
  box-sizing: border-box;
  height: 32px;
  background: var(--panel-2);
  border: 1px solid var(--border-bright);
  color: inherit;
  font: 13px var(--font-body);
  line-height: 30px;
  padding: 0 28px 0 28px;
  border-radius: 4px;
  cursor: pointer;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M1 1l4 4 4-4' fill='none' stroke='%238f8b80' stroke-width='1.5'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
}
.lang-switch:hover,
.lang-switch:focus-within { color: var(--text); }
.lang-switch select:hover,
.lang-switch select:focus { border-color: #55555f; }
.lang-switch select:focus { outline: none; border-color: var(--accent-deep); }
.lang-switch select option { background: var(--panel); color: var(--text); }

.header-discord {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  flex: none;
  color: var(--text-dim);
  background: var(--panel-2);
  border: 1px solid var(--border-bright);
  border-radius: 4px;
}
.header-discord:hover {
  color: #7a8cff;
  border-color: #5a6cff;
  background: var(--panel);
  text-decoration: none;
}

.header-steam {
  appearance: none;
  display: flex;
  align-items: center;
  gap: 7px;
  height: 32px;
  padding: 0 10px;
  flex: none;
  color: var(--text-dim);
  background: var(--panel-2);
  border: 1px solid var(--border-bright);
  border-radius: 4px;
  font-family: var(--font-display);
  font-size: 15px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  white-space: nowrap;
  cursor: pointer;
}
.header-steam:hover {
  color: var(--text);
  border-color: var(--accent-deep);
  background: var(--panel);
  text-decoration: none;
}
.header-steam svg { display: block; flex: none; }

.friend-toasts {
  position: fixed;
  right: 16px;
  bottom: 16px;
  z-index: 40;
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: min(320px, calc(100vw - 32px));
  pointer-events: none;
}

.search {
  display: flex;
  align-items: center;
  flex: none;
  gap: 0;
  margin-left: auto;
  border: 1px solid var(--border-bright);
  border-radius: 4px;
  background: var(--panel);
  overflow: hidden;
}
.search:focus-within { border-color: var(--accent-deep); box-shadow: 0 0 8px rgba(198, 18, 23, 0.25); }
.search input {
  width: 240px;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--text);
  font: 13px var(--font-body);
  padding: 7px 10px;
}
.search input::placeholder { color: var(--text-faint); }
.search button {
  appearance: none;
  border: 0;
  border-left: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text-dim);
  padding: 8px 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
}
.search button:hover { color: var(--accent-bright); background: var(--panel); }
.search button:disabled { opacity: 0.5; cursor: wait; }

.search-error {
  margin: 0;
  padding: 5px 20px 7px;
  font-size: 12px;
  color: #e07070;
  text-align: right;
  max-width: var(--page);
  margin-inline: auto;
}
.site-header.wide .header-inner {
  min-width: min(100%, var(--page-home));
}
.site-header.wide .search-error {
  max-width: var(--page-home);
}

@media (max-width: 900px) {
  .header-inner { padding: 8px 16px; gap: 10px; }
  .burger { display: flex; }
  .header-logo img { height: 30px; }
  .header-tools {
    display: none;
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    flex: none;
    min-width: 0;
    align-items: stretch;
    flex-direction: column;
    gap: 12px;
    padding: 14px 16px 18px;
    background: rgba(10, 10, 12, 0.98);
    border-bottom: 1px solid var(--border);
    box-shadow: 0 14px 26px rgba(0, 0, 0, 0.55);
  }
  .header-tools.open { display: flex; }
  .header-nav { flex: none; flex-direction: column; gap: 2px; }
  .header-nav a { padding: 8px 10px; }
  .search { width: 100%; margin-left: 0; }
  .search input { flex: 1; width: auto; min-width: 0; }
  .header-actions { justify-content: flex-start; flex-wrap: wrap; }
  .header-discord { margin-left: auto; }
}

.site-header.cramped .header-inner { padding: 8px 16px; gap: 10px; }
.site-header.cramped .burger { display: flex; }
.site-header.cramped .header-logo img { height: 30px; }
.site-header.cramped .header-tools {
  display: none;
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  flex: none;
  min-width: 0;
  align-items: stretch;
  flex-direction: column;
  gap: 12px;
  padding: 14px 16px 18px;
  background: rgba(10, 10, 12, 0.98);
  border-bottom: 1px solid var(--border);
  box-shadow: 0 14px 26px rgba(0, 0, 0, 0.55);
}
.site-header.cramped .header-tools.open { display: flex; }
.site-header.cramped .header-nav { flex: none; flex-direction: column; gap: 2px; }
.site-header.cramped .header-nav a { padding: 8px 10px; }
.site-header.cramped .search { width: 100%; margin-left: 0; }
.site-header.cramped .search input { flex: 1; width: auto; min-width: 0; }
.site-header.cramped .header-actions { justify-content: flex-start; flex-wrap: wrap; }
.site-header.cramped .header-discord { margin-left: auto; }

.footer {
  margin-top: 50px;
  padding: 18px 20px;
  border-top: 1px solid var(--border);
  color: var(--text-faint);
  font-size: 12.5px;
  text-align: center;
}
</style>
