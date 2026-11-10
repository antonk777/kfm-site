<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { fetchSession, type SessionDetailInfo, type SessionDetailPlayer } from "~/api";
import { i18n, MESSAGES, t } from "~/i18n";
import { SESSION_STATUS_SINCE, fmtDate, prettyMap } from "~/lib/format";
import DifficultyLabel from "~/components/DifficultyLabel.vue";
import PerkIcon from "~/components/PerkIcon.vue";
import SessionCharts from "~/components/SessionCharts.vue";
import { setPageTitle } from "~/title";

const props = defineProps<{ id: string }>();

const data = ref<SessionDetailInfo | null>(null);
const loading = ref(true);
const failed = ref(false);
const avatarFailed = ref<Record<string, boolean>>({});
let timer: ReturnType<typeof setInterval> | undefined;

const PERK_ICON: Record<string, string> = {
  Field_Medic: "Medic",
  Support_Specialist: "Support",
  Sharpshooter: "SharpShooter",
  Commando: "Commando",
  Berserker: "Berserker",
  Firebug: "Firebug",
  Demolition: "Demolition",
};

async function load(): Promise<void> {
  loading.value = !data.value;
  failed.value = false;
  try {
    data.value = await fetchSession(props.id);
  } catch {
    if (!data.value) failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.id, () => {
  data.value = null;
  avatarFailed.value = {};
  void load();
});

watch(
  () => {
    if (loading.value) return null;
    if (failed.value) return { key: "error" };
    if (!data.value?.found) return { key: "sessions.notFound" };
    const map = prettyMap(data.value.mapPretty || data.value.map);
    return map === "—" ? null : map;
  },
  (name) => setPageTitle(name),
  { immediate: true },
);

function onVisible(): void {
  if (document.hidden) return;
  void load();
}

onMounted(() => {
  void load();
  if (props.id !== "demo") {
    timer = setInterval(() => void load(), 60000);
    document.addEventListener("visibilitychange", onVisible);
  }
});

onUnmounted(() => {
  if (timer) clearInterval(timer);
  document.removeEventListener("visibilitychange", onVisible);
});

function fmtDuration(sec: number): string {
  if (!sec || sec <= 0) return "—";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m >= 60) {
    const h = Math.floor(m / 60);
    return `${h}h ${m % 60}m`;
  }
  if (m > 0) return `${m}m ${s.toString().padStart(2, "0")}s`;
  return `${s}s`;
}

function outcomeClass(o: string): string {
  if (o === "win" || o === "victory") return "win";
  if (o === "loss" || o === "defeat") return "loss";
  if (o === "leave") return "leave";
  if (o === "playing") return "playing";
  return "unknown";
}

function outcomeLabel(o: string): string {
  const key = `outcome.${o}`;
  const label = t(key);
  return label === key ? o : label;
}

function waveText(wave: number, finalWave: number, outcome: string): string {
  const w = Math.max(0, wave);
  const f = finalWave || 0;
  const boss = outcome === "win" || outcome === "victory" || (f > 0 && w > f);
  if (boss) return t("sessions.boss");
  if (!w && !f) return "—";
  return `${w}/${f || "?"}`;
}

function playerWaveText(p: SessionDetailPlayer, finalWave: number): string {
  return waveText(p.maxWave, finalWave, p.outcome);
}

function perkIdOf(raw: string): string {
  if (!raw) return "";
  if (PERK_ICON[raw]) return raw;
  const underscored = raw.replace(/\s+/g, "_");
  if (PERK_ICON[underscored]) return underscored;
  const lower = raw.toLowerCase().replace(/[\s_]+/g, "");
  for (const id of Object.keys(PERK_ICON)) {
    if (id.toLowerCase().replace(/_/g, "") === lower) return id;
  }
  return underscored || raw;
}

function perkNameOf(id: string): string {
  const canon = perkIdOf(id);
  if (!canon) return "—";
  const key = `perk.${canon}`;
  const label = t(key);
  return label === key ? canon.replace(/_/g, " ") : label;
}

