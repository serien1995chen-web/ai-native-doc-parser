import { defineStore } from 'pinia'
import { mockTasks } from '../api/client'
import type { Task } from '../types'

export const useTaskStore = defineStore('tasks', {
  state: () => ({
    tasks: [] as Task[],
    loading: false,
    error: null as string | null,
  }),
  getters: {
    completedCount: (state) =>
      state.tasks.filter((task) => task.status === 'completed').length,
  },
  actions: {
    async fetchTasks() {
      this.loading = true
      this.error = null
      try {
        const response = await mockTasks()
        this.tasks = response.data?.items ?? []
      } catch (error) {
        this.error = error instanceof Error ? error.message : '加载任务失败'
      } finally {
        this.loading = false
      }
    },
  },
})
