import axios from 'axios'
import type {
  APIResponse,
  CollectionItem,
  ContentType,
  FileItem,
  FileStatus,
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

export async function mockScreenshotUpload(
  imageBase64: string,
): Promise<APIResponse<FileUploadResponse>> {
  await delay(350)
  // TODO(B-10): switch to real screenshot upload API.
  return {
    success: true,
    data: {
      file_id: mockId('file'),
      original_name: 'screenshot.png',
      file_size: Math.ceil(imageBase64.length * 0.75),
      status: 'uploaded',
    },
    error: null,
  }
}

export async function mockTextUpload(
  content: string,
  typeHint: 'text' | 'code',
): Promise<APIResponse<FileUploadResponse>> {
  void typeHint
  await delay(350)
  // TODO(B-10): switch to real text upload API.
  return {
    success: true,
    data: {
      file_id: mockId('file'),
      original_name: 'paste.txt',
      file_size: content.length,
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

export async function mockRecentFiles(): Promise<
  APIResponse<PaginatedResponse<FileItem>>
> {
  await delay(280)
  const now = Date.now()
  const iso = (minutesAgo: number) =>
    new Date(now - minutesAgo * 60_000).toISOString()
  const rows: Array<
    [string, string, ContentType, string, number, string, FileStatus]
  > = [
    ['file-1001', '产品需求文档.pdf', 'file', 'pdf', 2048576, 'application/pdf', 'completed'],
    ['file-1002', '架构图.png', 'image', 'image', 1536000, 'image/png', 'completed'],
    ['file-1003', '会议纪要.md', 'text_block', 'md', 8192, 'text/markdown', 'completed'],
    ['file-1004', '合同扫描件.jpg', 'image', 'image', 4096000, 'image/jpeg', 'completed'],
    ['file-1005', '财务模型.xlsx', 'file', 'xlsx', 102400, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'completed'],
    ['file-1006', 'API设计文档.docx', 'file', 'docx', 307200, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'completed'],
    ['file-1007', '代码片段.py', 'code', 'code', 4096, 'text/x-python', 'completed'],
    ['file-1008', '品牌海报.png', 'image', 'image', 2097152, 'image/png', 'parsing'],
    ['file-1009', '会议记录.html', 'file', 'html', 65536, 'text/html', 'completed'],
    ['file-1010', '公式截图.png', 'formula', 'image_formula', 524288, 'image/png', 'failed'],
  ]
  // TODO(B-10): switch to real files API.
  return {
    success: true,
    data: {
      items: rows.map((row, index) => ({
        file_id: row[0],
        original_name: row[1],
        uploaded_type: 'file',
        content_type: row[2],
        file_size: row[4],
        status: row[6],
        mime_type: row[5],
        identified_type: row[3],
        identified_confidence: 0.95,
        created_at: iso(index * 37),
        updated_at: iso(index * 12),
      })),
      total: rows.length,
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

export async function mockAddCollectionItem(
  collectionId: string,
  taskId: string,
): Promise<APIResponse<CollectionItem>> {
  await delay(260)
  // TODO(B-10): switch to real collections API.
  return {
    success: true,
    data: {
      id: mockId('item'),
      collection_id: collectionId,
      task_id: taskId,
      file_id: 'file-1001',
      content_type: 'file',
      original_name: '产品需求文档.pdf',
      label: null,
      notes: null,
      tags: [],
      created_at: new Date().toISOString(),
    },
    error: null,
  }
}

export function mockTaskIdForFile(fileId: string): string {
  // TODO(B-10): switch to real task lookup API.
  return `task-${fileId}`
}