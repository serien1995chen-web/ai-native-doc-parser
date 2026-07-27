## 2. 系统架构

### 2.1 分层架构总览

```
================================================================================
                           接入层 (Access Layer)
   ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────────┐
   │  API Gateway      │  │  Web UI (SPA)    │  │  WebSocket Service    │
   │  统一入口/认证/限流 │  │  前端静态资源服务  │  │  实时状态推送          │
   └──────────────────┘  └──────────────────┘  └────────────────────────┘
================================================================================
                          核心业务层 (Core Business Layer)
   ┌────────────────────────────────────────────────────────────────────┐
   │  上传服务 (Upload Service)                                          │
   │  ├─ 文件上传 (multipart)                                            │
   │  ├─ 截图上传 (Base64 → 临时文件)                                    │
   │  └─ 文本粘贴 (raw text → 临时文件)                                  │
   └──────────────────┬─────────────────────────────────────────────────┘
                      │
   ┌──────────────────▼─────────────────────────────────────────────────┐
   │  文件类型识别服务 (File Type ID)                                      │
   │  4 层级联管道 (Layer 1-4)                                           │
   │  产出: identified_type + content_type + confidence                  │
   └──────────────────┬─────────────────────────────────────────────────┘
                      │
   ┌──────────────────▼─────────────────────────────────────────────────┐
   │  解析调度器 (Parser Router)                                         │
   │  Registry 模式，按 final_type 匹配对应的 Parser 实现                  │
   └──────────────────┬─────────────────────────────────────────────────┘
                      │
          ┌───────────┼───────────────┐
          │           │               │
   ┌──────▼────┐  ┌───▼───────┐  ┌───▼──────────┐
   │ 文档解析器组 │  │ 图片解析器  │  │ [预留] 音频/  │
   │ PDF/Word/  │  │ doclayout- │  │ 视频解析     │
   │ PPT/Excel/ │  │ yolo      │  │ (Parser 接口 │
   │ HTML/TXT   │  │ PaddleOCR │  │  已定义)     │
   │ 文本/代码   │  │ TableTrans│  └──────────────┘
   └────────────┘  │ former    │
                   │ UniMERNet │
                   │ 阅读顺序   │
                   └───────────┘

   ┌────────────────────────────────────────────────────────────────────┐
   │  统一输出格式化器 (Unified Output Formatter)                          │
   │  → Markdown 格式化器 → .md 文件                                     │
   │  → JSON 序列化器     → .json 文件                                   │
   └────────────────────────────────────────────────────────────────────┘
================================================================================
                           业务支撑层 (Business Support Layer)
   ┌────────────────┐  ┌────────────────┐  ┌────────────────┐
   │ 任务管理服务     │  │ 收藏管理服务     │  │ 文件预览服务     │
   │ CRUD/重试/批量   │  │ 关联 task_id    │  │ PDF 渲染        │
   │ 状态聚合         │  │ content_type 分类│  │ + bbox 覆盖     │
   └────────────────┘  └────────────────┘  └────────────────┘
================================================================================
                             数据层 (Data Layer)
   ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────┐
   │  PostgreSQL          │  │  对象存储              │  │  消息队列 (可选)   │
   │  元数据/任务/用户/    │  │  MinIO / 本地文件系统   │  │  Redis / PG 内置  │
   │  收藏                 │  │  原始文件 + 结果文件    │  │                    │
   └──────────────────────┘  └──────────────────────┘  └──────────────────┘
================================================================================
                          基础设施层 (Infrastructure Layer)
   ┌──────────────────────┐  ┌──────────────────────┐
   │  模型推理服务          │  │  监控 / 日志 / 告警   │
   │  GPU 模型独立容器      │  │                      │
   └──────────────────────┘  └──────────────────────┘
================================================================================
```

### 2.2 模块职责说明

