<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import DifficultyLabel from "~/components/DifficultyLabel.vue";
import PerkIcon from "~/components/PerkIcon.vue";
import Donut from "~/components/stats/Donut.vue";
import LineChart, { type LineSeries } from "~/components/stats/LineChart.vue";
import SteamMark from "~/components/SteamMark.vue";
import { countryName } from "~/data/countries";
import { i18n, t } from "~/i18n";
import { fmtNum, prettyMap } from "~/lib/format";
import { PERK_IDS, canonPerkId } from "~/lib/perkLevel";
import { loadSteamUser, steamReady, steamUser } from "~/lib/steam";

interface CountItem {
  name: string;
  c: number;
}
interface ServerTab {
  name: string;
  label?: string;
  remote?: boolean;
  vps?: string;
}
interface Summary {
  serverTabs?: ServerTab[];
  vpsHosts?: { id: string; label: string }[];
  days: number[];
  peak: number[];
  unique: number[];
  retention_d1: (number | null)[];
  retention_d7: (number | null)[];
  avg_playtime_sec: (number | null)[];
  downloads?: number[];
  downloadsTotal?: number;
  downloadsToday?: number;
  todayPeak: number;
  todayUnique: number;
  sessions: number;
  players: number;
  perks?: CountItem[];
  maps?: CountItem[];
  outcomes?: CountItem[];
  loss_waves?: CountItem[];
  countries?: CountItem[];
  servers?: CountItem[];
}
interface LivePlayer {
  name: string;
  perk?: string;
  perkIdx?: number;
  perkLevel?: number;
  prestigeRank?: number;
  steamId?: string;
  accountId?: number;
  country?: string;
}
interface LiveSnap {
  server?: string;
  map?: string;
  wave?: number;
  finalWave?: number;
  difficulty?: number;
  online?: number;
  players?: LivePlayer[];
  worstTick?: number;
  peakTick?: number;
  stale?: boolean;
  steam?: { listed?: boolean; checked?: number; queryPort?: number; players?: number; map?: string } | null;
  health?: { level?: string; peakMs?: number | null };
}
interface LoadChart {
  scope?: string;
  server?: string;
  label?: string;
  ts?: number[];
  cpu?: (number | null)[];
  mem?: (number | null)[];
  mem_mb?: (number | null)[];
  net_mbps?: (number | null)[];
  tick_ms?: (number | null)[];
  peak_tick_ms?: (number | null)[];
  peakTick?: number;
  now?: { cpu?: number | null; mem?: number | null; mem_mb?: number | null; net_mbps?: number | null } | null;
  host?: string;
  live?: LiveSnap;
  hosts?: LoadChart[];
  liveAll?: Record<string, LiveSnap>;
}
interface CardState {
  msg: string;
  err: boolean;
  log: string;
  logOpen: boolean;
  map: string;
}

const server = ref("");
const summary = ref<Summary | null>(null);
const load = ref<LoadChart | null>(null);
const maps = ref<string[]>([]);
const failed = ref("");
const blocked = ref(false);
const busy = ref(false);
const cardState = reactive<Record<string, CardState>>({});
const allMsg = reactive({ text: "", err: false });

let timer: ReturnType<typeof setInterval> | undefined;
let summaryGen = 0;

const access = computed(() => {
  if (!steamReady.value) return "loading" as const;
  if (!steamUser.value?.loggedIn) return "login" as const;
  if (!steamUser.value.admin || blocked.value) return "denied" as const;
  return "ready" as const;
});

const tabs = computed(() => summary.value?.serverTabs ?? [{ name: "", label: "" }]);

function tabLabel(name: string): string {
  if (!name) return t("dash.all");
  const tab = tabs.value.find((item) => (item.name || "") === name);
  return tab?.label || name;
}

const scopeText = computed(() => {
  if (server.value) {
    const tab = tabs.value.find((item) => item.name === server.value);
    return tab?.remote ? t("dash.scopeRemote") : t("dash.scopeProcess");
  }
  return (summary.value?.vpsHosts?.length || 0) > 1 ? t("dash.scopeEach") : t("dash.scopeHost");
});

const liveSlots = computed(() => {
  const named = tabs.value.filter((item) => item.name);
  const ids = server.value ? [server.value] : named.map((item) => item.name);
  return ids.map((id) => ({
    id,
    label: tabLabel(id),
    snap: (server.value ? load.value?.live : load.value?.liveAll?.[id]) || {},
  }));
});

watch(liveSlots, (slots) => {
  for (const slot of slots) {
    if (!cardState[slot.id]) {
      cardState[slot.id] = { msg: "", err: false, log: "", logOpen: false, map: "" };
    }
  }
});

