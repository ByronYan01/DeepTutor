# RAGAnything + MinerU：扫描版 PDF 完整处理流程

> 以上传一本扫描版《JavaScript权威指南》中文版 PDF 为例，追踪从前端上传到最终知识图谱构建的每一步。

---

## 一、全局流程总览

```
用户上传 PDF
     │
     ▼
┌──────────────────────────────────────────────────────────┐
│  Phase 1: API 接收 & 文件落盘                             │
│  knowledge.py → DocumentValidator → raw/ 目录             │
│  💰 消耗：无                                              │
└──────────────────────┬───────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────┐
│  Phase 2: 文件分类路由                                    │
│  FileTypeRouter → 判断走 MinerU 还是纯文本                │
│  💰 消耗：无                                              │
└──────────────────────┬───────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────┐
│  Phase 3: MinerU 文档解析（OCR + 布局分析）               │
│  rag.parse_document() → content_list + 图片文件           │
│  💰 消耗：本地 GPU/CPU（PaddleOCR），不调大模型            │
└──────────────────────┬───────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────┐
│  Phase 4: 图片迁移 & 路径修正                             │
│  migrate_images_and_update_paths()                        │
│  💰 消耗：磁盘 I/O                                       │
└──────────────────────┬───────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────┐
│  Phase 5: 插入 LightRAG（知识图谱 + 向量索引）            │
│  rag.insert_content_list() → 分块 → 实体提取 → 向量化     │
│  💰 消耗：LLM API（实体提取）+ Embedding API（向量化）    │
└──────────────────────┬───────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────┐
│  Phase 6: 编号项提取 & 清理                               │
│  extract_numbered_items() + cleanup                       │
│  💰 消耗：LLM API（少量）                                 │
└──────────────────────────────────────────────────────────┘
```

---

## 二、Phase 1：API 接收 & 文件落盘

### 入口

**新建知识库 + 上传文件：**

```
POST /api/v1/knowledge/create
  ├─ name: "js"
  ├─ files: [扫描版.pdf]
  └─ rag_provider: "raganything"     ← 前端选择的 RAG 模式
```

**追加文件到已有知识库：**

```
POST /api/v1/knowledge/{kb_name}/upload
  ├─ files: [新文件.pdf]
  └─ rag_provider: 忽略（使用 KB 已有的 provider）
```

### 代码流程

```
src/api/routers/knowledge.py
│
├─ create_knowledge_base()           # 新建 KB
│   ├─ KnowledgeBaseManager.update_kb_status()   # 注册到 kb_config.json
│   ├─ KnowledgeBaseInitializer.create_directory_structure()
│   │   └─ 创建目录：raw/ images/ rag_storage/ content_list/
│   ├─ 保存上传文件到 raw/ 目录
│   └─ BackgroundTasks.add_task(run_initialization_task)  ← 异步后台执行
│
└─ upload_files()                    # 追加文件
    ├─ DocumentValidator.validate_upload_safety()   # 校验文件名/大小/类型
    ├─ 流式写入文件到 raw/（边读边检查大小，防止超限）
    └─ BackgroundTasks.add_task(run_upload_processing_task)  ← 异步后台执行
```

### 关键细节

- **文件大小限制**：PDF 最大 50MB，其他文件 100MB
- **文件名清洗**：移除路径穿越字符、控制字符、特殊符号
- **MIME 类型验证**：防止恶意文件伪装
- **异步处理**：API 立即返回，后台处理文件（用户通过 WebSocket 接收进度）

### 落盘后的目录结构

```
data/knowledge_bases/js/
├── raw/                    # 原始文件存放
│   └── JavaScript权威指南.pdf
├── images/                 # 图片存放（Phase 4 填充）
├── content_list/           # 解析结果（Phase 3 填充）
├── rag_storage/            # LightRAG 存储（Phase 5 填充）
├── metadata.json           # 元数据（provider、file_hashes 等）
└── numbered_items.json     # 编号项（Phase 6 填充）
```

---

## 三、Phase 2：文件分类路由

### 入口

