<script setup lang="ts">
// Dark-themed port of the production landing page (site/index.html):
// server monitor + Discord card (live data from the production stats API),
// Companion download block and release notes.
import { onMounted, onUnmounted, ref } from "vue";
import { t } from "../i18n";
import { prettyMap } from "../lib/format";

interface LivePlayer {
  name: string;
  perk: string;
}

interface ServerInfo {
  id: string;
  label: string;
  host: string;
  port: number;
  steam?: string | { listed?: boolean; checked?: number };
  map: string;
  difficulty: number;
  wave: number;
  finalWave: number;
  online: number;
  maxPlayers: number;
  players: LivePlayer[];
  stale: boolean;
}

interface DiscordInfo {
  name: string;
  icon: string;
  invite: string;
  online: number;
  members: number;
  checked: number;
  stale: boolean;
  onlineMembers: { name: string; avatar: string; status: string; game: string }[];
}

interface ReleaseInfo {
  tag?: string;
  file?: string;
  download?: string;
  body?: string;
}

const servers = ref<ServerInfo[] | null>(null);
const serversFailed = ref(false);
const discord = ref<DiscordInfo | null>(null);
const discordFailed = ref(false);
const openLists = ref(new Set<string>());
const copiedIp = ref<string | null>(null);
let copiedTimer: ReturnType<typeof setTimeout> | undefined;
const release = ref<ReleaseInfo | null>(null);
const changelogText = ref("");

let serversTimer: ReturnType<typeof setInterval> | undefined;
let discordTimer: ReturnType<typeof setInterval> | undefined;

function difficultyName(d: number): string {
  if (!Number.isFinite(d) || d <= 0) return "";
  if (d >= 8) return t("diff.brutal");
  if (d >= 7) return t("diff.hoe");
  if (d >= 5) return t("diff.suicidal");
  if (d >= 4) return t("diff.hard");
  if (d >= 2) return t("diff.normal");
  return t("diff.beginner");
}

function subText(srv: ServerInfo): string {
  const parts: string[] = [];
  const diff = difficultyName(srv.difficulty);
  if (diff) parts.push(diff);
  if (srv.finalWave > 0 && srv.wave > srv.finalWave) parts.push(t("srv.bossWave"));
  else if (srv.wave > 0) parts.push(`${t("srv.wave")} ${srv.wave}${srv.finalWave > 0 ? " / " + srv.finalWave : ""}`);
  return parts.join(" · ");
}

function joinUrl(srv: ServerInfo): string {
  return typeof srv.steam === "string" && srv.steam
    ? srv.steam
    : `steam://run/1250//${srv.host}:${srv.port}`;
}

function togglePlayers(id: string): void {
  const set = new Set(openLists.value);
  if (set.has(id)) set.delete(id);
  else set.add(id);
  openLists.value = set;
}

function fallbackCopy(text: string): boolean {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  ta.remove();
  return ok;
}

async function copyIp(srv: ServerInfo): Promise<void> {
  const text = `${srv.host}:${srv.port}`;
  try {
    if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
    else if (!fallbackCopy(text)) return;
  } catch {
    if (!fallbackCopy(text)) return;
  }
  copiedIp.value = srv.id;
  if (copiedTimer) clearTimeout(copiedTimer);
  copiedTimer = setTimeout(() => (copiedIp.value = null), 1500);
}

async function pollServers(): Promise<void> {
  try {
    const res = await fetch("/api/stats/servers", { cache: "no-store" });
    if (!res.ok) throw new Error(String(res.status));
    const data = (await res.json()) as { servers?: ServerInfo[] };
    if (data && Array.isArray(data.servers)) {
      servers.value = data.servers;
      serversFailed.value = false;
    }
  } catch {
    if (!servers.value) serversFailed.value = true;
  }
}

async function pollDiscord(): Promise<void> {
  try {
    const res = await fetch("/api/stats/discord", { cache: "no-store" });
    if (!res.ok) throw new Error(String(res.status));
    const data = (await res.json()) as DiscordInfo;
    if (data && data.invite) {
      discord.value = data;
      discordFailed.value = false;
    }
  } catch {
    if (!discord.value) discordFailed.value = true;
  }
}

