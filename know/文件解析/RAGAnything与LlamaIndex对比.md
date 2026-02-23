# DeepTutor RAG Pipeline 四大引擎对比

> DeepTutor 项目支持 **4 种 RAG Pipeline**，通过环境变量 `RAG_PROVIDER` 选择。它们在文档解析能力、索引结构、检索模式上各有特色。

---

## 一、四大 Pipeline 总览

| Pipeline | Provider 名称 | 核心引擎 | 一句话定位 |
|----------|-------------|----------|-----------|
| **RAGAnything (MinerU)** | `raganything` | LightRAG + MinerU 解析器 | 多模态学术文档处理，最全面（默认） |
| **RAGAnything (Docling)** | `raganything_docling` | LightRAG + Docling 解析器 | Office/HTML 友好，易安装 |
| **LightRAG** | `lightrag` | 纯 LightRAG | 纯文本知识图谱，速度适中 |
| **LlamaIndex** | `llamaindex` | llama-index 官方库 | 纯向量检索，最简单最快 |

---

## 二、架构对比

| 维度 | RAGAnything (MinerU) | RAGAnything (Docling) | LightRAG | LlamaIndex |
|------|---------------------|----------------------|----------|------------|
| **索引类型** | 向量 + 关键词 + 知识图谱 | 向量 + 关键词 + 知识图谱 | 向量 + 关键词 + 知识图谱 | 纯向量索引 |
| **文档解析** | MinerU（多模态：图表/公式/图片） | Docling（Office/HTML 友好） | PDFParser（提取纯文本） | PyMuPDF / 直接读文本 |
| **多模态** | ✅ 支持（图片/表格/公式） | ✅ 支持 | ❌ 纯文本 | ❌ 纯文本 |
| **知识图谱** | ✅ 有（实体关系抽取） | ✅ 有 | ✅ 有 | ❌ 无 |
| **分块策略** | MinerU 内部 + LightRAG 内部 | Docling 内部 + LightRAG 内部 | LightRAG 内部处理 | SentenceSplitter (512/50) |
| **存储目录** | `rag_storage/` | `rag_storage/` | `rag_storage/` | `llamaindex_storage/` |
| **处理速度** | 慢（最全面） | 中等 | 中等 (~10-15s/文档) | 快（最简单） |
| **编号条目提取** | ✅ 支持 | ✅ 支持 | ❌ | ❌ |

---

## 三、检索模式对比（核心差异）

### RAGAnything / LightRAG（三者共用 LightRAG 引擎）

`rag_search(query, mode=...)` 的 `mode` 参数**完全生效**，支持 4 种模式：

| 模式 | 检索方式 | 适用场景 |
|------|---------|---------|
| `naive` | 纯向量相似度搜索 | 精确定义、公式、术语查询 |
| `local` | 基于知识图谱的局部实体/关系检索 | 实体及其直接关系 |
| `global` | 基于知识图谱的全局社区摘要检索 | 宏观概念、主题总结 |
| `hybrid` | **向量 + 关键词 + 知识图谱** 多路融合 | 综合分析、跨概念对比 |

```python
# raganything.py - mode 直接传给 LightRAG
answer = await rag.aquery(query, mode=mode)

# lightrag retriever - 同理
query_param = QueryParam(mode=mode)
answer = await rag.aquery(query, param=query_param)
```

### LlamaIndex

`mode` 参数**被完全忽略**，始终走纯向量搜索：

```python
# llamaindex.py 第 233 行
# mode: Search mode (ignored, LlamaIndex uses similarity)

retriever = index.as_retriever(similarity_top_k=top_k)  # 固定 top_k=5
nodes = retriever.retrieve(query)  # 只有向量相似度
```

---

## 四、`rag_naive` vs `rag_hybrid` 实际行为

| 工具名称 | RAGAnything / LightRAG | LlamaIndex |
|----------|----------------------|------------|
| `rag_naive` | 纯向量搜索 | 纯向量搜索（top-5） |
| `rag_hybrid` | 向量 + 关键词 + 知识图谱混合 | **同样是纯向量搜索（top-5）** |
| `mode` 参数 | ✅ 生效，走不同检索路径 | ❌ 被忽略，行为一致 |
| 结果差异 | naive 快但单一；hybrid 全面但较慢 | 两者结果完全相同 |

