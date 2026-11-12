<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import AccountMenu from "~/components/AccountMenu.vue";
import FriendToast from "~/components/FriendToast.vue";
import FriendsStrip from "~/components/FriendsStrip.vue";
import { t } from "~/i18n";
import { prettyMap, noticePlace } from "~/lib/format";
import {
  beginFriendDemo,
  emitFriendAlert,
  friendDesktopNotify,
  friendNotify,
  refreshFriends,
  setFriendDesktopNotify,
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
    difficulty: 2,
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
    difficulty: 0,
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
    difficulty: 0,
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
    difficulty: 0,
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
    difficulty: 5,
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
    difficulty: 0,
  },
];

const playing = DEMO_FRIENDS[0];
const menuOpen = ref(true);
const denied = ref(typeof Notification !== "undefined" && Notification.permission === "denied");
const osStatus = ref<"" | "ask" | "sent" | "denied" | "unsupported">("");
const restore = beginFriendDemo(DEMO_FRIENDS);

function showNotice(): void {
  emitFriendAlert(playing, true);
}

function showOsNotice(): void {
  osStatus.value = "";
  if (typeof window === "undefined" || typeof Notification === "undefined") {
    osStatus.value = "unsupported";
    return;
  }
  const finish = (perm: NotificationPermission) => {
    denied.value = perm === "denied";
    if (perm !== "granted") {
      osStatus.value = "denied";
      return;
    }
    void deliverOsNotice();
  };
  // Called in the click itself. An async handler can lose the gesture, and
  // then the browser neither prompts nor shows anything.
  if (Notification.permission === "default") {
    osStatus.value = "ask";
    void Notification.requestPermission().then(finish, () => finish("denied"));
    return;
  }
  finish(Notification.permission);
}

async function deliverOsNotice(): Promise<void> {
  const where = noticePlace(playing.map ? prettyMap(playing.map) : "", playing.difficulty, playing.server);
  const title = playing.name;
  const body = t("friends.noticeBody", { place: where });
  const profileUrl = `/players/${playing.profile}`;
  const options: NotificationOptions = {
    body,
    tag: "kfm-friend-test",
    renotify: true,
    data: { url: profileUrl },
  };
  const openProfile = () => {
    window.focus();
    void navigateTo(profileUrl);
  };
  try {
    // A page Notification is hidden while this tab is focused. The worker
    // shows it on the device anyway. A click opens the player's stats page.
    if ("serviceWorker" in navigator) {
      await navigator.serviceWorker.register("/sw.js", { scope: "/" });
      const reg = await navigator.serviceWorker.ready;
      await reg.showNotification(title, options);
      osStatus.value = "sent";
      return;
    }
  } catch {
    // Fall through to the page notification.
  }
  try {
    const note = new Notification(title, options);
    note.onclick = () => {
      openProfile();
      note.close();
    };
    osStatus.value = "sent";
  } catch {
    osStatus.value = "denied";
    denied.value = true;
  }
}

function onToggleNotify(): void {
  setFriendNotify(!friendNotify.value);
}

function onToggleDesktop(): void {
  const next = !friendDesktopNotify.value;
  if (!next) {
    void setFriendDesktopNotify(false);
    return;
  }
  if (typeof Notification === "undefined") {
    denied.value = false;
    return;
  }
  const enable = (result: NotificationPermission) => {
    denied.value = result === "denied";
    if (result === "granted") void setFriendDesktopNotify(true);
  };
  if (Notification.permission === "default") {
    void Notification.requestPermission().then(enable, () => enable("denied"));
    return;
  }
  enable(Notification.permission);
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
      :desktop="friendDesktopNotify"
      :denied="denied"
      @toggle="menuOpen = !menuOpen"
      @toggle-notify="onToggleNotify"
      @toggle-desktop="onToggleDesktop"
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
      :join="playing.join"
      :full="playing.full"
      :difficulty="playing.difficulty"
    />
    <div class="notice-actions">
      <button class="again" type="button" @click="showNotice">{{ t("demo.showNotice") }}</button>
      <button class="again" type="button" @click="showOsNotice">{{ t("demo.testOs") }}</button>
    </div>
    <p v-if="osStatus === 'ask'" class="empty-note">{{ t("demo.osAsk") }}</p>
    <p v-else-if="osStatus === 'sent'" class="empty-note">{{ t("demo.osSent") }}</p>
    <p v-else-if="osStatus === 'denied'" class="empty-note">{{ t("friends.allow") }}</p>
    <p v-else-if="osStatus === 'unsupported'" class="empty-note">{{ t("demo.osUnsupported") }}</p>
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
.notice-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
.again {
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
.again:hover { color: var(--text); border-color: var(--accent-deep); }
</style>