function nums(raw: (number | null | undefined)[] | undefined): (number | null)[] {
  return (raw || []).map((v) => (v == null || !Number.isFinite(Number(v)) ? null : Number(v)));
}
function round1(n: number): string {
  return String(Math.round(n * 10) / 10);
}
function fmtPct(n: number): string {
  return `${Math.round(n)}%`;
}
function fmtMs(n: number): string {
  return t("dash.tickMs", { n: Math.round(n) });
}
function fmtDur(sec: number | null | undefined): string {
  if (sec == null || !Number.isFinite(sec)) return "—";
  const m = Math.floor(Math.max(0, Math.round(sec)) / 60);
  const h = Math.floor(m / 60);
  if (h > 0) return `${h}h ${m % 60}m`;
  return `${m}m`;
}
function fmtDay(n: number): string {
  const s = String(n);
  return s.length === 8 ? `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}` : s;
}
function fmtClock(ts: number): string {
  const d = new Date(ts * 1000);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
function shortTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}
function kb(n: number): number {
  return Math.round(n / 1024);
}
function mb(n: number): number {
  return Math.round(n / 1048576);
}

function perkIdOf(p: LivePlayer): string {
  const idx = p.perkIdx;
  const id = typeof idx === "number" ? PERK_IDS[idx] : "";
  if (id) return id;
  return canonPerkId(p.perk || "");
}
function perkTitle(p: LivePlayer): string {
  const id = perkIdOf(p);
  let name = p.perk || "";
  if (id) {
    const key = `perk.${id}`;
    const label = t(key);
    name = label === key ? id.replace(/_/g, " ") : label;
  }
  if (typeof p.perkLevel !== "number" || p.perkLevel < 0) return name;
  return p.perkLevel >= 9 ? `${name} · MANIAC` : `${name} · ${p.perkLevel}`;
}
function playerTo(p: LivePlayer): string {
  if (p.steamId && /^\d{16,20}$/.test(p.steamId)) return `/players/${p.steamId}`;
  if (p.accountId) return `/players/${p.accountId}`;
  return "";
}
function playerCountry(p: LivePlayer): string {
  const raw = String(p.country || "").trim().toLowerCase();
  return /^[a-z]{2}$/.test(raw) ? raw : "";
}
function waveCaption(snap: LiveSnap): string {
  const wave = snap.wave || 0;
  const finalWave = snap.finalWave || 0;
  if (snap.map && wave <= 0) return t("srv.lobby");
  if (finalWave > 0 && wave > finalWave) return t("srv.bossWave");
  if (wave > 0) return `${t("srv.wave")} ${wave}${finalWave > 0 ? " / " + finalWave : ""}`;
  return "—";
}
function healthLevel(id: string): string {
  return load.value?.liveAll?.[id]?.health?.level || "unknown";
}
function healthLabel(level: string | undefined): string {
  const key = `dash.health.${level || "unknown"}`;
  const label = t(key);
  return label === key ? t("dash.health.unknown") : label;
}
function peakMs(snap: LiveSnap): number | null {
  const raw = snap.health?.peakMs ?? snap.peakTick;
  if (raw == null || raw < 0) return null;
  return Math.round(raw);
}
function healthPeak(snap: LiveSnap): string {
  const ms = peakMs(snap);
  return ms == null ? "" : t("dash.healthPeak", { ms });
}
function tickClass(ms: number | undefined): string {
  if (ms == null || ms < 0) return "";
  if (ms >= 250) return "bad";
  if (ms >= 100) return "warn";
  return "ok";
}
function sliceName(items: CountItem[] | undefined, map: (name: string) => string): { name: string; c: number }[] {
  return (items || []).filter((item) => item.c > 0).map((item) => ({ name: map(String(item.name)), c: item.c }));
}
function perkSlice(name: string): string {
  const id = canonPerkId(name);
  if (!id) return name;
  const key = `perk.${id}`;
  const label = t(key);
  return label === key ? id.replace(/_/g, " ") : label;
}
function outcomeSlice(name: string): string {
  const key = `outcome.${name}`;
  const label = t(key);
  return label === key ? name : label;
}
function countrySlice(code: string): string {
  if (code.toLowerCase() === "other") return t("dash.other");
  const cc = code.toUpperCase();
  const name = countryName(code, i18n.locale);
  return name && name !== cc ? `${name} (${cc})` : cc;
}

const dayLabels = computed(() => (summary.value?.days || []).map(fmtDay));
const history = computed(() => {
  const data = summary.value;
  if (!data) return [];
  const rows = [];
  for (let i = data.days.length - 1; i >= 0; i--) {
    const dayNum = data.days[i];
    if (dayNum == null) continue;
    rows.push({
      day: fmtDay(dayNum),
      peak: data.peak[i] ?? 0,
      unique: data.unique[i] ?? 0,
      downloads: data.downloads?.[i] ?? 0,
      d1: data.retention_d1[i] ?? null,
      d7: data.retention_d7[i] ?? null,
      time: data.avg_playtime_sec[i] ?? null,
    });
  }
  return rows;
});

