<script setup lang="ts">
import { computed } from "vue";
import { t } from "~/i18n";
import ServerCardIcon from "./ServerCardIcon.vue";

export interface CardLoad {
  scope: "process" | "host";
  now: {
    cpu?: number | null;
    cpu_seconds?: number;
    core_pct?: number;
    mem?: number | null;
    mem_mb?: number | null;
    net_mbps?: number | null;
  } | null;
}

const props = defineProps<{ load?: CardLoad; remote?: boolean }>();
const isProcess = computed(() => props.load ? props.load.scope === "process" : !props.remote);
const scopeLabel = computed(() => t(isProcess.value ? "dash.process" : "dash.host"));

function metric(label: string, short: string, value: number | null | undefined, unit: string, reference: number) {
  const ratio = value == null ? -1 : value / reference;
  const tone = ratio < 0 ? "unknown" : ratio >= 0.9 ? "high" : ratio >= 0.7 ? "warn" : "good";
  return {
    label: t(label), short: t(short), ratio, tone,
    value: value == null ? "—" : Number(value.toFixed(2)) + unit,
    hint: t("dash.loadReference", { n: reference + unit }),
  };
}
const rows = computed(() => {
  const now = props.load?.now;
  const proc = isProcess.value;
  return [
    metric(proc ? "dash.coreLoad" : "dash.cpu", "dash.cpu", proc ? now?.core_pct : now?.cpu, "%", 100),
    metric(proc ? "dash.memoryRss" : "dash.memory", "dash.memory", proc ? now?.mem_mb : now?.mem, proc ? " MiB" : "%", proc ? 1024 : 100),
    metric(proc && !props.remote ? "dash.udpTraffic" : "dash.network", "dash.network", now?.net_mbps, " Mbit/s", proc ? 20 : 100),
  ];
});
const worst = computed(() => rows.value.reduce((a, b) => a.ratio >= b.ratio ? a : b));
const summary = computed(() => {
  if (worst.value.ratio < 0) return t("dash.health.unknown");
  const cpu = rows.value[0]!;
  const row = worst.value.tone === "good" && cpu.ratio >= 0 ? cpu : worst.value;
  return t("dash.load." + worst.value.tone) + " · " + row.short + " " + row.value;
});
const cpuTime = computed(() => {
  const n = props.load?.now?.cpu_seconds;
  if (n == null) return "—";
  return [Math.floor(n / 3600), Math.floor(n / 60) % 60, Math.floor(n) % 60]
    .map(v => String(v).padStart(2, "0")).join(":");
});
</script>

<template>
  <details class="status-row">
    <summary>
      <ServerCardIcon name="load" /><span class="row-label">{{ t("dash.load") }} <small v-if="load">{{ scopeLabel }}</small></span>
      <span class="reading" :data-level="worst.tone"><i />{{ summary }}</span><ServerCardIcon name="chevron" class="chevron" />
    </summary>
    <dl class="facts">
      <template v-for="(row, index) in rows" :key="row.label">
        <div><dt>{{ row.label }}</dt><dd :data-level="row.tone" :title="row.hint">{{ row.value }}</dd></div>
        <div v-if="index === 0 && isProcess"><dt>{{ t("dash.cpuTime") }}</dt><dd>{{ cpuTime }}</dd></div>
      </template>
    </dl>
  </details>
</template>
