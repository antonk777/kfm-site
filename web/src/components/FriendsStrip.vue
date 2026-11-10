<script setup lang="ts">
import { computed } from "vue";
import { t } from "../i18n";
import { friends, friendsStatus, steamFriendsPrivacy } from "../lib/friends";
import { steamUser } from "../lib/steam";
import FriendRow from "./FriendRow.vue";

const privacy = computed(() => steamFriendsPrivacy(steamUser.value?.steamId || ""));
const all = computed(() => friends.value ?? []);
const list = computed(() => all.value.filter((friend) => friend.played));
</script>

<template>
  <section>
    <h2 class="section-title">
      {{ t("friends.title") }}
      <span v-if="friendsStatus === 'ok'" class="count">{{ list.length }}</span>
    </h2>
    <p v-if="friendsStatus === 'idle' || friendsStatus === 'loading'" class="empty-note">{{ t("loading") }}</p>
    <p v-else-if="friendsStatus === 'private'" class="empty-note">
      {{ t("friends.private") }}
      <a v-if="privacy" :href="privacy" target="_blank" rel="noopener">{{ t("friends.privacy") }}</a>
    </p>
    <p v-else-if="friendsStatus === 'noconfig'" class="empty-note">{{ t("friends.noconfig") }}</p>
    <p v-else-if="friendsStatus === 'unavailable' || friendsStatus === 'login'" class="empty-note">{{ t("friends.unavailable") }}</p>
    <p v-else-if="!all.length" class="empty-note">{{ t("friends.empty") }}</p>
    <p v-else-if="!list.length" class="empty-note">{{ t("friends.nonePlayed") }}</p>
    <div v-else class="cards">
      <FriendRow v-for="friend in list" :key="friend.steamId" :friend="friend" />
    </div>
  </section>
</template>

<style scoped>
.cards {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}
@media (max-width: 1100px) {
  .cards { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
@media (max-width: 860px) {
  .cards { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 640px) {
  .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 420px) {
  .cards { grid-template-columns: minmax(0, 1fr); }
}
.empty-note a { margin-left: 6px; }
</style>
