# backend/ — FastAPI 服务

## 模块

| 文件 | 说明 |
|------|------|
| `main.py` | FastAPI app，CORS 中间件，路由注册 |
| `routes.py` | REST API 端点 |
| `ws.py` | WebSocket 进度推送 |
| `worker.py` | 翻译执行器（OCR→翻译→推送） |
| `task_manager.py` | 任务生命周期管理 |

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/upload` | 上传 PDF → `task_id` |
| `POST` | `/api/translate/{id}` | 启动翻译 |
| `GET` | `/api/status/{id}` | 查询进度 |
| `GET` | `/api/download/{id}` | 下载 Markdown + 图片 ZIP |
| `GET` | `/api/image/{id}/{name}` | 截取图片 |
| `WS` | `/ws/{id}` | 实时进度推送 |

## WebSocket 事件

```
start       → 总页数
page_start  → 开始处理某页
block_done  → 单块翻译完成（en, zh, type, verified）
figure      → 图片截取完成（figure_id, bbox）
page_done   → 某页完成
complete    → 全部完成
error       → 错误
```

## Worker 流程

```
for page in pages:
    ocr = load_OCR()           # 加载 OCR 模型
    recognize → parse → merge  # 识别 + 合并拆分块
    ocr.close()                # 卸载 OCR

    for block in page:
        if passthrough → emit  # 公式/表格/图片 → 直接推送
        zh = translate_block() # SmartTranslator
        emit block_done        # 推送到前端
```

## 启动

```bash
python backend/main.py    # http://localhost:7860
```
