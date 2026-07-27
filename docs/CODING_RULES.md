## 7. 编码规范

### 7.1 Python 编码规范

- **Python 版本**：目标 Python 3.12+
- **代码风格**：遵循 PEP 8 规范，使用 Black 作为自动格式化工具，行长度限制为 88 字符
- **类型注解**：所有函数参数和返回值必须标注类型，使用 `from __future__ import annotations` 启用延迟注解求值
- **导入顺序**：标准库 → 第三方库 → 本地模块（每组之间空一行），使用 isort 自动整理
- **命名约定**：
  - 模块名：`snake_case`（如 `pdf_parser.py`）
  - 类名：`PascalCase`（如 `BaseParser`、`ParserRegistry`）
  - 函数/方法：`snake_case`（如 `get_parser()`、`register()`）
  - 常量：`UPPER_SNAKE_CASE`（如 `MAX_UPLOAD_SIZE`）
  - 私有属性/方法：前缀 `_`（如 `_parsers`）
- **文档字符串**：公共 API 必须编写 docstring，遵循 Google 风格

### 7.2 FastAPI 项目规范

- **路由组织**：按业务模块划分路由文件，如 `routers/files.py`、`routers/tasks.py`、`routers/collections.py`
- **依赖注入**：使用 FastAPI 的 `Depends` 机制管理认证、数据库会话等横切关注点
- **Pydantic 模型**：请求/响应体使用 Pydantic v2 模型定义，放置在 `schemas/` 目录下
- **异常处理**：使用自定义异常类（如 `AppException`）配合全局异常处理器，统一输出错误码格式

### 7.3 数据库操作规范

- **ORM**：使用 SQLAlchemy 2.0 异步模式（`asyncpg` driver）
- **迁移**：使用 Alembic 管理数据库迁移，每次变更生成新的迁移脚本
- **会话管理**：使用 FastAPI 中间件或 `Depends` 管理数据库会话的生命周期
- **索引命名**：`idx_表名_列名`，如 `idx_files_user_id`

### 7.4 异步任务规范

- **任务队列**：使用 arq（基于 Redis 的异步任务队列）
- **任务定义**：每个 Parser 的异步执行逻辑封装为独立的任务函数
- **错误处理**：任务内部必须捕获已知异常并写入 `error_message` 和 `error_details` 字段
- **重试策略**：遵守系统配置 `task.max_retry_count`（默认 3 次），指数退避

### 7.5 Git 提交规范

- **分支模型**：`main` → `develop` → `feature/*` / `fix/*`
- **提交信息格式**：`<type>(<scope>): <description>`，如 `feat(upload): add screenshot paste endpoint`
- **类型**：`feat` / `fix` / `refactor` / `docs` / `test` / `chore` / `style`

---