// Same cleanup as the production page.
function releaseNotes(raw: string): string {
  let text = String(raw || "");
  text = text.replace(/<!--[\s\S]*?-->/g, "");
  text = text.replace(/^\s*\*{0,2}Full Changelog\*{0,2}\s*:\s*\S+\s*$/gim, "");
  text = text.replace(/https?:\/\/github\.com\/[^\s]+\/compare\/[^\s]+/g, "");
  text = text.replace(/\n{3,}/g, "\n\n").trim();
  if (/^#{1,6}\s+\S.*$/.test(text) && !/\n/.test(text)) return "";
  return text;
}

function onVisible(): void {
  if (document.hidden) return;
  pollServers();
  pollDiscord();
}

onMounted(() => {
  pollServers();
  pollDiscord();
  serversTimer = setInterval(pollServers, 10000);
  discordTimer = setInterval(pollDiscord, 60000);
  document.addEventListener("visibilitychange", onVisible);
  fetch("/release.json")
    .then((res) => (res.ok ? res.json() : null))
    .then((data) => {
      if (!data) return;
      release.value = data as ReleaseInfo;
      const body = releaseNotes(data.body || "");
      if (body) changelogText.value = body;
    })
    .catch(() => {});
});

onUnmounted(() => {
  if (serversTimer) clearInterval(serversTimer);
  if (discordTimer) clearInterval(discordTimer);
  document.removeEventListener("visibilitychange", onVisible);
});
</script>

<template>
  <div class="page landing">
    <!-- servers -->
    <h2 class="section-title">{{ t("srv.servers") }}</h2>
    <p v-if="!servers" class="empty-note">
      {{ serversFailed ? t("srv.unavailable") : t("srv.loading") }}
    </p>
    <section v-else class="server-grid">
      <article
        v-for="srv in servers"
        :key="srv.id"
        class="panel server-card"
        :class="{ stale: srv.stale, open: openLists.has(srv.id) }"
      >
        <div class="shot">
          <img
            v-if="srv.map"
            :src="`/maps/${encodeURIComponent(srv.map.toLowerCase())}.jpg`"
            alt=""
            loading="lazy"
            @error="(e) => ((e.target as HTMLImageElement).hidden = true)"
          />
          <span class="label">{{ srv.label || srv.id }}</span>
          <span class="count" :class="{ full: srv.online >= (srv.maxPlayers || 6) }">
            {{ srv.online }} / {{ srv.maxPlayers || 6 }}
          </span>
          <div class="caption">
            <span class="map">{{ srv.map ? prettyMap(srv.map) : t("srv.offline") }}</span>
            <small class="sub">{{ subText(srv) }}</small>
          </div>
        </div>
        <p class="server-meta">
          <span v-if="srv.stale" class="status">{{ srv.map ? t("srv.stale") : t("srv.offline") }}</span>
          <span
            v-if="srv.steam && typeof srv.steam === 'object' && srv.steam.checked"
            class="steam"
            :class="srv.steam.listed ? 'ok' : 'bad'"
            :title="`${t('srv.steamChecked')} ${new Date(srv.steam.checked * 1000).toLocaleTimeString()}`"
          >
            {{ srv.steam.listed ? t("srv.steamListed") : t("srv.steamMissing") }}
          </span>
        </p>
        <div class="server-actions">
          <a class="join" :href="joinUrl(srv)" rel="noopener">{{ t("srv.join") }}</a>
          <button type="button" class="plist-toggle" @click="togglePlayers(srv.id)">
            {{ t("srv.players") }} · {{ srv.online }}
          </button>
        </div>
        <ul v-if="openLists.has(srv.id)" class="plist">
          <li v-if="!srv.players.length" class="empty">{{ t("srv.noPlayers") }}</li>
          <li v-for="(p, i) in srv.players" :key="i">
            <span>{{ p.name || "???" }}</span>
            <span v-if="p.perk" class="perk">{{ p.perk }}</span>
          </li>
        </ul>
        <p class="server-addr">
          <span class="lbl">{{ t("srv.address") }}:</span>
          <span
            class="ip"
            :class="{ copied: copiedIp === srv.id }"
            :data-tip="t('srv.copied')"
            @click="copyIp(srv)"
          >{{ srv.host }}:{{ srv.port }}</span>
        </p>
      </article>
    </section>

    <!-- discord -->
    <h2 class="section-title">{{ t("srv.discord") }}</h2>
    <p v-if="!discord" class="empty-note">
      {{ discordFailed ? t("srv.discordUnavailable") : t("srv.loading") }}
    </p>
    <article v-else class="panel discord-card" :class="{ stale: discord.stale && !!discord.checked }">
      <img v-if="discord.icon" class="dc-icon" :src="discord.icon" alt="" />
      <div class="dc-body">
        <div class="dc-name">{{ discord.name || "Discord" }}</div>
        <p class="dc-counts">
          <template v-if="discord.checked">
            <span class="dc-online">{{ t("srv.discordOnline") }}: {{ discord.online || 0 }}</span>
            · <span>{{ t("srv.discordMembers") }}: {{ discord.members || 0 }}</span>
          </template>
          <template v-else>{{ t(discord.stale ? "srv.discordUnavailable" : "srv.loading") }}</template>
        </p>
      </div>
      <a class="join" :href="discord.invite || 'https://discord.gg/MJXsav9DFC'" target="_blank" rel="noopener">
        {{ t("srv.discordJoin") }}
      </a>
    </article>

    <!-- companion copy -->
    <section class="copy panel">
      <p>{{ t("landing.intro") }}</p>
      <ol>
        <li>{{ t("landing.step1") }}</li>
        <li>{{ t("landing.step2") }}</li>
        <li>{{ t("landing.step3") }}</li>
        <li>{{ t("landing.step4") }}</li>
      </ol>
      <p>
        <a
          class="dl"
          :href="release?.file || release?.download || '#'"
          :download="release?.file || undefined"
        >
          {{ t("landing.download") }}{{ release?.tag ? " " + release.tag : "" }}
        </a>
      </p>
      <p class="note muted">{{ t("landing.note") }}</p>
      <p class="warn">
        {{ t("landing.warn") }}
        <a href="https://github.com/antonk777/KFMCompanion" target="_blank" rel="noopener">
          {{ t("landing.source") }}
        </a>
      </p>
      <details v-if="changelogText" class="log">
        <summary>{{ t("landing.changelog") }}</summary>
        <pre>{{ changelogText }}</pre>
      </details>
    </section>
  </div>
</template>

<style scoped>
.landing { padding-top: 14px; }
/* Landing sections are centered. */
.landing .section-title { justify-content: center; }
.landing .section-title:first-of-type { margin-top: 8px; }
.landing .empty-note { text-align: center; }

.server-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 20rem), 1fr));
  gap: 12px;
  max-width: 900px;
  margin: 0 auto;
}