function chartOf(source: LoadChart): { labels: string[]; series: LineSeries[]; rightMax?: number } {
  const labels = (source.ts || []).map((ts) => fmtClock(ts));
  const net = nums(source.net_mbps);
  let mx = 1;
  for (const v of net) if (v != null && v > mx) mx = v;
  const mem = nums(source.mem);
  const memMb = source.mem_mb || [];
  const series: LineSeries[] = [
    {
      label: t("dash.cpu"),
      color: "#8fd16a",
      values: nums(source.cpu),
      tips: nums(source.cpu).map((v) => (v == null ? null : `${round1(v)}%`)),
    },
    {
      label: source.scope === "process" ? t("dash.memoryRss") : t("dash.memory"),
      color: "#5cc8e6",
      values: mem,
      tips: mem.map((v, i) => {
        if (source.scope === "process" && memMb[i] != null) {
          return v == null ? `${memMb[i]} MB` : `${memMb[i]} MB (${round1(v)}%)`;
        }
        return v == null ? null : `${round1(v)}%`;
      }),
    },
    {
      label: t("dash.network"),
      color: "#e8b53c",
      values: net.map((v) => (v == null ? null : (100 * v) / mx)),
      tips: net.map((v) => (v == null ? null : t("dash.mbps", { n: round1(v) }))),
    },
  ];
  const ticks = nums(source.tick_ms);
  const peaks = nums(source.peak_tick_ms);
  const showTicks = (source.scope === "process" || !!source.server) && ticks.some((v) => v != null);
  let rightMax: number | undefined;
  if (showTicks) {
    const tip = (v: number | null) => (v == null ? null : t("dash.tickMs", { n: Math.round(v) }));
    series.push({ label: t("dash.tickWindow"), color: "#e6a05c", values: ticks, tips: ticks.map(tip), axis: "right", dash: true });
    if (peaks.some((v) => v != null)) {
      series.push({ label: t("dash.tickPeak"), color: "#e07070", values: peaks, tips: peaks.map(tip), axis: "right", dash: true });
    }
    const finite = [...ticks, ...peaks].filter((v): v is number => v != null);
    rightMax = Math.max(50, ...finite);
  }
  return { labels, series, rightMax };
}

function loadTitle(source: LoadChart): string {
  if (source.scope === "process") return t("dash.loadProcess", { server: tabLabel(server.value || source.server || "") });
  return source.label ? t("dash.loadTitleNamed", { label: source.label }) : t("dash.loadTitle");
}
function loadHint(source: LoadChart): string {
  if (source.scope === "process") return t("dash.loadHintProcess");
  if (!source.now && (source.ts || []).length) return t("dash.loadHintStale");
  if (!source.now) return t("dash.loadHintWait");
  return t("dash.loadHintHost");
}
function loadMem(source: LoadChart): string {
  const now = source.now;
  if (!now) return "—";
  if (source.scope === "process" && now.mem_mb != null) {
    return now.mem != null ? `${now.mem_mb} MB (${round1(now.mem)}%)` : `${now.mem_mb} MB`;
  }
  return now.mem != null ? `${round1(now.mem)}%` : "—";
}

const loadPanels = computed(() => {
  const data = load.value;
  // Machine load belongs to one server. All stays on players, sessions, and totals.
  if (!data || !server.value) return [];
  const sources = [data];
  return sources.map((source, i) => {
    const chart = chartOf(source);
    const now = source.now;
    const lastTick = [...nums(source.tick_ms)].reverse().find((v) => v != null);
    const windowTick = source.live?.worstTick != null && source.live.worstTick >= 0 ? source.live.worstTick : lastTick;
    const showTick = (source.scope === "process" || !!source.server) && windowTick != null && windowTick >= 0;
    const showPeak = (source.scope === "process" || !!source.server) && (source.peakTick ?? -1) >= 0;
    return {
      key: `${source.host || source.server || "load"}-${i}`,
      title: loadTitle(source),
      hint: loadHint(source),
      cpu: now?.cpu != null ? `${round1(now.cpu)}%` : "—",
      memLabel: source.scope === "process" ? t("dash.memoryRss") : t("dash.memory"),
      mem: loadMem(source),
      net: now?.net_mbps != null ? t("dash.mbps", { n: round1(now.net_mbps) }) : "—",
      tick: showTick ? t("dash.tickMs", { n: Math.round(windowTick as number) }) : "",
      peak: showPeak ? t("dash.tickMs", { n: Math.round(source.peakTick as number) }) : "",
      ...chart,
    };
  });
});

async function readJson(res: Response): Promise<Record<string, unknown>> {
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (res.status === 401) {
    blocked.value = true;
    throw new Error("auth");
  }
  if (!res.ok && data.ok !== false) throw new Error(String(data.error || `HTTP ${res.status}`));
  return data;
}

async function loadMaps(): Promise<void> {
  if (maps.value.length) return;
  try {
    const res = await fetch("/api/stats/admin/maps", { cache: "no-store" });
    if (res.status === 401) {
      blocked.value = true;
      return;
    }
    if (!res.ok) return;
    const data = (await res.json()) as { maps?: string[] };
    maps.value = Array.isArray(data.maps) ? data.maps : [];
  } catch {
    // The map list is only for the change-map control.
  }
}