| 模块               | 职责                                                  | 运行时依赖                    |
|--------------------|-------------------------------------------------------|------------------------------|
| API Gateway       | 反向代理、认证鉴权、速率限制                             | 无                           |
| Web UI            | 前端 SPA 资源服务                                       | 无                           |
| WebSocket Service | 向用户推送任务状态变更                                   | 消息队列（可选）               |
| 上传服务           | 文件校验、去重、存储、记录元数据                          | 对象存储 + 数据库             |
| 文件类型识别       | 独立的识别引擎，4 层级联管道                              | 无（纯 CPU 算法）             |
| 解析调度器         | 消费文件类型识别结果，通过可配置对照表匹配对应解析器       | Parser Registry + 路由配置表  |
| 文档解析器组       | 解析 PDF/Word/PPT/Excel/HTML/TXT/MD                   | 各格式库（python-docx 等）    |
| 图片解析器         | 版面分析/OCR/表格/公式/阅读顺序                          | 模型推理服务（GPU）            |
| 统一输出格式化器   | 结构化中间态 → Markdown/JSON                           | 无                           |
| 任务管理           | 任务 CRUD、重试、取消、批量操作                          | 数据库                        |
| 收藏管理           | 收藏集 CRUD、按 content_type 分类浏览                   | 数据库                        |
| 文件预览           | 文档渲染 + bbox 数据生成                                | 对象存储 + 数据库             |

### 2.3 独立模块一：文件类型识别

文件类型识别是一个独立的识别引擎，不依赖下游的解析路由。输出结果写入 `file_identifications` 表。系统采用 4 层级联管道：

**Layer 1（扩展名层）—— 快速预识别**  
通过文件扩展名进行快速识别，但识别不准确，文件识别可信度低。目的不是给出最终答案，而是为下游各层提供一个候选假设。产出：候选类型 + 低置信度（通常 < 0.5）。

**Layer 2（签名层）—— 整个识别流程的核心，占大块头**  
非结构化数据在磁盘底层储存一定是二进制比特流，文件签名相当于每个文件格式自带的身份证号码。通过魔术字节和容器探查两种方法结合来判断文件类型：

- **魔术字节检测（Magic Byte Detection）**：读取文件头部签名（前 8-16 KB）+ 尾部 512 字节，与已知格式的魔数签名库匹配。范围严格控制，避免全文件读取。
- **容器探查（Container Probing）**：企业有大量的压缩包格式（如 DOCX、XLSX、PPTX 本质是 ZIP），这些格式仅凭头部/尾部残留信息无法区分。容器探查逻辑：读取文件的头 4 字节判断是否为 ZIP 签名，如果是则读取容器内部 [Content_Types].xml 来确定确切子类型。

**Layer 3（内容嗅探层）—— 识别同态文件**  
当 Layer 2 无法区分时（如文本文件 .text、.cfg、.log 全部是纯文本），通过正则和模式匹配代码特征和文本特征来区分 txt 和 code。产出：候选类型 + 中等置信度（通常在 0.50-0.85）。

**Layer 4（AI 兜底层）—— 极少数疑难杂症**  
当 Layer 1-3 都无法给出足够置信度（所有候选置信度均低于 0.5）时，由 AI 模型兜底。这是一个极轻量的 MLP 分类器，输入来自前 3 层及文件统计特征（文件大小、字节分布熵、行数、平均行长等），输出最终决定。这是最后的兜底方案，通常不会被触发。

### 2.4 独立模块二：文件类型 → 解析路由对照表

解析调度器消费文件类型识别产出的 identified_type（来自 file_identifications 表），按以下对照表选择对应的解析器：

