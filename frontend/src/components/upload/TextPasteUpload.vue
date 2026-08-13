<script setup lang="ts">
import { ref } from 'vue'
import { mockTaskIdForFile, mockTextUpload } from '../../api/client'

const emit = defineEmits<{
  (e: 'uploaded', payload: { taskId: string }): void
}>()

const content = ref('')
const typeHint = ref<'text' | 'code'>('text')
const submitting = ref(false)
const error = ref<string | null>(null)

async function submit() {
  const text = content.value.trim()
  if (!text) return
  submitting.value = true
  error.value = null
  try {
    const response = await mockTextUpload(text, typeHint.value)
    const fileId = response.data?.file_id
    if (!fileId) throw new Error('上传失败')
    emit('uploaded', { taskId: mockTaskIdForFile(fileId) })
    content.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : '上传失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="upload-card">
    <h2>文本/代码粘贴</h2>
    <div class="segmented">
      <button
        :class="{ active: typeHint === 'text' }"
        @click="typeHint = 'text'"
      >
        文本
      </button>
      <button
        :class="{ active: typeHint === 'code' }"
        @click="typeHint = 'code'"
      >
        代码
      </button>
    </div>
    <textarea
      v-model="content"
      :disabled="submitting"
      placeholder="粘贴文本或代码"
    ></textarea>
    <button
      class="submit-button"
      :disabled="submitting || !content.trim()"
      @click="submit"
    >
      {{ submitting ? '提交中...' : '开始解析' }}
    </button>
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

.segmented {
  display: flex;
  gap: 4px;
  margin-bottom: 10px;
}

.segmented button {
  flex: 1;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  border-radius: 6px;
  padding: 6px;
  cursor: pointer;
}

.segmented button.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
}

textarea {
  width: 100%;
  min-height: 120px;
  resize: vertical;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 10px;
  font: inherit;
}

.submit-button {
  width: 100%;
  margin-top: 10px;
  border: 1px solid var(--color-primary);
  background: var(--color-primary);
  color: #fff;
  border-radius: var(--radius);
  padding: 8px;
  cursor: pointer;
}

.submit-button:disabled {
  opacity: 0.6;
  cursor: default;
}

.error {
  margin: 10px 0 0;
  color: #b91c1c;
  font-size: 13px;
}
</style>