```python
# src/services/rag/components/routing.py
classification = FileTypeRouter.classify_files(file_paths)
# → classification.needs_mineru = ["JavaScript权威指南.pdf"]  # PDF → MinerU
# → classification.text_files = []
# → classification.unsupported = []
```

### 路由规则

| 文件类型 | 扩展名 | 路由目标 | 处理方式 |
|---------|--------|---------|---------|
| **PDF** | `.pdf` | `needs_mineru` | MinerU 完整解析 |
| **Word** | `.docx` `.doc` | `needs_mineru` | MinerU 解析 |
| **图片** | `.png` `.jpg` 等 | `needs_mineru` | MinerU OCR |
| **纯文本** | `.txt` `.md` `.py` 等 | `text_files` | 直接读取文本 |
| **其他** | 未知扩展名 | 先尝试 UTF-8 检测 | 能读就当文本，否则 `unsupported` |

### 两条处理路径

```
                    FileTypeRouter
                    /           \
              needs_mineru      text_files
              /                       \
    MinerU 完整解析流程           直接读取文本
    (Phase 3-4-5)               → rag.lightrag.ainsert(content)
                                跳过 MinerU，直接入图谱
```

> **扫描版 PDF 走左边的 MinerU 路径。** 这是处理最重的路径，但也是唯一能处理扫描版的路径。

---

## 四、Phase 3：MinerU 文档解析

这是整个流程中**最耗时**的环节（对扫描版可能要几十分钟），但**不消耗大模型 API**。

### 调用入口

```python
# src/services/rag/pipelines/raganything.py:180-184
content_list, doc_id = await rag.parse_document(
    file_path=file_path,
    output_dir=str(content_list_dir),
    parse_method="auto",       # auto = 自动检测是扫描版还是原生 PDF
)
```

### MinerU 内部处理（`raganything` 库）

`parse_document()` 是 RAGAnything 库提供的方法，内部调用 MinerU 命令行工具。

```
MinerU 处理流程（本地执行，不联网）
│
├─ 1. PDF 类型检测
│   ├─ parse_method="auto" → 自动判断
│   ├─ parse_method="ocr"  → 强制 OCR 模式（扫描版推荐）
│   └─ parse_method="txt"  → 强制文本提取（原生 PDF 推荐）
│
├─ 2. 页面布局分析（LayoutLMv3 模型）
│   └─ 检测每页中的：文本区域、图片区域、表格区域、公式区域
│
├─ 3. OCR 文字识别（PaddleOCR）       ← 扫描版的核心步骤
│   ├─ 对每个文本区域执行 OCR
│   ├─ 支持中文、英文、多语言
│   └─ 输出：识别出的文字 + 位置坐标
│
├─ 4. 表格识别（Table Transformer）
│   ├─ 检测表格结构（行/列/单元格）
│   └─ 输出：结构化表格数据
│
├─ 5. 公式识别（UniMERNet / LaTeX-OCR）
│   ├─ 数学公式区域 → LaTeX 文本
│   └─ 输出：$E = mc^2$ 形式的 LaTeX
│
├─ 6. 图片提取
│   ├─ 从 PDF 页面中裁剪出图片区域
│   └─ 保存为独立的 .png/.jpg 文件
│
└─ 7. 生成 content_list（JSON 格式）
    └─ 按页面顺序排列的内容项列表
```

### content_list 输出格式

MinerU 的输出是一个 JSON 数组，每个元素代表 PDF 中的一个内容块：

```json
[
    {
        "type": "text",
        "text": "第7章 数组\n\n数组是值的有序集合...",
        "page_idx": 0
    },
    {
        "type": "image",
        "img_path": "content_list/JavaScript权威指南/auto/images/img_0_1.png",
        "page_idx": 1
    },
    {
        "type": "table",
        "text": "| 方法 | 描述 | 返回值 |\n|---|---|---|\n| push() | 末尾添加 | 新长度 |",
        "page_idx": 5
    },
    {
        "type": "equation",
        "text": "$O(n \\log n)$",
        "page_idx": 10
    }
]
```

### 输出文件位置

