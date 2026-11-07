<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { fetchRecentSessions, SESSION_HISTORY_LIMIT, type RecentSessionInfo } from "../api";
import { t } from "../i18n";
import SessionTable from "../components/SessionTable.vue";

const PAGE_SIZE = 20;

const route = useRoute();
const router = useRouter();

const sessions = ref<RecentSessionInfo[] | null>(null);
const failed = ref(false);
let timer: ReturnType<typeof setInterval> | undefined;

const pageCount = computed(() => {
  const n = sessions.value?.length ?? 0;
  return Math.max(1, Math.ceil(n / PAGE_SIZE));
});

const page = computed(() => {
  const n = Number(route.query.page);
  const requested = Number.isInteger(n) && n > 0 ? n : 1;
  if (!sessions.value) return requested;
  return Math.min(requested, pageCount.value);
});

const pageRows = computed(() => {
  const all = sessions.value ?? [];
  const start = (page.value - 1) * PAGE_SIZE;
  return all.slice(start, start + PAGE_SIZE);
});

const pageItems = computed<(number | "gap")[]>(() => {
  const total = pageCount.value;
  const current = page.value;
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const items: (number | "gap")[] = [1];
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  if (start > 2) items.push("gap");
  for (let i = start; i <= end; i++) items.push(i);
  if (end < total - 1) items.push("gap");
  items.push(total);
  return items;
});

function go(n: number): void {
  const next = Math.min(pageCount.value, Math.max(1, n));
  router.push({ name: "sessions", query: next <= 1 ? {} : { page: String(next) } });
}

watch([sessions, () => route.query.page], () => {
  if (!sessions.value || !route.query.page) return;
  const raw = Number(route.query.page);
  if (Number.isInteger(raw) && raw >= 1 && raw <= pageCount.value) return;
  const next = Math.min(pageCount.value, Math.max(1, Number.isInteger(raw) ? raw : 1));
  router.replace({ name: "sessions", query: next <= 1 ? {} : { page: String(next) } });
});

async function load(): Promise<void> {
  try {
    sessions.value = await fetchRecentSessions(SESSION_HISTORY_LIMIT);
    failed.value = false;
  } catch {
    if (!sessions.value) failed.value = true;
  }
}

function onVisible(): void {
  if (document.hidden) return;
  void load();
}

onMounted(() => {
  void load();
  timer = setInterval(() => void load(), 60000);
  document.addEventListener("visibilitychange", onVisible);
});

onUnmounted(() => {
  if (timer) clearInterval(timer);
  document.removeEventListener("visibilitychange", onVisible);
});
</script>

<template>
  <div class="page">
    <h2 class="section-title">
      {{ t("sessions.history") }}
      <span v-if="sessions?.length" class="count">{{ sessions.length }}</span>
    </h2>
    <p v-if="!sessions" class="empty-note">
      {{ failed ? t("sessions.unavailable") : t("srv.loading") }}
    </p>
    <p v-else-if="!sessions.length" class="empty-note">{{ t("sessions.empty") }}</p>
    <template v-else>
      <nav v-if="pageCount > 1" class="pager" :aria-label="t('sessions.pages')">
        <button type="button" :disabled="page <= 1" @click="go(page - 1)">{{ t("sessions.prev") }}</button>
        <template v-for="(item, i) in pageItems" :key="i">
          <span v-if="item === 'gap'" class="gap">…</span>
          <button
            v-else
            type="button"
            :class="{ on: item === page }"
            :aria-current="item === page ? 'page' : undefined"
            @click="go(item)"
          >
            {{ item }}
          </button>
        </template>
        <button type="button" :disabled="page >= pageCount" @click="go(page + 1)">{{ t("sessions.next") }}</button>
      </nav>
      <SessionTable :sessions="pageRows" />
      <nav v-if="pageCount > 1" class="pager below" :aria-label="t('sessions.pages')">
        <button type="button" :disabled="page <= 1" @click="go(page - 1)">{{ t("sessions.prev") }}</button>
        <template v-for="(item, i) in pageItems" :key="'b' + i">
          <span v-if="item === 'gap'" class="gap">…</span>
          <button
            v-else
            type="button"
            :class="{ on: item === page }"
            :aria-current="item === page ? 'page' : undefined"
            @click="go(item)"
          >
            {{ item }}
          </button>
        </template>
        <button type="button" :disabled="page >= pageCount" @click="go(page + 1)">{{ t("sessions.next") }}</button>
      </nav>
    </template>
  </div>
</template>

<style scoped>
.pager {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 0 0 14px;
}
.pager.below { margin: 14px 0 0; }
.pager button {
  appearance: none;
  min-width: 34px;
  height: 32px;
  padding: 0 10px;
  background: var(--panel-2);
  border: 1px solid var(--border);
  color: var(--text-dim);
  font-family: var(--font-display);
  font-size: 15px;
  letter-spacing: 0.04em;
  cursor: pointer;
}
.pager button:hover:not(:disabled) {
  color: #fff;
  border-color: var(--border-bright);
}
.pager button.on {
  color: #fff;
  background: rgba(198, 18, 23, 0.16);
  border-color: var(--accent-deep);
}
.pager button:disabled { opacity: 0.35; cursor: default; }
.pager .gap { color: var(--text-faint); padding: 0 2px; }
</style>
