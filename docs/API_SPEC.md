## 5. API 接口规范

### 5.1 通用约定

- 所有接口前缀：`/api/v1`
- 认证方式：`Header Authorization: Bearer <api_key>`
- 请求/响应格式：JSON
- 统一错误响应格式：

```json
{
  "error": {
    "code": "FILE_NOT_FOUND",
    "message": "文件不存在",
    "detail": null
  }
}
```

### 5.2 上传接口

#### POST /api/v1/files/upload — 文件上传

```
Content-Type: multipart/form-data
Body: file (二进制文件)

Response 200:
{
  "file_id": "uuid",
  "original_name": "合同.pdf",
  "file_size": 2048576,
  "status": "uploaded"
}
```

#### POST /api/v1/files/upload/screenshot — 截图上传

```
Body: { "image_base64": "data:image/png;base64,..." }

Response 200: { "file_id": "uuid", ... }
```

#### POST /api/v1/files/upload/text — 文本/代码粘贴

```
Body: {
  "content": "def hello():\n    print('world')",
  "type_hint": "code"
}

Response 200: { "file_id": "uuid", ... }
```

### 5.3 文件接口

#### GET /api/v1/files — 文件列表

```
Query:
  page=1, limit=20
  status=all|uploaded|identifying|parsing|completed|failed
  search=关键词
  sort=created_at:desc

Response 200:
{
  "items": [
    {
      "file_id": "uuid",
      "original_name": "合同.pdf",
      "content_type": "file",
      "file_size": 2048576,
      "status": "completed",
      "created_at": "2026-07-07T10:00:00Z"
    }
  ],
  "total": 156, "page": 1, "limit": 20
}
```

#### GET /api/v1/files/{file_id} — 文件详情
#### DELETE /api/v1/files/{file_id} — 删除文件
#### GET /api/v1/files/{file_id}/preview?page=1 — 文件预览 + bbox

### 5.4 任务接口

#### GET /api/v1/tasks — 任务管理表格
#### GET /api/v1/tasks/{task_id} — 任务详情（含进度）
#### POST /api/v1/tasks/{task_id}/retry — 失败重试
#### POST /api/v1/tasks/{task_id}/cancel — 取消排队中的任务

### 5.5 结果接口

#### GET /api/v1/results/{task_id}?format=markdown|json — 获取解析结果
#### GET /api/v1/results/{task_id}/download?format=markdown|json|html|latex|docx — 下载结果文件

转换机制（下载时的格式转换）：
- Markdown / JSON：解析管线直接产出，零转换
- HTML / LaTeX / DOCX：通过 Pandoc 在下载时即时转换（懒转换方案）
- Pandoc 调用方式：Converter Service 内部通过 `subprocess.call(["pandoc", input_path, "-o", output_path])` 调用 Pandoc 命令行

### 5.6 收藏接口

#### GET /api/v1/collections — 收藏集列表
#### POST /api/v1/collections — 创建收藏集
#### PUT /api/v1/collections/{id} — 编辑收藏集
#### DELETE /api/v1/collections/{id} — 删除收藏集
#### GET /api/v1/collections/{id}/items?type=file&page=1 — 按类型浏览收藏条目
#### POST /api/v1/collections/{id}/items — 收藏当前解析结果
#### DELETE /api/v1/collections/items/{item_id} — 取消收藏

### 5.7 WebSocket 接口

#### WS /api/v1/ws/tasks?user_id={user_id} — 实时状态推送

### 5.8 管理接口（私有化运维）

#### GET /api/v1/admin/stats — 系统统计
#### GET /api/v1/admin/models/status — 模型服务健康状况

### 5.9 错误码表

| 错误码              | HTTP 状态码 | 说明             | 触发条件                                     |
|--------------------|-----------|-----------------|---------------------------------------------|
| FILE_NOT_FOUND     | 404       | 文件不存在       | 请求的 file_id 不存在或已被删除                |
| FILE_TOO_LARGE     | 413       | 超过大小限制     | 上传文件超过系统配置的最大值（默认 100MB）     |
| UNSUPPORTED_FORMAT | 400       | 不支持的格式     | 文件类型识别产出的格式没有对应的 Parser        |
| PARSER_FAILED      | 500       | 解析器内部错误   | 解析器运行时抛出未预期的异常                   |
| GPU_UNAVAILABLE    | 503       | GPU 模型不可用   | GPU 容器未启动或显存耗尽                      |
| TASK_CANCELLED     | 200       | 任务被取消       | 用户主动取消了排队中的任务                     |
| TASK_STATE_CONFLICT| 409       | 任务状态冲突     | 任务状态不允许重试或取消                       |
| FILE_DUPLICATE     | 409       | 文件重复         | 上传了已存在的文件（SHA-256 匹配）             |
| UNAUTHORIZED       | 401       | 未认证           | 请求未携带有效的 JWT 或 API Key               |
| FORBIDDEN          | 403       | 无权限           | 请求的资源不属于当前用户                       |

---

