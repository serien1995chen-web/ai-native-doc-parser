<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { mockScreenshotUpload, mockTaskIdForFile } from '../../api/client'

const emit = defineEmits<{
  (e: 'uploaded', payload: { taskId: string }): void
}>()

const preview = ref<string | null>(null)
const submitting = ref(false)
const error = ref<string | null>(null)

function handlePaste(event: ClipboardEvent) {
  const items = event.clipboardData?.items ?? []
  const imageItem = Array.from(items).find((item) =>
    item.type.startsWith('image/'),
  )
  const file = imageItem?.getAsFile()
  if (!file) return
  event.preventDefault()
  const reader = new FileReader()
  reader.onload = async () => {
    const dataUrl = String(reader.result ?? '')
    preview.value = dataUrl
    submitting.value = true
    error.value = null
    try {
      const response = await mockScreenshotUpload(dataUrl)
      const fileId = response.data?.file_id
      if (!fileId) throw new Error('上传失败')
      emit('uploaded', { taskId: mockTaskIdForFile(fileId) })
    } catch (err) {
      error.value = err instanceof Error ? err.message : '上传失败'
    } finally {
      submitting.value = false
    }
  }
  reader.readAsDataURL(file)
}

onMounted(() => {
  window.addEventListener('paste', handlePaste)
})

onBeforeUnmount(() => {
  window.removeEventListener('paste', handlePaste)
})
</script>

<template>
  <div class="upload-card">
    <h2>截图粘贴</h2>
    <div class="paste-zone" tabindex="0">
      <p>{{ submitting ? '上传中...' : '复制图片后按 Ctrl+V 粘贴' }}</p>
      <img v-if="preview" :src="preview" alt="截图预览" />
    </div>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<style scoped>
.upload-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 18px;
}

.upload-card h2 {
  margin: 0 0 14px;
  font-size: 16px;
}

.paste-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 120px;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius);
  color: var(--color-text-secondary);
  text-align: center;
}

.paste-zone img {
  max-width: 100%;
  max-height: 140px;
  border-radius: var(--radius);
}

.error {
  margin: 10px 0 0;
  color: #b91c1c;
  font-size: 13px;
}
</style>