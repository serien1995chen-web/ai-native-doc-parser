## 6. 开发流程

### 6.1 环境搭建流程

**第 1 步：创建两个虚拟环境（conda）**

```bash
conda create -n docparse_pytorch python=3.12
conda create -n docparse_paddle python=3.12
```

**第 2 步：安装 PyTorch 环境**

```bash
conda activate docparse_pytorch
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
pip install doclayout-yolo table-transformer unimernet
```

**第 3 步：安装 PaddlePaddle 环境**

```bash
conda activate docparse_paddle
pip install paddlepaddle-gpu paddleocr
```

**第 4 步：安装系统工具**

```bash
conda install -c conda-forge ffmpeg poppler pandoc
```

**第 5 步：安装主程序依赖**

```bash
conda activate docparse_pytorch
pip install -r backend/requirements.txt
```

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