function perkLevelText(level: number | null | undefined, compact = false): string {
  if (typeof level !== "number" || level < 0) return "";
  return !compact && level >= 9 ? "MANIAC" : String(level);
}

function playerLink(steamId: string): string {
  return /^\d{16,20}$/.test(steamId) ? `/players/${steamId}` : "";
}

function avatarUrl(steamId: string): string {
  return /^\d{16,20}$/.test(steamId) ? `/api/stats/avatar/full?steam=${steamId}` : "";
}

function skinUrl(p: SessionDetailPlayer): string {
  return p.hasSkin && p.skinName ? `/assets/skins/${encodeURIComponent(p.skinName)}.png` : "";
}

function fmtCash(n: number): string {
  if (!n) return "—";
  if (n >= 1000) return `£${(n / 1000).toFixed(n % 1000 === 0 ? 0 : 1)}K`;
  return `£${n}`;
}

function dash(n: number): string {
  return n ? String(n) : "—";
}

const meta = computed(() => {
  const s = data.value;
  if (!s || !s.found) return [];
  return [
    { label: t("sessions.difficulty"), value: "", difficulty: true },
    { label: t("sessions.outcome"), value: outcomeLabel(s.outcome), className: outcomeClass(s.outcome), difficulty: false },
    { label: t("sessions.started"), value: fmtDate(s.startedAt), difficulty: false },
    { label: t("sessions.duration"), value: fmtDuration(s.durationSec), difficulty: false },
    { label: t("srv.players"), value: String(s.playerCount || s.players.length), difficulty: false },
    { label: t("sessions.server"), value: s.server || "—", difficulty: false },
  ];
});

const waveProgress = computed(() => {
  const s = data.value;
  if (!s || !s.found) return null;
  const final = Math.max(1, s.finalWave || 7);
  const wave = Math.max(0, s.wave || 0);
  const won = s.outcome === "win" || s.outcome === "victory";
  const lost = s.outcome === "loss" || s.outcome === "defeat";
  const pastFinal = wave > final;

  let shown = 0;
  let failWave = 0;
  let showBoss = false;
  let bossOn = false;
  let bossFail = false;

  if (won) {
    shown = final;
    showBoss = true;
    bossOn = true;
  } else if (lost) {
    if (pastFinal) {
      shown = final;
      showBoss = true;
      bossFail = true;
    } else {
      shown = Math.max(1, Math.min(final, wave || 1));
      failWave = shown;
    }
  } else if (pastFinal) {
    shown = final;
    showBoss = true;
  } else {
    shown = Math.min(final, wave);
  }

  return {
    ticks: shown > 0 ? Array.from({ length: shown }, (_, i) => i + 1) : [],
    failWave,
    showBoss,
    bossOn,
    bossFail,
  };
});

const squad = computed(() => {
  const players = data.value?.players ?? [];
  return [...players].sort(
    (a, b) => b.points - a.points || b.kills - a.kills || a.name.localeCompare(b.name),
  );
});

type BadgeTone = "glory" | "support" | "hunt" | "muted";
type Badge = { key: string; tone: BadgeTone };

const PERK_BADGE: Record<string, string> = {
  Field_Medic: "badge.medic",
  Support_Specialist: "badge.supplier",
  Sharpshooter: "badge.marksman",
  Commando: "badge.rifleman",
  Berserker: "badge.brawler",
  Firebug: "badge.pyro",
  Demolition: "badge.breacher",
};

function playerKey(p: SessionDetailPlayer): string {
  return p.steamId || p.name;
}

function wonOutcome(p: SessionDetailPlayer): boolean {
  return p.outcome === "win" || p.outcome === "victory";
}

function lostOutcome(p: SessionDetailPlayer): boolean {
  return p.outcome === "loss" || p.outcome === "defeat";
}