```
data/knowledge_bases/js/content_list/
├── JavaScript权威指南/           # MinerU 临时输出目录
│   └── auto/                    # parse_method="auto" 的输出
│       ├── images/              # 提取的图片
│       │   ├── img_0_1.png
│       │   ├── img_0_2.png
│       │   └── ...
│       └── JavaScript权威指南.json   # content_list
└── (Phase 4 后) JavaScript权威指南.json  # 路径修正后的最终版
```

### 关键：OCR 不消耗大模型

| 组件 | 模型 | 运行位置 | API 调用 |
|------|------|---------|---------|
| PaddleOCR | PP-OCRv4 | **本地 GPU/CPU** | 无 |
| 布局检测 | LayoutLMv3 | **本地 GPU/CPU** | 无 |
| 表格识别 | Table Transformer | **本地 GPU/CPU** | 无 |
| 公式识别 | UniMERNet | **本地 GPU/CPU** | 无 |

> **整个 Phase 3 零 API 消耗**，但对本地算力要求较高。没有 GPU 时 CPU 也能跑，只是更慢。

---

## 五、Phase 4：图片迁移 & 路径修正

### 为什么需要这一步？

MinerU 输出图片到临时嵌套目录 `content_list/文档名/auto/images/`，但后续 RAG 检索时需要从 `kb/images/` 读取。如果先入库再迁移，RAG 里存的路径就错了。

**所以必须在入库前迁移图片、更新路径。**

### 代码流程

```python
# src/services/rag/pipelines/raganything.py:186-193
# Step 2: Migrate images and update paths
updated_content_list, num_migrated = await migrate_images_and_update_paths(
    content_list=content_list,           # MinerU 输出的 content_list
    source_base_dir=content_list_dir,    # content_list/ 目录
    target_images_dir=images_dir,        # kb/images/ 目录
    batch_size=50,                       # 每批处理 50 张
)
```

### 迁移逻辑

```python
# src/services/rag/utils/image_migration.py

# 1. 扫描 content_list 中所有包含 img_path 的项
# 2. 将图片从临时目录复制到 kb/images/
# 3. 处理文件名冲突（同名不同内容 → 加后缀 _1, _2...）
# 4. 更新 content_list 中的路径引用
# 5. 并发控制：最多 10 个并发文件操作
```

### 迁移前后对比

```
迁移前（MinerU 输出的路径）:
  "img_path": "content_list/JavaScript权威指南/auto/images/img_0_1.png"

迁移后（规范化路径）:
  "img_path": "/Users/.../data/knowledge_bases/js/images/img_0_1.png"
```

### 保存修正后的 content_list

```python
# src/services/rag/pipelines/raganything.py:197-199
content_list_file = content_list_dir / f"{Path(file_path).stem}.json"
with open(content_list_file, "w", encoding="utf-8") as f:
    json.dump(updated_content_list, f, ensure_ascii=False, indent=2)
```

最终文件：`content_list/JavaScript权威指南.json`（路径已修正的最终版本）

---

## 六、Phase 5：插入 LightRAG

这是**消耗大模型 API 最多**的环节。

### 调用入口

```python
# src/services/rag/pipelines/raganything.py:201-207
# Step 3: Insert into RAG with corrected paths
await rag.insert_content_list(
    content_list=updated_content_list,   # 路径已修正的 content_list
    file_path=file_path,                 # 原始 PDF 路径
    doc_id=doc_id,                       # 文档唯一 ID
)
```

### LightRAG 内部处理

`insert_content_list()` 是 RAGAnything 库提供的方法，内部调用 LightRAG 的核心功能：

