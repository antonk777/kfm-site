<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

export interface LineSeries {
  label: string;
  color: string;
  values: (number | null)[];
  tips?: (string | null)[];
  axis?: "left" | "right";
  dash?: boolean;
}

const props = defineProps<{
  labels: string[];
  series: LineSeries[];
  leftMin?: number;
  leftMax?: number;
  rightMax?: number;
  formatLeft?: (n: number) => string;
  formatRight?: (n: number) => string;
}>();

const VB_H = 220;
const PAD = { l: 46, r: 46, t: 12, b: 26 };
const box = ref<HTMLElement | null>(null);
const plotW = ref(800);
let observer: ResizeObserver | undefined;

function measure(): void {
  const w = box.value?.clientWidth ?? 0;
  if (w > 0) plotW.value = Math.max(320, Math.round(w));
}

const hover = ref<number | null>(null);

function fmtLeft(n: number): string {
  return props.formatLeft ? props.formatLeft(n) : String(Math.round(n));
}
function fmtRight(n: number): string {
  return props.formatRight ? props.formatRight(n) : String(Math.round(n));
}

function extent(axis: "left" | "right"): { min: number; max: number } {
  const min = axis === "left" ? (props.leftMin ?? 0) : 0;
  const forced = axis === "left" ? props.leftMax : props.rightMax;
  if (forced != null) return { min, max: forced };
  let max = min;
  for (const s of props.series) {
    if ((s.axis ?? "left") !== axis) continue;
    for (const v of s.values) {
      if (v != null && Number.isFinite(v)) max = Math.max(max, v);
    }
  }
  if (max <= min) max = min + 1;
  return { min, max };
}

const hasRight = computed(() => props.series.some((s) => s.axis === "right" && s.values.some((v) => v != null)));
const left = computed(() => extent("left"));
const right = computed(() => extent("right"));
const innerW = computed(() => plotW.value - PAD.l - (hasRight.value ? PAD.r : 12));
const innerH = VB_H - PAD.t - PAD.b;

function xAt(i: number): number {
  const n = props.labels.length;
  if (n <= 1) return PAD.l + innerW.value / 2;
  return PAD.l + (i / (n - 1)) * innerW.value;
}

function yAt(v: number, axis: "left" | "right"): number {
  const box = axis === "right" ? right.value : left.value;
  const span = box.max - box.min || 1;
  return PAD.t + (1 - (v - box.min) / span) * innerH;
}

function linePath(s: LineSeries): string {
  const axis = s.axis ?? "left";
  const parts: string[] = [];
  s.values.forEach((v, i) => {
    if (v == null || !Number.isFinite(v)) return;
    const cmd = parts.length ? "L" : "M";
    parts.push(`${cmd}${xAt(i).toFixed(1)} ${yAt(v, axis).toFixed(1)}`);
  });
  return parts.join(" ");
}

const yTicks = computed(() => [0, 0.25, 0.5, 0.75, 1].map((f) => left.value.min + (left.value.max - left.value.min) * f));
const xTicks = computed(() => {
  const n = props.labels.length;
  if (!n) return [];
  const count = Math.min(6, n);
  const out: number[] = [];
  for (let i = 0; i < count; i++) out.push(Math.round((i * (n - 1)) / Math.max(1, count - 1)));
  return [...new Set(out)];
});

const tipStyle = computed(() => {
  if (hover.value == null || !props.labels.length) return {};
  const pct = (xAt(hover.value) / plotW.value) * 100;
  if (pct > 68) return { left: `${pct}%`, transform: "translateX(-100%)" };
  return { left: `${pct}%` };
});

function tipValue(s: LineSeries, i: number): string {
  const custom = s.tips?.[i];
  if (custom) return custom;
  const v = s.values[i];
  if (v == null || !Number.isFinite(v)) return "—";
  return (s.axis === "right" ? fmtRight : fmtLeft)(v);
}

onMounted(() => {
  measure();
  if (!box.value || typeof ResizeObserver === "undefined") return;
  observer = new ResizeObserver(measure);
  observer.observe(box.value);
});
onBeforeUnmount(() => observer?.disconnect());

