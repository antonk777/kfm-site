<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import DifficultyLabel from "~/components/DifficultyLabel.vue";
import PerkIcon from "~/components/PerkIcon.vue";
import Donut from "~/components/stats/Donut.vue";
import LineChart, { type LineSeries } from "~/components/stats/LineChart.vue";
import SteamMark from "~/components/SteamMark.vue";
import ServerCardIcon from "~/components/stats/ServerCardIcon.vue";
import ServerLoadRow, { type CardLoad } from "~/components/stats/ServerLoadRow.vue";
import { countryName } from "~/data/countries";
import { i18n, t } from "~/i18n";
import { fmtNum, prettyMap } from "~/lib/format";
import { PERK_IDS, canonPerkId } from "~/lib/perkLevel";
import { loadSteamUser, steamReady, steamUser } from "~/lib/steam";
import { usePageTitle } from "~/title";

definePageMeta({ path: "/statistics/:server?" });
if (import.meta.server) usePageTitle();

interface CountItem {
  name: string;
  c: number;
}
interface ServerTab {
  name: string;
  label?: string;
  host?: string;
  port?: number;
  country?: string;
  remote?: boolean;
  vps?: string;
}
interface Summary {
  serverTabs?: ServerTab[];
  vpsHosts?: { id: string; label: string }[];
  days: number[];
  peak: (number | null)[];
  unique: number[];
  retention_d1: (number | null)[];
  retention_d7: (number | null)[];
  avg_playtime_sec: (number | null)[];
  downloads?: number[];
  downloadsTotal?: number;
  downloadsToday?: number;
  todayPeak: number | null;
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
  maxPlayers?: number;
  players?: LivePlayer[];
  revision?: string;
  stale?: boolean;
  steam?: { listed?: boolean; checked?: number; queryPort?: number; players?: number; map?: string } | null;
  health?: { level?: string; avgTickMs?: number | null };
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
  avg_tick_ms?: (number | null)[];
  now?: { cpu?: number | null; mem?: number | null; mem_mb?: number | null; net_mbps?: number | null } | null;
  host?: string;
  live?: LiveSnap;
  hosts?: LoadChart[];
  liveAll?: Record<string, LiveSnap>;
  slotLoad?: Record<string, CardLoad>;
}
interface CardState {
  msg: string;
  err: boolean;
  log: string;
  logOpen: boolean;
  logLoading: boolean;
  rosterOpen: boolean;
  map: string;
  mapFilter: string;
}

const route = useRoute();
const server = computed(() => String(route.params.server || ""));
const loginTo = computed(() => "/api/stats/steam/login?next=" + encodeURIComponent(serverTo(server.value)));
const summary = ref<Summary | null>(null);
const tabs = ref<ServerTab[]>([{ name: "", label: "" }]);
const load = ref<LoadChart | null>(null);
const maps = ref<string[]>([]);
const failed = ref("");
const blocked = ref(false);
const busy = ref(false);
const cardState = reactive<Record<string, CardState>>({});
const allMsg = reactive({ text: "", err: false });
const copyNotice = ref<{ id: string; text: string; error: boolean } | null>(null);
let copyTimer: ReturnType<typeof setTimeout> | undefined;
let copyAttempt = 0;

let timer: ReturnType<typeof setInterval> | undefined;
let summaryGen = 0;
let loadGen = 0;

const access = computed(() => {
  if (!steamReady.value) return "loading" as const;
  if (!steamUser.value?.loggedIn) return "login" as const;
  if (!steamUser.value.admin || blocked.value) return "denied" as const;
  return "ready" as const;
});

const unknownServer = computed(() => !!summary.value && !!server.value && !tabs.value.some((tab) => tab.name === server.value));

function serverTo(id: string): string {
  return id ? `/statistics/${encodeURIComponent(id)}/` : "/statistics/";
}

function tabLabel(name: string): string {
  if (!name) return t("dash.all");
  const tab = tabs.value.find((item) => (item.name || "") === name);
  return tab?.label || name;
}

function serverAddress(tab: ServerTab): string {
  if (!tab.host || !tab.port) return "";
  const host = tab.host.includes(":") && !tab.host.startsWith("[") ? "[" + tab.host + "]" : tab.host;
  return host + ":" + tab.port;
}

const scopeText = computed(() => {
  if (server.value) {
    const scope = load.value?.slotLoad?.[server.value]?.scope ?? load.value?.scope;
    return scope ? t(scope === "host" ? "dash.scopeRemote" : "dash.scopeProcess") : "—";
  }
  return (summary.value?.vpsHosts?.length || 0) > 1 ? t("dash.scopeEach") : t("dash.scopeHost");
});

const liveSlots = computed(() => {
  const visible = tabs.value.filter((tab) => tab.name && (!server.value || tab.name === server.value));
  return visible.map((tab) => ({
    id: tab.name,
    label: tab.label || tab.name,
    country: countryCode(tab.country),
    address: serverAddress(tab),
    remote: tab.remote,
    resources: load.value?.slotLoad?.[tab.name],
    snap: (server.value ? load.value?.live : load.value?.liveAll?.[tab.name]) || {},
  }));
});

