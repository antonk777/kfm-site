<script setup lang="ts">
import { computed, ref } from "vue";
import { t } from "../i18n";
import { prettyMap } from "../lib/format";
import type { Friend } from "../lib/friends";
import PerkIcon from "./PerkIcon.vue";

const props = defineProps<{ friend: Friend }>();
const broken = ref(false);

const avatar = computed(() =>
  !broken.value && props.friend.avatar.startsWith("https://") ? props.friend.avatar : "",
);
const profileTo = computed(() => `/players/${props.friend.profile}`);
const joinHref = computed(() =>
  props.friend.playing && props.friend.join.startsWith("steam://run/") ? props.friend.join : "",
);
const mapLabel = computed(() => (props.friend.map ? prettyMap(props.friend.map) : ""));
</script>

<template>
  <article class="friend panel" :class="{ playing: friend.playing }">
    <router-link class="who" :to="profileTo">
      <span class="avatar">
        <img v-if="avatar" :src="avatar" alt="" @error="broken = true" />
        <img v-else src="/assets/avatar-skull.svg" alt="" />
      </span>
      <span class="meta">
        <span class="name">{{ friend.name }}</span>
        <span v-if="friend.playing" class="where">
          <PerkIcon v-if="friend.perk" :perk="friend.perk" :size="18" />
          <span class="where-text">
            <b>{{ friend.server }}</b>
            <span v-if="mapLabel" class="map">{{ mapLabel }}</span>
          </span>
        </span>
      </span>
    </router-link>
    <a v-if="joinHref && !friend.full" class="join" :href="joinHref">{{ t("friends.join") }}</a>
    <span v-else-if="friend.playing && friend.full" class="full">{{ t("srv.full") }}</span>
  </article>
</template>

<style scoped>
.friend {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 10px;
  height: 100%;
  min-width: 0;
  padding: 12px;
  box-sizing: border-box;
}
.friend.playing {
  border-color: #7d2023;
  background: linear-gradient(180deg, rgba(198, 18, 23, 0.28), #12080a);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08), 0 1px 2px rgba(0, 0, 0, 0.5);
}
.who {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 10px;
  min-width: 0;
  color: var(--text);
}
.who:hover { color: #fff; text-decoration: none; }
.avatar {
  width: 44px;
  height: 44px;
  flex: none;
  background: #0c0c10;
  border: 1px solid var(--border);
  overflow: hidden;
}
.avatar img { width: 100%; height: 100%; object-fit: cover; display: block; }
.meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-display);
  font-size: 16px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.where {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  color: var(--text-dim);
  font-size: 12px;
}
.where-text { min-width: 0; }
.where b {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
  font-weight: 600;
}
.map {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-faint);
}
.join {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 28px;
  margin-top: auto;
  padding: 0 10px;
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
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 28px;
  margin-top: auto;
  color: var(--text-faint);
  font-family: var(--font-display);
  font-size: 13px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
</style>