> ⚠️ 在 LlamaIndex pipeline 下，`rag_naive` 和 `rag_hybrid` 返回的结果完全一致。

---

## 五、如何选择 Pipeline

| 场景 | 推荐 Pipeline | 原因 |
|------|-------------|------|
| 学术 PDF（含复杂公式/图表） | **RAGAnything (MinerU)** | MinerU 对学术文档解析最强 |
| Office 文档（.docx/.pptx）、HTML | **RAGAnything (Docling)** | Docling 对 Office 格式支持更好 |
| 纯文本文档、需要知识图谱 | **LightRAG** | 无需多模态，图谱检索速度适中 |
| 简单文档、快速原型 | **LlamaIndex** | 部署最简单，无需图谱基础设施 |
| 需要 `rag_hybrid` 真正生效 | **避免 LlamaIndex** | LlamaIndex 忽略 mode 参数 |

---

## 六、代码调用链路

```
rag_search(query, kb_name, mode)
    └── RAGService.search()
            └── factory.get_pipeline(provider)
                    ├── "raganything"  → RAGAnythingPipeline.search(mode=...)   ← mode 生效
                    ├── "raganything_docling" → RAGAnythingDoclingPipeline.search(mode=...)  ← mode 生效
                    ├── "lightrag"    → RAGPipeline → LightRAGRetriever.process(mode=...)  ← mode 生效
                    └── "llamaindex"  → LlamaIndexPipeline.search(mode=...)    ← mode 被忽略
```

Pipeline 的选择由环境变量 `RAG_PROVIDER` 决定，默认值为 `raganything`。

---

## 七、RAGAnything vs LightRAG 的区别

两者都基于 LightRAG 引擎做检索，核心区别在**文档解析阶段**：

| | RAGAnything | 纯 LightRAG |
|---|---|---|
| **解析器** | MinerU / Docling（多模态） | PDFParser（纯文本提取） |
| **图片处理** | ✅ 提取并存入 `images/` 目录 | ❌ 忽略 |
| **表格处理** | ✅ 结构化提取 | ❌ 忽略 |
| **公式处理** | ✅ LaTeX 提取 | ❌ 忽略 |
| **内容列表** | ✅ 保存 `content_list/*.json` | ❌ 无 |
| **编号条目** | ✅ 提取 `numbered_items.json` | ❌ 无 |
| **检索能力** | 完全相同（都用 LightRAG.aquery） | 完全相同 |

> 💡 简单来说：RAGAnything = **更强的文档解析** + LightRAG 检索引擎。如果你的文档是纯文本，用 LightRAG 就够了；如果有图表公式，用 RAGAnything。

---

## 八、关键源码位置

| 文件 | 说明 |
|------|------|
| [rag_tool.py](file:///Users/macbook/Desktop/shensi/DeepTutor/src/tools/rag_tool.py) | RAG 工具入口，`rag_search` 函数 |
| [service.py](file:///Users/macbook/Desktop/shensi/DeepTutor/src/services/rag/service.py) | RAGService，路由到不同 Pipeline |
| [factory.py](file:///Users/macbook/Desktop/shensi/DeepTutor/src/services/rag/factory.py) | Pipeline 工厂，注册 4 种 Pipeline |
| [raganything.py](file:///Users/macbook/Desktop/shensi/DeepTutor/src/services/rag/pipelines/raganything.py) | RAGAnything (MinerU) 实现 |
| [raganything_docling.py](file:///Users/macbook/Desktop/shensi/DeepTutor/src/services/rag/pipelines/raganything_docling.py) | RAGAnything (Docling) 实现 |
| [lightrag.py](file:///Users/macbook/Desktop/shensi/DeepTutor/src/services/rag/pipelines/lightrag.py) | 纯 LightRAG Pipeline 实现 |
| [llamaindex.py](file:///Users/macbook/Desktop/shensi/DeepTutor/src/services/rag/pipelines/llamaindex.py) | LlamaIndex Pipeline 实现 |
| [lightrag retriever](file:///Users/macbook/Desktop/shensi/DeepTutor/src/services/rag/components/retrievers/lightrag.py) | LightRAG 检索器（mode 生效） |
