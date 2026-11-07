<script setup lang="ts">
import { computed } from "vue";
import { perkIconSrc, perkStars } from "../lib/perkLevel";

const props = withDefaults(
  defineProps<{
    perk: string;
    level?: number | null;
    prestigeRank?: number;
    size?: number;
    title?: string;
  }>(),
  { level: null, prestigeRank: 0, size: 48, title: undefined },
);

const src = computed(() => perkIconSrc(props.perk, props.level, props.prestigeRank > 0));
const stars = computed(() => perkStars(props.level ?? -1));
const starSize = computed(() => Math.max(1, Math.round(props.size * 0.14)));
const maniac = computed(() => props.level !== null && props.level >= 9);
</script>

<template>
  <span
    v-if="src || stars.count"
    class="perk-badge"
    :class="{ maniac }"
    :style="{ width: `${size}px`, height: `${size}px` }"
    :title="title"
  >
    <img v-if="src" :src="src" alt="" />
    <span
      v-if="stars.count"
      class="perk-stars"
      :style="{ '--star': `${starSize}px` }"
      aria-hidden="true"
    >
      <img
        v-for="n in stars.count"
        :key="n"
        class="star"
        :src="stars.tone === 'gold' ? '/assets/perks/Hud_Perk_Star_Gold.png' : '/assets/perks/Hud_Perk_Star.png'"
        alt=""
      />
    </span>
  </span>
</template>

<style scoped>
.perk-badge {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  overflow: visible;
  transform: scale(var(--perk-grow, 1));
}
.perk-badge.maniac { transform: scale(calc(var(--perk-grow, 1) * 1.16)); }
.perk-badge img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
.perk-stars {
  position: absolute;
  right: 0;
  bottom: 0;
  width: var(--star);
  display: flex;
  flex-direction: column-reverse;
  align-items: center;
  gap: calc(var(--star) * 0.28);
  line-height: 0;
  filter: drop-shadow(0 0 1px #000);
}
.perk-stars .star {
  width: var(--star);
  height: var(--star);
  object-fit: contain;
  display: block;
}
</style>
