<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import AccountMenu from "~/components/AccountMenu.vue";
import FriendToast from "~/components/FriendToast.vue";
import FriendsStrip from "~/components/FriendsStrip.vue";
import { t } from "~/i18n";
import { prettyMap } from "~/lib/format";
import {
  beginFriendDemo,
  emitFriendAlert,
  friendNotify,
  refreshFriends,
  setFriendNotify,
  type Friend,
} from "~/lib/friends";
import { profileTo, steamUser } from "~/lib/steam";

const DEMO_FRIENDS: Friend[] = [
  {
    steamId: "76561198000000002",
    name: "Alex",
    profile: "76561198000000002",
    avatar: "",
    playing: true,
    played: true,
    serverId: "meatgrinder",
    server: "Meat Grinder",
    map: "KF-WestLondon",
    perk: "Commando",
    join: "steam://run/1250//85.192.30.108:7707",
    full: false,
  },
  {
    steamId: "76561198000000003",
    name: "Blair",
    profile: "76561198000000003",
    avatar: "",
    playing: false,
    played: true,
    serverId: "",
    server: "",
    map: "",
    perk: "",
    join: "",
    full: false,
  },
  {
    steamId: "76561198000000005",
    name: "Drew",
    profile: "76561198000000005",
    avatar: "",
    playing: false,
    played: true,
    serverId: "",
    server: "",
    map: "",
    perk: "",
    join: "",
    full: false,
  },
  {
    steamId: "76561198000000006",
    name: "Eden",
    profile: "76561198000000006",
    avatar: "",
    playing: false,
    played: true,
    serverId: "",
    server: "",
    map: "",
    perk: "",
    join: "",
    full: false,
  },
  {
    steamId: "76561198000000007",
    name: "Fran",
    profile: "76561198000000007",
    avatar: "",
    playing: true,
    played: true,
    serverId: "bloodbath",
    server: "Bloodbath",
    map: "KF-Foundry",
    perk: "Berserker",
    join: "steam://run/1250//85.192.30.108:7708",
    full: true,
  },
  {
    steamId: "76561198000000004",
    name: "Casey",
    profile: "76561198000000004",
    avatar: "",
    playing: false,
    played: false,
    serverId: "",
    server: "",
    map: "",
    perk: "",
    join: "",
    full: false,
  },
];

const playing = DEMO_FRIENDS[0];
const menuOpen = ref(true);
const denied = ref(typeof Notification !== "undefined" && Notification.permission === "denied");
const restore = beginFriendDemo(DEMO_FRIENDS);

function showNotice(): void {
  emitFriendAlert(playing);
}

async function onToggleNotify(): Promise<void> {
  const next = !friendNotify.value;
  if (next && typeof Notification !== "undefined" && Notification.permission === "default") {
    try {
      const result = await Notification.requestPermission();
      denied.value = result === "denied";
    } catch {
      denied.value = true;
    }
  } else if (typeof Notification !== "undefined") {
    denied.value = Notification.permission === "denied";
  }
  await setFriendNotify(next);
}

onMounted(() => {
  window.setTimeout(showNotice, 0);
});

onBeforeUnmount(() => {
  restore();
  if (steamUser.value?.loggedIn) void refreshFriends();
});
</script>

<template>
  <div class="page">
    <h2 class="section-title">{{ t("demo.title") }}</h2>
    <p class="empty-note">{{ t("demo.hint") }}</p>

    <h3 class="label">{{ t("demo.menu") }}</h3>
    <AccountMenu
      inline
      :open="menuOpen"
      profile-to="/players"
      :playing="2"
      :notify="friendNotify"
      :denied="friendNotify && denied"
      @toggle="menuOpen = !menuOpen"
      @toggle-notify="onToggleNotify"
    />

    <h3 class="label">{{ t("demo.profile") }}</h3>
    <section class="panel you">
      <img src="/assets/avatar-skull.svg" alt="" />
      <div>
        <b>{{ t("demo.you") }}</b>
        <router-link :to="profileTo">{{ t("nav.profile") }}</router-link>
      </div>
    </section>
    <FriendsStrip />

    <h3 class="label">{{ t("demo.notice") }}</h3>
    <FriendToast
      :name="playing.name"
      :server="playing.server"
      :map="prettyMap(playing.map)"
      :profile="playing.profile"
    />
    <button class="again" type="button" @click="showNotice">{{ t("demo.showNotice") }}</button>
  </div>
</template>

<style scoped>
.label {
  margin: 28px 0 10px;
  font-family: var(--font-display);
  font-size: 15px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-dim);
  font-weight: 500;
}
.you {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 8px;
  padding: 14px 16px;
}
.you img {
  width: 64px;
  height: 64px;
  object-fit: cover;
  background: #0c0c10;
  border: 1px solid var(--border);
}
.you b {
  display: block;
  font-family: var(--font-display);
  font-size: 28px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-weight: 500;
  color: #fff;
}
.again {
  appearance: none;
  margin-top: 12px;
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
.again:hover { color: var(--text); border-color: var(--accent-deep); }
</style>
