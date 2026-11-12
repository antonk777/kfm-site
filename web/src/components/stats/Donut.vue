<script setup lang="ts">
import { computed } from "vue";

const PALETTE = ["#c61217", "#e8b53c", "#5cc8e6", "#8fd16a", "#c78b12", "#e07070", "#7a8cff", "#d8d2c4", "#c9a0ff", "#5ce6b8", "#e68a5c", "#e65ca8"];

const props = defineProps<{ items: { name: string; c: number }[] }>();

interface Slice {
  label: string;
  value: number;
  color: string;
  start: number;
  end: number;
}

const slices = computed<Slice[]>(() => {
  const rows = props.items
    .map((item, i) => ({
      label: item.name,
      value: Math.max(0, item.c),
      color: PALETTE[i % PALETTE.length] ?? "#c61217",
    }))
    .filter((row) => row.value > 0);
  const total = rows.reduce((sum, row) => sum + row.value, 0);
  if (!total) return [];
  let angle = -Math.PI / 2;
  return rows.map((row) => {
    const sweep = (row.value / total) * Math.PI * 2;
    const slice: Slice = { ...row, start: angle, end: angle + sweep };
    angle += sweep;
    return slice;
  });
});

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

function pct(value: number): string {
  const total = slices.value.reduce((sum, s) => sum + s.value, 0);
  if (!total) return "0%";
  return `${Math.round((value / total) * 100)}%`;
}
</script>

<template>
  <div v-if="slices.length" class="pie-row">
    <svg viewBox="0 0 100 100" class="pie" aria-hidden="true">
      <path v-for="(s, i) in slices" :key="i" :d="arcPath(s)" :fill="s.color" />
      <circle cx="50" cy="50" r="22" fill="var(--panel)" />
    </svg>
    <ul class="legend">
      <li v-for="(s, i) in slices" :key="i">
        <i :style="{ background: s.color }" />
        <span class="name">{{ s.label }}</span>
        <b>{{ s.value }}</b>
        <em>{{ pct(s.value) }}</em>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.pie-row { display: flex; gap: 14px; align-items: center; min-width: 0; }
.pie { width: 110px; height: 110px; flex: none; }
.legend {
  list-style: none;
  margin: 0;
  padding: 0;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
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
</style>
