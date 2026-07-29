## 6. 开发流程

### 6.1 环境搭建流程

整个环境搭建以项目工程基础层的文件为基石,按照 .gitignore -> .env.example -> pyproject.toml -> requirements.txt -> docker-compose.yml + Dockerfile 的顺序逐步展开。

每步都会告诉你:看哪个文件、文件在哪里、怎么安装。

---

#### 第 1 步:配置 Git 版本控制规则

**文件**:.gitignore
**位置**:项目根目录

项目根目录下的 .gitignore 已预制了 Python、Docker、IDE 的忽略规则:
- Python:__pycache__、.venv、*.pyc 等
- 环境文件:.env(本地私有,禁止提交)
- 操作系统:.DS_Store、Thumbs.db
- 项目数据:data/、uploads/、results/、logs/

无需修改,直接使用。首次 git commit 前自动生效。

---

#### 第 2 步:配置环境变量

**文件**:.env.example -> 复制为 .env
**位置**:项目根目录

.env.example 是环境变量模板(纳入 Git 追踪),展示了项目运行所需的全部环境参数。配置分层参考本文档 3.6 节。

操作:
  cp .env.example .env
  编辑 .env,修改以下必须变更的值:
    POSTGRES_PASSWORD       改为随机密码
    MINIO_SECRET_KEY        改为随机密钥
    JWT_SECRET              改为随机密钥

第 1 层配置变量(必须配置,本文档 3.6 节):

  DATABASE_URL              PostgreSQL 连接串
  REDIS_URL                 Redis 连接串
  MINIO_ENDPOINT            对象存储地址
  L1_CONFIDENCE_THRESHOLD   扩展名层置信度阈值(默认0.95)
  L2_CONFIDENCE_THRESHOLD   签名层置信度阈值(默认0.90)
  L3_CONFIDENCE_THRESHOLD   内容嗅探层置信度阈值(默认0.85)
  MAX_UPLOAD_SIZE           上传文件大小上限(默认100MB)
  PANDOC_ENABLED            Pandoc 格式转换开关(默认true)

---

#### 第 3 步:安装 Python 项目依赖

**文件**:pyproject.toml(源配置)、requirements.txt(pip 兼容清单)
**位置**:项目根目录

pyproject.toml 是 Python 现代项目的核心配置文件(PEP 621 标准),定义项目元信息、所有依赖、工具配置。
requirements.txt 是 pyproject.toml 的 pip 兼容导出清单,供 Docker 等场景使用。

操作:
  conda activate docparse_pytorch
  cd /path/to/project-root
  pip install -r requirements.txt

提示:pyproject.toml 是源配置,requirements.txt 由它导出。新增依赖时先写入 pyproject.toml,再同步到 requirements.txt。

---

#### 第 4 步:搭建 GPU 虚拟环境(两台独立 conda 环境)

**文件**:requirements.gpu-pytorch.txt、requirements.gpu-paddle.txt
**位置**:项目根目录

由于 PyTorch 和 PaddlePaddle 不能装在同一个环境(本文档 3.5 节),需要创建两个独立的 conda 环境:

环境 1:docparse_pytorch(版面分析 + 表格 + 公式)
  conda create -n docparse_pytorch python=3.12 -y
  conda activate docparse_pytorch
  pip install -r requirements.gpu-pytorch.txt

环境 2:docparse_paddle(OCR 文字识别)
  conda create -n docparse_paddle python=3.12 -y
  conda activate docparse_paddle
  pip install -r requirements.gpu-paddle.txt

环境分工:
  docparse_pytorch:torch + doclayout-YOLO + TableTransformer + UniMERNet
  docparse_paddle:paddlepaddle-gpu + PaddleOCR

注意:第零层开发只需要 docparse_pytorch 环境。docparse_paddle 可在第三层开发前再安装。

---

#### 第 5 步:安装系统工具(Docker 容器内)

**文件**:docker/Dockerfile.tools
**位置**:docker/Dockerfile.tools

系统工具已集成在 Docker 容器中,由 docker-compose 统一管理。(本文档 3.4 节)

容器内预安装的系统工具:
  LibreOffice headless   文档渲染 + 格式转换
  Pandoc(>= 3.x)        LaTeX/HTML/DOCX 格式转换
  FFmpeg                 预留音视频处理
  Poppler-utils          PDF 渲染

