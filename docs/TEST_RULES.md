## 8. 测试规范

### 8.1 测试层级

| 层级       | 工具                     | 目标覆盖率  | 说明                                  |
|-----------|--------------------------|-----------|---------------------------------------|
| 单元测试   | pytest                   | ≥ 80%     | 测试核心业务逻辑、Parser 协议、工具函数 |
| 集成测试   | pytest + httpx (AsyncClient) | ≥ 60%  | 测试 API 端点与数据库、对象存储的交互    |
| 端到端测试 | Playwright               | 关键路径   | 测试前端到后端的完整用户流程            |

### 8.2 测试目录结构

```
backend/
  tests/
    __init__.py
    conftest.py              # 全局 fixture（DB session、client、mock 对象存储）
    unit/
      test_file_type_id.py   # 文件类型识别单元测试
      test_parser_base.py    # Parser 协议与注册机制测试
      test_output_formatter.py  # 输出格式化测试
    integration/
      test_upload_api.py     # 上传接口集成测试
      test_task_api.py       # 任务接口集成测试
      test_collection_api.py # 收藏接口集成测试
```

### 8.3 单元测试规范

- 每个测试函数使用 `def test_<被测功能>_<场景>():` 命名
- 使用 pytest fixture 管理测试依赖，避免在测试函数内直接初始化外部资源
- 对外部服务（MinIO、PostgreSQL）的调用使用 `unittest.mock` 或 `pytest-mock` 打桩
- CPU 模型（如文件类型识别）直接测试，GPU 模型使用 mock 模拟返回值

### 8.4 集成测试规范

- 使用 pytest 的 `httpx.AsyncClient` 模拟 API 请求
- 测试数据库使用独立的 test 数据库（通过 pytest fixture 创建/销毁）
- 每个集成测试类结束后清理测试数据
- 必须测试错误路径：非法输入、权限不足、资源不存在、服务不可用

### 8.5 测试标记与运行

```bash
# 运行所有测试
pytest

# 仅运行单元测试
pytest -m unit

# 运行集成测试（跳过 GPU 相关）
pytest -m integration --ignore-gpu

# 生成覆盖率报告
pytest --cov=app --cov-report=term-missing
```

### 8.6 特殊情况

- GPU 模型推理无对应的单元测试文件，由专用的 GPU 容器测试套件覆盖
- 文件类型识别中的 AI 兜底层（Layer 4）模型极小（MLP 分类器），可直接在单元测试中加载并测试推理路径

---

