<script setup lang="ts">
import { onMounted, ref } from "vue";
import { fetchTopPlayers, type TopPlayerEntry } from "~/api";
import { fmtNum } from "~/lib/format";
import { friendsById, type Friend } from "~/lib/friends";
import { t } from "~/i18n";

const rows = ref<TopPlayerEntry[]>([]);
const loading = ref(true);
const failed = ref(false);
const avatarFailed = ref(new Set<number>());

onMounted(async () => {
  try {
    rows.value = await fetchTopPlayers();
  } catch {
    failed.value = true;
  } finally {
    loading.value = false;
  }
});

function linkFor(r: TopPlayerEntry): string {
  return `/players/${/^\d{16,20}$/.test(r.steamId) ? r.steamId : r.id}`;
}

function avatarUrl(r: TopPlayerEntry): string {
  return /^\d{16,20}$/.test(r.steamId) && !avatarFailed.value.has(r.id)
    ? `/api/stats/avatar/full?steam=${r.steamId}`
    : "";
}

function onAvatarError(r: TopPlayerEntry): void {
  avatarFailed.value = new Set(avatarFailed.value).add(r.id);
}

function liveFriend(r: TopPlayerEntry): Friend | null {
  const friend = friendsById.value.get(r.steamId);
  return friend?.playing ? friend : null;
}
</script>

