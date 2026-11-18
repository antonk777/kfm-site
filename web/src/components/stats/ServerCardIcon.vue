<script setup lang="ts">
const paths = {
  players: "M3 20v-2a6 6 0 0 1 12 0v2M9 5a3 3 0 1 0 0 6 3 3 0 0 0 0-6Zm7 0a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 5",
  revision: "M6 7v10m0-3c7 0 12-1 12-5M6 3a2 2 0 1 0 0 4 2 2 0 0 0 0-4Zm0 14a2 2 0 1 0 0 4 2 2 0 0 0 0-4ZM18 5a2 2 0 1 0 0 4 2 2 0 0 0 0-4Z",
  difficulty: "M7.7 15.7c.7-1.6 2.3-2.5 4.2-2.2a5 5 0 0 1 9.6 1.9c0 3.4-3.1 5.6-7.2 5.6H8.8c-3.2 0-6.5-1.1-6.5-3.5 0-2.1 1.3-7.4 2.4-11.4l.4-1.3c.2-.7.8-1.2 1.5-1.4L9 2.9c.6-.1 1.1.1 1.5.6L12 5.6c.3.5.2 1.1-.3 1.4l-1.5 1c-.4.2-.9.3-1.3.1l-1.3-.5.6 7m3.7-1.6c.9.1 1.7.5 2.3 1.1",
  wave: "M5 21V4m0 1c4-4 8 3 14 0v9c-6 3-10-4-14 0",
  health: "M2 12h5l3-8 4 16 3-8h5",
  load: "M6 5h12a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Zm3 4h6v6H9zM9 2v3m6-3v3M9 19v3m6-3v3M2 9h3m-3 6h3m14-6h3m-3 6h3",
  map: "m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2zm6-2v16m6-14v16",
  log: "M3 4h18v16H3zM6 9l3 3-3 3m6 0h4",
  restart: "M3 10a9 9 0 1 1 1.3 7M3 4v6h6",
  sword: "m8.5 13.5 10-10 3-.5-.5 3-10 10M6.5 11.5l6 6m-3-3L4 20m-1-1 2 2",
  chevron: "m6 9 6 6 6-6",
};
defineProps<{ name: keyof typeof paths }>();
</script>

<template>
  <svg class="card-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path :d="paths[name]" />
  </svg>
</template>
