<script setup lang="ts">
import { computed } from "vue";
import type { SessionDetailPlayer } from "../api";
import { t } from "../i18n";

const props = defineProps<{ players: SessionDetailPlayer[] }>();

const PALETTE = ["#c61217", "#e8b53c", "#5cc8e6", "#8fd16a", "#c78b12", "#e07070", "#7a8cff", "#d8d2c4"];

interface Slice {
  label: string;
  value: number;
  color: string;
  start: number;
  end: number;
}

function slicesFor(pick: (p: SessionDetailPlayer) => number): Slice[] {
  const rows = props.players
    .map((p, i) => ({ label: p.name, value: Math.max(0, pick(p)), color: PALETTE[i % PALETTE.length] }))
    .filter((r) => r.value > 0)
    .sort((a, b) => b.value - a.value);
  const total = rows.reduce((a, r) => a + r.value, 0);
  if (!total) return [];
  let angle = -Math.PI / 2;
  return rows.map((r) => {
    const sweep = (r.value / total) * Math.PI * 2;
    const slice: Slice = { ...r, start: angle, end: angle + sweep };
    angle += sweep;
    return slice;
  });
}

function arcPath(s: Slice, r = 42, cx = 50, cy = 50): string {
  const x1 = cx + r * Math.cos(s.start);
  const y1 = cy + r * Math.sin(s.start);
  const x2 = cx + r * Math.cos(s.end);
  const y2 = cy + r * Math.sin(s.end);
  const large = s.end - s.start > Math.PI ? 1 : 0;
  if (Math.abs(s.end - s.start) >= Math.PI * 2 - 1e-6) {
    return `M ${cx} ${cy - r} A ${r} ${r} 0 1 1 ${cx - 0.01} ${cy - r} Z`;
  }
  return `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`;
}

const killSlices = computed(() => slicesFor((p) => p.kills));
const pointSlices = computed(() => slicesFor((p) => p.points));

const bigZedBars = computed(() => {
  const rows = props.players.map((p, i) => ({
    label: p.name,
    scrakes: p.scrakes,
    fps: p.fps,
    color: PALETTE[i % PALETTE.length],
  }));
  const max = Math.max(1, ...rows.map((r) => r.scrakes + r.fps));
  return { rows, max };
});

const PERK_IDS = [
  "Field_Medic",
  "Support_Specialist",
  "Sharpshooter",
  "Commando",
  "Berserker",
  "Firebug",
  "Demolition",
];

function perkLabel(raw: string): string {
  if (!raw) return "?";
  const underscored = raw.replace(/\s+/g, "_");
  const lower = raw.toLowerCase().replace(/[\s_]+/g, "");
  const canon =
    PERK_IDS.find((id) => id === raw || id === underscored) ||
    PERK_IDS.find((id) => id.toLowerCase().replace(/_/g, "") === lower) ||
    underscored;
  const key = `perk.${canon}`;
  const label = t(key);
  return label === key ? canon.replace(/_/g, " ") : label;
}

