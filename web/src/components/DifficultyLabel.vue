<script setup lang="ts">
import { computed } from "vue";
import { t } from "../i18n";
import { difficultyName } from "../lib/format";

const props = defineProps<{ level: number; at?: number }>();

const tier = computed(() => difficultyName(props.level, props.at));

const label = computed(() => {
  const name = tier.value;
  const key =
    name === "Underworld"
      ? "diff.underworld"
      : name === "Brutal"
        ? "diff.brutal"
        : name === "Hell on Earth"
          ? "diff.hoe"
          : name === "Suicidal"
            ? "diff.suicidal"
            : name === "Hard"
              ? "diff.hard"
              : name === "Normal"
                ? "diff.normal"
                : name === "Beginner"
                  ? "diff.beginner"
                  : "";
  if (!key) return "";
  const text = t(key);
  return text === key ? name : text;
});

const tone = computed(() => {
  const n = props.level;
  if (n >= 8) return "brutal";
  if (n >= 7) return "hoe";
  if (n >= 5) return "suicidal";
  if (n >= 4) return "hard";
  if (n >= 2) return "normal";
  if (n > 0) return "beginner";
  return "";
});
</script>

<template>
  <span v-if="label" class="diff" :class="tone">{{ label }}</span>
  <span v-else class="diff none">—</span>
</template>

<style scoped>
.diff { color: var(--text); }
.diff.none { color: var(--text-faint); }
.diff.beginner { color: var(--text-dim); }
.diff.normal { color: #fff; }
.diff.hard { color: #f0d24a; }
.diff.suicidal {
  color: #f08a2a;
  text-shadow: 0 0 8px rgba(240, 138, 42, 0.45);
}
.diff.hoe {
  color: #e04a1a;
  text-shadow: 0 0 8px rgba(224, 74, 26, 0.55), 0 0 16px rgba(224, 74, 26, 0.25);
}
.diff.brutal {
  font-family: var(--font-display);
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #c61217;
  text-shadow: 0 0 8px rgba(198, 18, 23, 0.9), 0 0 18px rgba(198, 18, 23, 0.45);
  animation: brutal-shimmer 2.4s ease-in-out infinite;
}
@keyframes brutal-shimmer {
  0%, 100% { filter: brightness(1); }
  50% { filter: brightness(1.35); }
}
</style>