async function loadSummary(): Promise<void> {
  const q = server.value ? `?server=${encodeURIComponent(server.value)}` : "";
  const gen = ++summaryGen;
  try {
    const res = await fetch(`/api/stats/summary${q}`, { cache: "no-store" });
    const data = await readJson(res);
    if (gen !== summaryGen) return;
    summary.value = data as unknown as Summary;
    failed.value = "";
  } catch (e) {
    if (gen !== summaryGen || (e as Error).message === "auth") return;
    if (!summary.value) failed.value = t("dash.unavailable", { error: (e as Error).message });
  }
}

async function refreshLoad(): Promise<void> {
  const q = server.value ? `?server=${encodeURIComponent(server.value)}` : "";
  try {
    const res = await fetch(`/api/stats/load${q}`, { cache: "no-store" });
    const data = await readJson(res);
    load.value = data as unknown as LoadChart;
  } catch {
    // Keep the last sample. A 401 sets blocked and the gate takes over.
  }
}

function start(): void {
  if (!import.meta.client) return;
  stop();
  void loadMaps();
  void loadSummary();
  void refreshLoad();
  timer = setInterval(() => {
    if (document.hidden) return;
    void refreshLoad();
  }, 2000);
}
function stop(): void {
  if (timer) clearInterval(timer);
  timer = undefined;
}
function onVisible(): void {
  if (document.hidden || access.value !== "ready") return;
  void refreshLoad();
}

watch(access, (value) => {
  if (value === "ready") start();
  else stop();
}, { immediate: true });

watch(server, () => {
  if (access.value !== "ready") return;
  void loadSummary();
  void refreshLoad();
});

onMounted(() => {
  void loadSteamUser();
  document.addEventListener("visibilitychange", onVisible);
});
onBeforeUnmount(() => {
  stop();
  if (import.meta.client) document.removeEventListener("visibilitychange", onVisible);
});

function cardMap(id: string): string {
  return cardState[id]?.map || "";
}
function onMapChange(id: string, event: Event): void {
  const row = cardState[id];
  const target = event.target;
  if (!row || !(target instanceof HTMLSelectElement)) return;
  row.map = target.value;
}

function setMsg(id: string | null, text: string, err: boolean): void {
  if (!id) {
    allMsg.text = text;
    allMsg.err = err;
    return;
  }
  const row = cardState[id];
  if (!row) return;
  row.msg = text;
  row.err = err;
}

async function post(path: string, body: object): Promise<Record<string, unknown>> {
  const res = await fetch(path, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

async function restart(id: string | null): Promise<void> {
  if (busy.value) return;
  const label = id ? tabLabel(id) : t("dash.all");
  const question = id ? t("dash.confirmRestart", { server: label }) : t("dash.confirmRestartAll");
  if (!window.confirm(question)) return;
  busy.value = true;
  setMsg(id, t("dash.restarting"), false);
  try {
    const data = await post("/api/stats/admin/restart", { server: id || "all" });
    const ok = data.ok !== false && !data.error;
    setMsg(id, ok ? t("dash.done", { what: label }) : t("dash.failed", { error: String(data.error || "fail") }), !ok);
  } catch (e) {
    if ((e as Error).message !== "auth") setMsg(id, (e as Error).message, true);
  } finally {
    busy.value = false;
  }
}

async function changeMap(id: string): Promise<void> {
  const row = cardState[id];
  const mapName = row?.map || "";
  if (!mapName) {
    setMsg(id, t("dash.pickMap"), true);
    return;
  }
  if (busy.value) return;
  if (!window.confirm(t("dash.confirmMap", { server: tabLabel(id), map: mapName }))) return;
  busy.value = true;
  setMsg(id, t("dash.changing", { map: mapName }), false);
  try {
    const data = await post("/api/stats/admin/map", { server: id, map: mapName });
    const ok = data.ok !== false && !data.error;
    setMsg(id, ok ? t("dash.done", { what: String(data.map || mapName) }) : t("dash.failed", { error: String(data.error || "fail") }), !ok);
  } catch (e) {
    if ((e as Error).message !== "auth") setMsg(id, (e as Error).message, true);
  } finally {
    busy.value = false;
  }
}

async function showLog(id: string): Promise<void> {
  const row = cardState[id];
  if (!row) return;
  if (row.logOpen && row.log) {
    row.logOpen = false;
    return;
  }
  setMsg(id, t("dash.readingLog"), false);
  try {
    const res = await fetch(`/api/stats/admin/logs?server=${encodeURIComponent(id)}&lines=250`, { cache: "no-store" });
    const data = await readJson(res);
    row.log = String(data.text || t("dash.emptyLog"));
    row.logOpen = true;
    setMsg(id, t("dash.logMeta", { server: tabLabel(id), size: kb(Number(data.size) || 0) }), false);
  } catch (e) {
    if ((e as Error).message !== "auth") setMsg(id, (e as Error).message, true);
  }
}

async function downloadLog(id: string): Promise<void> {
  const res = await fetch(`/api/stats/admin/logs?server=${encodeURIComponent(id)}&download=1`, { cache: "no-store" });
  if (res.status === 401) {
    blocked.value = true;
    return;
  }
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `kfm-${id}.log`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 2000);
}

async function writeClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.style.position = "fixed";
  area.style.left = "-9999px";
  document.body.appendChild(area);
  area.select();
  const ok = document.execCommand("copy");
  area.remove();
  if (!ok) throw new Error("copy failed");
}