```
insert_content_list()
│
├─ 1. 文本提取 & 拼接
│   ├─ 遍历 content_list 中的所有 text 项
│   ├─ 拼接成完整的纯文本文档
│   └─ 图片项 → 调用 Vision LLM 生成图片描述文本 💰
│
├─ 2. 文本分块（Chunking）
│   ├─ 按 token 数切分（默认 1200 tokens/chunk，100 tokens 重叠）
│   └─ 输出：text_chunks[] 列表
│
├─ 3. 实体 & 关系提取 💰💰💰（最贵的步骤）
│   ├─ 对每个 chunk 调用 LLM 提取实体和关系
│   ├─ Prompt: "从以下文本中提取所有实体和关系..."
│   ├─ LLM 返回：
│   │   实体: [("Array", "CONCEPT"), ("push()", "METHOD"), ...]
│   │   关系: [("Array", "has_method", "push()"), ...]
│   ├─ entity_extract_max_gleaning: 反复精炼次数（默认 1）
│   └─ enable_llm_cache_for_entity_extract: 启用缓存避免重复调用
│
├─ 4. 图谱合并（Merge）
│   ├─ 新提取的实体/关系 → 与已有图谱合并
│   ├─ 同名实体 → 合并描述（可能再调 LLM 做摘要）💰
│   └─ 去重、消歧
│
├─ 5. 向量嵌入（Embedding）
│   ├─ 每个 chunk → Embedding API → 向量 💰（便宜）
│   ├─ 每个实体 → Embedding API → 向量
│   ├─ 每个关系 → Embedding API → 向量
│   └─ 存入向量数据库（默认 FAISS 文件）
│
└─ 6. 持久化存储
    ├─ rag_storage/kv_store_text_chunks.json      # 文本块
    ├─ rag_storage/kv_store_full_entities.json     # 实体
    ├─ rag_storage/kv_store_full_relations.json    # 关系
    ├─ rag_storage/vdb_chunks.json                 # chunk 向量索引
    ├─ rag_storage/vdb_entities.json               # 实体向量索引
    ├─ rag_storage/vdb_relationships.json          # 关系向量索引
    └─ rag_storage/graph_chunk_entity_relation.graphml  # 图谱文件
```

### 各步骤的资源消耗

假设一本 700 页的扫描版 PDF，OCR 后得到约 50 万字，切成 ~500 个 chunk：

| 步骤 | 调用什么 | 次数 | 单次 Token | 总消耗 |
|------|---------|------|-----------|--------|
| 图片描述 | Vision LLM | ~50 张图 | ~500 token | ~25K token |
| **实体提取** | **LLM** | **~500 chunk** | **~2000 token** | **~1M token** |
| 实体合并摘要 | LLM | ~200 次 | ~500 token | ~100K token |
| 向量嵌入 | Embedding | ~2000 次 | ~200 token | ~400K token |

> **实体提取是 token 消耗大户**，占总消耗的 ~80%。
> 用 GPT-4o-mini 约 $0.15-0.30，用 GPT-4o 约 $2.50-5.00。

---

## 七、Phase 6：编号项提取 & 清理

### 编号项提取

从 content_list 中提取有编号的学术项（定义、定理、图表编号等），方便后续精确引用。

```python
# src/services/rag/pipelines/raganything.py:231-232
if extract_numbered_items:
    await self._extract_numbered_items(kb_name)
```

对技术书籍来说，这会提取类似：
- `Figure 7-1: Array methods overview`
- `Table 3-2: JavaScript operators`
- `Example 6-1: Closure demonstration`

### 清理临时目录

```python
# 清理 MinerU 的临时输出目录
await cleanup_parser_output_dirs(content_list_dir)
# 删除 content_list/JavaScript权威指南/auto/ 目录
# 保留 content_list/JavaScript权威指南.json 最终文件
```

---

## 八、最终知识库目录结构

```
data/knowledge_bases/js/
├── raw/
│   └── JavaScript权威指南.pdf                      # 原始扫描版 PDF
├── images/
│   ├── img_0_1.png                                # 迁移后的图片
│   ├── img_0_2.png
│   └── ...
├── content_list/
│   └── JavaScript权威指南.json                     # MinerU 解析结果（路径已修正）
├── rag_storage/
│   ├── kv_store_text_chunks.json                  # 文本块存储
│   ├── kv_store_full_entities.json                # 实体存储
│   ├── kv_store_full_relations.json               # 关系存储
│   ├── vdb_chunks.json                            # chunk 向量索引
│   ├── vdb_entities.json                          # 实体向量索引
│   ├── vdb_relationships.json                     # 关系向量索引
│   ├── graph_chunk_entity_relation.graphml        # 知识图谱
│   └── kv_store_doc_status.json                   # 文档处理状态
├── metadata.json                                  # 元数据
│   {
│     "name": "js",
│     "rag_provider": "raganything",
│     "file_hashes": { "JavaScript权威指南.pdf": "sha256..." }
│   }
└── numbered_items.json                            # 编号项索引
```

