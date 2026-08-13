<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import FilePreview from '../components/result/FilePreview.vue'
import JsonViewer from '../components/result/JsonViewer.vue'
import MarkdownViewer from '../components/result/MarkdownViewer.vue'
import { mockResult } from '../api/client'
import { useCollectionStore } from '../stores/collectionStore'
import type { ContentType, FileItem, ParseResult } from '../types'

const route = useRoute()
const collectionStore = useCollectionStore()

const result = ref<ParseResult | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const viewMode = ref<'markdown' | 'json'>('markdown')
const copied = ref(false)
const selectedCollectionId = ref('collection-1')
const favorited = ref(false)

const downloadFormats: Array<'markdown' | 'json' | 'html' | 'latex' | 'docx'> =
  ['markdown', 'json', 'html', 'latex', 'docx']

const taskId = computed(() => String(route.params.task_id ?? ''))
const currentText = computed(() => {
  if (!result.value) return ''
  if (viewMode.value === 'markdown') return result.value.output_text ?? ''
  return JSON.stringify(result.value, null, 2)
})

const previewFile = computed<FileItem | null>(() => {
  if (!result.value) return null
  return {
    file_id: result.value.file_id,
    original_name: result.value.original_name,
    uploaded_type: 'file',
    content_type: 'file' as ContentType,
    file_size: result.value.output_size ?? null,
    status: 'completed',
    mime_type: null,
    identified_type: result.value.output_format,
    identified_confidence: null,
    created_at: result.value.created_at,
    updated_at: result.value.created_at,
  }
})

async function loadResult() {
  loading.value = true
  error.value = null
  try {
    const response = await mockResult(taskId.value)
    result.value = response.data
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载结果失败'
  } finally {
    loading.value = false
  }
}

async function copy() {
  if (!currentText.value) return
  try {
    await navigator.clipboard.writeText(currentText.value)
    copied.value = true
    window.setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch {
    copied.value = false
  }
}

function download(format: 'markdown' | 'json' | 'html' | 'latex' | 'docx') {
  if (!result.value) return
  // TODO(B-10): use GET /results/{task_id}/download?format=...
  let content = ''
  if (format === 'markdown') {
    content = result.value.output_text ?? ''
  } else if (format === 'json') {
    content = JSON.stringify(result.value, null, 2)
  } else {
    content = `# ${result.value.original_name}\n\nMock ${format} export`
  }
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `result.${format}`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

async function favorite() {
  if (favorited.value || !result.value) return
  if (collectionStore.collections.length === 0) {
    await collectionStore.loadCollections()
  }
  const item = await collectionStore.addItem(selectedCollectionId.value, {
    taskId: result.value.task_id,
    fileId: result.value.file_id,
    contentType: 'file',
    originalName: result.value.original_name,
  })
  if (item) {
    favorited.value = true
  }
}

onMounted(loadResult)
</script>

<template>
  <section class="page result-page">
    <h1>解析结果</h1>
    <p v-if="loading" class="muted">加载中...</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <template v-else-if="result">
      <div class="result-layout">
        <FilePreview :file="previewFile" :result="result" />
        <div class="result-content">
          <div class="viewer-toolbar">
            <button
              :class="{ active: viewMode === 'markdown' }"
              @click="viewMode = 'markdown'"
            >
              Markdown
            </button>
            <button
              :class="{ active: viewMode === 'json' }"
              @click="viewMode = 'json'"
            >
              JSON
            </button>
            <button class="toolbar-action" @click="copy">
              {{ copied ? '已复制' : '复制' }}
            </button>
          </div>
          <MarkdownViewer
            v-if="viewMode === 'markdown'"
            :content="currentText"
          />
          <JsonViewer v-else :content="currentText" />
        </div>
      </div>
      <div class="result-actions">
        <button
          v-for="format in downloadFormats"
          :key="format"
          class="download-button"
          @click="download(format)"
        >
          下载 {{ format }}
        </button>
        <select v-model="selectedCollectionId">
          <option
            v-for="collection in collectionStore.collections"
            :key="collection.id"
            :value="collection.id"
          >
            {{ collection.name }}
          </option>
        </select>
        <button class="favorite-button" :disabled="favorited" @click="favorite">
          {{ favorited ? '已收藏' : '收藏' }}
        </button>
      </div>
    </template>
  </section>
</template>

<style scoped>
.result-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.muted {
  color: var(--color-text-secondary);
}

.error {
  color: #b91c1c;
}

.result-layout {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}

.result-content {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  overflow: hidden;
}

.viewer-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border);
}

.viewer-toolbar button {
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  border-radius: 6px;
  padding: 6px 10px;
  cursor: pointer;
}

.viewer-toolbar button.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
}

.viewer-toolbar .toolbar-action {
  margin-left: auto;
}

.result-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.download-button,
.favorite-button {
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  border-radius: 6px;
  padding: 8px 12px;
  cursor: pointer;
}

.favorite-button:disabled {
  opacity: 0.6;
  cursor: default;
}

@media (max-width: 900px) {
  .result-layout {
    grid-template-columns: 1fr;
  }
}
</style>