| identified_type              | Parser                    | 方式      | 依赖                                                    |
|------------------------------|---------------------------|-----------|--------------------------------------------------------|
| doc / docx                   | docx_parser               | 同步      | python-docx                                            |
| ppt / pptx                   | pptx_parser               | 同步      | python-pptx                                            |
| xls / xlsx                   | xlsx_parser               | 同步      | openpyxl                                               |
| html / htm                   | html_parser               | 同步      | BeautifulSoup                                          |
| txt / md / text              | text_parser               | 同步      | 无                                                     |
| code / python / javascript   | code_parser               | 同步      | Pygments                                               |
| pdf                          | pdf_parser                | 异步      | PyMuPDF + Poppler + GPU 管线                           |
| image / jpg / png / bmp      | image_pipeline            | 异步+GPU  | doclayout-YOLO + PaddleOCR + TableTransformer + UniMERNet |
| image_formula                | image_pipeline（公式分支） | 异步+GPU  | UniMERNet                                              |
| image_table                  | image_pipeline（表格分支） | 异步+GPU  | TableTransformer                                        |

> 同步解析器在 API 进程中直接运行（< 1 秒）。异步解析器通过 arq 队列提交，由 worker 处理。系统有处理能力上限（由 worker 数量和 GPU 显存决定），当提交的任务超过处理上限时，新任务进入等待队列排队，系统不会因为超载而崩溃。未匹配的路由统一返回 UNSUPPORTED_FORMAT 错误。

### 2.5 数据流

#### 全局数据流

```
                     ┌────────────────────────────┐
                     │          新解析              │
                     │  ┌──────────────────────┐  │
                     │  │ 1. 上传文件           │  │
                     │  │ 2. 截图粘贴 (Ctrl+V)  │  │
                     │  │ 3. 粘贴文本/代码      │  │
                     │  └─────────┬────────────┘  │
                     └────────────┼───────────────┘
                                  │
                     ┌────────────▼───────────────┐
                     │     上传服务                 │
                     │  ├─ 校验 / 去重 / 落盘       │
                     │  ├─ 文本粘贴 → 存为临时文件   │
                     │  ├─ 截图粘贴 → 存为临时图片   │
                     │  └─ 写 files 表 → 入识别队列  │
                     └────────────┬───────────────┘
                                  │
                     ┌────────────▼───────────────┐
                     │ 文件类型识别 (4 层级联)      │
                     │  产出: identified_type +    │
                     │  content_type + confidence  │
                     └────────────┬───────────────┘
                                  │
                     ┌────────────▼───────────────┐
                     │ 解析调度器 (Registry 匹配)   │
                     └────────────┬───────────────┘
                                  │
              ┌───────────────────┼────────────────────┐
              │                   │                    │
     ┌────────▼───────┐  ┌───────▼───────┐  ┌────────▼───────┐
     │ 文档解析器       │  │ 图片解析器     │  │ [预留] 音频/   │
     │ PDF/Word/PPT/   │  │ 版面→OCR→表格  │  │ 视频 (Parser  │
     │ Excel/HTML/TXT  │  │ →公式→阅读顺序  │  │  协议已定义)   │
     │ 文本/代码        │  └───────┬───────┘  └────────────────┘
     └────────┬───────┘           │
              │                   │
              └───────────────────┼───────────────────┘
                                  │
                     ┌────────────▼───────────────┐
                     │     统一输出格式化器          │
                     │  → Markdown                 │
                     │  → JSON                     │
                     │  → 写入 parse_results 表     │
                     └────────────┬───────────────┘
                                  │
                     ┌────────────▼───────────────┐
                     │     WebSocket 推送完成通知   │
                     │     更新 files.status       │
                     └────────────┬───────────────┘
                                  │
                     ┌────────────▼──────────────────────────┐
                     │     自动跳转 → 解析结果呈现页           │
                     │  ┌──────────┐  ┌────────────────────┐ │
                     │  │ 左侧:    │  │ 右侧:              │ │
                     │  │ 原文件    │  │ Markdown ↔ JSON    │ │
                     │  │ + bbox   │  │ 切换 + 一键复制     │ │
                     │  └──────────┘  └──────┬─────────────┘ │
                     │                       │               │
                     │            点击[收藏] │               │
                     │                       ▼               │
                     │           写 collection_items 表       │
                     └───────────────────────────────────────┘

后续入口:
  任务管理  → 表格视图 → 点击某条 → 跳转到解析结果呈现页 (同上)
  我的收藏  → Tab筛选  → 点击某条 → 跳转到解析结果呈现页 (同上)
```

