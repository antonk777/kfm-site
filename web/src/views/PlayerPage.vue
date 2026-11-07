<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { fetchPlayer, resolveVanity, type PlayerPayload, type SessionInfo } from "../api";
import {
  fmtDate,
  fmtDateOnly,
  fmtNum,
} from "../lib/format";
import { t, i18n } from "../i18n";
import { countryName } from "../data/countries";
import DifficultyLabel from "../components/DifficultyLabel.vue";
import PerkCard from "../components/PerkCard.vue";
import { achIconSrc } from "../lib/achIcons";
import { SESSIONS_PUBLIC } from "../lib/flags";

const props = defineProps<{ id: string }>();

const router = useRouter();

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
    let steamId = props.id;
    if (!/^\d+$/.test(props.id)) {
      const resolved = await resolveVanity(props.id);
      if (!resolved) return; // unknown custom URL -> "not found"
      steamId = resolved;
    }
    data.value = await fetchPlayer(steamId);
    // Canonical URL: redirect SteamID64 / old KFM-id pages to the player's
    // custom Steam URL when they have one.
    if (/^\d+$/.test(props.id) && data.value?.vanity) {
      router.replace(`/players/${data.value.vanity}`);
    }
  } catch {
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.id, load, { immediate: true });

const skinUrl = computed(() => {
  const d = data.value;
  if (!d) return "/assets/skins/unknown.png";
  return d.hasSkin
    ? `/assets/skins/${encodeURIComponent(d.skinName)}.png`
    : "/assets/skins/unknown.png";
});

const avatarUrl = computed(() => {
  const d = data.value;
  return d && /^\d{16,20}$/.test(d.steamId)
    ? `/api/stats/avatar/full?steam=${d.steamId}`
    : "";
});

const avatarFailed = ref(false);
watch(() => props.id, () => (avatarFailed.value = false));

const steamUrl = computed(() => {
  const d = data.value;
  return d && /^\d{16,20}$/.test(d.steamId)
    ? `https://steamcommunity.com/profiles/${d.steamId}`
    : "";
});

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
          <div class="identity-top">
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
            <div v-if="data.skinName" class="skin-mini">
              <div class="skin-mini-frame">
                <img :src="skinUrl" :alt="data.skinName" />
              </div>
              <div class="skin-plate">
                {{ t("hero.skin") }}
                <b>{{ data.skinName.replace(/_/g, " ") }}</b>
              </div>
            </div>
            <div style="min-width: 0">
              <h1 class="nick">{{ data.name }}</h1>
              <div class="badges">
                <span v-if="data.clan" class="badge clan" :title="data.clan.leader ? t('hero.clanLeader') : ''">
                  {{ data.clan.name }}
                </span>
                <span v-if="data.admin" class="badge admin">{{ t("hero.admin") }}</span>
                <span v-if="data.veteran" class="badge veteran" tabindex="0">
                  {{ t("hero.veteran") }}
                  <span class="badge-tip" role="tooltip">{{ t("hero.veteranHint") }}</span>
                </span>
                <span v-if="data.ban" class="badge banned">{{ t("hero.banned") }}</span>
                <span v-if="data.country" class="badge flag" :title="countryName(data.country, i18n.locale)">
                  <span class="fi" :class="`fi-${data.country.toLowerCase()}`"></span>
                  {{ countryName(data.country, i18n.locale) }}
                </span>
              </div>
              <div class="meta-line">
                <b>{{ t("hero.id") }}</b> {{ data.id }}
                <span class="sep">•</span>
                <b>{{ t("hero.playsSince") }}</b>
                {{ data.dateCreated ? fmtDateOnly(data.dateCreated) : "—" }}
                <span class="sep">•</span>
                <b>{{ t("hero.lastSeen") }}</b>
                {{ data.lastJoined ? fmtDate(data.lastJoined) : t("hero.never") }}
              </div>
              <div v-if="data.ban" class="meta-line" style="color: #c86a6a; margin-top: 4px">
                {{ data.ban.reason || t("hero.banned") }}
                <template v-if="data.ban.until"> ({{ fmtDate(data.ban.until ? Math.floor(new Date(data.ban.until.replace(' ', 'T') + 'Z').getTime() / 1000) : 0) }})</template>
                <template v-if="data.ban.adminName"> — {{ data.ban.adminName }}</template>
              </div>
              <div style="margin: 12px 0 22px">
                <a v-if="steamUrl" class="steam-btn" :href="steamUrl" target="_blank" rel="noopener">
                  {{ t("hero.steamProfile") }} →
                </a>
              </div>
            </div>
          </div>
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

