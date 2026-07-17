<div align="center">

<img src="assets/logo.jpg" width="120" height="120" style="border-radius:50%;border:3px solid rgba(59,130,246,0.3);box-shadow:0 4px 20px rgba(59,130,246,0.15);" />

# 月读 · LunePaper

**本地化的科研论文 PDF 翻译工具**


<br>

<img src="https://img.shields.io/badge/GPU-NVIDIA%208GB%2B-green?style=flat-square" />
<img src="https://img.shields.io/badge/License-Apache%202.0-orange?style=flat-square" />
<img src="https://img.shields.io/badge/Privacy-100%25%20Local-purple?style=flat-square" />

</div>

---

<br>

<div align="center">
<img src="assets/showcase.png" width="90%" style="border-radius:12px;box-shadow:0 8px 40px rgba(0,0,0,0.12);" />
<br><br>
<em>LunePaper界面一览</em>
</div>

<br>

---

## <img src="assets/2.jpg" width="60" height="60" style="border-radius:50%;vertical-align:middle;margin-right:8px;" /> 月读是什么

月读是一个 **纯本地运行** 的 PDF 学术论文翻译器。上传英文 PDF，自动完成 OCR 识别、智能翻译、双语对照预览，最终输出 Markdown + 图片的 ZIP 包。

**全程不经过任何云服务器，数据零外传。**

```
  PDF 上传  ──►  OCR 识别  ──►  智能翻译  ──►  双语预览  ──►  下载 ZIP
     📄            🔍            🌐           📖            📦
```

<details>
<summary><b>📐 系统架构</b></summary>
<br>

```
┌──────────────┐     REST + WebSocket      ┌──────────────┐
│   Frontend   │ ◄═══════════════════════► │   Backend    │
│  React + TS  │    逐块实时推送翻译结果     │   FastAPI    │
│  TailwindCSS │                            │   Uvicorn    │
└──────────────┘                            └──────┬───────┘
                                                   │ ctypes
                                            ┌──────▼───────┐
                                            │    Infer     │
                                            │  llama.cpp   │
                                            │  bindings    │
                                            └──────┬───────┘
                                                   │ C ABI
                                            ┌──────▼───────┐
                                            │   GPU 推理    │
                                            │ *.dll + *.gguf│
                                            └──────────────┘
```

</details>

<br>

---

##  核心特性

| 特性 | 说明 |
|:-----|:-----|
| **流式翻译** | 逐页 OCR → 逐块翻译 → 前端实时渲染，无需等待全文完成 |
| **公式渲染** | KaTeX 渲染块级和行内 LaTeX 公式 |
| **表格保留** | HTML table 原样展示，样式完整 |
| **图片截取** | 自动裁剪 PDF 中的 figure / chart 区域 |
| **伪标题检测** | 自动跳过 "Abstract"、"3.2 Model" 等非正文标题 |
| **块合并** | 修复 OCR 误拆分的连续段落 |
| **论文方向注入** | 从摘要提取研究主题，指导全文翻译保持一致 |
| **长文分段** | >500 字自动按句切分 + 滑动上下文窗口 |
| **回译验证** | 每段翻译后回译核对，低分自动低温重译 |
| **PDF 对照** | 一键开启原文 / 翻译左右对照模式 |
| **页码导航** | 左侧缩略图目录，点击跳转对应页 |
| **防刷新保护** | 翻译中 / 完成后刷新自动弹出确认 |

<br>

---

## <img src="assets/3.jpg" width="60" height="60" style="border-radius:50%;vertical-align:middle;margin-right:8px;" /> 模型

