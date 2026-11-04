<script setup lang="ts">
import { computed } from "vue";
import type { PerkInfo } from "../api";
import { fmtNum } from "../lib/format";
import { t } from "../i18n";

const props = defineProps<{ perk: PerkInfo }>();

// Texture names in MutZombies_T.HUD (full-res, extracted from the .utx).
const GAME_ICON: Record<string, string> = {
  Field_Medic: "Medic",
  Support_Specialist: "Support",
  Sharpshooter: "SharpShooter",
  Commando: "Commando",
  Berserker: "Berserker",
  Firebug: "Firebug",
  Demolition: "Demolition",
};

const iconUrl = computed(() => {
  const base = GAME_ICON[props.perk.id] ?? props.perk.id;
  // Game HUD tier: prestiged perks show the coloured icon, prestige rank 2+
  // the gold one (OnPrlvlHUDIcons / OnPr6lvlHUDIcons in HUDKillingFloorExNew).
  const variant =
    props.perk.prestigeRank >= 2 ? "Gold_Prestige" : props.perk.prestigeRank > 0 ? "Prestige" : "White";
  return `/assets/perks/Perk_${base}_${variant}.png`;
});

const note = computed(() =>
  props.perk.stats
    .map((s) => `${t(`stat.${s.key}`)} ${fmtNum(s.effective)} / ${fmtNum(s.req)}`)
    .join(" · "),
);

function statLine(s: PerkInfo["stats"][number]): string {
  return `${t(`stat.${s.key}`)} ${fmtNum(s.effective)} / ${fmtNum(s.req)}`;
}
</script>

<template>
  <div class="perk-card" :class="{ prestige: perk.prestigeRank > 0 }">
    <div class="perk-icon">
      <img :src="iconUrl" :alt="t(`perk.${perk.id}`)" />
    </div>
    <div class="perk-body">
      <div class="perk-head">
        <span class="perk-name">{{ t(`perk.${perk.id}`) }}</span>
        <span class="perk-level">
          <template v-if="perk.level >= 9">MANIAC</template>
          <template v-else><small>{{ t("perks.level") }}</small> {{ perk.level }}</template>
          <small v-if="perk.prestigeRank > 0">· P{{ perk.prestigeRank }}</small>
        </span>
      </div>
      <div class="progress-track">
        <div class="progress-fill" :style="{ width: `${Math.round(perk.progress * 100)}%` }" />
      </div>
      <div class="progress-note">
        <template v-if="perk.stats.length > 1">
          <div>
            <span class="note-pct">{{ Math.round(perk.progress * 100) }}%</span><span class="note-sep">&nbsp;&nbsp;·&nbsp;&nbsp;</span>{{ statLine(perk.stats[0]) }}
          </div>
          <div v-for="s in perk.stats.slice(1)" :key="s.key">{{ statLine(s) }}</div>
        </template>
        <template v-else>
          <span class="note-pct">{{ Math.round(perk.progress * 100) }}%</span><span class="note-sep">&nbsp;&nbsp;·&nbsp;&nbsp;</span>{{ note }}
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.perk-card {
  padding: 14px;
  display: flex;
  gap: 14px;
  min-width: 0;
  overflow: hidden;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.035), rgba(0, 0, 0, 0.3));
  border: 1px solid var(--border);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}
.perk-card.prestige {
  border-color: #6e5513;
  background: linear-gradient(180deg, #241d0f, #17120a);
}
.perk-icon {
  width: 44px;
  height: 44px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
}
.perk-icon img { max-width: 100%; max-height: 100%; }

.perk-body { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.perk-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  column-gap: 10px;
  row-gap: 2px;
}
.perk-name {
  font-family: var(--font-display);
  font-size: 24px;
  line-height: 1.05;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text);
  min-width: 0;
}
.perk-level {
  font-family: var(--font-display);
  font-size: 24px;
  line-height: 1.05;
  color: #fff;
  white-space: nowrap;
}
.perk-level small { color: var(--text-faint); font-size: 13px; letter-spacing: 0.12em; }
.perk-card.prestige .perk-level { color: var(--gold-bright); }

.progress-track {
  margin-top: 10px;
  height: 9px;
  background: #0b0b0e;
  border: 1px solid var(--border);
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent-deep), var(--accent));
  box-shadow: 0 0 8px rgba(198, 18, 23, 0.55);
}
.perk-card.prestige .progress-fill {
  background: linear-gradient(90deg, #6e5513, var(--gold));
  box-shadow: 0 0 8px rgba(199, 139, 18, 0.5);
}
.progress-note { margin-top: 7px; font-size: 11.5px; line-height: 1.45; color: var(--text-dim); overflow-wrap: anywhere; }
.perk-card.prestige .progress-note { color: var(--gold); }
.note-pct { color: #fff; font-weight: 700; }
.note-sep { color: var(--text-faint); }
</style>