#### 完整流水线

**Phase 1: 上传**  
用户操作 → 上传服务 → 校验/去重/落盘 → 对象存储（存原始文件）→ 数据库（写 files 表）→ 入识别队列

**Phase 2: 文件类型识别**  
Layer 1（扩展名层）→ Layer 2（签名层+容器探查）→ Layer 3（内容嗅探层）→ Layer 4（AI 兜底层）→ 写 file_identifications 表

**Phase 3: Parser 路由与执行**  
读取 file_identifications 最终结果 → Router 匹配 Parser → 同步/异步执行 → 产生 ParseResult

**Phase 4: 输出格式化**  
ParseResult → Markdown/JSON 格式化 → 写入 parse_results 表 → WebSocket 推送完成通知

### 2.6 模块独立性与部署拓扑

系统分为 6 个功能切片，各切片可独立部署、独立扩缩容：

| 切片   | 组件                                    | 说明                                            |
|--------|-----------------------------------------|-------------------------------------------------|
| 切片 1 | API Server                             | FastAPI 主进程（uvicorn），承载上传、文件类型识别、解析调度、任务管理、收藏管理、文件预览 |
| 切片 2 | Async Worker                           | arq worker 进程，消费 Redis 队列，处理 PDF 解析 + 图片解析等异步任务 |
| 切片 3 | Frontend                               | Nginx + Vue 3 SPA 静态文件                      |
| 切片 4 | PostgreSQL + Redis + MinIO              | 元数据库 / 消息队列 / 对象存储                   |
| 切片 5 | LibreOffice + Pandoc                    | 系统工具容器（文档渲染 + 格式转换）               |
| 切片 6 | GPU 推理容器                            | doclayout-YOLO + PaddleOCR + TableTransformer + UniMERNet |

未来扩展：当需要加入音频/视频解析时，新增一个 GPU 容器即可。只需实现 Parser 接口协议并注册到 Registry，现有容器零改动。

### 2.7 解析器插件协议

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

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
    def info(self) -> ParserInfo:
        pass

    @abstractmethod
    def parse(self, file_path: str, options: dict = None) -> ParseResult:
        pass

    def estimate(self, file_path: str) -> dict:
        return {"estimated_seconds": 0, "gpu_memory_mb": 0}
```

**注册机制：**

```python
class ParserRegistry:
    _parsers: dict = {}

    @classmethod
    def register(cls, parser: BaseParser):
        info = parser.info()
        for file_type in info.supported_types:
            cls._parsers[file_type] = parser

    @classmethod
    def get_parser(cls, file_type: str) -> Optional[BaseParser]:
        return cls._parsers.get(file_type)

    @classmethod
    def list_parsers(cls) -> List[ParserInfo]:
        return [p.info() for p in set(cls._parsers.values())]
```

**解析器加载机制：**

```
main.py (lifespan)
  → from app import parsers
    → parsers/__init__.py 导入各 parser 实现模块
      → 各 parser.py 的模块级代码执行
        → ParserRegistry.register(ParserClass())
          → ParserRegistry._parsers[type] = parser 实例
```

parsers/__init__.py 示例：
```python
from app.parsers.base import BaseParser, ParseResult, ParserInfo
from app.parsers.registry import ParserRegistry
from app.parsers.implementations import pdf_parser
from app.parsers.implementations import docx_parser
from app.parsers.implementations import pptx_parser
from app.parsers.implementations import xlsx_parser
from app.parsers.implementations import html_parser
from app.parsers.implementations import text_parser
from app.parsers.implementations import code_parser
from app.parsers.implementations.image_pipeline import pipeline as image_pipeline
```

**新增解析器流程：**  
1. 在 implementations/ 下创建 parser.py（或子目录）  
2. 文件末尾调用 ParserRegistry.register(YourParser())  
3. 在 parsers/__init__.py 中追加一行 import（不是覆盖）  
4. 重启服务即可生效，无需修改 Router 代码

---

