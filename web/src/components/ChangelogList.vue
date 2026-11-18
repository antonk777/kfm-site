<script setup lang="ts">
import type { DayGroup } from "../lib/changelog";
import { t } from "../i18n";

defineProps<{ groups: DayGroup[] }>();
</script>

<template>
  <section v-for="group in groups" :key="group.key" class="day panel">
    <h3>{{ group.day }}</h3>
    <p v-if="group.summary" class="day-summary">{{ group.summary }}</p>
    <details class="day-details">
      <summary>{{ t("changelog.all") }} <span class="note-count">({{ group.notes.length }})</span></summary>
      <ul>
        <li v-for="(note, i) in group.notes" :key="`${group.key}-${i}`">{{ note }}</li>
      </ul>
    </details>
  </section>
</template>

<style scoped>
.day {
  padding: 16px 18px;
  margin: 0 0 12px;
}
.day h3 {
  margin: 0 0 4px;
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 500;
  letter-spacing: 0.03em;
  color: var(--gold-bright);
}
.day ul {
  margin: 0;
  padding: 0;
  list-style: none;
}
.day-summary {
  margin: 10px 0 14px;
  line-height: 1.65;
  max-width: 85ch;
  overflow-wrap: anywhere;
  white-space: pre-line;
}
.day-details summary {
  cursor: pointer;
  padding: 8px 0;
  color: var(--gold-bright);
  width: fit-content;
}
.day-details summary:hover { text-decoration: underline; }
.day-details summary:focus-visible {
  outline: 2px solid var(--gold-bright);
  outline-offset: 4px;
}
.note-count { opacity: 0.65; }
.day-details[open] summary { margin-bottom: 4px; }
.day-details[open] ul { border-top: 1px solid var(--border); }
.day li {
  position: relative;
  padding: 8px 0 8px 14px;
  border-top: 1px solid var(--border);
  line-height: 1.45;
  overflow-wrap: anywhere;
}
.day li:first-child { border-top: 0; }
.day li::before {
  content: "";
  position: absolute;
  left: 0;
  top: 16px;
  width: 5px;
  height: 5px;
  background: var(--accent);
}
</style>
