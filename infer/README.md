# infer/ — 推理引擎

基于 llama.cpp 的 ctypes 封装，实现本地 GPU 推理。

## 模块

| 文件 | 说明 |
|------|------|
| `llama_binding.py` | llama.dll ctypes 封装，GPT-2 byte-level 解码器，LlamaModel 类 |
| `mtmd_binding.py` | mtmd.dll 多模态封装，MtmdOCR 类 |
| `ocr.py` | Unlimited-OCR 引擎，`<\|det\|>` 输出解析 |
| `translate.py` | 最简翻译器（基础 prompt） |
| `translate_v2.py` | SmartTranslator：方向引导 + 块合并 + 伪标题检测 + 回译验证 |
| `workflow.py` | LangGraph 流式工作流（实验性） |

## 翻译策略（translate_v2.py）

```
translate_block(text, block_type)
    ├─ title / pseudo-title → None (skip)
    ├─ text < 200 chars   → _translate_short()
    ├─ text > 500 chars   → _translate_long()  分块+上下文窗口+逐块验证
    └─ text 200-500       → _translate_normal() 方向引导+回译验证
```

### 伪标题检测（is_pseudo_title）

跳过翻译的条件（避免幻觉）：
- < 40 字符
- 已知标题词（Abstract, Introduction, References...）
- 编号开头（3.4.2. KV cache management）
- 全 Title Case + 无句号

### 块合并（merge_split_blocks）

相邻 text 块合并条件：
- 前块不以 `.` `?` `!` 结束
- 后块以小写开头
- bbox 垂直间距 < 2.5 行高

## 依赖

- 编译产物：`llama.dll`, `ggml*.dll`, `mtmd.dll`
- 模型：`Unlimited-OCR-Q8_0.gguf`, `mmproj-Unlimited-OCR-F16.gguf`, `Hy-MT2-1.8B-Q8_0.gguf`
