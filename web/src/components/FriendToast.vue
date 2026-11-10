<script setup lang="ts">
import { computed } from "vue";
import { t } from "../i18n";
import { noticePlace } from "../lib/format";

const props = defineProps<{
  name: string;
  server: string;
  map?: string;
  profile: string;
  join?: string;
  full?: boolean;
  difficulty?: number;
}>();

const place = computed(() => noticePlace(props.map || "", props.difficulty || 0, props.server));
const joinHref = computed(() =>
  !props.full && props.join && props.join.startsWith("steam://run/") ? props.join : "",
);
</script>

<template>
  <article class="friend-toast">
    <router-link class="who" :to="`/players/${profile}`">
      <b>{{ name }}</b>
      <span v-if="place">{{ t("friends.noticeWhere", { place }) }}</span>
    </router-link>
    <a v-if="joinHref" class="join" :href="joinHref">{{ t("friends.join") }}</a>
    <span v-else-if="full" class="full">{{ t("srv.full") }}</span>
  </article>
</template>

<style scoped>
.friend-toast {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  width: min(320px, 100%);
  padding: 10px 12px;
  background: rgba(16, 16, 20, 0.98);
  border: 1px solid var(--border-bright);
  border-left: 3px solid var(--accent);
  border-radius: 4px;
  box-shadow: 0 14px 26px rgba(0, 0, 0, 0.55);
  color: var(--text);
  pointer-events: auto;
}
.who {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  color: var(--text);
}
.who:hover { text-decoration: none; color: #fff; }
.who b {
  font-family: var(--font-display);
  font-size: 16px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-weight: 500;
}
.who span { color: var(--text-dim); font-size: 13px; }
.join {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 28px;
  color: #fff;
  background: linear-gradient(180deg, var(--accent-bright), var(--accent-deep));
  border: 1px solid #7d2023;
  border-radius: 4px;
  font-family: var(--font-display);
  font-size: 14px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.join:hover { color: #fff; text-decoration: none; filter: brightness(1.12); }
.full {
  color: var(--text-faint);
  font-family: var(--font-display);
  font-size: 12px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
</style>