.server-card { display: flex; flex-direction: column; overflow: hidden; }
.server-card.stale .shot img { opacity: 0.55; }
.server-card .shot {
  position: relative;
  aspect-ratio: 16 / 9;
  background: #0b0b0e;
  overflow: hidden;
}
.server-card .shot img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.server-card .shot .label {
  position: absolute;
  left: 10px;
  top: 8px;
  font-family: var(--font-display);
  font-size: 18px;
  letter-spacing: 0.064em;
  text-transform: uppercase;
  color: #fff;
  background: rgba(10, 10, 12, 0.72);
  border: 1px solid var(--border);
  padding: 2px 8px 1px;
}
.server-card .shot .count {
  position: absolute;
  right: 10px;
  top: 8px;
  font-family: var(--font-display);
  font-size: 18px;
  color: var(--green);
  background: rgba(10, 10, 12, 0.72);
  border: 1px solid var(--border);
  padding: 2px 8px 1px;
}
.server-card .shot .count.full { color: var(--accent-bright); }
.server-card .shot .caption {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 18px 10px 7px;
  background: linear-gradient(transparent, rgba(10, 10, 12, 0.92));
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
}
.server-card .shot .caption .map {
  font-family: var(--font-display);
  font-size: 19px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #fff;
  text-shadow: 0 1px 4px #000;
}
.server-card .shot .caption .sub { color: var(--text-dim); font-size: 12px; white-space: nowrap; }

