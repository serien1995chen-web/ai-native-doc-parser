<script setup lang="ts">
import { ref } from 'vue'
import { mockTaskIdForFile, mockUpload } from '../../api/client'

const emit = defineEmits<{
  (e: 'uploaded', payload: { taskId: string }): void
}>()

const submitting = ref(false)
const error = ref<string | null>(null)

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  submitting.value = true
  error.value = null
  try {
    const response = await mockUpload(file)
    const fileId = response.data?.file_id
    if (!fileId) throw new Error('上传失败')
    emit('uploaded', { taskId: mockTaskIdForFile(fileId) })
  } catch (err) {
    error.value = err instanceof Error ? err.message : '上传失败'
  } finally {
    submitting.value = false
    input.value = ''
  }
}
</script>

<template>
  <div class="upload-card">
    <h2>文件上传</h2>
    <label class="file-trigger">
      <input type="file" :disabled="submitting" @change="handleFileChange" />
      <span>{{ submitting ? '上传中...' : '选择文件' }}</span>
    </label>
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

.file-trigger {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius);
  cursor: pointer;
  color: var(--color-text-secondary);
}

.file-trigger input {
  display: none;
}

.error {
  margin: 10px 0 0;
  color: #b91c1c;
  font-size: 13px;
}
</style>