function uniqueLeader(
  players: SessionDetailPlayer[],
  value: (p: SessionDetailPlayer) => number,
  min = 1,
): SessionDetailPlayer | null {
  let best: SessionDetailPlayer | null = null;
  let bestV = 0;
  let ties = 0;
  for (const p of players) {
    const v = value(p);
    if (v > bestV) {
      best = p;
      bestV = v;
      ties = 1;
    } else if (v === bestV && v > 0) {
      ties += 1;
    }
  }
  return best && bestV >= min && ties === 1 ? best : null;
}

function leadMargin(
  players: SessionDetailPlayer[],
  value: (p: SessionDetailPlayer) => number,
  min: number,
): { player: SessionDetailPlayer; margin: number } | null {
  const ranked = [...players].sort((a, b) => value(b) - value(a));
  if (!ranked.length) return null;
  const top = value(ranked[0]);
  if (top < min) return null;
  const second = ranked.length > 1 ? value(ranked[1]) : 0;
  if (top === second) return null;
  return { player: ranked[0], margin: (top - second) / Math.max(second, 1) };
}

const squadBadges = computed(() => {
  const players = squad.value;
  const assigned = new Map<string, Badge>();
  const used = new Set<string>();

  function give(p: SessionDetailPlayer | null, key: string, tone: BadgeTone) {
    if (!p) return;
    const id = playerKey(p);
    if (assigned.has(id) || used.has(key)) return;
    assigned.set(id, { key, tone });
    used.add(key);
  }

  const winners = players.filter(wonOutcome);
  if (
    players.length > 1 &&
    winners.length === 1 &&
    players.every((p) => wonOutcome(p) || lostOutcome(p) || p.outcome === "leave")
  ) {
    give(winners[0], "badge.sole", "glory");
  }

  const waveLead = uniqueLeader(players, (p) => p.maxWave);
  if (
    waveLead &&
    players.length > 1 &&
    players.some((p) => p !== waveLead && (lostOutcome(p) || p.outcome === "leave"))
  ) {
    give(waveLead, "badge.lastStand", "glory");
  }

  give(uniqueLeader(players, (p) => p.healed), "badge.surgeon", "support");

  const scrakeLead = uniqueLeader(players, (p) => p.scrakes);
  const fpLead = uniqueLeader(players, (p) => p.fps);
  if (scrakeLead && fpLead && playerKey(scrakeLead) === playerKey(fpLead)) {
    give(scrakeLead, "badge.bigGame", "glory");
  } else {
    give(fpLead, "badge.fleshpound", "hunt");
    give(scrakeLead, "badge.scrake", "hunt");
  }

  give(uniqueLeader(players, (p) => p.kills), "badge.slayer", "glory");
  give(uniqueLeader(players, (p) => p.points), "badge.ace", "glory");
  give(uniqueLeader(players, (p) => p.donated ?? 0), "badge.philanthropist", "support");
  give(uniqueLeader(players, (p) => p.welded), "badge.welder", "support");

  const deathless = players.filter((p) => p.deaths === 0 && (p.kills > 0 || p.points > 0 || p.healed > 0));
  if (deathless.length === 1 && players.some((p) => p.deaths > 0)) {
    give(deathless[0], "badge.untouchable", "glory");
  }

  const niches = [
    { key: "badge.siren", value: (p: SessionDetailPlayer) => p.sirens },
    { key: "badge.husk", value: (p: SessionDetailPlayer) => p.husks },
    { key: "badge.bloat", value: (p: SessionDetailPlayer) => p.bloats },
  ]
    .map((n) => ({ ...n, lead: leadMargin(players, n.value, 3) }))
    .filter((n) => n.lead)
    .sort((a, b) => b.lead!.margin - a.lead!.margin);
  for (const n of niches) give(n.lead!.player, n.key, "hunt");

  for (const p of players) {
    if (assigned.has(playerKey(p))) continue;
    if (p.outcome === "leave") {
      assigned.set(playerKey(p), { key: "badge.earlyExit", tone: "muted" });
      continue;
    }
    if (lostOutcome(p)) {
      assigned.set(playerKey(p), { key: "badge.fallen", tone: "muted" });
      continue;
    }
    if (p.deaths === 0 && players.some((o) => o.deaths > 0)) {
      assigned.set(playerKey(p), { key: "badge.cleanRun", tone: "glory" });
      continue;
    }
    const perkKey = PERK_BADGE[perkIdOf(p.perk)];
    assigned.set(playerKey(p), { key: perkKey || "badge.survivor", tone: "muted" });
  }

  return assigned;
});

