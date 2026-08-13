<script setup lang="ts">
defineProps<{ content: string }>()
</script>

<template>
  <pre class="markdown-viewer">{{ content }}</pre>
</template>

<style scoped>
.markdown-viewer {
  margin: 0;
  padding: 16px;
  min-height: 320px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 14px;
  line-height: 1.6;
}
</style>