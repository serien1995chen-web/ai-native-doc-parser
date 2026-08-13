<script setup lang="ts">
import type { FileItem, ParseResult } from '../../types'

defineProps<{
  file: FileItem | null
  result: ParseResult | null
}>()
</script>

<template>
  <aside class="file-preview">
    <h2>文件信息</h2>
    <dl>
      <dt>文件名</dt>
      <dd>{{ file?.original_name ?? result?.original_name ?? '暂无' }}</dd>
      <dt>类型</dt>
      <dd>{{ file?.content_type ?? result?.output_format ?? '暂无' }}</dd>
      <dt>状态</dt>
      <dd>{{ file?.status ?? (result ? 'completed' : '暂无') }}</dd>
    </dl>
    <div class="preview-body">
      <p>{{ result?.output_text?.slice(0, 500) || '暂无预览' }}</p>
      <!-- TODO(B-10): integrate real preview API. -->
    </div>
  </aside>
</template>

<style scoped>
.file-preview {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 18px;
}

.file-preview h2 {
  margin: 0 0 14px;
  font-size: 16px;
}

.file-preview dl {
  margin: 0 0 16px;
}

.file-preview dt {
  color: var(--color-text-secondary);
  font-size: 12px;
  margin-top: 8px;
}

.file-preview dd {
  margin: 2px 0 0;
  word-break: break-word;
}

.preview-body {
  border-top: 1px solid var(--color-border);
  padding-top: 12px;
  color: var(--color-text-secondary);
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
}
</style>