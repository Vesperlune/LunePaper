# frontend/ — Web UI

React + TypeScript + TailwindCSS + Vite

## 文件

| 文件 | 说明 |
|------|------|
| `src/App.tsx` | 主组件：Upload / Translating / Done 三模式 |
| `src/api.ts` | HTTP + WebSocket 客户端 |
| `src/types.ts` | TypeScript 类型定义 |
| `src/hooks/useWebSocket.ts` | WebSocket 连接 hook |

## 页面模式

```
Upload          拖拽上传 PDF
Translating     进度条 + 双语预览区（逐块实时渲染）
Done            完整对照 + 下载 ZIP
```

## 块渲染

| 类型 | 方式 |
|------|------|
| text, title | EN 灰斜 + ZH 黑正文 |
| equation | KaTeX |
| table | HTML table |
| image, chart | 后端截取 `<img>` |
| page_number | 隐藏 |

## 启动

```bash
npm install && npm run dev     # http://localhost:5173
```
