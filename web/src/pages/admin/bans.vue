<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import SteamMark from "~/components/SteamMark.vue";
import { i18n, t } from "~/i18n";
import { loadSteamUser, steamReady, steamUser } from "~/lib/steam";

interface Player { accountId: number; name: string; steamId: string; admin?: boolean; banned?: boolean }
interface Ban extends Player {
  id: number; reason: string; adminName: string; bannedAt: string; untilAt: string | null;
  unbannedAt: string | null; status: "active" | "expired" | "revoked"; version: string;
}
interface BanEvent { id: number; action: string; actorName: string; changedAt: string; before: Ban | null; after: Ban }
interface BanList { bans: Ban[]; total: number; page: number; pageSize: number }

const blocked = ref(false);
const route = useRoute();
const router = useRouter();
const profileFilter = computed(() => typeof route.query.player === "string" ? route.query.player.slice(0, 100) : "");
const banTarget = computed(() => typeof route.query.ban === "string" && /^[0-9]{1,20}$/.test(route.query.ban) ? route.query.ban : "");
const loginTo = computed(() => "/api/stats/steam/login?next=" + encodeURIComponent(
  banTarget.value ? "/admin/bans?ban=" + banTarget.value : "/admin/bans",
));
const access = computed(() => !steamReady.value ? "loading" : !steamUser.value?.loggedIn ? "login"
  : !steamUser.value.admin || blocked.value ? "denied" : "ready");
const filter = ref("active");
const query = ref(profileFilter.value);
const appliedQuery = ref(profileFilter.value);
const page = ref(1);
const data = ref<BanList | null>(null);
const loading = ref(false);
const error = ref("");
const notice = ref("");
const dialog = ref<HTMLDialogElement | null>(null);
const mode = ref<"create" | "edit" | "revoke" | "history">("create");
const selected = ref<Player | null>(null);
const editing = ref<Ban | null>(null);
const reason = ref("");
const reasonInput = ref<HTMLTextAreaElement | null>(null);
const duration = ref("24");
const until = ref("");
const playerQuery = ref("");
const players = ref<Player[]>([]);
const searched = ref(false);
const searching = ref(false);
const saving = ref(false);
const formError = ref("");
const history = ref<BanEvent[]>([]);
const historyLoading = ref(false);
let listGen = 0;
let searchGen = 0;
let historyGen = 0;
let opener: HTMLElement | null = null;

function message(code: string): string {
  const key = `bans.error.${code}`;
  const translated = t(key);
  return translated === key ? t("bans.error.failed") : translated;
}

async function request<T>(url: string, body?: object): Promise<T> {
  const res = await fetch(url, {
    cache: "no-store",
    ...(body ? { method: "POST", headers: { "Content-Type": "application/json", "X-KFM-Admin": "1" }, body: JSON.stringify(body) } : {}),
  });
  const payload = await res.json();
  if (res.status === 401 || payload.error === "auth_required") {
    if (res.status === 401) steamUser.value = null;
    else blocked.value = true;
    dialog.value?.close();
  }
  if (!res.ok) throw new Error(payload.error || "failed");
  return payload as T;
}

async function refresh() {
  const gen = ++listGen;
  if (access.value !== "ready") return;
  loading.value = true;
  error.value = "";
  try {
    const params = new URLSearchParams({ q: appliedQuery.value, status: filter.value, page: String(page.value) });
    const result = await request<BanList>(`/api/stats/admin/bans?${params}`);
    if (gen === listGen) { data.value = result; page.value = result.page; }
  } catch (e) {
    if (gen === listGen) { error.value = message((e as Error).message); data.value = null; }
  } finally {
    if (gen === listGen) loading.value = false;
  }
}

function searchBans() { appliedQuery.value = query.value.trim(); page.value = 1; void refresh(); }
function changePage(value: number) { page.value = value; void refresh(); }
watch(filter, () => { page.value = 1; void refresh(); });
watch(profileFilter, (value) => { query.value = value; searchBans(); });
watch(access, (value) => {
  if (value === "ready") void refresh();
  else { ++listGen; ++searchGen; ++historyGen; data.value = null; players.value = []; history.value = []; dialog.value?.close(); }
});
watch([access, banTarget], async ([value, target]) => {
  if (!import.meta.client || value !== "ready" || !target) return;
  await open("create");
  if (banTarget.value !== target || !dialog.value?.open) return;
  playerQuery.value = target;
  await searchPlayers(target);
}, { immediate: true, flush: "post" });
onMounted(() => { void loadSteamUser(); if (access.value === "ready") void refresh(); });
onBeforeUnmount(() => { ++listGen; ++searchGen; ++historyGen; });

