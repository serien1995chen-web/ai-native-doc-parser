# gpu-paddle

PaddleOCR GPU 推理容器，负责 OCR 文字识别。

模型由 PaddleOCR 自动下载，也可通过 /models 缓存。

接口：

- GET /health
- POST /ocr