| 模型 | 参数量 | 大小 | 用途 | 来源 |
|:-----|:------:|:----:|:-----|:-----|
| **Unlimited-OCR** | 3B MoE | ~2.9 GB | 文档 OCR（文字 / 公式 / 表格 / 图片） | [HuggingFace](https://huggingface.co/sahilchachra/Unlimited-OCR-GGUF) |
| **mmproj** | — | ~774 MB | 视觉投影器（配合 OCR） | 同上 |
| **Hy-MT2** | 1.8B | ~1.8 GB | 英→中学术翻译 | [HuggingFace](https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF) |

<br>

---

## <img src="assets/1.jpg" width="60" height="60" style="border-radius:50%;vertical-align:middle;margin-right:8px;" /> 硬件要求

| 项目 | 最低要求 |
|:----:|:---------|
| **GPU** | NVIDIA 8GB+ VRAM（RTX 4060 测试通过） |
| **RAM** | 16GB+ |
| **系统** | Windows / Linux / macOS |
| **存储** | ~8 GB（模型 + 编译产物） |

<br>

---

## <img src="assets/4.jpg" width="40" height="40" style="border-radius:50%;vertical-align:middle;margin-right:8px;" /> 快速开始

### Step 1 · 克隆仓库

```bash
git clone https://github.com/yourname/paper-translator.git
cd paper-translator
```

### Step 2 · 编译 llama.cpp

项目只用到核心推理库（`llama.dll` + `mtmd.dll`），不需要完整工具链。

**前提**：Visual Studio 2022 / GCC+Clang、CMake ≥ 3.22、Ninja、CUDA Toolkit 12.x

<details>
<summary><b>Windows（VS 2022 + CUDA）</b></summary>

```powershell
git clone https://github.com/ggml-org/llama.cpp.git
cd llama.cpp

cmake -B build_min -G Ninja ^
  -DCMAKE_BUILD_TYPE=Release ^
  -DBUILD_SHARED_LIBS=ON ^
  -DGGML_CUDA=ON ^
  -DLLAMA_BUILD_COMMON=OFF ^
  -DLLAMA_BUILD_TESTS=OFF ^
  -DLLAMA_BUILD_TOOLS=OFF ^
  -DLLAMA_BUILD_EXAMPLES=OFF ^
  -DLLAMA_BUILD_SERVER=OFF ^
  -DLLAMA_BUILD_APP=OFF ^
  -DLLAMA_BUILD_MTMD=ON

cmake --build build_min --config Release --target llama mtmd -j 8
cp build_min/bin/*.dll ../paper-translator/
```

</details>

<details>
<summary><b>Linux（GCC + CUDA）</b></summary>

```bash
git clone https://github.com/ggml-org/llama.cpp.git
cd llama.cpp

cmake -B build_min -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=ON \
  -DGGML_CUDA=ON \
  -DLLAMA_BUILD_COMMON=OFF \
  -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_TOOLS=OFF \
  -DLLAMA_BUILD_EXAMPLES=OFF \
  -DLLAMA_BUILD_SERVER=OFF \
  -DLLAMA_BUILD_APP=OFF \
  -DLLAMA_BUILD_MTMD=ON

cmake --build build_min --target llama mtmd -j $(nproc)
cp build_min/bin/*.so ../paper-translator/
```

</details>

### Step 3 · 下载模型

```bash
# OCR 模型（推荐 Q8_0）
wget https://huggingface.co/sahilchachra/Unlimited-OCR-GGUF/resolve/main/Unlimited-OCR-Q8_0.gguf

# 视觉投影器（必需）
wget https://huggingface.co/sahilchachra/Unlimited-OCR-GGUF/resolve/main/mmproj-Unlimited-OCR-F16.gguf

# 翻译模型
wget https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q8_0.gguf
```

将三个 `.gguf` 文件放到项目根目录。

### Step 4 · 环境准备

```bash
# Python 后端
conda create -n pt python=3.10
conda activate pt
pip install -r requirements.txt

# 前端
cd frontend
npm install
```

### Step 5 · 启动

```bash
# 终端 1：后端
conda activate pt
python backend/main.py              # http://localhost:7860

# 终端 2：前端
cd frontend
npm run dev                         # http://localhost:5173
```

打开 `http://localhost:5173`，拖拽 PDF 即可开始翻译。

<br>

---

##  配置

编辑 `config.yaml` 调整参数：

```yaml
gpu:
  ocr_layers: 99          # OCR 模型 GPU 层数
  trans_layers: 99        # 翻译模型 GPU 层数

ocr:
  max_tokens: 4096        # 每页最大输出 token
  dpi: 144                # PDF 渲染 DPI（越高越清晰，越慢）

translation:
  verify: true            # 回译验证
  chunk_size: 500         # 长文分段阈值（字符数）

sampling:
  temperature: 0.3        # 翻译采样温度
```

<br>

---

##  目录结构

```
LunePaper/
├── backend/                  # FastAPI 后端
│   ├── main.py               #   入口 + CORS
│   ├── routes.py             #   REST API（上传 / 翻译 / 下载 / 缩略图）
│   ├── ws.py                 #   WebSocket 实时推送
│   ├── worker.py             #   翻译执行器（OCR → 翻译 → 推送）
│   └── task_manager.py       #   内存任务管理
│
├── infer/                    # 推理引擎
│   ├── llama_binding.py      #   llama.dll ctypes 封装
│   ├── mtmd_binding.py       #   mtmd.dll 多模态封装
│   ├── ocr.py                #   OCR 引擎 + 输出解析
│   ├── translate.py          #   基础翻译器
│   ├── translate_v2.py       #   增强翻译器（方向引导 + 回译 + 分块）
│   └── workflow.py           #   LangGraph 工作流（实验性）
│
├── frontend/                 # Web 前端
│   ├── src/
│   │   ├── App.tsx           #   主组件（上传 / 翻译 / 对照）
│   │   ├── api.ts            #   HTTP + WebSocket 客户端
│   │   ├── types.ts          #   TypeScript 类型定义
│   │   └── hooks/
│   │       └── useWebSocket.ts
│   ├── public/               #   静态资源（logo / 背景 / 角色）
│   └── package.json
│
├── assets/                   # README 展示素材
├── config.yaml               # 统一配置文件
├── config.py                 # 配置加载器
├── requirements.txt          # Python 依赖
└── NOTICE.md                 # 第三方开源 Attribution
```

<br>

---

<div align="center">

**月读 · LunePaper** — 让每一篇论文都能被读懂

<br>

<img src="assets/logo.jpg" width="40" height="40" style="border-radius:50%;vertical-align:middle;" />

*Apache 2.0 License*

</div>
