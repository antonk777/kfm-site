<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { fetchPlayer, resolveVanity, type PlayerPayload, type SessionInfo } from "~/api";
import {
  fmtDate,
  fmtDateOnly,
  fmtNum,
  prettyMap,
} from "~/lib/format";
import { t, i18n } from "~/i18n";
import { countryName } from "~/data/countries";
import DifficultyLabel from "~/components/DifficultyLabel.vue";
import PerkCard from "~/components/PerkCard.vue";
import { achIconSrc } from "~/lib/achIcons";
import { SESSIONS_PUBLIC } from "~/lib/flags";
import { steamUser } from "~/lib/steam";
import { setPageTitle } from "~/title";
import FriendsStrip from "~/components/FriendsStrip.vue";

const route = useRoute();
const router = useRouter();

const playerId = computed(() => {
  const raw = route.params.id;
  return (Array.isArray(raw) ? raw[0] : raw) || "";
});

const data = ref<PlayerPayload | null>(null);
const loading = ref(true);
const failed = ref(false);

async function load() {
  loading.value = true;
  failed.value = false;
  data.value = null;
  try {
    // A non-numeric id is a Steam custom URL name: resolve it to SteamID64
    // for the data lookup, but keep the custom URL in the address bar.
    const id = playerId.value;
    if (!id) return;
    let steamId = id;
    if (!/^\d+$/.test(id)) {
      const resolved = await resolveVanity(id);
      if (!resolved) return; // unknown custom URL -> "not found"
      steamId = resolved;
    }
    data.value = await fetchPlayer(steamId);
    // Canonical URL: redirect SteamID64 / old KFM-id pages to the player's
    // custom Steam URL when they have one.
    if (/^\d+$/.test(id) && data.value?.vanity && playerId.value === id) {
      router.replace(`/players/${data.value.vanity}`);
    }
  } catch {
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(playerId, load, { immediate: true });

const isMine = computed(() => {
  const mine = steamUser.value?.steamId || "";
  const theirs = data.value?.steamId || "";
  return mine.length > 0 && mine === theirs;
});

watch(
  () => {
    if (loading.value) return null;
    if (failed.value) return { key: "error" };
    if (!data.value?.found) return { key: "notFound" };
    return data.value.name || null;
  },
  (name) => setPageTitle(name),
  { immediate: true },
);

const skinUrl = computed(() => {
  const d = data.value;
  if (!d) return "/assets/skins/unknown.png";
  return d.hasSkin
    ? `/assets/skins/${encodeURIComponent(d.skinName)}.png`
    : "/assets/skins/unknown.png";
});

const skinLabel = computed(() => (data.value?.skinName || "").replace(/_/g, " "));

const avatarUrl = computed(() => {
  const d = data.value;
  return d && /^\d{16,20}$/.test(d.steamId)
    ? `/api/stats/avatar/full?steam=${d.steamId}`
    : "";
});

const avatarFailed = ref(false);
watch(playerId, () => (avatarFailed.value = false));

const steamUrl = computed(() => {
  const d = data.value;
  return d && /^\d{16,20}$/.test(d.steamId)
    ? `https://steamcommunity.com/profiles/${d.steamId}`
    : "";
});

interface LiveSeat {
  label: string;
  map: string;
  mapFile: string;
  difficulty: number;
  wave: number;
  finalWave: number;
  online: number;
  maxPlayers: number;
  join: string;
  full: boolean;
}

interface LiveServer {
  id: string;
  label?: string;
  map?: string;
  difficulty?: number;
  wave?: number;
  finalWave?: number;
  online?: number;
  maxPlayers?: number;
  stale?: boolean;
  steam?: string | { listed?: boolean };
  players?: { steamId?: string; steam?: string }[];
}

const live = ref<LiveSeat | null>(null);
let liveTimer = 0;

function seatFor(servers: LiveServer[], steamId: string): LiveSeat | null {
  for (const srv of servers) {
    if (srv.stale) continue;
    const here = (srv.players || []).some((p) => (p.steamId || p.steam || "") === steamId);
    if (!here) continue;
    const cap = srv.maxPlayers || 6;
    const online = srv.online || 0;
    const join = typeof srv.steam === "string" && srv.steam.startsWith("steam://run/") ? srv.steam : "";
    return {
      label: srv.label || srv.id,
      map: srv.map ? prettyMap(srv.map) : "",
      mapFile: srv.map || "",
      difficulty: Number(srv.difficulty) || 0,
      wave: Number(srv.wave) || 0,
      finalWave: Number(srv.finalWave) || 0,
      online,
      maxPlayers: cap,
      join,
      full: cap > 0 && online >= cap,
    };
  }
  return null;
}

async function pollLive(): Promise<void> {
  const steamId = data.value?.steamId || "";
  if (!/^\d{16,20}$/.test(steamId)) {
    live.value = null;
    return;
  }
  try {
    const res = await fetch("/api/stats/servers", { cache: "no-store" });
    if (!res.ok) return;
    const payload = (await res.json()) as { servers?: LiveServer[] };
    live.value = seatFor(payload.servers || [], steamId);
  } catch {
    // Keep the last seat until the next poll.
  }
}

const liveWave = computed(() => {
  const seat = live.value;
  if (!seat) return "";
  if (seat.map && seat.wave <= 0) return t("srv.lobby");
  if (seat.finalWave > 0 && seat.wave > seat.finalWave) return t("srv.bossWave");
  if (seat.wave > 0) return `${t("srv.wave")} ${seat.wave}${seat.finalWave > 0 ? " / " + seat.finalWave : ""}`;
  return "";
});

const shotFailed = ref(false);
watch(() => live.value?.mapFile, () => {
  shotFailed.value = false;
});

onMounted(() => {
  liveTimer = window.setInterval(() => void pollLive(), 10000);
});
onBeforeUnmount(() => window.clearInterval(liveTimer));

// Combat stats merged into the top strip (Kills is already a strip cell).
interface StripCell {
  key: string;
  label: string;
  value: number;
  text?: string;
  primary?: boolean;
}

const mainStats = computed<StripCell[]>(() => {
  const d = data.value;
  if (!d) return [];
  const byKey = new Map(d.stats.map((s) => [s.key, s.value]));
  const pick = (k: string) => byKey.get(k) ?? 0;
  return [
    { key: "score", label: t("score.title"), value: d.score, primary: true },
    {
      key: "rank",
      label: t("score.rank"),
      value: d.rank ?? 0,
      text: d.rank ? `#${d.rank}` : t("score.noRank"),
      primary: true,
    },
    { key: "kills", label: t("score.kills"), value: pick("Kills") },
    { key: "headshots", label: t("score.headshots"), value: pick("HeadshotKills") },
    { key: "healed", label: t("score.healed"), value: pick("DamageHealed") },
    { key: "welded", label: t("score.welded"), value: pick("WeldingPoints") },
    { key: "sole", label: t("stat.SoleSurvivorWaves"), value: pick("SoleSurvivorWaves") },
    { key: "cash", label: t("stat.CashDonated"), value: pick("CashDonated") },
  ];
});

function fmtDuration(sec: number): string {
  if (!sec || sec <= 0) return "—";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m >= 60) {
    const h = Math.floor(m / 60);
    return `${h}h ${m % 60}m`;
  }
  if (m > 0) return `${m}m`;
  return `${s}s`;
}

function outcomeClass(o: string): string {
  if (o === "win" || o === "victory") return "win";
  if (o === "loss" || o === "defeat") return "loss";
  if (o === "leave") return "leave";
  return "unknown";
}

function waveText(s: SessionInfo): string {
  // Boss is FinalWave+1 (or a win). Old rows stored FinalWave+2 on a clear.
  const w = Math.max(0, s.maxWave || s.wave);
  const f = s.finalWave || 0;
  const o = s.outcome || "";
  const boss =
    o === "win" ||
    o === "victory" ||
    (f > 0 && w > f);
  if (boss) return t("sessions.boss");
  return `${w}/${f || "?"}`;
}

function perkNameOf(id: string): string {
  return t(`perk.${id}`) !== `perk.${id}` ? t(`perk.${id}`) : id;
}

function clearDiffParts(c: { count: number; difficulties?: { difficulty: number; count: number; lastAt: number }[] }) {
  const parts = [...(c.difficulties ?? [])]
    .filter((d) => d.count > 0 && d.difficulty > 0)
    .sort((a, b) => b.difficulty - a.difficulty || b.lastAt - a.lastAt);
  if (!parts.length) return [];
  const single = parts.length === 1 && parts[0].count >= c.count;
  return parts.map((d) => ({ ...d, showCount: !single }));
}
</script>

<template>
  <div class="page">
    <template v-if="loading">
      <div class="state-note"><h2>{{ t("loading") }}</h2></div>
    </template>

    <template v-else-if="failed">
      <div class="state-note">
        <h2>{{ t("error") }}</h2>
        <router-link to="/">{{ t("backToList") }}</router-link>
      </div>
    </template>

    <template v-else-if="!data || !data.found">
      <div class="state-note">
        <h2>{{ t("notFound") }}</h2>
        <p>{{ t("notFoundHint") }}</p>
        <router-link to="/">{{ t("backToList") }}</router-link>
      </div>
    </template>

    <template v-else>
      <!-- profile: identity (avatar + skin) then top stats and perks -->
      <section class="panel profile">
        <div class="identity">
          <div class="identity-top" :class="{ 'has-skin': data.hasSkin }">
            <div class="avatar-slot">
              <div class="avatar-frame" :class="{ placeholder: !avatarUrl || avatarFailed }">
                <img
                  v-if="avatarUrl && !avatarFailed"
                  :src="avatarUrl"
                  alt="Steam avatar"
                  @error="avatarFailed = true"
                />
                <img
                  v-else
                  class="avatar-placeholder"
                  src="/assets/avatar-skull.svg"
                  alt=""
                />
              </div>
            </div>
            <div v-if="data.hasSkin" class="skin-mini" tabindex="0" :data-tip="skinLabel">
              <div class="skin-mini-frame">
                <img :src="skinUrl" :alt="skinLabel" />
              </div>
            </div>
            <div style="min-width: 0">
              <h1 class="nick">{{ data.name }}</h1>
              <div class="meta-line">
                <template v-if="data.clan">
                  <span :title="data.clan.leader ? t('hero.clanLeader') : undefined">{{ data.clan.name }}</span>
                  <span class="sep">·</span>
                </template>
                <template v-if="data.admin">
                  <span>{{ t("hero.admin") }}</span>
                  <span class="sep">·</span>
                </template>
                <template v-if="data.veteran">
                  <span :title="t('hero.veteranHint')">{{ t("hero.veteran") }}</span>
                  <span class="sep">·</span>
                </template>
                <template v-if="data.ban">
                  <span>{{ t("hero.banned") }}</span>
                  <span class="sep">·</span>
                </template>
                <template v-if="data.country">
                  <span><span class="fi" :class="`fi-${data.country.toLowerCase()}`"></span> {{ countryName(data.country, i18n.locale) }}</span>
                  <span class="sep">·</span>
                </template>
                <span><b>{{ t("hero.id") }}</b> {{ data.id }}</span>
                <span class="sep">·</span>
                <span><b>{{ t("hero.playsSince") }}</b> {{ data.dateCreated ? fmtDateOnly(data.dateCreated) : "—" }}</span>
                <span class="sep">·</span>
                <span><b>{{ t("hero.lastSeen") }}</b> {{ data.lastJoined ? fmtDate(data.lastJoined) : t("hero.never") }}</span>
              </div>
              <div v-if="data.ban" class="meta-line" style="color: #c86a6a; margin-top: 4px">
                {{ data.ban.reason || t("hero.banned") }}
                <template v-if="data.ban.until"> ({{ fmtDate(data.ban.until ? Math.floor(new Date(data.ban.until.replace(' ', 'T') + 'Z').getTime() / 1000) : 0) }})</template>
                <template v-if="data.ban.adminName"> — {{ data.ban.adminName }}</template>
              </div>
              <div class="profile-actions">
                <a v-if="steamUrl" class="steam-btn" :href="steamUrl" target="_blank" rel="noopener">
                  {{ t("hero.steamProfile") }}
                  <svg class="steam-arrow" viewBox="0 0 12 12" aria-hidden="true" focusable="false">
                    <path d="M3.5 2.25 8.25 6 3.5 9.75" />
                  </svg>
                </a>
              </div>
            </div>
          </div>
          <article v-if="live" class="now-panel">
            <div class="now-shot">
              <img
                v-if="live.mapFile && !shotFailed"
                :src="`/maps/${encodeURIComponent(live.mapFile.toLowerCase())}.jpg`"
                alt=""
                @error="shotFailed = true"
              />
            </div>
            <div class="now-body">
              <span class="now-label">{{ t("hero.playingOn", { server: live.label }) }}</span>
              <b v-if="live.map">{{ live.map }}</b>
              <div class="now-meta">
                <span v-if="live.difficulty > 0"><DifficultyLabel :level="live.difficulty" /></span>
                <span v-if="liveWave">{{ liveWave }}</span>
                <span>{{ live.online }} / {{ live.maxPlayers }}</span>
              </div>
            </div>
            <a v-if="live.join && !live.full" class="join-btn" :href="live.join">{{ t("friends.join") }}</a>
            <span v-else-if="live.full" class="now-full">{{ t("srv.full") }}</span>
          </article>
        </div>

        <div class="profile-divider"></div>

        <!-- top stats -->
        <div class="score-strip">
          <div
            v-for="s in mainStats"
            :key="s.key"
            class="score-cell"
            :class="{ primary: s.primary }"
          >
            <div class="label">{{ s.label }}</div>
            <div class="value">{{ s.text ?? fmtNum(s.value) }}</div>
          </div>
        </div>

        <div class="profile-divider">
          <span class="profile-label">{{ t("perks.title") }}</span>
        </div>

        <!-- perks -->
        <div class="perk-grid">
          <PerkCard v-for="p in data.perks" :key="p.index" :perk="p" />
        </div>
      </section>

      <FriendsStrip v-if="isMine" />

      <!-- clears -->
      <h2 class="section-title">
        {{ t("clears.title") }}
        <span v-if="data.clears.length" class="count">{{ data.clears.length }}</span>
      </h2>
      <p v-if="!data.clears.length" class="empty-note">{{ t("clears.empty") }}</p>
      <section v-else class="clear-grid">
        <div v-for="c in data.clears" :key="c.map" class="panel clear-card">
          <img
            v-if="c.hasMapImage"
            :src="`/maps/${encodeURIComponent(c.map)}.jpg`"
            :alt="c.mapPretty"
            loading="lazy"
          />
          <div class="clear-shade"></div>
          <div class="clear-info">
            <div class="clear-text">
              <span class="map-name">{{ c.mapPretty }}</span>
              <span class="clear-diff">
                <template v-for="(d, i) in clearDiffParts(c)" :key="`${c.map}-${d.difficulty}-${d.lastAt}`">
                  <template v-if="i"> · </template>
                  <DifficultyLabel :level="d.difficulty" :at="d.lastAt" />
                  <template v-if="d.showCount"> ×{{ d.count }}</template>
                </template>
              </span>
            </div>
            <span class="times">{{ c.count }}</span>
          </div>
        </div>
      </section>

      <!-- sessions -->
      <template v-if="SESSIONS_PUBLIC">
      <h2 class="section-title">
        {{ t("sessions.title") }}
        <span v-if="data.sessions.length" class="count">{{ data.sessions.length }}</span>
      </h2>
      <p v-if="!data.sessions.length" class="empty-note">{{ t("sessions.empty") }}</p>
      <div v-else class="panel" style="overflow-x: auto">
        <table class="sessions-table">
          <thead>
            <tr>
              <th>{{ t("sessions.map") }}</th>
              <th>{{ t("sessions.difficulty") }}</th>
              <th>{{ t("sessions.date") }}</th>
              <th>{{ t("sessions.outcome") }}</th>
              <th>{{ t("sessions.perk") }}</th>
              <th>{{ t("sessions.waves") }}</th>
              <th>{{ t("sessions.duration") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(s, i) in data.sessions"
              :key="s.id || i"
              :class="{ link: s.id > 0 }"
              @click="s.id > 0 && $router.push(`/sessions/${s.id}`)"
            >
              <td>
                <div class="map-cell">
                  <img
                    v-if="s.hasMapImage"
                    class="map-thumb"
                    :src="`/maps/${encodeURIComponent(s.map)}.jpg`"
                    :alt="s.mapPretty"
                    loading="lazy"
                  />
                  <div>
                    <div>
                      <router-link
                        v-if="s.id > 0"
                        class="map-link"
                        :to="`/sessions/${s.id}`"
                        @click.stop
                      >{{ s.mapPretty }}</router-link>
                      <template v-else>{{ s.mapPretty }}</template>
                    </div>
                    <div v-if="s.server" style="color: var(--text-faint); font-size: 11.5px">{{ s.server }}</div>
                  </div>
                </div>
              </td>
              <td style="white-space: nowrap"><DifficultyLabel :level="s.difficulty" :at="s.startedAt" /></td>
              <td style="white-space: nowrap">{{ fmtDate(s.startedAt) }}</td>
              <td>
                <span class="outcome" :class="outcomeClass(s.outcome)">
                  {{ t(`outcome.${s.outcome}`) !== `outcome.${s.outcome}` ? t(`outcome.${s.outcome}`) : s.outcome }}
                </span>
              </td>
              <td>{{ s.perk ? perkNameOf(s.perk) : "—" }}</td>
              <td>{{ waveText(s) }}</td>
              <td>{{ fmtDuration(s.durationSec) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      </template>

      <!-- achievements -->
      <h2 class="section-title">
        {{ t("ach.title") }}
        <span class="count">{{ t("ach.completed", { done: data.achievements.completed, total: data.achievements.total }) }}</span>
      </h2>
      <section class="ach-grid">
        <div
          v-for="a in data.achievements.list"
          :key="a.index"
          class="panel ach-tile"
          :class="{ done: a.completed }"
        >
          <img
            v-if="achIconSrc(a.index)"
            class="ach-icon"
            :src="achIconSrc(a.index)"
            alt=""
            loading="lazy"
          />
          <div class="ach-body">
            <div class="ach-name">{{ a.name }}</div>
            <div class="ach-desc">{{ a.desc }}</div>
            <div class="ach-bar">
              <i :style="{ width: `${a.den > 0 ? Math.min(100, Math.round((a.progress / a.den) * 100)) : 0}%` }" />
            </div>
            <div class="ach-meta">
              <span>{{ a.completed ? "✓" : `${a.progress}/${a.den || 0}` }}</span>
              <span v-if="!a.completed">{{ t("ach.locked") }}</span>
            </div>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.profile { position: relative; }
.profile::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: linear-gradient(var(--accent-deep), var(--accent), var(--accent-deep));
}

/* Skin art is 200×400. Match the identity text height and keep that 1:2 ratio. */
.skin-mini {
  position: relative;
  align-self: stretch;
  justify-self: start;
  aspect-ratio: 1 / 2;
  width: auto;
  min-width: 64px;
  min-height: 128px;
  outline: none;
  cursor: help;
}
.skin-mini::after {
  content: attr(data-tip);
  position: absolute;
  left: 50%;
  top: calc(100% + 6px);
  transform: translateX(-50%);
  z-index: 6;
  background: #1d1d25;
  border: 1px solid var(--border-bright);
  color: var(--text);
  font-family: var(--font-body);
  font-size: 12px;
  line-height: 1.3;
  padding: 3px 8px;
  border-radius: 3px;
  white-space: nowrap;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.6);
  pointer-events: none;
  opacity: 0;
  visibility: hidden;
}
.skin-mini:hover::after,
.skin-mini:focus-visible::after {
  opacity: 1;
  visibility: visible;
}
.skin-mini-frame {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: linear-gradient(180deg, #1d1d25, #0d0d11);
  border: 1px solid var(--border-bright);
  box-shadow: 0 0 18px rgba(198, 18, 23, 0.22), inset 0 0 20px rgba(0, 0, 0, 0.55);
  clip-path: polygon(9px 0, 100% 0, 100% calc(100% - 9px), calc(100% - 9px) 100%, 0 100%, 0 9px);
}
.skin-mini-frame img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: top center;
  display: block;
}
.skin-mini-frame::after {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: linear-gradient(180deg, transparent 55%, rgba(198, 18, 23, 0.28));
}

.identity { display: flex; flex-direction: column; gap: 14px; padding: 22px 22px 0; }
.identity-top {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 20px;
  align-items: stretch;
  padding-bottom: 22px;
}
.identity-top.has-skin { grid-template-columns: auto auto minmax(0, 1fr); }

.profile-divider {
  height: 1px;
  margin: 0 22px 18px;
  background: linear-gradient(90deg, transparent, var(--border) 6%, var(--border) 94%, transparent);
  display: flex;
  align-items: center;
}
.profile-divider:has(.profile-label) {
  margin-top: 18px;
  margin-bottom: 36px;
}
.profile-label {
  position: relative;
  top: -1px;
  background: var(--panel-2);
  padding: 4px 12px 2px;
  margin: 0 auto;
  font-family: var(--font-display);
  font-size: 15px;
  letter-spacing: 0.176em;
  text-transform: uppercase;
  color: var(--text-dim);
  border: 1px solid var(--border);
  display: inline-flex;
  gap: 8px;
  align-items: center;
}
.profile-label::before {
  content: "";
  width: 5px;
  height: 12px;
  background: var(--accent);
  box-shadow: 0 0 8px rgba(198, 18, 23, 0.7);
}

.avatar-slot {
  align-self: stretch;
  justify-self: start;
  aspect-ratio: 1;
  width: auto;
  min-width: 128px;
  min-height: 128px;
}
.avatar-frame {
  position: relative;
  width: 100%;
  height: 100%;
  background: #0d0d11;
  border: 1px solid var(--border-bright);
  box-shadow: 0 0 18px rgba(198, 18, 23, 0.25);
  clip-path: polygon(10px 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%, 0 10px);
  overflow: hidden;
}
.avatar-frame img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.avatar-frame.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle at 50% 40%, #1c1c24, #0c0c10);
}
.avatar-frame .avatar-placeholder {
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0.82;
  filter: drop-shadow(0 0 8px rgba(198, 18, 23, 0.45));
}

.nick {
  margin: 2px 0 8px;
  font-family: var(--font-display);
  font-size: 46px;
  line-height: 1;
  letter-spacing: 0.04em;
  color: #fff;
  text-shadow: 0 2px 0 rgba(0, 0, 0, 0.8), 0 0 18px rgba(198, 18, 23, 0.35);
  word-break: break-word;
}

.meta-line { color: var(--text-dim); font-size: 13.5px; }
.meta-line b { color: var(--text); font-weight: 600; }
.meta-line .sep { color: var(--text-faint); margin: 0 8px; }
.meta-line .fi {
  display: inline-block;
  width: 18px;
  height: 13px;
  margin-right: 6px;
  vertical-align: 0;
}

.profile-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin: 12px 0 0;
}
.now-panel {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
  padding: 10px;
  border: 1px solid #7d2023;
  background: linear-gradient(105deg, rgba(198, 18, 23, 0.28), #141018 42%, #12080a);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08), 0 2px 8px rgba(0, 0, 0, 0.45);
}
.now-shot {
  width: 168px;
  height: 94px;
  flex: none;
  background: #0b0b0e;
  border: 1px solid var(--border);
  overflow: hidden;
}
.now-shot img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.now-body {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
  min-width: 0;
  flex: 1;
}
.now-body b {
  color: #fff;
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.now-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  color: var(--text-dim);
  font-size: 13.5px;
}
.now-meta > span + span::before {
  content: "·";
  margin: 0 8px;
  color: var(--text-faint);
}
.now-meta :deep(.diff) {
  font-family: var(--font-display);
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.now-label {
  font-size: 13.5px;
  color: var(--text-dim);
}
.join-btn {
  display: inline-flex;
  align-items: center;
  align-self: center;
  flex: none;
  font-family: var(--font-display);
  font-size: 17px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #fff;
  background: linear-gradient(180deg, var(--accent-bright), var(--accent-deep));
  border: 1px solid #7d2023;
  padding: 7px 16px 5px;
}
.join-btn:hover { color: #fff; text-decoration: none; filter: brightness(1.12); }
.now-full {
  flex: none;
  font-family: var(--font-display);
  font-size: 14px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-faint);
}
@media (max-width: 640px) {
  .now-panel { flex-wrap: wrap; }
  .now-shot { width: 100%; height: 140px; }
}
.steam-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  width: fit-content;
  font-family: var(--font-display);
  font-size: 17px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #fff;
  background: linear-gradient(180deg, #2b3d4d, #1e2a35);
  border: 1px solid #46637a;
  padding: 7px 16px 5px;
}
.steam-arrow {
  width: 12px;
  height: 12px;
  flex: none;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.75;
  stroke-linecap: square;
  stroke-linejoin: miter;
}
.steam-btn:hover { text-decoration: none; filter: brightness(1.15); }

.score-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  padding: 0 22px 20px;
}
.score-cell {
  padding: 12px 14px 10px;
  position: relative;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid var(--border);
}
.score-cell::after {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 2px;
  background: var(--accent-deep);
}
.score-cell.primary::after { background: linear-gradient(90deg, var(--accent-deep), var(--accent)); }
.score-cell .label {
  font-family: var(--font-display);
  font-size: 13px;
  letter-spacing: 0.112em;
  text-transform: uppercase;
  color: var(--text-dim);
}
.score-cell .value {
  font-family: var(--font-display);
  font-size: 26px;
  line-height: 1.1;
  color: #fff;
  margin-top: 3px;
}
.score-cell.primary .value { color: var(--accent-bright); text-shadow: 0 0 14px rgba(198, 18, 23, 0.5); }

.perk-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
  padding: 0 22px 24px;
}
@media (min-width: 640px) {
  .perk-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (min-width: 1000px) {
  .perk-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

.sessions-table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
.sessions-table th, .sessions-table td {
  text-align: left;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
.sessions-table th {
  font-family: var(--font-display);
  font-size: 13px;
  letter-spacing: 0.112em;
  text-transform: uppercase;
  color: var(--text-faint);
  font-weight: 400;
}
.sessions-table tbody tr:hover { background: rgba(255, 255, 255, 0.025); }
.sessions-table tbody tr.link { cursor: pointer; }
.map-link { color: var(--text); text-decoration: none; }
.map-link:hover { color: #fff; }
.map-cell { display: flex; align-items: center; gap: 10px; min-width: 210px; }
.map-thumb {
  width: 76px;
  height: 44px;
  object-fit: cover;
  border: 1px solid var(--border);
  background: #0b0b0e;
  flex: none;
}
.outcome { font-weight: 600; }
.outcome.win { color: var(--green); }
.outcome.loss { color: #e07070; }
.outcome.leave { color: var(--text-dim); }
.outcome.unknown { color: var(--text-faint); }

.clear-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}
.clear-card { position: relative; overflow: hidden; height: 152px; display: block; }
.clear-card img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  filter: saturate(0.9) brightness(0.9);
}
.clear-shade {
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(10, 10, 12, 0.1), rgba(10, 10, 12, 0.88));
}
.clear-info {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 10px 12px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 8px;
}
.clear-text { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.clear-info .clear-diff {
  font-family: var(--font-display);
  font-size: 12px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--gold-bright);
  text-shadow: 0 1px 3px #000;
  line-height: 1.25;
}
.clear-info .clear-diff:empty { display: none; }
.clear-info .map-name {
  font-family: var(--font-display);
  font-size: 18px;
  letter-spacing: 0.048em;
  text-transform: uppercase;
  color: #fff;
  text-shadow: 0 1px 4px #000;
}
.clear-info .times {
  font-family: var(--font-display);
  font-size: 24px;
  color: var(--accent-bright);
  text-shadow: 0 1px 4px #000;
  white-space: nowrap;
}

.ach-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr));
  gap: 8px;
}
.ach-tile {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 10px 12px;
  border-left: 3px solid var(--border);
}
.ach-tile.done {
  border-left-color: var(--accent);
  background: linear-gradient(180deg, #1d1517, #151012);
}
.ach-icon {
  width: 64px;
  height: 64px;
  flex: none;
  object-fit: contain;
  display: block;
}
.ach-tile:not(.done) .ach-icon {
  filter: saturate(0.2) brightness(0.72);
}
.ach-body { min-width: 0; flex: 1; }
.ach-name { font-weight: 600; font-size: 13px; color: var(--text); }
.ach-desc { font-size: 11.5px; color: var(--text-faint); margin: 2px 0 6px; }
.ach-tile.done .ach-desc { color: var(--text-dim); }
.ach-bar { height: 5px; background: #0b0b0e; border: 1px solid var(--border); }
.ach-bar i { display: block; height: 100%; background: var(--accent-deep); }
.ach-tile.done .ach-bar i { background: var(--accent); }
.ach-meta { margin-top: 4px; font-size: 11px; color: var(--text-faint); display: flex; justify-content: space-between; }
.ach-tile.done .ach-meta { color: var(--accent-bright); }

.state-note { padding: 60px 0; text-align: center; color: var(--text-dim); }
.state-note h2 {
  font-family: var(--font-display);
  font-size: 30px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text);
  margin: 0 0 8px;
}

@media (max-width: 900px) {
  .score-strip { grid-template-columns: repeat(2, 1fr); }
  .nick { font-size: 36px; }
}
@media (max-width: 640px) {
  .identity { padding: 16px 14px 0; }
  .score-strip { padding: 0 14px 16px; gap: 8px; }
  .perk-grid { padding: 0 14px 20px; }
  .profile-divider { margin: 0 14px 16px; }
  .profile-divider:has(.profile-label) { margin: 14px 14px 28px; }
}
@media (max-width: 560px) {
  .identity-top,
  .identity-top.has-skin { grid-template-columns: auto; justify-items: start; }
  .avatar-slot { width: 128px; height: 128px; }
  .skin-mini { width: 64px; height: 128px; }
}
</style>