// Titles describe how the map finished. A live match still has people leaving,
// so the same rules would name survivors before anyone knows the result.
// The demo fixture carries the full counter set. Live rows do only once this version is recording them.
const showStatuses = computed(() => {
  if (props.id === "demo") return true;
  const s = data.value;
  if (!s || s.outcome === "playing" || s.endedAt <= 0) return false;
  return s.startedAt >= SESSION_STATUS_SINCE;
});

function badgeOf(p: SessionDetailPlayer): Badge {
  return squadBadges.value.get(playerKey(p)) ?? { key: "badge.survivor", tone: "muted" };
}

// Flavour text is written per language, not translated, so there is no English fallback.
function badgeHint(key: string): string {
  return MESSAGES[i18n.locale]?.[`${key}.hint`] ?? "";
}
</script>

<template>
  <div class="page">
    <p class="back">
      <router-link to="/sessions">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M15 6l-6 6 6 6" />
        </svg>
        {{ t("sessions.back") }}
      </router-link>
    </p>

    <template v-if="loading">
      <div class="state-note"><h2>{{ t("loading") }}</h2></div>
    </template>

    <template v-else-if="failed">
      <div class="state-note">
        <h2>{{ t("error") }}</h2>
        <router-link to="/sessions">{{ t("sessions.back") }}</router-link>
      </div>
    </template>

    <template v-else-if="!data || !data.found">
      <div class="state-note">
        <h2>{{ t("sessions.notFound") }}</h2>
        <p>{{ t("sessions.notFoundHint") }}</p>
        <router-link to="/sessions">{{ t("sessions.back") }}</router-link>
      </div>
    </template>

    <template v-else>
      <header class="hero panel" :class="{ debug: data.debug }">
        <div
          class="hero-bg"
          :style="data.hasMapImage ? { backgroundImage: `url(/maps/${encodeURIComponent(data.map)}.jpg)` } : undefined"
        />
        <div class="hero-shade" />
        <div class="hero-body">
          <img
            v-if="data.hasMapImage"
            class="hero-shot"
            :src="`/maps/${encodeURIComponent(data.map)}.jpg`"
            :alt="prettyMap(data.mapPretty || data.map)"
          />
          <div class="hero-main">
            <div class="hero-badges">
              <span class="outcome pill" :class="outcomeClass(data.outcome)">{{ outcomeLabel(data.outcome) }}</span>
              <span v-if="data.debug" class="pill debug">{{ t("sessions.debug") }}</span>
            </div>
            <h1 class="hero-title">{{ prettyMap(data.mapPretty || data.map) }}</h1>
            <a v-if="data.outcome === 'playing' && data.join" class="join" :href="data.join">{{ t("srv.join") }}</a>
            <div v-if="waveProgress?.ticks.length || waveProgress?.showBoss" class="wave-rail" :aria-label="t('sessions.waves')">
              <span
                v-for="n in waveProgress.ticks"
                :key="n"
                class="wave-tick"
                :class="{
                  on: waveProgress.failWave ? n < waveProgress.failWave : true,
                  fail: n === waveProgress.failWave,
                }"
              >{{ n }}</span>
              <span
                v-if="waveProgress.showBoss"
                class="wave-tick boss"
                :class="{ on: waveProgress.bossOn, fail: waveProgress.bossFail }"
              >P</span>
            </div>
          </div>
          <div class="meta-grid">
            <div v-for="row in meta" :key="row.label" class="meta-cell">
              <div class="meta-label">{{ row.label }}</div>
              <div class="meta-value" :class="row.className">
                <DifficultyLabel v-if="row.difficulty" :level="data.difficulty" :at="data.startedAt" />
                <template v-else>{{ row.value }}</template>
              </div>
            </div>
          </div>
        </div>
      </header>

      <p v-if="data.debug" class="debug-banner">{{ t("sessions.debugHint") }}</p>

      <h2 class="section-title">
        {{ t("sessions.squad") }}
        <span v-if="data.players.length" class="count">{{ data.players.length }}</span>
      </h2>
      <p v-if="!data.players.length" class="empty-note">{{ t("sessions.noPlayers") }}</p>
      <div v-else class="squad">
        <router-link
          v-for="p in squad"
          :key="p.steamId || p.name"
          class="squad-card panel"
          :to="playerLink(p.steamId) || '#'"
          :class="{ dead: !playerLink(p.steamId) }"
          @click="!playerLink(p.steamId) && $event.preventDefault()"
        >
          <div class="squad-head">
            <div class="faces">
              <div class="avatar" :class="{ placeholder: !avatarUrl(p.steamId) || avatarFailed[p.steamId] }">
                <img
                  v-if="avatarUrl(p.steamId) && !avatarFailed[p.steamId]"
                  :src="avatarUrl(p.steamId)"
                  alt=""
                  @error="avatarFailed[p.steamId] = true"
                />
                <img v-else class="ph" src="/assets/avatar-skull.svg" alt="" />
              </div>
              <div v-if="skinUrl(p)" class="skin" :title="p.skinName.replace(/_/g, ' ')">
                <img :src="skinUrl(p)" :alt="p.skinName" />
              </div>
            </div>
            <div class="squad-id">
              <div class="squad-name">{{ p.name }}</div>
              <div class="squad-perk">
                <PerkIcon
                  :perk="p.perk"
                  :level="p.perkLevel"
                  :prestige-rank="p.prestigeRank"
                  :size="22"
                />
                <span class="perk-name">{{ perkNameOf(p.perk) }}</span>
                <b v-if="perkLevelText(p.perkLevel)" class="perk-lvl">{{ perkLevelText(p.perkLevel) }}</b>
              </div>
            </div>
          </div>
          <div class="squad-stats">
            <span><b>{{ dash(p.kills) }}</b><em>{{ t("score.kills") }}</em></span>
            <span><b>{{ dash(p.points) }}</b><em>{{ t("sessions.points") }}</em></span>
            <span><b>{{ dash(p.healed) }}</b><em>{{ t("score.healed") }}</em></span>
          </div>
          <div v-if="showStatuses" class="squad-badge">
            <div class="squad-status" :class="badgeOf(p).tone">{{ t(badgeOf(p).key) }}</div>
            <div v-if="badgeHint(badgeOf(p).key)" class="squad-status-hint">{{ badgeHint(badgeOf(p).key) }}</div>
          </div>
        </router-link>
      </div>

      <h2 class="section-title">{{ t("sessions.breakdown") }}</h2>
      <SessionCharts :players="squad" />

      <h2 class="section-title">{{ t("sessions.scoreboard") }}</h2>
      <div class="panel board-panel">
        <table class="board">
          <thead>
            <tr>
              <th class="col-player">{{ t("sessions.player") }}</th>
              <th class="col-perk">{{ t("sessions.perk") }}</th>
              <th class="num">{{ t("sessions.points") }}</th>
              <th class="num">{{ t("score.kills") }}</th>
              <th class="num">{{ t("sessions.scrakes") }}</th>
              <th class="num">{{ t("sessions.fps") }}</th>
              <th class="num">{{ t("sessions.cash") }}</th>
              <th class="num">{{ t("sessions.deaths") }}</th>
              <th class="num">{{ t("sessions.waves") }}</th>
              <th>{{ t("sessions.outcome") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in squad" :key="p.steamId || p.name">
              <td class="col-player">
                <div class="who">
                  <div class="avatar sm" :class="{ placeholder: !avatarUrl(p.steamId) || avatarFailed[p.steamId] }">
                    <img
                      v-if="avatarUrl(p.steamId) && !avatarFailed[p.steamId]"
                      :src="avatarUrl(p.steamId)"
                      alt=""
                      @error="avatarFailed[p.steamId] = true"
                    />
                    <img v-else class="ph" src="/assets/avatar-skull.svg" alt="" />
                  </div>
                  <div v-if="skinUrl(p)" class="skin sm">
                    <img :src="skinUrl(p)" :alt="p.skinName" />
                  </div>
                  <div class="who-text">
                    <router-link v-if="playerLink(p.steamId)" :to="playerLink(p.steamId)">{{ p.name }}</router-link>
                    <span v-else>{{ p.name }}</span>
                    <div class="who-sub">{{ fmtDuration(p.durationSec) }}</div>
                  </div>
                </div>
              </td>
              <td class="col-perk">
                <span class="perk-cell">
                  <PerkIcon
                    :perk="p.perk"
                    :level="p.perkLevel"
                    :prestige-rank="p.prestigeRank"
                    :size="20"
                  />
                  <span class="perk-name">{{ perkNameOf(p.perk) }}</span>
                  <b v-if="perkLevelText(p.perkLevel, true)" class="perk-lvl">{{ perkLevelText(p.perkLevel, true) }}</b>
                </span>
              </td>
              <td class="num">{{ dash(p.points) }}</td>
              <td class="num">{{ dash(p.kills) }}</td>
              <td class="num">{{ dash(p.scrakes) }}</td>
              <td class="num">{{ dash(p.fps) }}</td>
              <td class="num cash">{{ fmtCash(p.cash) }}</td>
              <td class="num">{{ dash(p.deaths) }}</td>
              <td class="num">{{ playerWaveText(p, data.finalWave) }}</td>
              <td>
                <span class="outcome" :class="outcomeClass(p.outcome)">{{ outcomeLabel(p.outcome) }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <h2 class="section-title">{{ t("sessions.moreStats") }}</h2>
      <div class="panel more-panel">
        <table class="board more">
          <thead>
            <tr>
              <th class="col-player">{{ t("sessions.player") }}</th>
              <th class="num">{{ t("score.healed") }}</th>
              <th class="num">{{ t("score.welded") }}</th>
              <th class="num">{{ t("sessions.bloats") }}</th>
              <th class="num">{{ t("sessions.sirens") }}</th>
              <th class="num">{{ t("sessions.husks") }}</th>
              <th class="num">{{ t("sessions.joinWave") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in squad" :key="'m' + (p.steamId || p.name)">
              <td class="col-player">
                <router-link v-if="playerLink(p.steamId)" :to="playerLink(p.steamId)">{{ p.name }}</router-link>
                <span v-else>{{ p.name }}</span>
              </td>
              <td class="num">{{ dash(p.healed) }}</td>
              <td class="num">{{ dash(p.welded) }}</td>
              <td class="num">{{ dash(p.bloats) }}</td>
              <td class="num">{{ dash(p.sirens) }}</td>
              <td class="num">{{ dash(p.husks) }}</td>
              <td class="num">{{ dash(p.joinWave) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="hint">{{ t("sessions.scoreboardHint") }}</p>
    </template>
  </div>
</template>

<style scoped>
.page { font-size: 16px; }
.back { margin: 0 0 14px; font-size: 15px; }
.back a {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-dim);
}
.back a svg { flex: none; }
.back a:hover { color: #fff; }
.state-note { padding: 32px 0; }
.state-note h2 { margin: 0 0 10px; font-family: var(--font-display); }

.hero {
  position: relative;
  overflow: hidden;
  min-height: 200px;
  margin-bottom: 14px;
  padding: 0;
  border: 1px solid var(--border);
}
.hero.debug { border-color: var(--gold); }
.hero-shot {
  display: block;
  width: 240px;
  max-width: 100%;
  aspect-ratio: 16 / 9;
  height: auto;
  object-fit: cover;
  border: 1px solid var(--border-bright);
  background: #0b0b0e;
}
.hero-bg {
  position: absolute;
  inset: -20px;
  background: #0b0b0e center/cover no-repeat;
  filter: blur(10px) saturate(0.85);
  transform: scale(1.04);
}
.hero-shade {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(90deg, rgba(10, 10, 12, 0.92) 0%, rgba(10, 10, 12, 0.72) 55%, rgba(10, 10, 12, 0.35) 100%),
    linear-gradient(0deg, rgba(10, 10, 12, 0.82) 0%, rgba(10, 10, 12, 0.35) 42%, transparent 70%);
}
.hero-body {
  position: relative;
  z-index: 1;
  padding: 22px 24px 0;
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-height: 220px;
}
.hero-main {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 720px;
}
.hero-badges { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.pill {
  display: inline-block;
  padding: 4px 11px;
  font-family: var(--font-display);
  font-size: 14px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  border: 1px solid var(--border-bright);
  background: rgba(0, 0, 0, 0.35);
}
.pill.win { color: var(--green); border-color: rgba(143, 209, 106, 0.45); }
.pill.loss { color: #e07070; border-color: rgba(224, 112, 112, 0.45); }
.pill.playing { color: var(--gold-bright); border-color: rgba(232, 181, 60, 0.45); }
.pill.debug { color: var(--gold-bright); border-color: var(--gold); background: rgba(199, 139, 18, 0.12); }
.hero-main .join {
  align-self: flex-start;
  display: inline-block;
  padding: 4px 12px 3px;
  font-family: var(--font-display);
  font-size: 14px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #fff;
  text-decoration: none;
  background: var(--accent-deep);
  border: 1px solid var(--accent-deep);
}
.hero-main .join:hover { color: #fff; text-decoration: none; filter: brightness(1.12); }
.hero-title {
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(34px, 5.2vw, 50px);
  letter-spacing: 0.04em;
  font-weight: 500;
  line-height: 1.05;
  text-transform: uppercase;
}
.wave-rail { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.wave-tick {
  min-width: 30px;
  height: 28px;
  padding: 0 7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-display);
  font-size: 14px;
  letter-spacing: 0.04em;
  color: var(--text-faint);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border);
}
.wave-tick.on {
  color: var(--green);
  border-color: rgba(143, 209, 106, 0.5);
  background: rgba(143, 209, 106, 0.14);
}
.wave-tick.fail {
  color: #fff;
  border-color: var(--accent-deep);
  background: rgba(198, 18, 23, 0.28);
}
.wave-tick.boss.on { color: var(--gold-bright); border-color: var(--gold); background: rgba(199, 139, 18, 0.18); }
.wave-tick.boss.fail {
  color: #fff;
  border-color: var(--accent-deep);
  background: rgba(198, 18, 23, 0.28);
}

.debug-banner {
  margin: 0 0 14px;
  padding: 10px 14px;
  border: 1px solid rgba(199, 139, 18, 0.45);
  background: rgba(199, 139, 18, 0.08);
  color: var(--gold-bright);
  font-size: 14.5px;
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: 12px 16px;
  margin: 0 -24px;
  padding: 14px 24px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}
.meta-label {
  font-family: var(--font-display);
  font-size: 12px;
  letter-spacing: 0.112em;
  text-transform: uppercase;
  color: var(--text-faint);
  margin-bottom: 3px;
}
.meta-value { font-size: 16px; color: var(--text); }
.meta-value.win, .outcome.win { color: var(--green); }
.meta-value.loss, .outcome.loss { color: #e07070; }
.meta-value.leave, .outcome.leave { color: var(--text-dim); }
.meta-value.playing, .outcome.playing { color: var(--gold-bright); }
.outcome { font-weight: 600; }

.squad {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px;
  margin-bottom: 18px;
}
.squad-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 12px;
  text-decoration: none;
  color: inherit;
  min-width: 0;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.squad-card:hover { border-color: var(--border-bright); background: var(--panel-2); text-decoration: none; color: inherit; }
.squad-card.dead { cursor: default; }
.squad-head {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.faces { display: flex; gap: 4px; flex: none; }
.avatar {
  width: 56px;
  height: 56px;
  border: 1px solid var(--border-bright);
  background: #0b0b0e;
  overflow: hidden;
  flex: none;
}
.avatar img { width: 100%; height: 100%; object-fit: cover; display: block; }
.avatar .ph { width: 100%; height: 100%; margin: 0; object-fit: cover; opacity: 0.82; }
.avatar.placeholder { display: flex; align-items: center; justify-content: center; }
.avatar.sm { width: 36px; height: 36px; }
.skin {
  width: 40px;
  height: 56px;
  border: 1px solid var(--border);
  background: #0b0b0e;
  overflow: hidden;
  flex: none;
}
.skin img { width: 100%; height: 100%; object-fit: cover; object-position: top center; display: block; }
.skin.sm { width: 26px; height: 36px; }
.squad-id { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 3px; justify-content: center; }
.squad-badge {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  text-align: center;
  min-width: 0;
}
.squad-status {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  line-height: 1.1;
  max-width: 100%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.squad-status.glory { color: var(--gold-bright); }
.squad-status.support { color: var(--green); }
.squad-status.hunt { color: #f0a050; }
.squad-status.muted { color: var(--text-dim); }
.squad-status-hint {
  color: var(--text-faint);
  font-size: 12px;
  line-height: 1.3;
  max-width: 100%;
}
.squad-name {
  font-family: var(--font-display);
  font-size: 20px;
  letter-spacing: 0.04em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.squad-perk {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-dim);
  font-size: 14px;
  min-width: 0;
}
.squad-perk .perk-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.perk-lvl {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--text);
  flex: none;
}
.squad-perk .perk-lvl {
  margin-left: auto;
  font-size: 12px;
  letter-spacing: 0.06em;
  line-height: 1.05;
}
.squad-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px 10px;
  font-size: 12px;
  color: var(--text-dim);
  text-align: center;
}
.squad-stats > span {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  min-width: 0;
}
.squad-stats b {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: #fff;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
.squad-stats em {
  font-style: normal;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.board-panel, .more-panel { padding: 0; overflow: hidden; }
.board {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: clamp(12.5px, 1.25vw, 15px);
}
.board th, .board td {
  text-align: left;
  padding: 9px 9px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.board th {
  font-family: var(--font-display);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-faint);
  font-weight: 400;
}
.board tbody tr:hover { background: rgba(255, 255, 255, 0.025); }
.board .num { font-variant-numeric: tabular-nums; text-align: right; }
.board .cash { color: #ffe07d; }
.board a { color: var(--text); }
.board a:hover { color: #fff; }
.col-player { width: 28%; }
.col-perk { width: 14%; }
.who { display: flex; align-items: center; gap: 6px; min-width: 0; }
.who-text { min-width: 0; overflow: hidden; }
.who-text a, .who-text > span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.who-sub { color: var(--text-faint); font-size: 12.5px; }
.perk-cell {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
  max-width: 100%;
  min-width: 0;
}
.perk-cell .perk-badge { align-self: center; }
.perk-cell .perk-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.perk-cell .perk-lvl { font-size: 14px; }
.hint {
  margin: 10px 0 0;
  color: var(--text-faint);
  font-size: 13.5px;
}

@media (max-width: 720px) {
  .board .col-perk,
  .board th.col-perk,
  .board td.col-perk { display: none; }
  .col-player { width: 36%; }
  .skin:not(.sm) { display: none; }
}
</style>
