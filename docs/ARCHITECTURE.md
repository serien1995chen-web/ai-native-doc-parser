# 系统架构

> 基于《AI Native 文档解析平台 · 系统设计文档 v1.0》系统架构章节整理

---

## 分层架构总览

系统采用五层分层架构：

| 层级 | 组件 | 职责 |
|------|------|------|
| **接入层** | API Gateway、Web UI (SPA)、WebSocket Service | 统一入口、认证限流、前端资源服务、实时状态推送 |
| **核心业务层** | 上传服务、文件类型识别、解析调度器、各解析器、统一输出格式化器 | 数据摄入→识别→解析→输出的全链路处理 |
| **业务支撑层** | 任务管理、收藏管理、文件预览 | 任务 CRUD/重试/批量、收藏集管理、文档渲染与 bbox |
| **数据层** | PostgreSQL、对象存储(MinIO/本地文件系统)、消息队列(Redis/PG) | 元数据/任务/用户数据、原始文件与结果文件存储、任务队列 |
| **基础设施层** | GPU 模型推理服务、监控/日志/告警 | 模型推理容器、运维可观测性 |

## 模块职责说明

| 模块 | 职责 | 运行时依赖 |
|------|------|-----------|
| API Gateway | 反向代理、认证鉴权、速率限制 | 无 |
| Web UI | 前端 SPA 资源服务 | 无 |
| WebSocket Service | 向用户推送任务状态变更 | 消息队列（可选） |
| 上传服务 | 文件校验、去重、存储、记录元数据 | 对象存储 + 数据库 |
| 文件类型识别 | 独立的识别引擎，4 层级联管道 | 无（纯 CPU 算法） |
| 解析调度器 | 消费识别结果，通过配置对照表匹配解析器 | Parser Registry + 路由配置表 |
| 文档解析器组 | 解析 PDF/Word/PPT/Excel/HTML/TXT/MD | 各格式库（python-docx 等） |
| 图片解析器 | 版面分析/OCR/表格/公式/阅读顺序 | 模型推理服务（GPU） |
| 统一输出格式化器 | 结构化中间态 → Markdown/JSON | 无 |
| 任务管理 | 任务 CRUD、重试、取消、批量操作 | 数据库 |
| 收藏管理 | 收藏集 CRUD、按 content_type 分类浏览 | 数据库 |
| 文件预览 | 文档渲染 + bbox 数据生成 | 对象存储 + 数据库 |

## 文件类型识别（4 层级联管道）

文件类型识别是独立的识别引擎，不依赖下游解析路由，输出写入 `file_identifications` 表：

- **Layer 1（扩展名层）** — 通过文件扩展名快速预识别，提供候选类型与低置信度（< 0.5）
- **Layer 2（签名层）** — 识别流程核心。通过魔术字节（ Magic Byte，前 8-16 KB + 尾 512 字节签名匹配）和容器探查（ ZIP 格式解析 `[Content_Types].xml` ）确定文件类型
- **Layer 3（内容嗅探层）** — 通过正则与模式匹配区分同态文件（如 .text / .cfg / .log 的纯文本与代码），产出中等置信度（0.50-0.85）
- **Layer 4（AI 兜底层）** — 轻量 MLP 分类器，输入前 3 层及文件统计特征，处理极少数疑难杂症

## 解析路由对照表

| identified_type | Parser | 方式 | 依赖 |
|----------------|--------|------|------|
| doc / docx | docx_parser | 同步 | python-docx |
| ppt / pptx | pptx_parser | 同步 | python-pptx |
| xls / xlsx | xlsx_parser | 同步 | openpyxl |
| html / htm | html_parser | 同步 | BeautifulSoup |
| txt / md / text | text_parser | 同步 | 无 |
| code / python / javascript | code_parser | 同步 | Pygments |
| pdf | pdf_parser | 异步 | PyMuPDF + Poppler + GPU 管线 |
| image / jpg / png / bmp | image_pipeline | 异步+GPU | doclayout-YOLO + PaddleOCR + TableTransformer + UniMERNet |
| image_formula | image_pipeline（公式分支） | 异步+GPU | UniMERNet |
| image_table | image_pipeline（表格分支） | 异步+GPU | TableTransformer |

> 同步解析器在 API 进程中直接运行（< 1 秒）；异步解析器通过 arq 队列提交，由 worker 处理。系统有处理能力上限，超限任务进入等待队列排队，系统不会因超载崩溃。未匹配路由统一返回 UNSUPPORTED_FORMAT 错误。

## 数据流

### 全局数据流

上传/截图/文本粘贴 → 上传服务（校验/去重/落盘）→ 文件类型识别（4 层级联）→ 解析调度器（Registry 匹配）→ 对应解析器执行 → 统一输出格式化器（Markdown/JSON）→ WebSocket 推送完成 → 解析结果呈现页

### 完整流水线

- **Phase 1：上传** — 用户操作 → 上传服务 → 校验/去重/落盘 → 对象存储 → 写 files 表 → 入识别队列
- **Phase 2：文件类型识别** — Layer 1 → Layer 2 → Layer 3 → Layer 4 → 写 file_identifications 表
- **Phase 3：Parser 路由与执行** — 读取识别结果 → Router 匹配 Parser → 同步/异步执行 → 产生 ParseResult
- **Phase 4：输出格式化** — ParseResult → Markdown/JSON 格式化 → 写入 parse_results 表 → WebSocket 推送

## 模块独立性与部署拓扑

系统分为 6 个功能切片，各切片可独立部署、独立扩缩容：

| 切片 | 组件 | 说明 |
|------|------|------|
| 切片 1 | API Server | FastAPI 主进程（uvicorn），承载上传、识别、调度、任务管理、收藏管理、文件预览 |
| 切片 2 | Async Worker | arq worker 进程，消费 Redis 队列，处理 PDF 解析 + 图片解析等异步任务 |
| 切片 3 | Frontend | Nginx + Vue 3 SPA 静态文件 |
| 切片 4 | PostgreSQL + Redis + MinIO | 元数据库 / 消息队列 / 对象存储 |
| 切片 5 | LibreOffice + Pandoc | 系统工具容器（文档渲染 + 格式转换） |
| 切片 6 | GPU 推理容器 | doclayout-YOLO + PaddleOCR + TableTransformer + UniMERNet |

> 未来扩展音频/视频解析时，新增 GPU 容器即可，实现 Parser 接口协议并注册到 Registry，现有容器零改动。

## 解析器插件协议

系统通过 `BaseParser` 抽象基类和 `ParserRegistry` 注册机制提供可扩展的解析器架构：

- **BaseParser** — 定义 `info()`、`parse()`、`estimate()` 抽象接口
- **ParserRegistry** — 以 Registry 模式管理所有解析器，按 `supported_types` 匹配
- **加载机制** — 系统启动时通过 `parsers/__init__.py` 导入各实现模块，自动执行 `register()` 完成注册
- **新增解析器** — 只需在 `implementations/` 下创建新 Parser 实现，注册后在 `__init__.py` 追加 import，重启生效，无需修改 Router 代码

```python
@dataclass
class ParseResult:
    markdown: str
    json_data: dict
    page_count: Optional[int] = None
    processing_time_ms: Optional[int] = None

@dataclass
class ParserInfo:
    name: str
    supported_types: List[str]
    required_gpu: bool
    required_models: List[str]
    version: str

class BaseParser(ABC):
    @abstractmethod
    def info(self) -> ParserInfo: ...
    @abstractmethod
    def parse(self, file_path: str, options: dict = None) -> ParseResult: ...
    def estimate(self, file_path: str) -> dict: ...
