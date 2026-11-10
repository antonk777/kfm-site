<script setup lang="ts">
import type { DayGroup } from "../lib/changelog";

defineProps<{ groups: DayGroup[] }>();
</script>

<template>
  <section v-for="group in groups" :key="group.day" class="day panel">
    <h3>{{ group.day }}</h3>
    <ul>
      <li v-for="(note, i) in group.notes" :key="`${group.day}-${i}`">{{ note }}</li>
    </ul>
  </section>
</template>

<style scoped>
.day {
  padding: 12px 18px 8px;
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
.day li {
  position: relative;
  padding: 8px 0 8px 14px;
  border-top: 1px solid var(--border);
  line-height: 1.45;
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