const perkSlices = computed(() => {
  const counts = new Map<string, number>();
  for (const p of props.players) {
    const key = perkLabel(p.perk || "?");
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  const rows = [...counts.entries()]
    .map(([label, value], i) => ({ label, value, color: PALETTE[i % PALETTE.length] }))
    .filter((r) => r.value > 0)
    .sort((a, b) => b.value - a.value);
  const total = rows.reduce((a, r) => a + r.value, 0);
  if (!total) return [];
  let angle = -Math.PI / 2;
  return rows.map((r) => {
    const sweep = (r.value / total) * Math.PI * 2;
    const slice: Slice = { ...r, start: angle, end: angle + sweep };
    angle += sweep;
    return slice;
  });
});

const hasCombat = computed(
  () => killSlices.value.length > 0 || pointSlices.value.length > 0 || bigZedBars.value.rows.some((r) => r.scrakes + r.fps > 0),
);

function pct(value: number, slices: Slice[]): string {
  const total = slices.reduce((a, s) => a + s.value, 0);
  if (!total) return "0%";
  return `${Math.round((value / total) * 100)}%`;
}
</script>

<template>
  <div v-if="players.length" class="charts">
    <div class="chart-card panel">
      <h3>{{ t("sessions.chartKills") }}</h3>
      <template v-if="killSlices.length">
        <div class="pie-row">
          <svg viewBox="0 0 100 100" class="pie" aria-hidden="true">
            <path v-for="(s, i) in killSlices" :key="i" :d="arcPath(s)" :fill="s.color" />
            <circle cx="50" cy="50" r="22" fill="var(--panel)" />
          </svg>
          <ul class="legend">
            <li v-for="(s, i) in killSlices" :key="i">
              <i :style="{ background: s.color }" />
              <span class="name">{{ s.label }}</span>
              <b>{{ s.value }}</b>
              <em>{{ pct(s.value, killSlices) }}</em>
            </li>
          </ul>
        </div>
      </template>
      <p v-else class="empty">{{ t("sessions.chartEmpty") }}</p>
    </div>

    <div class="chart-card panel">
      <h3>{{ t("sessions.chartPoints") }}</h3>
      <template v-if="pointSlices.length">
        <div class="pie-row">
          <svg viewBox="0 0 100 100" class="pie" aria-hidden="true">
            <path v-for="(s, i) in pointSlices" :key="i" :d="arcPath(s)" :fill="s.color" />
            <circle cx="50" cy="50" r="22" fill="var(--panel)" />
          </svg>
          <ul class="legend">
            <li v-for="(s, i) in pointSlices" :key="i">
              <i :style="{ background: s.color }" />
              <span class="name">{{ s.label }}</span>
              <b>{{ s.value }}</b>
              <em>{{ pct(s.value, pointSlices) }}</em>
            </li>
          </ul>
        </div>
      </template>
      <p v-else class="empty">{{ t("sessions.chartEmpty") }}</p>
    </div>

    <div class="chart-card panel">
      <h3>{{ t("sessions.chartBigZeds") }}</h3>
      <template v-if="hasCombat && bigZedBars.rows.some((r) => r.scrakes + r.fps > 0)">
        <div class="bars">
          <div v-for="(r, i) in bigZedBars.rows" :key="i" class="bar-row">
            <div class="bar-label">{{ r.label }}</div>
            <div class="bar-track">
              <span class="seg scrake" :style="{ width: `${(r.scrakes / bigZedBars.max) * 100}%` }" :title="`Scrakes ${r.scrakes}`" />
              <span class="seg fp" :style="{ width: `${(r.fps / bigZedBars.max) * 100}%` }" :title="`FPs ${r.fps}`" />
            </div>
            <div class="bar-val">{{ r.scrakes + r.fps }}</div>
          </div>
        </div>
        <div class="bar-key">
          <span><i class="scrake" /> {{ t("sessions.scrakes") }}</span>
          <span><i class="fp" /> {{ t("sessions.fps") }}</span>
        </div>
      </template>
      <p v-else class="empty">{{ t("sessions.chartEmpty") }}</p>
    </div>

    <div class="chart-card panel">
      <h3>{{ t("sessions.chartPerks") }}</h3>
      <template v-if="perkSlices.length">
        <div class="pie-row">
          <svg viewBox="0 0 100 100" class="pie" aria-hidden="true">
            <path v-for="(s, i) in perkSlices" :key="i" :d="arcPath(s)" :fill="s.color" />
            <circle cx="50" cy="50" r="22" fill="var(--panel)" />
          </svg>
          <ul class="legend">
            <li v-for="(s, i) in perkSlices" :key="i">
              <i :style="{ background: s.color }" />
              <span class="name">{{ s.label }}</span>
              <b>{{ s.value }}</b>
              <em>{{ pct(s.value, perkSlices) }}</em>
            </li>
          </ul>
        </div>
      </template>
      <p v-else class="empty">{{ t("sessions.chartEmpty") }}</p>
    </div>
  </div>
</template>

<style scoped>
.charts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 0 0 22px;
}
.chart-card { padding: 14px 16px 16px; min-width: 0; }
.chart-card h3 {
  margin: 0 0 12px;
  font-family: var(--font-display);
  font-size: 16px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-faint);
  font-weight: 400;
}
.pie-row { display: flex; gap: 14px; align-items: center; min-width: 0; }
.pie { width: 110px; height: 110px; flex: none; }
.legend { list-style: none; margin: 0; padding: 0; flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.legend li {
  display: grid;
  grid-template-columns: 10px minmax(0, 1fr) auto auto;
  gap: 8px;
  align-items: center;
  font-size: 14px;
}
.legend i { width: 10px; height: 10px; border-radius: 2px; display: block; }
.legend .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.legend b { font-variant-numeric: tabular-nums; color: #fff; }
.legend em { font-style: normal; color: var(--text-faint); width: 2.6em; text-align: right; }
.bars { display: flex; flex-direction: column; gap: 8px; }
.bar-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 2.2fr) auto; gap: 8px; align-items: center; font-size: 14px; }
.bar-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bar-track {
  display: flex;
  height: 12px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border);
  overflow: hidden;
}
.bar-track .seg { display: block; height: 100%; min-width: 0; }
.bar-track .scrake { background: var(--gold); }
.bar-track .fp { background: var(--accent); }
.bar-val { font-variant-numeric: tabular-nums; color: var(--text-dim); min-width: 1.5em; text-align: right; }
.bar-key { display: flex; gap: 14px; margin-top: 10px; font-size: 13px; color: var(--text-faint); }
.bar-key i { display: inline-block; width: 10px; height: 10px; margin-right: 5px; vertical-align: -1px; }
.bar-key i.scrake { background: var(--gold); }
.bar-key i.fp { background: var(--accent); }
.empty { margin: 18px 0 8px; color: var(--text-faint); font-size: 14px; }
@media (max-width: 900px) {
  .charts { grid-template-columns: 1fr; }
}
</style>