watch(liveSlots, (slots) => {
  for (const slot of slots) {
    if (!cardState[slot.id]) {
      cardState[slot.id] = { msg: "", err: false, log: "", logOpen: false, logLoading: false, rosterOpen: false, map: "", mapFilter: "" };
    }
  }
}, { immediate: true });

// Read the recent log once on entering a known server, independently of live polling.
watch(() => access.value === "ready" && summary.value && !unknownServer.value ? server.value : "", (id) => {
  if (id) void readLog(id);
}, { flush: "post" });

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
  return t("dash.tickMs", { n: round1(n) });
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
  return new Date(ts * 1000).toLocaleTimeString(i18n.locale, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
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
function countryCode(code: string | undefined): string {
  const raw = String(code || "").trim().toLowerCase();
  return /^[a-z]{2}$/.test(raw) ? raw : "";
}
function banTo(p: LivePlayer) {
  const id = playerTo(p).split("/").pop();
  return id ? { path: "/admin/bans", query: { ban: id } } : undefined;
}
function waveCaption(snap: LiveSnap): string {
  const wave = snap.wave || 0;
  const finalWave = snap.finalWave || 0;
  if (snap.map && wave <= 0) return t("srv.lobby");
  if (finalWave > 0 && wave > finalWave) return t("srv.bossWave");
  if (wave > 0) return wave + (finalWave > 0 ? " / " + finalWave : "");
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
const playtime = computed(() => {
  const times = summary.value?.avg_playtime_sec ?? [];
  const start = times.findIndex((time) => time != null);
  return start < 0 ? { labels: [], values: [] } : { labels: dayLabels.value.slice(start), values: times.slice(start) };
});
const history = computed(() => {
  const data = summary.value;
  if (!data) return [];
  const rows = [];
  for (let i = data.days.length - 1; i >= 0; i--) {
    const dayNum = data.days[i];
    if (dayNum == null) continue;
    rows.push({
      day: fmtDay(dayNum),
      peak: data.peak[i] ?? null,
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
  const ticks = nums(source.avg_tick_ms);
  const showTicks = (source.scope === "process" || !!source.server) && ticks.some((v) => v != null);
  let rightMax: number | undefined;
  if (showTicks) {
    series.push({ label: t("dash.tickAverage"), color: "#e6a05c", values: ticks, tips: ticks.map((v) => v == null ? null : fmtMs(v)), axis: "right", dash: true });
    const finite = ticks.filter((v): v is number => v != null);
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
    const average = source.live?.health?.avgTickMs;
    return {
      key: `${source.host || source.server || "load"}-${i}`,
      title: loadTitle(source),
      hint: loadHint(source),
      cpu: now?.cpu != null ? `${round1(now.cpu)}%` : "—",
      memLabel: source.scope === "process" ? t("dash.memoryRss") : t("dash.memory"),
      mem: loadMem(source),
      net: now?.net_mbps != null ? t("dash.mbps", { n: round1(now.net_mbps) }) : "—",
      tick: average == null ? "—" : fmtMs(average),
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
    if (summary.value.serverTabs?.length) tabs.value = summary.value.serverTabs;
    failed.value = "";
  } catch (e) {
    if (gen !== summaryGen || (e as Error).message === "auth") return;
    if (!summary.value) failed.value = t("dash.unavailable", { error: (e as Error).message });
  }
}

async function refreshLoad(): Promise<void> {
  const q = server.value ? `?server=${encodeURIComponent(server.value)}` : "";
  const gen = loadGen;
  try {
    const res = await fetch(`/api/stats/load${q}`, { cache: "no-store" });
    const data = await readJson(res);
    if (gen === loadGen) load.value = data as unknown as LoadChart;
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
  ++summaryGen;
  ++loadGen;
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
  ++loadGen;
  load.value = null;
  summary.value = null;
  failed.value = "";
  void loadSummary();
  void refreshLoad();
});

onMounted(() => {
  void loadSteamUser();
  document.addEventListener("visibilitychange", onVisible);
});
onBeforeUnmount(() => {
  stop();
  ++copyAttempt;
  clearTimeout(copyTimer);
  if (import.meta.client) document.removeEventListener("visibilitychange", onVisible);
});

function filteredMaps(query: string): string[] {
  const search = query.trim().toLowerCase();
  return maps.value.filter((m) => m.toLowerCase().includes(search) || prettyMap(m).toLowerCase().includes(search));
}
function closeMapPicker(event: Event): void {
  if (server.value) return;
  const picker = (event.target as HTMLElement).closest("details");
  if (picker?.open) {
    picker.open = false;
    picker.querySelector<HTMLElement>("summary")?.focus();
  }
}
function focusMapSearch(event: Event): void {
  if (server.value) return;
  const picker = event.currentTarget as HTMLDetailsElement;
  if (picker.open) {
    const menu = picker.querySelector<HTMLElement>(".map-menu");
    picker.classList.remove("above");
    if (menu && menu.getBoundingClientRect().bottom > window.innerHeight - 8 && picker.getBoundingClientRect().top > menu.offsetHeight) {
      picker.classList.add("above");
    }
    picker.querySelector("input")?.focus();
  }
}
function leaveMapPicker(event: FocusEvent): void {
  if (server.value) return;
  const picker = event.currentTarget as HTMLDetailsElement;
  if (event.relatedTarget instanceof Node && !picker.contains(event.relatedTarget)) picker.open = false;
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

async function changeMap(id: string, event: Event): Promise<void> {
  const row = cardState[id];
  const mapName = row?.map || "";
  if (!mapName) {
    setMsg(id, t("dash.pickMap"), true);
    return;
  }
  if (busy.value) return;
  const mapLabel = prettyMap(mapName);
  if (!window.confirm(t("dash.confirmMap", { server: tabLabel(id), map: mapLabel }))) return;
  closeMapPicker(event);
  if (row) row.mapFilter = "";
  busy.value = true;
  setMsg(id, t("dash.changing", { map: mapLabel }), false);
  try {
    const data = await post("/api/stats/admin/map", { server: id, map: mapName });
    const ok = data.ok !== false && !data.error;
    setMsg(id, ok ? t("dash.done", { what: prettyMap(String(data.map || mapName)) }) : t("dash.failed", { error: String(data.error || "fail") }), !ok);
  } catch (e) {
    if ((e as Error).message !== "auth") setMsg(id, (e as Error).message, true);
  } finally {
    busy.value = false;
  }
}

function showLog(id: string): void {
  const row = cardState[id];
  if (!row) return;
  row.logOpen = !row.logOpen;
  if (row.logOpen) void readLog(id);
}

async function readLog(id: string): Promise<void> {
  const row = cardState[id];
  if (!row || row.logLoading) return;
  row.logLoading = true;
  try {
    const res = await fetch(`/api/stats/admin/logs?server=${encodeURIComponent(id)}&lines=250`, { cache: "no-store" });
    const data = await readJson(res);
    if (!res.ok || data.error) throw new Error(String(data.error || `HTTP ${res.status}`));
    row.log = String(data.text || t("dash.emptyLog"));
  } catch (e) {
    if ((e as Error).message !== "auth") row.log = t("dash.failed", { error: (e as Error).message });
  } finally {
    row.logLoading = false;
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

async function copyAddress(id: string, address: string): Promise<void> {
  const attempt = ++copyAttempt;
  let text = t("srv.copied");
  let failed = false;
  try {
    await writeClipboard(address);
  } catch (error) {
    text = t("dash.failed", { error: (error as Error).message });
    failed = true;
  }
  if (attempt !== copyAttempt) return;
  clearTimeout(copyTimer);
  copyNotice.value = { id, text, error: failed };
  copyTimer = setTimeout(() => { copyNotice.value = null; }, failed ? 3500 : 1500);
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
  <div class="page dash" :class="{ overview: !server }">
    <h1 class="section-title">{{ t("nav.serverManagement") }}<template v-if="access === 'ready' && server && summary && !unknownServer"> · {{ tabLabel(server) }}</template></h1>

    <div v-if="access !== 'ready'" class="panel gate">
      <p v-if="access === 'loading'" class="empty-note">{{ t("loading") }}</p>
      <template v-else>
        <p>{{ access === "login" ? t("dash.loginNeed") : t("dash.denied") }}</p>
        <a v-if="access === 'login'" class="steam-btn" :href="loginTo">
          <SteamMark />
          {{ t("nav.login") }}
        </a>
      </template>
    </div>

    <template v-else>
      <nav class="tabs" :aria-label="t('nav.serverManagement')">
        <NuxtLink
          v-for="tab in tabs"
          :key="tab.name || 'all'"
          :to="serverTo(tab.name)"
          :aria-current="(tab.name || '') === server ? 'page' : undefined"
          :class="{ on: (tab.name || '') === server }"
        >
          <i v-if="tab.name" class="dot" :class="healthLevel(tab.name)" />
          {{ tab.name ? tab.label || tab.name : t("dash.all") }}
        </NuxtLink>
      </nav>
      <p class="note">
        <template v-if="server">{{ t("dash.server") }} <b>{{ tabLabel(server) }}</b>. {{ t("dash.loadIs") }} {{ scopeText }}. </template>
        <template v-else>{{ t("dash.filterAll") }} </template>
        {{ t("dash.downloadsShared") }}
      </p>

      <p v-if="!summary" class="empty-note">{{ failed || t("loading") }}</p>
      <p v-else-if="unknownServer" class="empty-note">{{ t("dash.unknownServer") }}</p>
      <template v-else>
        <div class="live-head">
          <h2 class="section-title">{{ server ? t("dash.liveNow") : t("dash.liveAll") }}</h2>
          <div v-if="!server" class="actions">
            <button type="button" class="btn danger" :disabled="busy" @click="restart(null)">{{ t("dash.restartAll") }}</button>
            <span class="msg" :class="{ err: allMsg.err }">{{ allMsg.text }}</span>
          </div>
        </div>
        <div class="live-grid" :class="{ 'single-server': server }">
          <article v-for="slot in liveSlots" :key="slot.id" class="panel live-card">
            <header class="card-head">
              <h3><NuxtLink v-if="!server" :to="serverTo(slot.id)">{{ slot.label }} <span aria-hidden="true">›</span></NuxtLink><template v-else>{{ slot.label }}</template></h3>
              <div class="head-tools">
                <component :is="server ? 'span' : 'button'" class="occupancy" :type="server ? undefined : 'button'" :title="t('dash.livePlayers')" :aria-label="t('dash.livePlayers') + ' · ' + (slot.snap.online ?? slot.snap.players?.length ?? '—')"
                  :aria-controls="server ? undefined : 'roster-' + slot.id" :aria-expanded="server ? undefined : !!cardState[slot.id]?.rosterOpen" :disabled="!server && !slot.snap.players?.length"
                  @click="!server && (cardState[slot.id]!.rosterOpen = !cardState[slot.id]!.rosterOpen)">
                  <ServerCardIcon name="players" /><b>{{ slot.snap.online ?? slot.snap.players?.length ?? "—" }}</b><span v-if="slot.snap.maxPlayers">/ {{ slot.snap.maxPlayers }}</span>
                  <ServerCardIcon v-if="!server && slot.snap.players?.length" name="chevron" class="chevron" />
                </component>
                <button v-if="server" class="tool restart" type="button" :disabled="busy" :aria-label="t('dash.restart')" :title="t('dash.restart')" @click="restart(slot.id)"><ServerCardIcon name="restart" /></button>
              </div>
              <div class="server-meta">
                <span v-if="slot.country" class="fi" :class="'fi-' + slot.country" role="img" :aria-label="countryName(slot.country, i18n.locale)" :title="countryName(slot.country, i18n.locale)" />
                <span v-if="slot.address" class="address-wrap">
                  <button class="server-address" type="button" :aria-label="t('dash.copy') + ' · ' + slot.address" :title="t('dash.copy') + ' · ' + t('srv.address')" @click="copyAddress(slot.id, slot.address)">{{ slot.address }}</button>
                  <span class="copy-notice" role="status" :class="{ err: copyNotice?.error }">{{ copyNotice?.id === slot.id ? copyNotice.text : "" }}</span>
                </span>
                <span class="revision" :title="t('dash.revision')" :aria-label="t('dash.revision') + ' ' + (slot.snap.revision || '—')"><ServerCardIcon name="revision" />{{ slot.snap.revision ? "R" + slot.snap.revision : "—" }}</span>
              </div>
            </header>
            <section v-show="server || (cardState[slot.id]?.rosterOpen && slot.snap.players?.length)" :id="'roster-' + slot.id" class="roster-section" :aria-label="t('dash.livePlayers')">
              <h4 v-if="server">{{ t("dash.livePlayers") }}</h4>
              <p v-if="server && !slot.snap.players?.length" class="empty-note">{{ t("dash.noPlayers") }}</p>
              <ul class="players">
                <li v-for="(p, i) in slot.snap.players" :key="p.steamId || p.accountId || p.name + i">
                  <PerkIcon v-if="perkIdOf(p) || (p.perkLevel ?? -1) >= 0" :perk="perkIdOf(p) || p.perk || ''" :level="p.perkLevel ?? null" :prestige-rank="p.prestigeRank ?? 0" :size="26" :title="perkTitle(p)" />
                  <NuxtLink v-if="playerTo(p)" class="player-name" :to="playerTo(p)">{{ p.name || "—" }}</NuxtLink><span v-else class="player-name">{{ p.name || "—" }}</span>
                  <span v-if="countryCode(p.country)" class="fi" :class="'fi-' + countryCode(p.country)" :title="countryName(countryCode(p.country), i18n.locale)" />
                  <NuxtLink v-if="banTo(p)" class="ban-link" :to="banTo(p)" :aria-label="t('dash.banPlayer', { name: p.name })" :title="t('dash.banPlayer', { name: p.name })"><ServerCardIcon name="sword" /></NuxtLink>
                </li>
              </ul>
            </section>
            <section class="match" :aria-label="t('sessions.map')">
              <img v-if="slot.snap.map" :key="slot.snap.map" :src="'/maps/' + encodeURIComponent(slot.snap.map.toLowerCase()) + '.jpg'" alt="" @error="($event.target as HTMLImageElement).hidden = true" />
              <strong>{{ prettyMap(slot.snap.map || "") || "—" }}</strong>
              <div class="match-meta">
                <DifficultyLabel :level="Number(slot.snap.difficulty || 0)" :title="t('sessions.difficulty')"><ServerCardIcon name="difficulty" /></DifficultyLabel>
                <span :title="t('srv.wave')"><ServerCardIcon name="wave" />{{ waveCaption(slot.snap) }}</span>
              </div>
            </section>
            <div class="card-status">
              <details class="status-row" :open="!!server">
                <summary><ServerCardIcon name="health" /><span class="row-label">{{ t("dash.health") }} <small>{{ t("dash.tickAverageShort") }}</small></span>
                  <span class="reading" :data-level="slot.snap.health?.level"><i />{{ slot.snap.health?.avgTickMs == null ? healthLabel(slot.snap.health?.level) : fmtMs(slot.snap.health.avgTickMs) }}</span><ServerCardIcon name="chevron" class="chevron" /></summary>
                <dl class="facts"><div><dt>{{ t("dash.health") }}</dt><dd>{{ healthLabel(slot.snap.health?.level) }}</dd></div>
                  <div><dt>{{ t("dash.tickAverageShort") }}</dt><dd>{{ slot.snap.health?.avgTickMs == null ? "—" : fmtMs(slot.snap.health.avgTickMs) }}</dd></div></dl>
              </details>
              <ServerLoadRow :load="slot.resources" :remote="slot.remote" :open="!!server" />
              <details class="status-row" :open="!!server">
                <summary><SteamMark /><span class="row-label">{{ t("dash.serverBrowser") }}</span>
                  <span class="reading" :data-level="slot.snap.steam ? (slot.snap.steam.listed ? 'good' : 'warn') : 'unknown'">{{ !slot.snap.steam ? t("dash.health.unknown") : t(slot.snap.steam.listed ? "dash.steamListed" : "dash.steamUnlisted") }}</span><ServerCardIcon name="chevron" class="chevron" /></summary>
                <div class="facts"><template v-if="slot.snap.steam?.checked">
                  <p v-if="slot.snap.steam.listed">{{ t("dash.steamSees", { players: slot.snap.steam.players ?? "?", map: prettyMap(slot.snap.steam.map || "") || "—" }) }}</p>
                  <p v-else-if="slot.snap.steam.queryPort">{{ t("dash.steamQueryPort", { port: slot.snap.steam.queryPort }) }}</p>
                  <p>{{ t("dash.steamChecked", { time: shortTime(slot.snap.steam.checked) }) }}</p>
                </template><p v-else>{{ t("dash.health.unknown") }}</p></div>
              </details>
              <p v-if="slot.snap.stale && (slot.snap.map || slot.snap.players?.length)" class="stale">{{ t("dash.stale") }}</p>
            </div>
            <footer v-if="cardState[slot.id]" class="card-actions">
              <details class="map-picker" :open="!!server" @toggle="focusMapSearch" @focusout="leaveMapPicker" @keydown.esc.stop.prevent="closeMapPicker">
                <summary class="picker" :title="t('dash.mapPick')" :aria-label="t('dash.mapPick')"><ServerCardIcon name="map" />{{ t("dash.maps") }}<ServerCardIcon name="chevron" class="chevron" /></summary>
                <div class="map-menu">
                  <input v-model="cardState[slot.id]!.mapFilter" type="search" :aria-label="t('dash.mapSearch')" :placeholder="t('dash.mapSearch')" />
                  <ul><li v-for="m in filteredMaps(cardState[slot.id]!.mapFilter)" :key="m">
                    <button type="button" :aria-pressed="cardState[slot.id]?.map === m" @click="cardState[slot.id]!.map = m">{{ prettyMap(m) }}</button>
                  </li></ul>
                  <p v-if="!filteredMaps(cardState[slot.id]!.mapFilter).length">{{ t("dash.noMaps") }}</p>
                  <button type="button" class="apply-map" :disabled="busy || !cardState[slot.id]?.map || cardState[slot.id]?.map === slot.snap.map" @click="changeMap(slot.id, $event)">{{ t("dash.applyMap") }}</button>
                </div>
              </details>
              <button v-if="!server" class="tool" type="button" :disabled="busy" :aria-label="t('dash.log')" :title="t('dash.log')" :aria-expanded="cardState[slot.id]?.logOpen" @click="showLog(slot.id)"><ServerCardIcon name="log" /></button>
              <button v-if="!server" class="tool restart" type="button" :disabled="busy" :aria-label="t('dash.restart')" :title="t('dash.restart')" @click="restart(slot.id)"><ServerCardIcon name="restart" /></button>
            </footer>
            <p v-if="cardState[slot.id]?.msg" class="msg" role="status" :class="{ err: !!cardState[slot.id]?.err }">{{ cardState[slot.id]?.msg }}</p>
            <section v-if="server || cardState[slot.id]?.logOpen" class="log-panel" :aria-label="t('dash.log')">
              <div class="actions"><h4 v-if="server">{{ t("dash.log") }}</h4>
                <button v-if="server" type="button" class="btn" :disabled="cardState[slot.id]?.logLoading" @click="readLog(slot.id)">{{ t("friends.refresh") }}</button>
                <button type="button" class="btn" @click="copyLog(slot.id)">{{ t("dash.copy") }}</button><button type="button" class="btn" @click="saveLog(slot.id)">{{ t("dash.download") }}</button>
              </div>
              <pre class="log" :aria-busy="!!cardState[slot.id]?.logLoading">{{ cardState[slot.id]?.log || t("dash.readingLog") }}</pre>
            </section>
          </article>
        </div>

        <div class="metrics">
          <div class="panel metric peak"><span>{{ t("dash.todayPeak") }}</span><b>{{ summary.todayPeak == null ? "—" : fmtNum(summary.todayPeak) }}</b></div>
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
            <div class="panel metric"><span>{{ t("dash.tickAverage") }}</span><b>{{ panel.tick }}</b></div>
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

        <div class="trend-charts">
          <div class="trend-grid">
            <section class="panel trend-card">
              <h2 class="section-title">{{ t("dash.peakTitle") }}</h2>
              <LineChart
                :labels="dayLabels"
                :series="[
                  { label: t('dash.peak'), color: '#e0282d', values: summary.peak },
                  { label: t('dash.unique'), color: '#e8b53c', values: summary.unique },
                ]"
              />
              <p v-if="!server" class="trend-note">{{ t("dash.concurrentNote") }}</p>
            </section>

            <section class="panel trend-card">
              <h2 class="section-title">{{ t("dash.downloadsTitle") }}</h2>
              <LineChart
                :labels="dayLabels"
                :series="[{ label: t('dash.downloads'), color: '#c9a0ff', values: summary.downloads || [] }]"
              />
              <p class="trend-note">{{ t("dash.downloadsNote") }}</p>
            </section>

            <section class="panel trend-card">
              <h2 class="section-title">{{ t("dash.retentionTitle") }}</h2>
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
              <p class="trend-note">{{ t("dash.retentionNote") }}</p>
            </section>

            <section class="panel trend-card">
              <h2 class="section-title">{{ t("dash.timeTitle") }}</h2>
              <LineChart
                :labels="playtime.labels"
                :format-left="fmtDur"
                :series="[{ label: t('dash.time'), color: '#8fd16a', values: playtime.values, tips: playtime.values.map(fmtDur) }]"
              />
              <p class="trend-note">{{ t("dash.timeNote") }}</p>
            </section>
          </div>
        </div>

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
                <td>{{ row.peak ?? "—" }}</td>
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
.dash.overview { max-width: 1800px; }
.dash > h1.section-title { margin-top: 12px; }
.note { color: var(--text-dim); margin: -4px 0 16px; }
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
.tabs a, .btn {
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
.tabs a { display: inline-flex; align-items: center; gap: 8px; text-decoration: none; }
.tabs a.on, .tabs a:hover, .btn:hover:not(:disabled) {
  color: #fff;
  border-color: var(--accent);
  background: rgba(198, 18, 23, 0.16);
}
.btn:disabled { opacity: 0.45; cursor: default; }
.btn.danger { border-color: var(--accent-deep); }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-faint); flex: none; }
.dot.good, .dot.ok { background: var(--green); box-shadow: 0 0 8px rgba(143, 209, 106, 0.7); }
.dot.warn { background: var(--gold-bright); box-shadow: 0 0 8px rgba(232, 181, 60, 0.6); }
.dot.bad { background: var(--accent-bright); box-shadow: 0 0 8px rgba(224, 40, 45, 0.7); }
.live-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 16px; }
.live-head .section-title { margin: 14px 0 10px; }
.live-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, max(288px, calc(20% - 8px))), 1fr)); gap: 10px; margin-bottom: 16px; align-items: stretch; }
.live-card { min-width: 0; display: flex; flex-direction: column; line-height: 1.4; }
.card-head { padding: 17px 17px 15px; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px 8px; align-items: center; }
.card-head h3 { margin: 0; min-width: 0; font: 600 22px/1.15 var(--font-display); text-transform: uppercase; overflow-wrap: anywhere; }
.card-head h3 a { color: var(--text); }
.card-head h3 a span { color: var(--text-dim); font-size: 15px; }
.head-tools { display: flex; align-items: center; gap: 8px; }
.server-meta { grid-column: 1 / -1; display: flex; align-items: center; flex-wrap: wrap; gap: 5px 8px; color: var(--text-dim); font-size: 12px; }
.server-meta .fi { width: 17px; height: 12px; }
.revision { display: inline-flex; align-items: center; gap: 4px; }
.server-meta > :not(:first-child).revision { border-left: 1px solid var(--border-bright); padding-left: 8px; line-height: 1; }
.server-address { max-width: 100%; min-width: 0; padding: 0; border: 0; background: transparent; color: #c0bdb7; font: 12px/1.4 ui-monospace, Consolas, monospace; overflow-wrap: anywhere; text-align: left; cursor: pointer; }
.server-address:hover { color: var(--text); text-decoration: underline; }
.address-wrap { position: relative; max-width: 100%; min-width: 0; }
.copy-notice:not(:empty) { position: absolute; z-index: 2; bottom: calc(100% + 4px); left: 0; width: max-content; max-width: min(240px, 65vw); padding: 3px 8px; background: var(--panel-2); border: 1px solid var(--border-bright); color: var(--green); font-size: 12px; pointer-events: none; }
.copy-notice.err { color: #ff8983; }
.revision svg { width: 13px; height: 13px; }
.occupancy, .picker, .tool, .ban-link { display: inline-flex; align-items: center; justify-content: center; gap: 5px; border: 0; border-radius: 4px; cursor: pointer; font: inherit; }
.occupancy { min-height: 29px; padding: 2px 7px; white-space: nowrap; font-size: 13px; font-variant-numeric: tabular-nums; color: var(--text); background: #2b2b34; }
.occupancy:disabled { cursor: default; }
.occupancy .card-icon { width: 14px; height: 14px; }
.live-card :deep(.chevron) { width: 11px; height: 11px; flex: none; color: #a4a3a6; }
.occupancy[aria-expanded="true"] .chevron, details[open] > summary .chevron, .card-status :deep(details[open] > summary .chevron) { transform: rotate(180deg); }
.players { list-style: none; margin: 0 17px; padding: 0 0 11px; max-height: 168px; overflow: auto; }
.players li { min-height: 30px; display: flex; align-items: center; gap: 8px; font-size: 13px; }
.players li + li { border-top: 1px solid var(--border); }
.player-name { flex: 1; min-width: 0; overflow-wrap: anywhere; color: var(--text); }
.ban-link { width: 25px; height: 25px; color: #bbadad; flex: none; }
.ban-link svg { width: 13px; height: 13px; }
.ban-link:hover, .tool.restart:hover { background: #43282a; color: #ffaaa7; }
.match { position: relative; isolation: isolate; min-height: 83px; padding: 12px 17px; display: flex; flex-direction: column; justify-content: center; overflow: hidden; background: #232628; }
.match img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; z-index: -2; filter: saturate(.7); }
.match::before { content: ""; position: absolute; inset: 0; z-index: -1; background: linear-gradient(90deg,#111418f7,#111418d9 35%,#11141873 65%,#1114181a),linear-gradient(0deg,#11141888,transparent 70%); }
.match strong { color: #fff; font-size: 16px; overflow-wrap: anywhere; text-shadow: 0 1px 3px #000b; }
.match-meta { display: flex; flex-wrap: wrap; gap: 5px 12px; margin-top: 5px; color: #e5e7e8; font-size: 12px; }
.match-meta > span { display: inline-flex; align-items: center; gap: 4px; background: #15181bcc; }
.match-meta .card-icon { width: 14px; height: 14px; }
.card-status { padding: 9px 17px; }
.card-status :deep(summary), .picker { display: flex; align-items: center; cursor: pointer; list-style: none; }
.card-status :deep(summary::-webkit-details-marker), .picker::-webkit-details-marker { display: none; }
.card-status :deep(summary) { min-height: 36px; gap: 7px; padding-block: 4px; font-size: 13px; }
.card-status :deep(summary > svg) { color: #a8a7aa; flex: none; width: 15px; height: 15px; }
.card-status :deep(.row-label) { flex: 1; min-width: 0; }
.card-status :deep(.row-label small) { color: #a5a3a4; font-size: 11px; }
.card-status :deep(.reading) { display: inline-flex; align-items: center; gap: 5px; color: #bcbabc; font-variant-numeric: tabular-nums; }
.card-status :deep(.reading i) { width: 5px; height: 5px; border-radius: 50%; background: currentColor; flex: none; }
.card-status :deep([data-level="good"]), .card-status :deep([data-level="ok"]) { color: var(--green); }
.card-status :deep([data-level="warn"]) { color: var(--gold-bright); }
.card-status :deep([data-level="high"]), .card-status :deep([data-level="bad"]), .msg.err { color: #ff8983; }
.card-status :deep(.facts) { margin: 2px 0 6px 22px; border-left: 1px solid var(--border-bright); padding: 4px 0 4px 9px; color: #b8b5b0; font-size: 12px; }
.card-status :deep(.facts > div) { display: flex; justify-content: space-between; gap: 6px; }
.card-status :deep(.facts dd) { margin: 0; text-align: right; }
.card-status :deep(.facts p), .stale { margin: 3px 0; }
.stale { color: var(--gold-bright); font-size: 12px; }
.card-actions { margin-top: auto; position: relative; display: flex; align-items: center; gap: 5px; border-top: 1px solid var(--border); padding: 10px 14px 11px 17px; }
.actions { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.map-picker { margin-right: auto; }
.picker, .tool { min-height: 30px; font-size: 12px; }
.picker { padding: 0 9px; background: #292930; border: 1px solid var(--border-bright); color: var(--text); font-weight: 600; }
.picker svg { width: 14px; height: 14px; }
.tool { width: 30px; background: transparent; color: #bab8bb; }
.tool:hover, .picker:hover, .occupancy:not(:disabled):hover { background: #383840; color: #fff; }
.map-menu { position: absolute; top: calc(100% - 4px); inset-inline: 10px; padding: 10px; z-index: 5; background: var(--panel-2); border: 1px solid var(--border-bright); box-shadow: 0 6px 20px #0009; }
.map-picker.above .map-menu { top: auto; bottom: calc(100% - 4px); }
.map-menu input, .map-menu button { width: 100%; font: inherit; color: var(--text); font-size: 13px; }
.map-menu input { background: var(--panel); border: 1px solid var(--border-bright); padding: 7px 8px; }
.map-menu ul { list-style: none; margin: 4px 0; padding: 0; max-height: 150px; overflow: auto; }
.map-menu li button, .apply-map { cursor: pointer; padding: 5px 8px; background: transparent; border: 0; }
.map-menu li button { text-align: left; overflow-wrap: anywhere; }
.map-menu li button:hover, .map-menu li button[aria-pressed="true"], .apply-map { background: #35353e; }
.map-menu li button[aria-pressed="true"]::after { content: "✓"; float: right; }
.apply-map:disabled { opacity: .45; cursor: default; }
.log-panel, .live-card > .msg { padding: 6px 12px; }
.single-server { grid-template-columns: minmax(0, 1fr); }
.single-server .live-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  grid-template-areas: "head" "map" "roster" "status" "maps" "log" "message";
}
.single-server .card-head { grid-area: head; }
.single-server .occupancy { cursor: default; }
.single-server .match { grid-area: map; min-height: clamp(90px, 9vw, 132px); }
.single-server .match strong { font-size: 20px; }
.single-server .roster-section { grid-area: roster; padding: 12px 17px; }
.single-server .players { max-height: none; padding: 0; margin: 6px 0 0; }
.single-server h4, .single-server .picker { font: 500 15px/1.3 var(--font-display); text-transform: uppercase; letter-spacing: .04em; }
.single-server h4 { margin: 0; }
.single-server .card-status { grid-area: status; padding: 10px 17px; border-top: 1px solid var(--border); }
.single-server .card-actions { grid-area: maps; display: block; margin: 0; padding: 12px 17px; }
.single-server .map-picker { margin: 0; }
.single-server .picker { padding: 0; width: max-content; border: 0; background: transparent; }
.single-server .map-menu { position: static; margin-top: 6px; padding: 0; background: transparent; border: 0; box-shadow: none; }
.single-server .log-panel { grid-area: log; min-width: 0; padding: 12px 17px; border-top: 1px solid var(--border); }
.single-server .log-panel .actions h4 { margin-right: auto; }
.single-server .log { max-height: 222px; overflow-wrap: anywhere; }
.single-server .live-card > .msg { grid-area: message; }
@media (min-width: 760px) {
  .single-server .live-card {
    grid-template-columns: minmax(205px, 1fr) minmax(0, 2.7fr);
    grid-template-areas: "head head" "map map" "roster status" "maps log" "message message";
  }
  .single-server .card-status, .single-server .log-panel { border-left: 1px solid var(--border); }
  .single-server .card-status { border-top: 0; }
}
@media (min-width: 1100px) {
  .single-server .card-status { display: grid; grid-template-columns: 1fr 1.15fr 1fr; gap: 14px; align-content: start; }
  .single-server .card-status :deep(.status-row) { min-width: 0; }
  .single-server .card-status .stale { grid-column: 1 / -1; }
}
.live-card :deep(:focus-visible) { outline: 2px solid var(--gold-bright); outline-offset: 2px; }
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
.trend-charts { container-type: inline-size; margin: 20px 0 12px; }
.trend-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px; }
.trend-card { min-width: 0; padding: 12px 10px; }
.trend-card .section-title { align-items: center; gap: 8px; margin: 0 0 8px; font-size: 18px; line-height: 1.15; letter-spacing: 0.04em; }
.trend-card .section-title::before { flex: 0 0 4px; height: 16px; }
.trend-note { margin: 6px 8px 0; color: var(--text-dim); font-size: 12px; }
.pies { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 8px 0 4px; }
.pie-card { padding: 14px 16px 16px; min-width: 0; container-type: inline-size; }
.pie-card :deep(.legend .name) { white-space: normal; overflow-wrap: anywhere; }
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
@container (min-width: 680px) {
  .trend-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .trend-card .section-title { min-height: 2.3em; }
}
@container (min-width: 1280px) {
  .trend-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
@container (max-width: 330px) {
  .pie-card :deep(.pie-row) { flex-direction: column; align-items: stretch; }
  .pie-card :deep(.pie) { align-self: center; }
}
@media (max-width: 980px) {
  .pies { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 720px) {
  .pies { grid-template-columns: minmax(0, 1fr); }
}
</style>