<template>
  <div class="page">
    <h2 class="section-title">{{ t("nav.home") }} <span class="count">TOP 100</span></h2>
    <p v-if="loading" class="empty-note">{{ t("loading") }}</p>
    <p v-else-if="failed" class="empty-note">{{ t("error") }}</p>
    <div v-else class="panel">
      <table class="top-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Player</th>
            <th>Score</th>
            <th>Kills</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="r in rows"
            :key="r.id"
            :class="{ 'friend-on': liveFriend(r) }"
            @click="$router.push(linkFor(r))"
          >
            <td class="top-rank">{{ r.rank }}</td>
            <td>
              <div class="top-cell">
                <img
                  v-if="avatarUrl(r)"
                  class="top-avatar"
                  :src="avatarUrl(r)"
                  :alt="r.name"
                  loading="lazy"
                  @error="onAvatarError(r)"
                />
                <span v-else class="top-avatar top-avatar-empty">
                  <img src="/assets/avatar-skull.svg" alt="" />
                </span>
                <span class="top-name">{{ r.name }}</span>
                <span v-if="r.admin" class="top-admin">{{ t("hero.admin") }}</span>
                <span v-if="r.veteran" class="top-veteran" :title="t('hero.veteranHint')">{{ t("hero.veteran") }}</span>
                <template v-if="liveFriend(r)">
                  <span class="top-where">{{ t("friends.playingOn", { server: liveFriend(r)?.server || "" }) }}</span>
                  <a
                    v-if="!liveFriend(r)?.full && (liveFriend(r)?.join || '').startsWith('steam://run/')"
                    class="top-join"
                    :href="liveFriend(r)?.join || ''"
                    @click.stop
                  >{{ t("friends.join") }}</a>
                  <span v-else-if="liveFriend(r)?.full" class="top-full">{{ t("srv.full") }}</span>
                </template>
              </div>
            </td>
            <td class="top-score">{{ fmtNum(r.score) }}</td>
            <td>{{ fmtNum(r.kills) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.top-table { width: 100%; border-collapse: collapse; table-layout: fixed; }
.top-table th, .top-table td {
  text-align: left;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
}
.top-table th:nth-child(1), .top-table td:nth-child(1) { width: 52px; }
.top-table th:nth-child(3), .top-table td:nth-child(3) { width: 110px; }
.top-table th:nth-child(4), .top-table td:nth-child(4) { width: 84px; }
.top-table th {
  font-family: var(--font-display);
  font-size: 13px;
  letter-spacing: 0.112em;
  text-transform: uppercase;
  color: var(--text-faint);
  font-weight: 400;
}
.top-table tbody tr { cursor: pointer; }
.top-table tbody tr:hover { background: rgba(198, 18, 23, 0.07); }
.top-table tbody tr.friend-on td {
  border-top: 1px solid #7d2023;
  border-bottom: 1px solid #3d1012;
  background: linear-gradient(180deg, rgba(198, 18, 23, 0.26), #12080a);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
}
.top-table tbody tr.friend-on td:first-child {
  box-shadow: inset 1px 0 0 #7d2023, inset 0 1px 0 rgba(255, 255, 255, 0.08);
}
.top-table tbody tr.friend-on td:last-child {
  box-shadow: inset -1px 0 0 #7d2023, inset 0 1px 0 rgba(255, 255, 255, 0.08);
}
.top-table tbody tr.friend-on:hover td {
  background: linear-gradient(180deg, rgba(198, 18, 23, 0.34), #1a0a0c);
}
.top-rank { font-family: var(--font-display); font-size: 20px; color: var(--accent-bright); width: 56px; }
.top-cell { display: flex; align-items: center; gap: 12px; min-width: 0; flex-wrap: wrap; }
.top-avatar {
  width: 40px;
  height: 40px;
  flex: none;
  border-radius: 50%;
  object-fit: cover;
  background: #0b0b0e;
  border: 1px solid var(--border);
  box-shadow: 0 0 10px rgba(198, 18, 23, 0.15);
}
.top-avatar-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle at 50% 40%, #1c1c24, #0c0c10);
}
.top-avatar-empty img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0.82;
}
.top-name { color: var(--text); font-weight: 600; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.top-admin {
  font-family: var(--font-display);
  font-size: 11px;
  letter-spacing: 0.096em;
  color: #ff8a8d;
  border: 1px solid #7d2023;
  background: rgba(198, 18, 23, 0.18);
  padding: 1px 6px;
  text-transform: uppercase;
}
.top-veteran {
  font-family: var(--font-display);
  font-size: 11px;
  letter-spacing: 0.096em;
  color: var(--gold-bright);
  border: 1px solid #7d6118;
  background: rgba(199, 139, 18, 0.14);
  padding: 1px 6px;
  text-transform: uppercase;
}
.top-where {
  margin-left: auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
  font-size: 13px;
}
.top-join {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  height: 24px;
  padding: 0 8px;
  color: #fff;
  background: linear-gradient(180deg, var(--accent-bright), var(--accent-deep));
  border: 1px solid #7d2023;
  border-radius: 4px;
  font-family: var(--font-display);
  font-size: 13px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.top-join:hover { color: #fff; text-decoration: none; filter: brightness(1.12); }
.top-full {
  flex: none;
  color: var(--text-faint);
  font-family: var(--font-display);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.top-score { font-family: var(--font-display); font-size: 20px; color: #fff; }

@media (max-width: 640px) {
  .top-table th, .top-table td { padding: 8px 6px; }
  .top-table th:nth-child(1), .top-table td:nth-child(1) { width: 34px; }
  .top-table th:nth-child(3), .top-table td:nth-child(3) { width: 86px; }
  .top-table th:nth-child(4), .top-table td:nth-child(4) { width: 54px; }
  .top-rank { font-size: 16px; }
  .top-cell { gap: 8px; flex-wrap: wrap; row-gap: 2px; }
  .top-avatar { width: 30px; height: 30px; }
  .top-name { font-size: 13px; flex: 1 1 auto; }
  .top-admin, .top-veteran { font-size: 9px; letter-spacing: 0.048em; padding: 0 4px; }
  .top-where { flex: 1 1 100%; margin-left: 38px; font-size: 12px; }
  .top-join { height: 22px; font-size: 12px; }
  .top-score { font-size: 16px; }
  .top-table td:nth-child(4) { font-size: 12.5px; }
}
</style>