function onMove(event: PointerEvent): void {
  const svg = event.currentTarget as SVGSVGElement;
  const rect = svg.getBoundingClientRect();
  if (!rect.width || props.labels.length < 1) return;
  const x = ((event.clientX - rect.left) / rect.width) * plotW.value;
  const n = props.labels.length;
  const t = (x - PAD.l) / innerW.value;
  const i = n <= 1 ? 0 : Math.round(t * (n - 1));
  hover.value = Math.max(0, Math.min(n - 1, i));
}
</script>

<template>
  <div ref="box" class="chart">
    <p v-if="!labels.length" class="empty-note">—</p>
    <svg
      v-else
      :viewBox="`0 0 ${plotW} ${VB_H}`"
      preserveAspectRatio="none"
      @pointermove="onMove"
      @pointerleave="hover = null"
    >
      <line
        v-for="(tick, i) in yTicks"
        :key="'g' + i"
        :x1="PAD.l"
        :x2="PAD.l + innerW"
        :y1="yAt(tick, 'left')"
        :y2="yAt(tick, 'left')"
        stroke="var(--border)"
      />
      <text
        v-for="(tick, i) in yTicks"
        :key="'yl' + i"
        :x="PAD.l - 6"
        :y="yAt(tick, 'left') + 3"
        text-anchor="end"
        fill="var(--text-faint)"
      >{{ fmtLeft(tick) }}</text>
      <text
        v-for="(tick, i) in (hasRight ? yTicks : [])"
        :key="'yr' + i"
        :x="PAD.l + innerW + 6"
        :y="yAt(right.min + (right.max - right.min) * (i / 4), 'right') + 3"
        text-anchor="start"
        fill="#e6a05c"
      >{{ fmtRight(right.min + (right.max - right.min) * (i / 4)) }}</text>
      <text
        v-for="i in xTicks"
        :key="'x' + i"
        :x="xAt(i)"
        :y="VB_H - 6"
        text-anchor="middle"
        fill="var(--text-faint)"
      >{{ labels[i] }}</text>
      <path
        v-for="(s, i) in series"
        :key="s.label + i"
        :d="linePath(s)"
        fill="none"
        :stroke="s.color"
        stroke-width="2"
        :stroke-dasharray="s.dash ? '4 3' : undefined"
      />
      <line
        v-if="hover != null"
        :x1="xAt(hover)"
        :x2="xAt(hover)"
        :y1="PAD.t"
        :y2="PAD.t + innerH"
        stroke="var(--border-bright)"
      />
      <template v-if="hover != null">
        <circle
          v-for="(s, i) in series"
          :key="'d' + i"
          v-show="s.values[hover] != null"
          :cx="xAt(hover)"
          :cy="yAt(s.values[hover] ?? 0, s.axis ?? 'left')"
          r="3"
          :fill="s.color"
        />
      </template>
    </svg>
    <div v-if="hover != null" class="tip" :style="tipStyle">
      <b>{{ labels[hover] }}</b>
      <div v-for="(s, i) in series" :key="i">
        <i :style="{ background: s.color }" />
        <span>{{ s.label }}</span>
        <em>{{ tipValue(s, hover) }}</em>
      </div>
    </div>
    <ul v-if="series.length" class="series-key">
      <li v-for="(s, i) in series" :key="i"><i :style="{ background: s.color }" />{{ s.label }}</li>
    </ul>
  </div>
</template>

<style scoped>
.chart { position: relative; }
svg { display: block; width: 100%; height: 220px; touch-action: none; }
text { font-size: 11px; font-family: var(--font-body); }
.empty-note { margin: 12px; }
.tip {
  position: absolute;
  top: 8px;
  z-index: 2;
  min-width: 160px;
  padding: 8px 10px;
  background: rgba(16, 16, 20, 0.96);
  border: 1px solid var(--border-bright);
  border-radius: 4px;
  pointer-events: none;
  font-size: 12px;
}
.tip b { display: block; margin-bottom: 4px; }
.tip div { display: flex; align-items: center; gap: 6px; }
.tip i { width: 8px; height: 8px; border-radius: 2px; flex: none; }
.tip em { margin-left: auto; font-style: normal; color: #fff; }
.series-key {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  margin: 0;
  padding: 0 8px 8px;
  list-style: none;
  color: var(--text-dim);
  font-size: 12px;
}
.series-key li { display: flex; align-items: center; gap: 6px; }
.series-key i { width: 10px; height: 10px; border-radius: 2px; display: block; }
</style>