.server-meta {
  margin: 8px 10px 0;
  min-height: 1.2em;
  font-size: 12px;
  color: var(--text-dim);
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.server-meta .status { color: #e6c35c; }
.server-meta .steam.ok { color: var(--green); }
.server-meta .steam.bad { color: #e07070; }

.server-actions {
  display: flex;
  gap: 6px;
  margin: 8px 10px 0;
}
.server-actions a.join {
  flex: 1;
  text-align: center;
  font-family: var(--font-display);
  font-size: 16px;
  letter-spacing: 0.064em;
  text-transform: uppercase;
  color: var(--text);
  background: var(--panel-2);
  border: 1px solid var(--border-bright);
  padding: 5px 10px 3px;
}
.server-actions a.join:hover { text-decoration: none; border-color: var(--accent-deep); color: #fff; }
.server-actions button.plist-toggle {
  appearance: none;
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-dim);
  font: 12px var(--font-body);
  padding: 4px 9px;
  cursor: pointer;
}
.server-actions button.plist-toggle:hover { border-color: var(--border-bright); color: var(--text); }
.server-actions button.plist-toggle::after { content: " ▸"; color: var(--text-faint); }
.server-card.open button.plist-toggle::after { content: " ▾"; }

.plist { margin: 8px 10px 0; padding: 6px 8px; list-style: none; background: rgba(0, 0, 0, 0.3); border: 1px solid var(--border); font-size: 12.5px; }
.plist li { display: flex; justify-content: space-between; gap: 10px; padding: 3px 0; border-bottom: 1px solid rgba(255, 255, 255, 0.05); }
.plist li:last-child { border-bottom: 0; }
.plist .perk { color: var(--green); white-space: nowrap; }
.plist .empty { color: var(--text-faint); }

.server-addr { margin: 8px 10px 12px; font-size: 12px; color: var(--text-dim); }
.server-addr .lbl { margin-right: 4px; }
.server-addr .ip { position: relative; color: var(--text); cursor: pointer; border-bottom: 1px dotted var(--border-bright); }
.server-addr .ip.copied::after {
  content: attr(data-tip);
  position: absolute;
  left: 0;
  bottom: calc(100% + 5px);
  background: #1d1d25;
  border: 1px solid var(--border-bright);
  color: var(--green);
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 3px;
  white-space: nowrap;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.6);
}

.discord-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  max-width: 760px;
  margin: 0 auto;
}
.dc-icon { width: 44px; height: 44px; border-radius: 50%; }
.dc-body { flex: 1; min-width: 0; }
.dc-name { font-family: var(--font-display); font-size: 20px; letter-spacing: 0.048em; text-transform: uppercase; }
.dc-counts { margin: 2px 0 0; color: var(--text-dim); font-size: 13px; }
.dc-online { color: var(--green); }
.discord-card a.join {
  flex: none;
  font-family: var(--font-display);
  font-size: 16px;
  letter-spacing: 0.064em;
  text-transform: uppercase;
  color: var(--text);
  background: var(--panel-2);
  border: 1px solid #5a6cff;
  padding: 6px 12px 4px;
}
.discord-card a.join:hover { text-decoration: none; border-color: #7a8cff; color: #fff; }

.copy { margin: 26px auto 0; padding: 18px 22px; max-width: 760px; text-align: center; }
.copy ol { display: inline-block; text-align: left; padding-left: 20px; margin: 10px 0; }
.copy li { margin: 3px 0; }
a.dl {
  display: inline-block;
  font-family: var(--font-display);
  font-size: 20px;
  letter-spacing: 0.064em;
  text-transform: uppercase;
  color: #fff;
  background: linear-gradient(180deg, var(--accent-bright), var(--accent-deep));
  border: 1px solid #7d2023;
  padding: 8px 18px 6px;
}
a.dl:hover { text-decoration: none; filter: brightness(1.12); }
.copy .note { color: var(--text-faint); font-size: 13px; }
.copy .warn { color: #e6c35c; font-size: 13px; }
.copy .log { margin-top: 10px; border: 1px solid var(--border); padding: 8px 12px; }
.copy .log summary { cursor: pointer; color: var(--text-dim); font-size: 13px; }
.copy .log pre {
  margin: 8px 0 0;
  max-height: 320px;
  overflow: auto;
  white-space: pre-wrap;
  font: 12px/1.5 Consolas, Menlo, monospace;
  color: var(--text-dim);
}

@media (max-width: 40rem) {
  .discord-card {
    flex-wrap: wrap;
    align-items: flex-start;
    gap: 10px;
    padding: 12px;
  }
  .dc-icon { width: 36px; height: 36px; }
  .dc-name { font-size: 18px; }
  .discord-card a.join {
    flex-basis: 100%;
    margin-top: 2px;
    text-align: center;
  }
  .copy { padding: 14px 14px; }
}
</style>
