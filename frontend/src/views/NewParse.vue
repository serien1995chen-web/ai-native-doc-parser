<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import FileUpload from '../components/upload/FileUpload.vue'
import ScreenshotUpload from '../components/upload/ScreenshotUpload.vue'
import TextPasteUpload from '../components/upload/TextPasteUpload.vue'
import { mockRecentFiles, mockTaskIdForFile } from '../api/client'
import type { FileItem } from '../types'

const router = useRouter()
const uploading = ref(false)
const recentFiles = ref<FileItem[]>([])
const recentLoading = ref(false)
const recentError = ref<string | null>(null)

async function loadRecentFiles() {
  recentLoading.value = true
  recentError.value = null
  try {
    const response = await mockRecentFiles()
    recentFiles.value = response.data?.items ?? []
  } catch (err) {
    recentError.value = err instanceof Error ? err.message : '加载最近解析失败'
  } finally {
    recentLoading.value = false
  }
}

function handleUploaded(payload: { taskId: string }) {
  uploading.value = false
  void router.push({
    name: 'results',
    params: { task_id: payload.taskId },
  })
}

function openResult(fileId: string) {
  void router.push({
    name: 'results',
    params: { task_id: mockTaskIdForFile(fileId) },
  })
}

onMounted(loadRecentFiles)
</script>

<template>
  <section class="page new-parse-page">
    <h1>新解析</h1>
    <div class="upload-grid">
      <FileUpload @uploaded="handleUploaded" />
      <ScreenshotUpload @uploaded="handleUploaded" />
      <TextPasteUpload @uploaded="handleUploaded" />
    </div>
    <section class="recent-section">
      <h2>最近解析</h2>
      <p v-if="recentLoading" class="muted">加载中...</p>
      <p v-else-if="recentError" class="error">{{ recentError }}</p>
      <ul v-else class="recent-list">
        <li
          v-for="file in recentFiles"
          :key="file.file_id"
          class="recent-item"
          @click="openResult(file.file_id)"
        >
          <span class="recent-name">{{ file.original_name }}</span>
          <span class="recent-meta">
            {{ file.content_type ?? 'file' }} · {{ file.status }}
          </span>
          <span class="recent-date">{{ file.created_at }}</span>
        </li>
      </ul>
    </section>
  </section>
</template>

<style scoped>
.new-parse-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.upload-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.recent-section {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 20px;
}

.recent-section h2 {
  margin: 0 0 12px;
  font-size: 16px;
}

.muted {
  color: var(--color-text-secondary);
}

.error {
  color: #b91c1c;
}

.recent-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.recent-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 16px;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--color-border);
  cursor: pointer;
}

.recent-item:last-child {
  border-bottom: none;
}

.recent-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-meta,
.recent-date {
  color: var(--color-text-secondary);
  font-size: 13px;
}

@media (max-width: 900px) {
  .upload-grid {
    grid-template-columns: 1fr;
  }

  .recent-item {
    grid-template-columns: 1fr;
    gap: 4px;
  }
}
</style>