---

#### 第 6 步:启动 Docker 容器化开发环境

**文件**:docker-compose.yml(编排)+ docker/Dockerfile.*(构建配方)

操作:
  docker compose build      构建全部镜像
  docker compose up -d      启动全部服务
  docker compose ps         查看状态
  docker compose logs -f api-server   查看 API 日志

9 个服务清单:

  postgres      pgvector/pgvector:pg15(含pgvector扩展)  5432
  redis         redis:7-alpine                          6379
  minio         minio/minio                             9000/9001
  tools         docker/Dockerfile.tools                 8100,8200
  api-server    docker/Dockerfile.api(target:dev)       8000
  async-worker  docker/Dockerfile.api(target:dev)       --
  frontend      docker/Dockerfile.frontend              80
  gpu-pytorch   docker/Dockerfile.gpu-pytorch           8001
  gpu-paddle    docker/Dockerfile.gpu-paddle            8002

注意:GPU 容器需要宿主机安装 NVIDIA Container Toolkit。

---

#### 第 7 步:验证环境

环境搭建完成后,执行以下检查:

  docker compose ps                   确认所有服务为 Up
  curl http://localhost:8000/health    API 健康检查
  docker compose exec postgres pg_isready -U docparser -d docparser    PG 检查
  docker compose exec redis redis-cli ping    Redis 检查(预期 PONG)
  docker compose run --rm gpu-pytorch python -c "import torch; print(torch.cuda.is_available())"    GPU 检查

---

#### 文件创建顺序总览(供参考)

  .gitignore ................. 第 1 步(Git 忽略规则)
  .env.example ............... 第 2 步(环境变量模板)
  pyproject.toml ............. 第 3 步(Python 项目配置)
  requirements.txt ........... 第 3 步(pip 依赖清单)
  requirements.gpu-pytorch.txt  第 4 步(GPU PyTorch 依赖)
  requirements.gpu-paddle.txt   第 4 步(GPU Paddle 依赖)
  docker/Dockerfile.* ........ 第 5-6 步(各服务构建配方)
  .dockerignore .............. 第 5-6 步(Docker 构建忽略)
  docker-compose.yml ......... 第 6 步(多容器编排)

每一行文件都在对应步骤中使用,按顺序执行即可完成开发环境搭建。
### 6.2 开发阶段划分

项目采用分阶段开发策略，优先完成核心链路能力：

| 阶段   | 内容                                                  | 目标                         |
|--------|-------------------------------------------------------|------------------------------|
| 第零层 | API 框架搭建 + 数据库表创建 + WebSocket 基础 + 项目骨架 | 可运行的空壳系统               |
| 第一层 | 上传服务 + 文件类型识别（4 层级联）                      | 文件能上传并识别类型           |
| 第二层 | 文档解析器组（PDF/Word/PPT/Excel/HTML/TXT/代码）      | 文档类文件可解析               |
| 第三层 | 图片解析管线 + GPU 容器                               | 图片类文件可解析               |
| 第四层 | 收藏管理 + 结果预览 + 格式下载转换                       | 完整交互体验                  |

### 6.3 前端页面与后端路由映射

| 前端页面       | URL                  | 后端接口                                              |
|---------------|----------------------|------------------------------------------------------|
| 新解析（首页） | /                    | GET /api/v1/files?limit=10（最近历史）+ 上传接口       |
| 任务管理       | /tasks               | GET /api/v1/tasks + 筛选/搜索/重试/取消                |
| 我的收藏       | /collections/:id     | GET /api/v1/collections/{id}/items                    |
| 解析结果呈现   | /results/:task_id    | GET /api/v1/results/{task_id} + 文件预览 + 下载按钮    |

### 6.4 开发注意事项

- PaddlePaddle 和 PyTorch 装在两个独立的 conda 环境中，互不干扰
- 系统工具（FFmpeg、Poppler）与 Python 环境无关，通过系统包管理器或 conda 安装
- GPU 模型容器在 Docker 中运行，与主程序分离，不依赖本地 conda 环境
- 开发环境搭建完第 1-4 步后即可开始第零层开发
- GPU 显存实验（GPU 容器前置条件）在两个环境中的任意一个执行均可，只需 CUDA 可用

---