function date(value: string | null): string {
  return value ? new Date(value).toLocaleString(i18n.locale, { dateStyle: "medium", timeStyle: "short" }) : t("bans.permanent");
}
function localInput(value: string): string {
  const d = new Date(value);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

async function open(kind: typeof mode.value, ban?: Ban) {
  opener = document.activeElement as HTMLElement;
  ++searchGen;
  ++historyGen;
  mode.value = kind;
  editing.value = ban || null;
  selected.value = ban || null;
  reason.value = ban?.reason || "";
  duration.value = ban ? (ban.untilAt ? "keep" : "permanent") : "24";
  until.value = ban?.untilAt ? localInput(ban.untilAt) : "";
  playerQuery.value = "";
  players.value = [];
  searched.value = false;
  searching.value = false;
  history.value = [];
  formError.value = "";
  await nextTick();
  if (dialog.value && !dialog.value.open) dialog.value.showModal();
  if (kind === "history" && ban) {
    const gen = historyGen;
    historyLoading.value = true;
    try {
      const result = await request<{ events: BanEvent[] }>(`/api/stats/admin/ban-history?id=${ban.id}`);
      if (gen === historyGen) history.value = result.events;
    } catch (e) { if (gen === historyGen) formError.value = message((e as Error).message); }
    finally { if (gen === historyGen) historyLoading.value = false; }
  }
}

function close() {
  if (saving.value) return;
  ++searchGen;
  ++historyGen;
  dialog.value?.close();
  if (banTarget.value) {
    const query = { ...route.query };
    delete query.ban;
    void router.replace({ query });
  }
  opener?.focus();
}

async function searchPlayers(exact = "") {
  const gen = ++searchGen;
  players.value = [];
  searched.value = false;
  formError.value = "";
  if (!playerQuery.value.trim()) return;
  searching.value = true;
  try {
    const result = await request<{ players: Player[] }>(`/api/stats/admin/ban-players?q=${encodeURIComponent(playerQuery.value.trim())}`);
    if (gen !== searchGen) return;
    players.value = exact
      ? result.players.filter((player) => player.steamId === exact || String(player.accountId) === exact)
      : result.players;
    searched.value = true;
    const player = exact ? players.value[0] : null;
    if (player && !player.admin && !player.banned) {
      selected.value = player;
      await nextTick();
      reasonInput.value?.focus();
    }
  } catch (e) { if (gen === searchGen) formError.value = message((e as Error).message); }
  finally { if (gen === searchGen) searching.value = false; }
}

async function save() {
  if (!selected.value || saving.value) return;
  formError.value = "";
  let untilAt: string | null = null;
  if (mode.value !== "revoke") {
    if (!reason.value.trim()) { formError.value = message("invalid_reason"); return; }
    if (duration.value === "keep") untilAt = editing.value?.untilAt || null;
    else if (duration.value === "custom") {
      const value = new Date(until.value);
      if (!Number.isFinite(value.getTime()) || value.getTime() <= Date.now()) { formError.value = message("invalid_expiry"); return; }
      untilAt = value.toISOString();
    } else if (duration.value !== "permanent") untilAt = new Date(Date.now() + Number(duration.value) * 3600000).toISOString();
  }
  saving.value = true;
  try {
    await request("/api/stats/admin/bans", {
      action: mode.value, accountId: selected.value.accountId, banId: editing.value?.id,
      version: editing.value?.version, reason: reason.value.trim(), untilAt,
    });
    notice.value = t(`bans.saved.${mode.value}`);
    saving.value = false;
    close();
    await refresh();
  } catch (e) { formError.value = message((e as Error).message); }
  finally { saving.value = false; }
}
</script>

<template>
  <div class="page bans-page">
    <div class="page-heading">
      <div><span class="eyebrow">{{ t("bans.admin") }}</span><h1>{{ t("bans.title") }}</h1></div>
      <button v-if="access === 'ready'" class="primary" @click="open('create')">+ {{ t("bans.create") }}</button>
    </div>
    <div v-if="access !== 'ready'" class="panel gate">
      <p>{{ access === "loading" ? t("loading") : access === "login" ? t("dash.loginNeed") : t("dash.denied") }}</p>
      <a v-if="access === 'login'" class="steam-btn" :href="loginTo"><SteamMark /> {{ t("nav.login") }}</a>
    </div>
    <template v-else>
      <p class="lead">{{ t("bans.lead") }}</p>
      <p v-if="notice" class="success" role="status">{{ notice }}</p>
      <section class="panel list-panel" :aria-label="t('bans.title')">
        <form class="filters" @submit.prevent="searchBans">
          <label class="search-label">{{ t("bans.search") }}<input v-model="query" type="search" maxlength="100" :placeholder="t('bans.searchHint')" /></label>
          <label>{{ t("bans.status") }}<select v-model="filter"><option v-for="status in ['active', 'all', 'expired', 'revoked']" :key="status" :value="status">{{ t(`bans.${status}`) }}</option></select></label>
          <button type="submit" :disabled="loading">{{ t("bans.searchButton") }}</button>
          <button type="button" :disabled="loading" @click="refresh">{{ t("bans.refresh") }}</button>
        </form>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <p v-else-if="loading" class="empty-note" role="status">{{ t("loading") }}</p>
        <template v-else-if="data">
          <p v-if="!data.bans.length" class="empty-note">{{ t("bans.empty") }}</p>
          <div v-else class="table-scroll">
            <table>
              <thead><tr><th>{{ t("bans.player") }}</th><th>{{ t("bans.reason") }}</th><th>{{ t("bans.status") }}</th><th>{{ t("bans.dates") }}</th><th>{{ t("bans.issuedBy") }}</th><th>{{ t("bans.actions") }}</th></tr></thead>
              <tbody><tr v-for="ban in data.bans" :key="ban.id">
                <td><router-link :to="`/players/${ban.steamId || ban.accountId}`" class="player-name">{{ ban.name || `#${ban.accountId}` }}</router-link><small>{{ ban.steamId }}</small><small>{{ t("bans.account") }} #{{ ban.accountId }} · {{ t("bans.ban") }} #{{ ban.id }}</small></td>
                <td class="reason-cell">{{ ban.reason || "—" }}</td>
                <td><span class="status" :class="ban.status">{{ t(`bans.${ban.status}`) }}</span></td>
                <td class="dates"><small>{{ t("bans.from") }}</small>{{ date(ban.bannedAt) }}<small>{{ t("bans.until") }}</small>{{ date(ban.untilAt) }}<template v-if="ban.status === 'revoked'"><small>{{ t("bans.revoked") }}</small>{{ date(ban.unbannedAt) }}</template></td>
                <td>{{ ban.adminName || "—" }}</td>
                <td><div class="row-actions"><template v-if="ban.status === 'active'"><button @click="open('edit', ban)">{{ t("bans.edit") }}</button><button @click="open('revoke', ban)">{{ t("bans.revoke") }}</button></template><button @click="open('history', ban)">{{ t("bans.history") }}</button></div></td>
              </tr></tbody>
            </table>
          </div>
          <div class="pager"><span>{{ t("bans.total", { count: data.total }) }}</span><nav :aria-label="t('sessions.pages')"><button :disabled="page <= 1" @click="changePage(page - 1)">{{ t("sessions.prev") }}</button><span>{{ page }} / {{ Math.max(1, Math.ceil(data.total / data.pageSize)) }}</span><button :disabled="page * data.pageSize >= data.total" @click="changePage(page + 1)">{{ t("sessions.next") }}</button></nav></div>
        </template>
      </section>
    </template>

    <dialog ref="dialog" aria-labelledby="ban-dialog-title" @cancel.prevent="close">
      <div class="dialog-heading"><h2 id="ban-dialog-title">{{ t(`bans.${mode === 'create' ? 'create' : mode}`) }}</h2><button type="button" :disabled="saving" :aria-label="t('bans.close')" @click="close">×</button></div>
      <template v-if="mode === 'create' && !selected">
        <form class="player-search" @submit.prevent="searchPlayers()"><label>{{ t("bans.findPlayer") }}<input v-model="playerQuery" autofocus type="search" required maxlength="100" :placeholder="t('bans.searchHint')" /></label><button :disabled="searching">{{ t("bans.searchButton") }}</button></form>
        <p v-if="searching" role="status">{{ t("loading") }}</p>
        <p v-else-if="searched && !players.length">{{ t("bans.noPlayers") }}</p>
        <ul class="player-results"><li v-for="player in players" :key="player.accountId"><button :disabled="player.admin || player.banned" @click="selected = player"><span><b>{{ player.name || `#${player.accountId}` }}</b><small>{{ player.steamId }} · #{{ player.accountId }}</small></span><span>{{ player.admin ? t("bans.admin") : player.banned ? t("bans.active") : t("bans.select") }}</span></button></li></ul>
        <p class="hint">{{ t("bans.searchLimit") }}</p>
      </template>
      <template v-else-if="selected">
        <div class="selected-player"><strong>{{ selected.name || `#${selected.accountId}` }}</strong><small>{{ selected.steamId }} · {{ t("bans.account") }} #{{ selected.accountId }}</small><button v-if="mode === 'create'" :disabled="saving" @click="selected = null">{{ t("bans.changePlayer") }}</button></div>
        <template v-if="mode === 'history'">
          <p class="hint">{{ t("bans.historyHint") }}</p>
          <p v-if="historyLoading">{{ t("loading") }}</p><p v-else-if="!history.length && !formError">{{ t("bans.noHistory") }}</p>
          <ol class="history"><li v-for="event in history" :key="event.id"><b>{{ t(`bans.event.${event.action}`) }} · {{ event.actorName }}</b><small>{{ date(event.changedAt) }}</small><p v-if="event.before">{{ t("bans.before") }}: {{ event.before.reason || "—" }} · {{ date(event.before.untilAt) }}</p><p>{{ t("bans.after") }}: {{ event.after.reason || "—" }} · {{ date(event.after.untilAt) }} · {{ t(`bans.${event.after.status}`) }}</p></li></ol>
        </template>
        <form v-else @submit.prevent="save">
          <fieldset :disabled="saving">
            <template v-if="mode !== 'revoke'">
              <label>{{ t("bans.reason") }}<textarea ref="reasonInput" v-model="reason" required maxlength="120" rows="3" /></label><p class="hint">{{ t("bans.reasonHint") }} <span>{{ reason.length }}/120</span></p>
              <label>{{ t("bans.duration") }}<select v-model="duration"><option v-if="editing?.untilAt" value="keep">{{ t("bans.keepExpiry") }}</option><option value="1">{{ t("bans.hour") }}</option><option value="24">{{ t("bans.day") }}</option><option value="168">{{ t("bans.week") }}</option><option value="720">{{ t("bans.month") }}</option><option value="permanent">{{ t("bans.permanent") }}</option><option value="custom">{{ t("bans.custom") }}</option></select></label>
              <label v-if="duration === 'custom'">{{ t("bans.until") }}<input v-model="until" type="datetime-local" required /></label>
              <p class="hint">{{ t("bans.timeHint") }}<template v-if="duration === 'keep'"> {{ date(editing?.untilAt || null) }}</template></p>
              <p class="hint">{{ t("bans.enforcement") }}</p>
            </template>
            <template v-else><p>{{ t("bans.confirmRevoke", { name: selected.name || `#${selected.accountId}` }) }}</p><p class="hint">{{ editing?.reason }} · {{ date(editing?.untilAt || null) }}</p></template>
          </fieldset>
          <div class="dialog-actions"><button type="button" :disabled="saving" @click="close">{{ t("bans.cancel") }}</button><button class="primary" type="submit" :disabled="saving">{{ saving ? t("bans.saving") : t(mode === 'revoke' ? 'bans.revoke' : mode === 'create' ? 'bans.create' : 'bans.save') }}</button></div>
        </form>
      </template>
      <p v-if="formError" class="error" role="alert">{{ formError }}</p>
    </dialog>
  </div>
</template>

<style scoped>
.page-heading, .dialog-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.eyebrow { color: var(--text-dim); font: 13px var(--font-display); text-transform: uppercase; letter-spacing: .12em; }
h1, h2 { font-family: var(--font-display); font-weight: 500; margin: 0; }
h1 { font-size: 32px; } h2 { font-size: 24px; }
.lead, .hint { color: var(--text-dim); }
.lead { margin: 12px 0 24px; }
.panel { padding: 20px; }
.steam-btn { display: inline-flex; align-items: center; gap: 8px; }
button, input, select, textarea { font: inherit; border: 1px solid var(--border-bright); border-radius: 4px; background: var(--panel-2); color: var(--text); padding: 8px 12px; }
button { cursor: pointer; white-space: nowrap; } button:hover:not(:disabled) { border-color: var(--accent-bright); color: #fff; }
button:disabled { opacity: .45; cursor: default; }
button.primary { background: var(--accent-deep); border-color: var(--accent); color: #fff; }
:is(button, input, select, textarea):focus-visible { outline: 2px solid var(--gold-bright); outline-offset: 3px; }
label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--text-dim); }
input, select, textarea { width: 100%; color-scheme: dark; } textarea { resize: vertical; }
.filters { display: flex; gap: 12px; align-items: end; flex-wrap: wrap; }
.search-label { flex: 1; min-width: 200px; }
.filters select { min-width: 140px; }
.table-scroll { overflow-x: auto; margin-top: 22px; }
table { width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }
th { color: var(--text-dim); font-size: 12px; font-weight: 500; }
th, td { padding: 14px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
th:first-child, td:first-child { padding-left: 0; }
.player-name { display: block; font-size: 15px; overflow-wrap: anywhere; min-width: 120px; }
small { display: block; color: var(--text-dim); font-size: 11px; margin-top: 4px; }
.reason-cell { min-width: 140px; max-width: 260px; overflow-wrap: anywhere; }
.dates { min-width: 155px; } .dates small:first-child { margin-top: 0; }
.status { display: inline-block; border: 1px solid var(--border-bright); border-radius: 3px; padding: 2px 7px; white-space: nowrap; color: var(--text-dim); }
.status.active { color: #f39393; background: #c6121718; border-color: var(--accent-deep); }
.status.revoked { color: var(--green); }
.row-actions { display: flex; flex-direction: column; gap: 6px; } .row-actions button { padding: 4px 9px; font-size: 12px; }
.pager, .pager nav { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.pager { justify-content: space-between; padding-top: 18px; font-size: 13px; color: var(--text-dim); }
.error { color: #ffaaaa; padding: 10px 12px; border: 1px solid var(--accent-deep); background: #c6121712; }
.success { color: var(--green); }
dialog { background: var(--panel); color: var(--text); border: 1px solid var(--border-bright); border-radius: 8px; width: min(580px, calc(100% - 24px)); max-height: calc(100dvh - 32px); padding: 24px; }
dialog::backdrop { background: #000b; }
.dialog-heading { margin-bottom: 20px; } .dialog-heading button { font-size: 22px; padding: 0 10px; }
.player-search { display: flex; gap: 10px; align-items: end; } .player-search label { flex: 1; min-width: 0; }
.player-results { list-style: none; padding: 0; margin: 16px 0; }
.player-results button { display: flex; width: 100%; justify-content: space-between; align-items: center; gap: 12px; text-align: left; white-space: normal; margin-top: 6px; }
.player-results b, .selected-player strong { overflow-wrap: anywhere; }
.selected-player { padding: 14px; background: var(--bg-2); border: 1px solid var(--border); margin-bottom: 20px; }
.selected-player button { margin-top: 12px; font-size: 12px; }
fieldset { border: 0; padding: 0; margin: 0; min-width: 0; } fieldset label + label { margin-top: 14px; }
.hint { font-size: 12px; } .hint span { float: right; }
.dialog-actions { display: flex; justify-content: end; gap: 10px; margin-top: 24px; }
.history { padding-left: 20px; } .history li { padding: 8px 0; border-bottom: 1px solid var(--border); overflow-wrap: anywhere; }
.history p { font-size: 13px; }
@media (max-width: 640px) { .panel { padding: 14px; } .page-heading { align-items: end; } h1 { font-size: 28px; } dialog { padding: 18px; } .filters label { flex: 1; } .search-label { min-width: 100%; } .pager { gap: 16px; } }
</style>