async function copyLog(id: string): Promise<void> {
  setMsg(id, t("dash.copying"), false);
  try {
    const res = await fetch(`/api/stats/admin/logs?server=${encodeURIComponent(id)}&full=1`, { cache: "no-store" });
    const data = await readJson(res);
    const size = Number(data.size) || 0;
    if (data.tooLarge) {
      setMsg(id, t("dash.tooBig", { size: mb(size) }), false);
      await downloadLog(id);
      setMsg(id, t("dash.downloadedMb", { size: mb(size) }), false);
      return;
    }
    await writeClipboard(String(data.text || ""));
    setMsg(id, t("dash.copied", { size: kb(size) }), false);
  } catch (e) {
    if ((e as Error).message !== "auth") setMsg(id, (e as Error).message, true);
  }
}

async function saveLog(id: string): Promise<void> {
  setMsg(id, t("dash.downloading"), false);
  try {
    await downloadLog(id);
    if (!blocked.value) setMsg(id, t("dash.downloaded"), false);
  } catch (e) {
    setMsg(id, (e as Error).message, true);
  }
}
</script>

<template>
  <div class="page dash">
    <h2 class="section-title">{{ t("nav.statistics") }}</h2>

    <div v-if="access !== 'ready'" class="panel gate">
      <p v-if="access === 'loading'" class="empty-note">{{ t("loading") }}</p>
      <template v-else>
        <p>{{ access === "login" ? t("dash.loginNeed") : t("dash.denied") }}</p>
        <a v-if="access === 'login'" class="steam-btn" href="/api/stats/steam/login?next=/statistics">
          <SteamMark />
          {{ t("nav.login") }}
        </a>
      </template>
    </div>

    <template v-else>
      <p class="lead">{{ t("dash.lead") }}</p>
      <div class="tabs" role="tablist">
        <button
          v-for="tab in tabs"
          :key="tab.name || 'all'"
          type="button"
          :class="{ on: (tab.name || '') === server }"
          @click="server = tab.name || ''"
        >
          <i v-if="tab.name" class="dot" :class="healthLevel(tab.name)" />
          {{ tab.name ? tab.label || tab.name : t("dash.all") }}
        </button>
      </div>
      <p class="note">
        <template v-if="server">{{ t("dash.server") }} <b>{{ tabLabel(server) }}</b>. {{ t("dash.loadIs") }} {{ scopeText }}. </template>
        <template v-else>{{ t("dash.filterAll") }} </template>
        {{ t("dash.downloadsShared") }}
      </p>

      <p v-if="!summary" class="empty-note">{{ failed || t("loading") }}</p>
      <template v-else>
        <div class="live-head">
          <h2 class="section-title">{{ server ? t("dash.liveNow") : t("dash.liveAll") }}</h2>
          <div v-if="!server" class="actions">
            <button type="button" class="btn danger" :disabled="busy" @click="restart(null)">{{ t("dash.restartAll") }}</button>
            <span class="msg" :class="{ err: allMsg.err }">{{ allMsg.text }}</span>
          </div>
        </div>
        <div class="live-grid">
          <article v-for="slot in liveSlots" :key="slot.id" class="panel live-card">
            <div class="health" :class="slot.snap.health?.level || 'unknown'">
              <i class="dot" :class="slot.snap.health?.level || 'unknown'" />
              {{ t("dash.health") }}: {{ healthLabel(slot.snap.health?.level) }}
              <template v-if="healthPeak(slot.snap)"> · {{ healthPeak(slot.snap) }}</template>
            </div>
            <h3>{{ slot.label }}</h3>
            <p class="meta">
              {{ t("sessions.map") }}: <b>{{ prettyMap(slot.snap.map || "") || "—" }}</b>
              · {{ t("sessions.difficulty") }}: <DifficultyLabel :level="Number(slot.snap.difficulty) || 0" />
              · {{ waveCaption(slot.snap) }}
              · {{ t("dash.online") }}: <b>{{ slot.snap.online ?? slot.snap.players?.length ?? 0 }}</b>
              <template v-if="tickClass(slot.snap.worstTick)">
                · {{ t("dash.tickWindow") }}:
                <b :class="tickClass(slot.snap.worstTick)">{{ t("dash.tickMs", { n: Math.round(slot.snap.worstTick || 0) }) }}</b>
              </template>
            </p>
            <p v-if="slot.snap.steam?.checked" class="steam-line">
              {{ t("dash.steamBrowser") }}:
              <b :class="slot.snap.steam.listed ? 'ok' : 'bad'">
                {{ slot.snap.steam.listed ? t("dash.steamListed") : t("dash.steamMissing", { port: slot.snap.steam.queryPort || "?" }) }}
              </b>
              <template v-if="slot.snap.steam.listed">
                · {{ t("dash.steamSees", { players: slot.snap.steam.players ?? "?", map: prettyMap(slot.snap.steam.map || "") || "—" }) }}
              </template>
              · {{ t("dash.steamChecked", { time: shortTime(slot.snap.steam.checked) }) }}
            </p>
            <p v-if="!slot.snap.players?.length" class="empty-note">{{ t("dash.noPlayers") }}</p>
            <ul v-else class="players">
              <li v-for="(p, i) in slot.snap.players" :key="p.steamId || p.accountId || p.name + i">
                <PerkIcon
                  v-if="perkIdOf(p) || (p.perkLevel ?? -1) >= 0"
                  :perk="perkIdOf(p) || p.perk || ''"
                  :level="p.perkLevel ?? null"
                  :prestige-rank="p.prestigeRank ?? 0"
                  :size="26"
                  :title="perkTitle(p)"
                />
                <router-link v-if="playerTo(p)" :to="playerTo(p)">{{ p.name || "—" }}</router-link>
                <span v-else>{{ p.name || "—" }}</span>
                <span v-if="playerCountry(p)" class="fi" :class="`fi-${playerCountry(p)}`" :title="countryName(playerCountry(p), i18n.locale)" />
              </li>
            </ul>
            <p v-if="slot.snap.stale && (slot.snap.map || slot.snap.players?.length)" class="stale">{{ t("dash.stale") }}</p>
            <div v-if="cardState[slot.id]" class="actions">
              <button type="button" class="btn danger" :disabled="busy" @click="restart(slot.id)">{{ t("dash.restart") }}</button>
              <select :value="cardMap(slot.id)" :disabled="busy" :aria-label="t('dash.map')" @change="onMapChange(slot.id, $event)">
                <option value="">{{ t("dash.mapPick") }}</option>
                <option v-for="m in maps" :key="m" :value="m">{{ m }}</option>
              </select>
              <button type="button" class="btn" :disabled="busy" @click="changeMap(slot.id)">{{ t("dash.map") }}</button>
              <button type="button" class="btn" :disabled="busy" @click="showLog(slot.id)">{{ t("dash.log") }}</button>
              <button type="button" class="btn" :disabled="busy" @click="copyLog(slot.id)">{{ t("dash.copy") }}</button>
              <button type="button" class="btn" :disabled="busy" @click="saveLog(slot.id)">{{ t("dash.download") }}</button>
            </div>
            <p v-if="cardState[slot.id]?.msg" class="msg" :class="{ err: !!cardState[slot.id]?.err }">{{ cardState[slot.id]?.msg }}</p>
            <pre v-if="cardState[slot.id]?.logOpen" class="log">{{ cardState[slot.id]?.log }}</pre>
          </article>
        </div>

        <div class="metrics">
          <div class="panel metric peak"><span>{{ t("dash.todayPeak") }}</span><b>{{ fmtNum(summary.todayPeak) }}</b></div>
          <div class="panel metric uniq"><span>{{ t("dash.todayUnique") }}</span><b>{{ fmtNum(summary.todayUnique) }}</b></div>
          <div class="panel metric dl"><span>{{ t("dash.downloadsToday") }}</span><b>{{ fmtNum(summary.downloadsToday || 0) }}</b></div>
          <div class="panel metric dl"><span>{{ t("dash.downloadsTotal") }}</span><b>{{ fmtNum(summary.downloadsTotal || 0) }}</b></div>
          <div class="panel metric"><span>{{ t("dash.sessions") }}</span><b>{{ fmtNum(summary.sessions) }}</b></div>
          <div class="panel metric"><span>{{ t("dash.players") }}</span><b>{{ fmtNum(summary.players) }}</b></div>
          <div class="panel metric"><span>{{ t("dash.days") }}</span><b>{{ fmtNum(summary.days.length) }}</b></div>
        </div>

        <section v-for="panel in loadPanels" :key="panel.key">
          <h2 class="section-title">{{ panel.title }}</h2>
          <div class="metrics">
            <div class="panel metric"><span>{{ t("dash.cpu") }}</span><b>{{ panel.cpu }}</b></div>
            <div class="panel metric"><span>{{ panel.memLabel }}</span><b>{{ panel.mem }}</b></div>
            <div class="panel metric"><span>{{ t("dash.network") }}</span><b>{{ panel.net }}</b></div>
            <div v-if="panel.tick" class="panel metric"><span>{{ t("dash.tickWindow") }}</span><b>{{ panel.tick }}</b></div>
            <div v-if="panel.peak" class="panel metric"><span>{{ t("dash.tickPeak") }}</span><b>{{ panel.peak }}</b></div>
          </div>
          <div class="panel chart-box">
            <LineChart
              :labels="panel.labels"
              :series="panel.series"
              :left-min="0"
              :left-max="100"
              :right-max="panel.rightMax"
              :format-left="fmtPct"
              :format-right="fmtMs"
            />
          </div>
          <p class="note">{{ panel.hint }}</p>
        </section>

        <h2 class="section-title">{{ t("dash.peakTitle") }}</h2>
        <div class="panel chart-box">
          <LineChart
            :labels="dayLabels"
            :series="[
              { label: t('dash.peak'), color: '#e0282d', values: summary.peak },
              { label: t('dash.unique'), color: '#e8b53c', values: summary.unique },
            ]"
          />
        </div>

        <h2 class="section-title">{{ t("dash.downloadsTitle") }}</h2>
        <div class="panel chart-box">
          <LineChart
            :labels="dayLabels"
            :series="[{ label: t('dash.downloads'), color: '#c9a0ff', values: summary.downloads || [] }]"
          />
        </div>
        <p class="note">{{ t("dash.downloadsNote") }}</p>

        <h2 class="section-title">{{ t("dash.retentionTitle") }}</h2>
        <div class="panel chart-box">
          <LineChart
            :labels="dayLabels"
            :left-min="0"
            :left-max="100"
            :format-left="fmtPct"
            :series="[
              { label: t('dash.d1'), color: '#5cc8e6', values: summary.retention_d1 },
              { label: t('dash.d7'), color: '#c78b12', values: summary.retention_d7 },
            ]"
          />
        </div>
        <p class="note">{{ t("dash.retentionNote") }}</p>

        <h2 class="section-title">{{ t("dash.timeTitle") }}</h2>
        <div class="panel chart-box">
          <LineChart
            :labels="dayLabels"
            :format-left="fmtDur"
            :series="[{ label: t('dash.time'), color: '#8fd16a', values: summary.avg_playtime_sec, tips: summary.avg_playtime_sec.map(fmtDur) }]"
          />
        </div>
        <p class="note">{{ t("dash.timeNote") }}</p>

        <div class="pies">
          <div class="panel pie-card">
            <h3>{{ t("dash.perks") }}</h3>
            <Donut v-if="sliceName(summary.perks, perkSlice).length" :items="sliceName(summary.perks, perkSlice)" />
            <p v-else class="empty-note">{{ t("dash.none") }}</p>
          </div>
          <div class="panel pie-card">
            <h3>{{ t("dash.maps") }}</h3>
            <Donut v-if="sliceName(summary.maps, prettyMap).length" :items="sliceName(summary.maps, prettyMap)" />
            <p v-else class="empty-note">{{ t("dash.none") }}</p>
          </div>
          <div class="panel pie-card">
            <h3>{{ t("dash.outcomes") }}</h3>
            <Donut v-if="sliceName(summary.outcomes, outcomeSlice).length" :items="sliceName(summary.outcomes, outcomeSlice)" />
            <p v-else class="empty-note">{{ t("dash.none") }}</p>
          </div>
          <div class="panel pie-card">
            <h3>{{ t("dash.lossWave") }}</h3>
            <Donut
              v-if="sliceName(summary.loss_waves, (n) => `${t('srv.wave')} ${n}`).length"
              :items="sliceName(summary.loss_waves, (n) => `${t('srv.wave')} ${n}`)"
            />
            <p v-else class="empty-note">{{ t("dash.none") }}</p>
          </div>
          <div class="panel pie-card">
            <h3>{{ t("dash.countries") }}</h3>
            <Donut v-if="sliceName(summary.countries, countrySlice).length" :items="sliceName(summary.countries, countrySlice)" />
            <p v-else class="empty-note">{{ t("dash.none") }}</p>
            <p class="note slim">
              {{ t("dash.countriesNote") }}
              <a href="https://db-ip.com" target="_blank" rel="noopener">{{ t("dash.geo") }}</a>
            </p>
          </div>
          <div v-if="!server" class="panel pie-card">
            <h3>{{ t("dash.servers") }}</h3>
            <Donut v-if="sliceName(summary.servers, tabLabel).length" :items="sliceName(summary.servers, tabLabel)" />
            <p v-else class="empty-note">{{ t("dash.none") }}</p>
          </div>
        </div>

        <h2 class="section-title">{{ t("dash.history") }}</h2>
        <div class="panel history">
          <table>
            <thead>
              <tr>
                <th>{{ t("sessions.date") }}</th>
                <th>{{ t("dash.peak") }}</th>
                <th>{{ t("dash.unique") }}</th>
                <th>{{ t("dash.downloads") }}</th>
                <th>{{ t("dash.d1") }}</th>
                <th>{{ t("dash.d7") }}</th>
                <th>{{ t("dash.time") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in history" :key="row.day">
                <td>{{ row.day }}</td>
                <td>{{ row.peak }}</td>
                <td>{{ row.unique }}</td>
                <td>{{ row.downloads }}</td>
                <td>{{ row.d1 == null ? "—" : row.d1 + "%" }}</td>
                <td>{{ row.d7 == null ? "—" : row.d7 + "%" }}</td>
                <td>{{ fmtDur(row.time) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.dash { max-width: var(--page-home); }
.lead, .note { color: var(--text-dim); margin: -4px 0 16px; }
.note b { color: var(--text); font-weight: 600; }
.note.slim { margin: 10px 0 0; font-size: 13px; }
.gate { padding: 22px 20px; max-width: 560px; }
.gate p { margin: 0 0 14px; }
.steam-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 32px;
  padding: 0 10px;
  color: var(--text-dim);
  background: var(--panel-2);
  border: 1px solid var(--border-bright);
  border-radius: 4px;
  font-family: var(--font-display);
  font-size: 15px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.steam-btn:hover { color: var(--text); border-color: var(--accent-deep); text-decoration: none; }
.tabs { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 14px; }
.tabs button, .btn, select {
  appearance: none;
  height: 32px;
  padding: 0 10px;
  background: var(--panel-2);
  color: var(--text);
  border: 1px solid var(--border-bright);
  border-radius: 4px;
  font-family: var(--font-display);
  font-size: 14px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  cursor: pointer;
}
.tabs button { display: inline-flex; align-items: center; gap: 8px; }
.tabs button.on, .tabs button:hover, .btn:hover:not(:disabled) {
  color: #fff;
  border-color: var(--accent);
  background: rgba(198, 18, 23, 0.16);
}
.btn:disabled, select:disabled { opacity: 0.45; cursor: default; }
.btn.danger { border-color: var(--accent-deep); }
select { text-transform: none; letter-spacing: 0; font-family: var(--font-body); font-size: 13px; max-width: 100%; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-faint); flex: none; }
.dot.good, .dot.ok { background: var(--green); box-shadow: 0 0 8px rgba(143, 209, 106, 0.7); }
.dot.warn { background: var(--gold-bright); box-shadow: 0 0 8px rgba(232, 181, 60, 0.6); }
.dot.bad { background: var(--accent-bright); box-shadow: 0 0 8px rgba(224, 40, 45, 0.7); }
.live-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 16px; }
.live-head .section-title { margin-bottom: 12px; }
.live-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px; margin-bottom: 8px; }
.live-card { padding: 14px; min-width: 0; }
.live-card h3 {
  margin: 0 0 6px;
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.health, .meta, .steam-line, .stale { color: var(--text-dim); margin: 0 0 8px; }
.meta b, .steam-line b, .health { color: var(--text); }
.steam-line b.ok { color: var(--green); }
.steam-line b.bad, .meta b.bad, .msg.err { color: #e07070; }
.meta b.warn { color: var(--gold-bright); }
.meta b.ok { color: var(--green); }
.stale { font-size: 13px; }
.players { list-style: none; margin: 8px 0 0; padding: 0; }
.players li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  border-top: 1px solid var(--border);
}
.players a { color: var(--text); }
.players a:hover { color: #fff; text-decoration: none; }
.players .fi { margin-left: auto; }
.actions { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 12px; }
.msg { margin: 8px 0 0; color: var(--text-dim); font-size: 13px; }
.log {
  max-height: 280px;
  overflow: auto;
  margin: 8px 0 0;
  padding: 10px;
  background: #0c0c0f;
  border: 1px solid var(--border);
  color: var(--text-dim);
  font: 12px/1.45 ui-monospace, Consolas, monospace;
  white-space: pre-wrap;
}
.metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(148px, 1fr)); gap: 10px; margin: 0 0 8px; }
.metric { padding: 12px 14px; }
.metric span {
  display: block;
  color: var(--text-faint);
  font-family: var(--font-display);
  font-size: 13px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.metric b {
  display: block;
  margin-top: 2px;
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 500;
  letter-spacing: 0.03em;
  line-height: 1.1;
  color: #fff;
}
.metric.peak b { color: var(--accent-bright); }
.metric.uniq b { color: var(--gold-bright); }
.metric.dl b { color: #c9a0ff; }
.chart-box { padding: 8px 4px 4px; margin-bottom: 8px; }
.pies { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; margin: 8px 0 4px; }
.pie-card { padding: 14px 16px 16px; min-width: 0; }
.pie-card h3 {
  margin: 0 0 12px;
  font-family: var(--font-display);
  font-size: 16px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-faint);
  font-weight: 400;
}
.history { overflow: auto; max-height: 460px; }
table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--border); white-space: nowrap; }
th {
  position: sticky;
  top: 0;
  background: var(--panel-2);
  font-family: var(--font-display);
  font-size: 13px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-faint);
  font-weight: 400;
}
tbody tr:hover { background: rgba(255, 255, 255, 0.025); }
</style>
