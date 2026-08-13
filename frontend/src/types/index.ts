export type TaskStatus = 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled'
export type FileStatus = 'uploaded' | 'identifying' | 'parsing' | 'completed' | 'failed'
export type ContentType = 'file' | 'image' | 'formula' | 'table' | 'text_block' | 'code'

export interface APIError {
  code: string
  message: string
  detail: string | null
}

export interface APIResponse<T> {
  success: boolean
  data: T | null
  error: APIError | null
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  limit: number
}

export interface Task {
  task_id: string
  file_id: string
  original_name: string
  parser_type: string | null
  status: TaskStatus
  progress: number
  created_at: string
  updated_at: string
  completed_at: string | null
  error_message: string | null
}

export interface FileItem {
  file_id: string
  original_name: string
  uploaded_type: string
  content_type: ContentType | null
  file_size: number | null
  status: FileStatus
  mime_type: string | null
  identified_type: string | null
  identified_confidence: number | null
  created_at: string
  updated_at: string
}

export interface FileUploadResponse {
  file_id: string
  original_name: string
  file_size: number
  status: FileStatus
}

export interface ParseBlock {
  type: string
  text?: string
  language?: string
  level?: number
  page?: number
  bbox?: number[]
  confidence?: number
  rows?: string[][]
  latex?: string
  src?: string
  caption?: string
}

export interface ParseResult {
  task_id: string
  file_id: string
  original_name: string
  output_format: 'markdown' | 'json'
  output_text: string | null
  output_path: string | null
  output_size: number | null
  processing_time_ms: number | null
  created_at: string
  blocks: ParseBlock[]
}

export interface Collection {
  id: string
  name: string
  description: string | null
  is_default: boolean
  created_at: string
  updated_at: string
}

export interface CollectionItem {
  id: string
  collection_id: string
  task_id: string
  file_id: string
  content_type: ContentType
  original_name: string | null
  label: string | null
  notes: string | null
  tags: string[] | null
  created_at: string
}
