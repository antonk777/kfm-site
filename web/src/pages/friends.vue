<script setup lang="ts">
import { computed, ref } from "vue";
import SteamMark from "~/components/SteamMark.vue";
import FriendRow from "~/components/FriendRow.vue";
import { t } from "~/i18n";
import { friends, friendsStatus, refreshFriends, steamFriendsPrivacy } from "~/lib/friends";
import { steamReady, steamUser } from "~/lib/steam";

const query = ref("");
const refreshing = ref(false);

const privacy = computed(() => steamFriendsPrivacy(steamUser.value?.steamId || ""));
const loggedIn = computed(() => steamUser.value?.loggedIn === true);

const known = computed(() => (friends.value ?? []).filter((friend) => friend.played));

const filtered = computed(() => {
  const list = known.value;
  const q = query.value.trim().toLowerCase();
  if (!q) return list;
  return list.filter((friend) => friend.name.toLowerCase().includes(q));
});

async function reload(): Promise<void> {
  refreshing.value = true;
  try {
    await refreshFriends(true);
  } finally {
    refreshing.value = false;
  }
}
</script>

<template>
  <div class="page">
    <h2 class="section-title">
      {{ t("friends.title") }}
      <span v-if="loggedIn && friendsStatus === 'ok'" class="count">{{ known.length }}</span>
    </h2>

    <p v-if="!steamReady" class="empty-note">{{ t("loading") }}</p>

    <section v-else-if="!loggedIn" class="panel gate">
      <a class="login" href="/api/stats/steam/login">
        <SteamMark />
        {{ t("nav.login") }}
      </a>
      <p>{{ t("friends.login") }}</p>
    </section>

    <template v-else>
      <p v-if="friendsStatus === 'loading' || friendsStatus === 'idle'" class="empty-note">{{ t("loading") }}</p>
      <section v-else-if="friendsStatus === 'private'" class="panel gate">
        <p>{{ t("friends.private") }}</p>
        <a v-if="privacy" class="privacy" :href="privacy" target="_blank" rel="noopener">{{ t("friends.privacy") }}</a>
      </section>
      <p v-else-if="friendsStatus === 'noconfig'" class="empty-note">{{ t("friends.noconfig") }}</p>
      <p v-else-if="friendsStatus === 'unavailable' || friendsStatus === 'login'" class="empty-note">{{ t("friends.unavailable") }}</p>
      <template v-else>
        <div class="toolbar">
          <input
            v-if="known.length > 8"
            v-model="query"
            type="search"
            :placeholder="t('friends.filter')"
            :aria-label="t('friends.filter')"
            spellcheck="false"
            autocomplete="off"
          />
          <button type="button" :disabled="refreshing" @click="reload">
            {{ t("friends.refresh") }}
          </button>
        </div>
        <p v-if="!(friends?.length ?? 0)" class="empty-note">{{ t("friends.empty") }}</p>
        <p v-else-if="!known.length" class="empty-note">{{ t("friends.nonePlayed") }}</p>
        <p v-else-if="!filtered.length" class="empty-note">{{ t("friends.noMatch") }}</p>
        <div v-else class="cards">
          <FriendRow v-for="friend in filtered" :key="friend.steamId" :friend="friend" />
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  gap: 8px;
  margin: 0 0 14px;
}
.toolbar input {
  flex: 1;
  min-width: 0;
  max-width: 320px;
  border: 1px solid var(--border-bright);
  border-radius: 4px;
  background: var(--panel);
  color: var(--text);
  font: 13px var(--font-body);
  padding: 7px 10px;
}
.toolbar input:focus { outline: none; border-color: var(--accent-deep); }
.toolbar button {
  appearance: none;
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--border-bright);
  border-radius: 4px;
  background: var(--panel-2);
  color: var(--text-dim);
  font-family: var(--font-display);
  font-size: 14px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  cursor: pointer;
}
.toolbar button:hover { color: var(--text); border-color: var(--accent-deep); }
.toolbar button:disabled { opacity: 0.5; cursor: wait; }
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
.gate {
  padding: 18px 16px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
}
.gate p { margin: 0; max-width: 40em; color: var(--text-dim); font-size: 14px; }
.login {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 14px;
  color: #fff;
  background: linear-gradient(180deg, var(--accent-bright), var(--accent-deep));
  border: 1px solid #7d2023;
  border-radius: 4px;
  font-family: var(--font-display);
  font-size: 16px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.login:hover { color: #fff; text-decoration: none; filter: brightness(1.12); }
.privacy { font-size: 14px; }
</style>
