<script setup lang="ts">
import type { RecentSessionInfo, RecentSessionPlayer } from "../api";
import { t } from "../i18n";
import { fmtDate, prettyMap } from "../lib/format";
import DifficultyLabel from "./DifficultyLabel.vue";

defineProps<{ sessions: RecentSessionInfo[] }>();

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
  if (o === "playing") return "playing";
  return "unknown";
}

function outcomeLabel(o: string): string {
  const key = `outcome.${o}`;
  const label = t(key);
  return label === key ? o : label;
}

function waveText(s: RecentSessionInfo): string {
  const w = Math.max(0, s.wave);
  const f = s.finalWave || 0;
  const boss = s.outcome === "win" || s.outcome === "victory" || (f > 0 && w > f);
  if (boss) return t("sessions.boss");
  if (!w && !f) return "—";
  return `${w}/${f || "?"}`;
}

function perkNameOf(id: string): string {
  if (!id) return "";
  const key = `perk.${id}`;
  const label = t(key);
  return label === key ? id.replace(/_/g, " ") : label;
}

function playerLink(p: RecentSessionPlayer): string {
  return /^\d{16,20}$/.test(p.steamId) ? `/players/${p.steamId}` : "";
}

function sessionLink(s: RecentSessionInfo): string {
  return s.id > 0 ? `/sessions/${s.id}` : "";
}
</script>

<template>
  <div class="panel sessions-panel">
    <table class="sessions-table">
      <thead>
        <tr>
          <th>{{ t("sessions.map") }}</th>
          <th>{{ t("sessions.difficulty") }}</th>
          <th>{{ t("sessions.date") }}</th>
          <th>{{ t("sessions.outcome") }}</th>
          <th>{{ t("srv.players") }}</th>
          <th>{{ t("sessions.waves") }}</th>
          <th>{{ t("sessions.duration") }}</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(s, i) in sessions"
          :key="s.id || `${s.server}-${s.map}-${s.startedAt}-${i}`"
          :class="{ link: !!sessionLink(s) }"
          @click="sessionLink(s) && $router.push(sessionLink(s))"
        >
          <td>
            <div class="map-cell">
              <img
                v-if="s.hasMapImage"
                class="map-thumb"
                :src="`/maps/${encodeURIComponent(s.map)}.jpg`"
                :alt="prettyMap(s.mapPretty || s.map)"
                loading="lazy"
              />
              <div>
                <div>
                  <router-link
                    v-if="sessionLink(s)"
                    class="map-link"
                    :to="sessionLink(s)"
                    @click.stop
                  >{{ prettyMap(s.mapPretty || s.map) }}</router-link>
                  <template v-else>{{ prettyMap(s.mapPretty || s.map) }}</template>
                </div>
                <div v-if="s.server" class="map-sub">{{ s.server }}</div>
              </div>
            </div>
          </td>
          <td class="nowrap"><DifficultyLabel :level="s.difficulty" :at="s.startedAt" /></td>
          <td class="nowrap">{{ fmtDate(s.startedAt) }}</td>
          <td>
            <span class="outcome" :class="outcomeClass(s.outcome)">{{ outcomeLabel(s.outcome) }}</span>
          </td>
          <td>
            <div v-if="s.players.length" class="squad" @click.stop>
              <span v-for="(p, i) in s.players" :key="p.steamId || p.name" class="member">
                <router-link v-if="playerLink(p)" :to="playerLink(p)" :title="perkNameOf(p.perk)">{{ p.name }}</router-link>
                <span v-else class="name" :title="perkNameOf(p.perk)">{{ p.name }}</span><span v-if="i < s.players.length - 1" class="sep">,&nbsp;</span>
              </span>
            </div>
            <span v-else>—</span>
          </td>
          <td class="nowrap">{{ waveText(s) }}</td>
          <td class="nowrap">{{ fmtDuration(s.durationSec) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.sessions-panel { overflow-x: auto; }
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
.sessions-table .nowrap { white-space: nowrap; }
.map-cell { display: flex; align-items: center; gap: 10px; min-width: 210px; }
.map-thumb {
  width: 76px;
  height: 44px;
  object-fit: cover;
  border: 1px solid var(--border);
  background: #0b0b0e;
  flex: none;
}
.map-link { color: var(--text); text-decoration: none; }
.map-link:hover { color: #fff; }
.map-sub { color: var(--text-faint); font-size: 11.5px; }
.outcome { font-weight: 600; }
.outcome.win { color: var(--green); }
.outcome.loss { color: #e07070; }
.outcome.leave { color: var(--text-dim); }
.outcome.playing { color: var(--gold-bright); }
.outcome.unknown { color: var(--text-faint); }
.squad { display: flex; flex-wrap: wrap; gap: 2px 0; max-width: 280px; }
.squad .member { display: inline; }
.squad a, .squad .name { color: var(--text); }
.squad a:hover { color: #fff; }
.squad .sep { color: var(--text-faint); }
</style>
