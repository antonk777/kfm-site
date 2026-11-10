<script setup lang="ts">
import { t } from "../i18n";

defineProps<{
  name: string;
  server: string;
  map?: string;
  profile: string;
}>();
</script>

<template>
  <router-link class="friend-toast" :to="`/players/${profile}`">
    <b>{{ name }}</b>
    <span>{{ t("friends.playingOn", { server }) }}</span>
    <span v-if="map" class="toast-map">{{ map }}</span>
  </router-link>
</template>

<style scoped>
.friend-toast {
  display: flex;
  flex-direction: column;
  gap: 2px;
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
.friend-toast:hover { text-decoration: none; color: #fff; }
.friend-toast b {
  font-family: var(--font-display);
  font-size: 16px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-weight: 500;
}
.friend-toast span { color: var(--text-dim); font-size: 13px; }
.toast-map { color: var(--text-faint); }
</style>
