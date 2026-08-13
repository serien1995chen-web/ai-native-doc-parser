<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ content: string }>()

const prettyJson = computed(() => {
  try {
    return JSON.stringify(JSON.parse(props.content), null, 2)
  } catch {
    return props.content
  }
})
</script>

<template>
  <pre class="json-viewer">{{ prettyJson }}</pre>
</template>

<style scoped>
.json-viewer {
  margin: 0;
  padding: 16px;
  min-height: 320px;
  overflow: auto;
  font-size: 13px;
  line-height: 1.5;
}
</style>