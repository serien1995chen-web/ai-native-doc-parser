import axios from 'axios'
import type {
  APIResponse,
  FileUploadResponse,
  PaginatedResponse,
  ParseResult,
  Task,
} from '../types'

export const http = axios.create({
  baseURL: '/api/v1',
})

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, milliseconds)
  })
}

function mockId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`
}

export async function mockUpload(
  file: File,
): Promise<APIResponse<FileUploadResponse>> {
  await delay(350)
  // TODO(B-10): switch to real upload API.
  return {
    success: true,
    data: {
      file_id: mockId('file'),
      original_name: file.name,
      file_size: file.size,
      status: 'uploaded',
    },
    error: null,
  }
}

export async function mockTasks(): Promise<
  APIResponse<PaginatedResponse<Task>>
> {
  await delay(250)
  const now = new Date().toISOString()
  // TODO(B-10): switch to real tasks API.
  return {
    success: true,
    data: {
      items: [
        {
          task_id: 'task-1001',
          file_id: 'file-1001',
          original_name: '产品需求文档.pdf',
          parser_type: 'pdf',
          status: 'completed',
          progress: 100,
          created_at: now,
          updated_at: now,
          completed_at: now,
          error_message: null,
        },
        {
          task_id: 'task-1002',
          file_id: 'file-1002',
          original_name: '架构图.png',
          parser_type: 'image',
          status: 'processing',
          progress: 60,
          created_at: now,
          updated_at: now,
          completed_at: null,
          error_message: null,
        },
      ],
      total: 2,
      page: 1,
      limit: 20,
    },
    error: null,
  }
}

export async function mockResult(
  taskId: string,
): Promise<APIResponse<ParseResult>> {
  await delay(300)
  const now = new Date().toISOString()
  // TODO(B-10): switch to real result API.
  return {
    success: true,
    data: {
      task_id: taskId,
      file_id: 'file-1001',
      original_name: '产品需求文档.pdf',
      output_format: 'markdown',
      output_text: '# 产品需求文档\n\n占位解析结果',
      output_path: null,
      output_size: null,
      processing_time_ms: 1280,
      created_at: now,
      blocks: [
        { type: 'heading', level: 1, text: '产品需求文档', page: 1 },
        { type: 'paragraph', text: '占位解析结果', page: 1 },
      ],
    },
    error: null,
  }
}
