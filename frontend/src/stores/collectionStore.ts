import { defineStore } from 'pinia'
import { mockAddCollectionItem } from '../api/client'
import type { Collection, CollectionItem, ContentType } from '../types'

export const useCollectionStore = defineStore('collections', {
  state: () => ({
    collections: [] as Collection[],
    itemsByCollection: {} as Record<string, CollectionItem[]>,
    loading: false,
    error: null as string | null,
  }),
  actions: {
    async loadCollections() {
      this.loading = true
      this.error = null
      try {
        const now = new Date().toISOString()
        const collection: Collection = {
          id: 'collection-1',
          name: '默认收藏',
          description: null,
          is_default: true,
          created_at: now,
          updated_at: now,
        }
        const item: CollectionItem = {
          id: 'item-1',
          collection_id: collection.id,
          task_id: 'task-1001',
          file_id: 'file-1001',
          content_type: 'file',
          original_name: '产品需求文档.pdf',
          label: null,
          notes: null,
          tags: [],
          created_at: now,
        }
        // TODO(B-10): switch to real collections API.
        this.collections = [collection]
        this.itemsByCollection[collection.id] = [item]
      } catch (error) {
        this.error = error instanceof Error ? error.message : '加载收藏失败'
      } finally {
        this.loading = false
      }
    },
    async addItem(
      collectionId: string,
      payload: {
        taskId: string
        fileId: string
        contentType: ContentType
        originalName: string | null
      },
    ) {
      const response = await mockAddCollectionItem(collectionId, payload.taskId)
      const item = response.data
      if (!item) return null
      const current = this.itemsByCollection[collectionId] ?? []
      this.itemsByCollection[collectionId] = [...current, item]
      return item
    },
  },
})