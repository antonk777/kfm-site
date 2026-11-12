<script setup lang="ts">
import { ref } from "vue";
import { t } from "../i18n";

defineProps<{
  open: boolean;
  inline?: boolean;
  profileTo: string;
  playing: number;
  notify: boolean;
  desktop: boolean;
  denied?: boolean;
  admin?: boolean;
}>();

defineEmits<{
  toggle: [];
  logout: [];
  "toggle-notify": [];
  "toggle-desktop": [];
}>();

const root = ref<HTMLElement | null>(null);

function contains(node: Node): boolean {
  return root.value?.contains(node) ?? false;
}

defineExpose({ contains });
</script>

<template>
  <div ref="root" class="header-account-wrap" :class="{ open, inline }">
    <div class="header-account">
      <button
        class="header-account-profile"
        type="button"
        aria-haspopup="menu"
        :aria-expanded="open"
        @click="$emit('toggle')"
      >
        {{ t("nav.profile") }}
        <span v-if="playing" class="account-badge">{{ playing }}</span>
        <svg class="account-caret" :class="{ open }" viewBox="0 0 10 6" width="10" height="6" aria-hidden="true">
          <path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.5" />
        </svg>
      </button>
    </div>
    <div v-if="open" class="account-menu" role="menu">
      <router-link role="menuitem" :to="profileTo" @click="$emit('toggle')">{{ t("nav.profile") }}</router-link>
      <router-link v-if="admin" role="menuitem" to="/statistics" @click="$emit('toggle')">{{ t("nav.statistics") }}</router-link>
      <router-link role="menuitem" to="/friends" @click="$emit('toggle')">
        {{ t("nav.friends") }}
        <span v-if="playing" class="menu-count">{{ playing }}</span>
      </router-link>
      <div class="account-notify">
        <button
          class="account-check"
          type="button"
          role="checkbox"
          :aria-checked="notify"
          @click="$emit('toggle-notify')"
        >
          <span class="box" :class="{ on: notify }" aria-hidden="true"></span>
          <span>{{ t("nav.notifySite") }}</span>
        </button>
        <button
          class="account-check"
          type="button"
          role="checkbox"
          :aria-checked="desktop"
          @click="$emit('toggle-desktop')"
        >
          <span class="box" :class="{ on: desktop }" aria-hidden="true"></span>
          <span>{{ t("nav.notifyDesktop") }}</span>
        </button>
      </div>
      <p v-if="denied" class="account-note">{{ t("friends.allow") }}</p>
      <div class="account-end">
        <button class="account-logout" type="button" role="menuitem" @click="$emit('logout')">
          {{ t("nav.logout") }}
          <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.header-account-wrap { position: relative; flex: none; }
.header-account-wrap.open .header-account { border-color: var(--accent-deep); }
.header-account-wrap.inline { width: 100%; }
.header-account {
  display: flex;
  align-items: stretch;
  width: fit-content;
  height: 32px;
  flex: none;
  border: 1px solid var(--border-bright);
  border-radius: 4px;
  background: var(--panel-2);
  overflow: hidden;
}
.header-account:hover { border-color: var(--accent-deep); }
.header-account-profile {
  appearance: none;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 10px;
  border: 0;
  background: transparent;
  color: var(--text-dim);
  font-family: var(--font-display);
  font-size: 15px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  white-space: nowrap;
  cursor: pointer;
}
.header-account-profile:hover {
  color: var(--text);
  background: var(--panel);
}
.account-caret { display: block; }
.account-caret.open { transform: rotate(180deg); }
.account-badge,
.menu-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  min-width: 16px;
  height: 16px;
  padding: 1px 4px 0;
  border-radius: 8px;
  background: var(--accent);
  color: #fff;
  font-family: var(--font-body);
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
  letter-spacing: 0;
  text-transform: none;
}
.account-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 30;
  min-width: 260px;
  padding: 6px;
  background: rgba(16, 16, 20, 0.98);
  border: 1px solid var(--border-bright);
  border-radius: 4px;
  box-shadow: 0 14px 26px rgba(0, 0, 0, 0.55);
}
.inline .account-menu {
  position: static;
  width: min(320px, 100%);
  min-width: 0;
  margin-top: 8px;
}
.account-menu a {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 10px;
  color: var(--text);
  font-family: var(--font-display);
  font-size: 16px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.account-menu a:hover,
.account-menu a.router-link-active {
  color: #fff;
  background: rgba(198, 18, 23, 0.16);
  text-decoration: none;
}
.account-notify {
  margin-top: 4px;
  padding: 8px 10px 2px;
  border-top: 1px solid var(--border);
}
.account-check {
  appearance: none;
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  margin: 0 0 8px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text);
  font: 13px/1.35 var(--font-body);
  text-align: left;
  cursor: pointer;
}
.box {
  width: 14px;
  height: 14px;
  flex: none;
  border: 1px solid var(--border-bright);
  border-radius: 2px;
  background: #1a1a20 center / 12px 12px no-repeat;
}
.box.on {
  background-color: var(--accent);
  border-color: var(--accent);
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'%3E%3Cpath d='M2 6.2 4.6 9 10 3' fill='none' stroke='white' stroke-width='1.8' stroke-linecap='square'/%3E%3C/svg%3E");
}
.account-check:hover { color: #fff; }
.account-note {
  margin: 0;
  padding: 0 10px 8px;
  color: var(--text-faint);
  font-size: 12px;
  line-height: 1.4;
}
.account-end {
  padding-top: 4px;
  border-top: 1px solid var(--border);
}
.account-logout {
  appearance: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 8px 10px;
  border: 0;
  background: transparent;
  color: var(--text-dim);
  font-family: var(--font-display);
  font-size: 16px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  text-align: left;
  cursor: pointer;
}
.account-logout svg { display: block; flex: none; }
.account-logout:hover {
  color: #fff;
  background: rgba(198, 18, 23, 0.16);
}
</style>