/* Small skin portrait next to the Steam avatar, matched to its height. */
.skin-mini { flex: none; width: 64px; }
.skin-mini-frame {
  position: relative;
  width: 64px;
  height: 128px;
  overflow: hidden;
  background: linear-gradient(180deg, #1d1d25, #0d0d11);
  border: 1px solid var(--border-bright);
  box-shadow: 0 0 18px rgba(198, 18, 23, 0.22), inset 0 0 20px rgba(0, 0, 0, 0.55);
  clip-path: polygon(9px 0, 100% 0, 100% calc(100% - 9px), calc(100% - 9px) 100%, 0 100%, 0 9px);
}
.skin-mini-frame img {
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
.skin-mini .skin-plate { margin-top: 7px; text-align: left; font-size: 11px; letter-spacing: 0.08em; }
.skin-mini .skin-plate b { font-size: 13px; letter-spacing: 0.032em; line-height: 1.25; }
.skin-mini .skin-plate .skin-hint { max-width: 72px; }

.identity { display: flex; flex-direction: column; gap: 14px; padding: 22px 22px 0; }
.identity-top { display: flex; gap: 20px; align-items: flex-start; flex-wrap: wrap; }

.profile-divider {
  height: 1px;
  margin: 0 22px 18px;
  background: linear-gradient(90deg, transparent, var(--border) 6%, var(--border) 94%, transparent);
  display: flex;
  align-items: center;
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

.skin-plate {
  margin-top: 10px;
  text-align: center;
  font-family: var(--font-display);
  font-size: 15px;
  letter-spacing: 0.096em;
  text-transform: uppercase;
  color: var(--text-dim);
}
.skin-plate b { display: block; color: var(--text); font-size: 19px; letter-spacing: 0.064em; }
.skin-plate .skin-hint {
  display: block;
  margin-top: 5px;
  font-family: var(--font-body);
  font-size: 11px;
  letter-spacing: 0.016em;
  text-transform: none;
  color: var(--text-faint);
  line-height: 1.35;
}

.avatar-frame {
  width: 128px;
  height: 128px;
  flex: none;
  background: #0d0d11;
  border: 1px solid var(--border-bright);
  box-shadow: 0 0 18px rgba(198, 18, 23, 0.25);
  clip-path: polygon(10px 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%, 0 10px);
  overflow: hidden;
}
.avatar-frame img { width: 100%; height: 100%; object-fit: cover; display: block; }
.avatar-frame.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle at 50% 40%, #1c1c24, #0c0c10);
}
.avatar-frame .avatar-placeholder {
  width: auto;
  height: 78%;
  object-fit: contain;
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

.badges { display: flex; gap: 7px; flex-wrap: wrap; margin: 8px 0; }
.badge {
  font-family: var(--font-display);
  font-size: 14px;
  letter-spacing: 0.112em;
  padding: 3px 9px 2px;
  border: 1px solid;
  text-transform: uppercase;
}
.badge.admin { color: #ff8a8d; border-color: #7d2023; background: rgba(198, 18, 23, 0.22); }
.badge.veteran {
  position: relative;
  color: var(--gold-bright);
  border-color: #7d6118;
  background: rgba(199, 139, 18, 0.14);
  cursor: help;
}
.badge.veteran .badge-tip {
  position: absolute;
  left: 0;
  top: calc(100% + 8px);
  z-index: 6;
  width: max-content;
  max-width: min(280px, 70vw);
  padding: 8px 10px 7px;
  font-family: var(--font-body);
  font-size: 13px;
  font-weight: 400;
  letter-spacing: 0;
  line-height: 1.35;
  text-transform: none;
  text-align: left;
  color: var(--text);
  background: #1a1a22;
  border: 1px solid #7d6118;
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.55);
  pointer-events: none;
  opacity: 0;
  visibility: hidden;
  transform: translateY(-4px);
  transition: opacity 0.12s ease, transform 0.12s ease, visibility 0.12s ease;
}
.badge.veteran:hover .badge-tip,
.badge.veteran:focus-visible .badge-tip {
  opacity: 1;
  visibility: visible;
  transform: none;
}
.badge.banned { color: #c86a6a; border-color: #4a1b1b; background: rgba(120, 30, 30, 0.3); }
.badge.clan { color: var(--blue); border-color: #174a5c; background: rgba(92, 200, 230, 0.1); }
.badge.flag { color: var(--text); border-color: var(--border-bright); background: var(--panel); }
.badge.flag .fi {
  display: inline-block;
  margin-right: 6px;
  vertical-align: -1px;
  border-radius: 2px;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.14);
}

.meta-line { color: var(--text-dim); font-size: 13.5px; }
.meta-line b { color: var(--text); font-weight: 600; }
.meta-line .sep { color: var(--text-faint); margin: 0 8px; }

.steam-btn {
  display: inline-block;
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
}
@media (max-width: 560px) {
  .identity-top { flex-direction: column; }
}
</style>
