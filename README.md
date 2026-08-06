# gpu-pytorch

PyTorch GPU 推理容器，负责版面分析（doclayout-YOLO）、表格检测（TableTransformer）、公式识别（UniMERNet）。

模型目录约定（挂载到 /models）：

- /models/doclayout_yolo/*.pt：DocLayout-YOLO 权重
- /models/table-transformer-detection/：HuggingFace TableTransformer 目录
- /models/unimernet/：UniMERNet 配置与模型

接口：

- GET /health
- POST /layout
- POST /table
- POST /formula（需先补齐 UniMERNet 配置与模型）
