<script setup lang="ts">
import { computed } from "vue";
import ChangelogList from "~/components/ChangelogList.vue";
import { groupNotes, useModChangelog } from "~/lib/changelog";
import { i18n, t } from "~/i18n";

const { entries } = useModChangelog();
const groups = computed(() => groupNotes(entries.value ?? [], i18n.locale));
</script>

<template>
  <div class="page changelog">
    <h1 class="section-title">{{ t("changelog.title") }}</h1>
    <p v-if="!entries" class="empty-note">{{ t("srv.loading") }}</p>
    <p v-else-if="!groups.length" class="empty-note">{{ t("changelog.empty") }}</p>
    <ChangelogList v-else :groups="groups" />
  </div>
</template>