---

## 九、代码调用链总结（一图看完）

```
前端上传
  │
  ▼
knowledge.py: create_knowledge_base()              [API 层]
  │  保存文件到 raw/，注册 KB
  │  启动 BackgroundTask
  ▼
knowledge.py: run_initialization_task()            [后台任务]
  │
  ▼
initializer.py: KnowledgeBaseInitializer
  ├── create_directory_structure()                 [创建目录]
  ├── process_documents()                          [核心处理]
  │     │
  │     ▼
  │   service.py: RAGService.initialize()          [RAG 服务入口]
  │     │
  │     ▼
  │   factory.py: get_pipeline("raganything")      [工厂获取 Pipeline]
  │     │
  │     ▼
  │   raganything.py: RAGAnythingPipeline.initialize()  [Pipeline 执行]
  │     │
  │     ├─ FileTypeRouter.classify_files()         [Phase 2: 文件分类]
  │     │
  │     ├─ rag.parse_document()                    [Phase 3: MinerU OCR]
  │     │   └─ (raganything 库 → MinerU 命令行)
  │     │
  │     ├─ migrate_images_and_update_paths()       [Phase 4: 图片迁移]
  │     │   └─ (image_migration.py)
  │     │
  │     ├─ rag.insert_content_list()               [Phase 5: LightRAG 入库]
  │     │   ├─ 分块
  │     │   ├─ LLM 实体提取 💰
  │     │   ├─ Embedding 向量化
  │     │   └─ 持久化存储
  │     │
  │     └─ cleanup_parser_output_dirs()            [清理临时文件]
  │
  ├── extract_numbered_items()                     [Phase 6: 编号项提取]
  └── display_statistics_generic()                 [统计信息]
```

---

## 十、关键源码文件索引

| 文件 | 职责 |
|------|------|
| `src/api/routers/knowledge.py` | API 入口，文件上传、KB 创建 |
| `src/utils/document_validator.py` | 文件校验（大小、类型、安全性） |
| `src/knowledge/initializer.py` | KB 初始化编排（目录创建 → 处理 → 统计） |
| `src/knowledge/add_documents.py` | 增量添加文档（带去重） |
| `src/services/rag/service.py` | RAG 服务统一入口 |
| `src/services/rag/factory.py` | Pipeline 工厂（根据 provider 创建实例） |
| `src/services/rag/pipelines/raganything.py` | RAGAnything Pipeline 核心（MinerU 版） |
| `src/services/rag/components/routing.py` | 文件类型路由（分类到不同处理路径） |
| `src/services/rag/utils/image_migration.py` | 图片迁移工具 |
| `src/knowledge/extract_numbered_items.py` | 编号项提取 |
| `src/knowledge/progress_tracker.py` | 进度追踪（WebSocket 推送给前端） |

---

## 十一、常见问题

### Q: 扫描版 PDF 应该用什么 parse_method？

**`auto` 通常够用**（MinerU 自动检测扫描版并启用 OCR）。如果自动检测不准，可改为 `ocr` 强制走 OCR。

### Q: 处理一本 700 页的书要多久？

- **MinerU OCR**：~30-60 分钟（取决于 GPU/CPU 性能）
- **LightRAG 入库**：~10-20 分钟（取决于 LLM API 速度）
- **总计**：约 1-2 小时

### Q: 能不能只做 OCR 不建知识图谱？

当前不支持。LightRAG 插入时必定执行实体提取。变通方案：
1. 用 MinerU 命令行单独 OCR → 导出文本 → 用 LlamaIndex 模式入库（纯向量）
2. 设置 `entity_extract_max_gleaning=0` 减少精炼次数（省一些，但不能完全跳过）

### Q: 中途失败了怎么办？

- 已上传的文件在 `raw/` 中保留，不会丢失
- `metadata.json` 中记录了 `file_hashes`，重新处理时自动跳过已完成的文件
- LightRAG 有 checkpoint 机制，可以从中断处继续
