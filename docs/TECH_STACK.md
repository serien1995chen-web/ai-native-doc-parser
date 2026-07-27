## 3. 技术栈说明

### 3.1 核心技术栈

| 层级           | 技术                    | 版本           | 用途                    |
|----------------|------------------------|----------------|------------------------|
| 后端语言       | Python                 | 3.12+          | 主开发语言              |
| Web 框架       | FastAPI                | 最新稳定版      | API 服务                |
| 任务队列       | arq                    | 最新稳定版      | 异步任务调度             |
| 前端框架       | Vue 3                  | 最新稳定版      | 单页应用                |
| Web 服务器     | Nginx                  | 最新稳定版      | 反向代理 + 静态资源服务   |
| 数据库         | PostgreSQL             | 15+            | 元数据/任务/用户/收藏    |
| 缓存/队列      | Redis                  | 7+             | 消息队列/缓存             |
| 对象存储       | MinIO                  | 最新稳定版      | 原始文件 + 结果文件       |
| 容器化         | Docker + Docker Compose | 最新稳定版      | 部署交付                 |

### 3.2 文档解析依赖

| 格式  | 依赖库         | 用途                |
|-------|---------------|---------------------|
| DOCX  | python-docx   | 文档解析             |
| PPTX  | python-pptx   | 演示文稿解析          |
| XLSX  | openpyxl      | 电子表格解析          |
| HTML  | BeautifulSoup | HTML 解析            |
| 代码  | Pygments      | 代码高亮与解析        |
| PDF   | PyMuPDF + Poppler | PDF 文件解析与渲染 |

### 3.3 图片解析依赖（GPU 模型）

| 模型              | 框架环境      | 用途         |
|-------------------|-------------|--------------|
| doclayout-YOLO    | PyTorch     | 版面分析      |
| PaddleOCR         | PaddlePaddle | OCR 文字识别  |
| TableTransformer  | PyTorch     | 表格识别      |
| UniMERNet         | PyTorch     | 公式识别      |

### 3.4 系统工具依赖

| 工具                    | 用途                           |
|------------------------|--------------------------------|
| LibreOffice（headless） | 文档渲染 + 格式转换              |
| Pandoc（>= 3.x）        | LaTeX / HTML / DOCX 格式转换    |
| FFmpeg                 | 预留音视频处理                   |
| CUDA                   | GPU 推理加速                    |

### 3.5 Python 环境方案

由于 PyTorch 和 PaddlePaddle 不能装在同一个 Python 环境里，至少需要两个独立 conda 环境：

| 环境                | 用途                    | 包含组件                                      |
|---------------------|------------------------|----------------------------------------------|
| docparse_pytorch    | 版面分析 + 表格 + 公式  | doclayout-YOLO、TableTransformer、UniMERNet |
| docparse_paddle     | OCR                    | PaddlePaddle、PaddleOCR                      |

GPU 模型容器在 Docker 中运行，与主程序分离。

### 3.6 配置分层策略

系统配置分为两层：

**第 1 层：.env 文件（启动时加载，修改后需重启生效）**
- 基础设施配置：`DATABASE_URL`、`REDIS_URL`、`MINIO_ENDPOINT`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`
- 文件识别阈值：`L1_CONFIDENCE_THRESHOLD`（默认 0.95）、`L2_CONFIDENCE_THRESHOLD`（默认 0.90）、`L3_CONFIDENCE_THRESHOLD`（默认 0.85）
- 上传限制：`MAX_UPLOAD_SIZE`（默认 104857600，即 100MB）
- 功能开关：`PANDOC_ENABLED`（默认 true）

**第 2 层：system_config 表（运行时修改，无需重启即可生效）**
- 模型开关：`model.doclayout_yolo.enabled`、`model.paddleocr.enabled`、`model.table_transformer.enabled`、`model.unimernet.enabled`
- 任务参数：`task.max_retry_count`（默认 3）、`task.processing_timeout_minutes`（默认 30）

.env 由 Pydantic Settings 在 `backend/app/core/config.py` 中读取，system_config 表由 ConfigService 从数据库加载。

---

