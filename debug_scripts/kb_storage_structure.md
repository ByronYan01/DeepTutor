# 知识库存储文件结构

> 本文档记录 DeepTutor 各 RAG provider 在知识库目录下生成的存储文件及其作用。
> 以 `data/knowledge_bases/<kb_name>/` 为根目录。

---

## 通用文件（所有 provider 共有）

| 文件/目录        | 说明                                                                                                                         |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `metadata.json`  | 知识库元信息：名称、创建时间、`rag_provider`、文件哈希等。**RAGService 通过此文件的 `rag_provider` 字段决定用哪个 pipeline** |
| `.progress.json` | 构建进度：stage、percent、timestamp 等                                                                                       |
| `raw/`           | 用户上传的原始文件（.md、.pdf 等）                                                                                           |
| `content_list/`  | 文件内容清单（部分 provider 使用）                                                                                           |
| `images/`        | 提取的图片（部分 provider 使用）                                                                                             |

---

## LlamaIndex（`rag_provider: "llamaindex"`）

存储目录：`llamaindex_storage/`

以 KB "22" 为例（3 个短文档：员工手册.md、组织架构.md、项目列表.md）：

### 文件清单

| 文件                         | 大小    | 说明                                                    |
| ---------------------------- | ------- | ------------------------------------------------------- |
| `docstore.json`              | ~5 KB   | 文档存储：原始文档和 chunk 的文本内容、元信息           |
| `default__vector_store.json` | ~278 KB | 向量存储：每个 chunk 的 embedding 向量（占存储大头）    |
| `index_store.json`           | ~0.5 KB | 索引元数据：index 类型、包含哪些 node                   |
| `graph_store.json`           | ~18 B   | 图存储：LlamaIndex 默认创建，当前为空（未使用知识图谱） |
| `image__vector_store.json`   | ~72 B   | 图片向量存储：LlamaIndex 默认创建，当前为空（无图片）   |

### docstore.json 详解

包含三个子字典：

#### `docstore/ref_doc_info` — 原始文档索引

记录每个原始文件对应一个 doc_id，以及它被切分成了哪些 chunk。

```
doc_id: ea46a563-...  →  file_name: "员工手册.md"
    node_ids: ["e2ab5288-..."]     ← 该文档被切成的 chunk ID 列表

doc_id: af200928-...  →  file_name: "组织架构.md"
    node_ids: ["937ef019-..."]

doc_id: cb98169f-...  →  file_name: "项目列表.md"
    node_ids: ["f884c154-..."]
```

关系：**1 个原始文档 → N 个 chunk 节点**（本例每个文档只有 1 个 chunk，因为文档很短）

#### `docstore/metadata` — 节点元信息

存储所有节点（原始文档 + chunk）的 hash 和关联关系。

- 原始文档节点：有 `doc_hash`，无 `ref_doc_id`
- Chunk 节点：有 `doc_hash` + `ref_doc_id`（指向所属的原始文档）

```
chunk e2ab5288-... → ref_doc_id: ea46a563-... (员工手册.md)
chunk 937ef019-... → ref_doc_id: af200928-... (组织架构.md)
chunk f884c154-... → ref_doc_id: cb98169f-... (项目列表.md)
```

#### `docstore/data` — chunk 文本内容

存储每个 chunk 的实际文本和来源文件信息。

```
node e2ab5288-...:
    file: "员工手册.md"
    text: "所有使用 NVIDIA A100 GPU 的项目，必须由**基础设施团队**审批。"

node 937ef019-...:
    file: "组织架构.md"
    text: "**基础设施团队**的负责人是**张三**，联系邮箱 zhangsan@company.com。"

node f884c154-...:
    file: "项目列表.md"
    text: "**项目 Phoenix** 使用了 NVIDIA A100 GPU 集群进行大模型训练。"
```

### default\_\_vector_store.json 详解

包含三个子字典，key 都是 chunk 的 node_id：

| 字段                    | 说明                                                                                                                                                             |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `embedding_dict`        | **核心**：每个 chunk 的向量嵌入（float 数组）。本例使用 Qwen3-Embedding-8B 模型，维度 4096，所以每个 chunk 对应一个 4096 维的 float 数组。这是文件体积最大的部分 |
| `text_id_to_ref_doc_id` | chunk node_id → 原始文档 doc_id 的映射（和 docstore 中的关系一致）                                                                                               |
| `metadata_dict`         | 每个 chunk 的元数据（file_path、file_name、file_type 等），检索时可用于过滤或展示来源                                                                            |

### index_store.json 详解

记录 index 本身的结构信息：

| 字段              | 说明                                              |
| ----------------- | ------------------------------------------------- |
| `index_id`        | 索引的唯一 ID                                     |
| `__type__`        | 索引类型（`vector_store` 表示 VectorStoreIndex）  |
| `nodes_dict`      | index 管理的所有 chunk node_id 列表               |
| `doc_id_dict`     | 原始文档 doc_id → 对应 chunk node_id 的映射       |
| `embeddings_dict` | 空（向量存储在 vector_store.json 中，这里不重复） |

### 数据关系图

```
原始文件 (raw/)
    员工手册.md ──┐
    组织架构.md ──┤  上传 & 切分
    项目列表.md ──┘
         │
         ▼
docstore.json
    ref_doc_info:  doc_id ←──→ file_name, [chunk_node_ids]
    metadata:      node_id ←──→ doc_hash, ref_doc_id
    data:          node_id ←──→ text, metadata
         │
         │  每个 chunk 计算 embedding
         ▼
default__vector_store.json
    embedding_dict:         node_id → float[4096]  (向量)
    text_id_to_ref_doc_id:  node_id → doc_id       (溯源)
    metadata_dict:          node_id → {file_name, file_path, ...}
         │
         │  检索时
         ▼
index_store.json
    VectorStoreIndex 管理所有 node，
    query → embedding → 余弦相似度 → Top-K nodes → 返回文本
```

### 检索流程（对应源码 `llamaindex.py:254-262`）

```
1. StorageContext.from_defaults(persist_dir)
   → 从磁盘加载 docstore + vector_store + index_store 到内存

2. load_index_from_storage(storage_context)
   → 重建 VectorStoreIndex 对象

3. index.as_retriever(similarity_top_k=5)
   → 创建 VectorIndexRetriever

4. retriever.retrieve(query)
   → query 经 embedding 模型转为向量
   → 在 embedding_dict 中做余弦相似度搜索
   → 返回 Top-K 个 NodeWithScore (包含 .node.text 和 .score)
```

---

## LightRAG（`rag_provider: "lightrag"`）

存储目录：`rag_storage/`

> TODO: 待补充

---

## RAGAnything（`rag_provider: "raganything"`）

存储目录：`rag_storage/`（与 LightRAG 共用，RAGAnything 基于 LightRAG 扩展）

> TODO: 待补充

---

## RAGAnything Docling（`rag_provider: "raganything_docling"`）

存储目录：`rag_storage/`

> TODO: 待补充

---

## 聊天会话存储

存储文件：`data/user/chat_sessions.json`

由 `SessionManager`（`src/agents/chat/session_manager.py`）管理，用于持久化聊天对话记录。

### 文件结构

```json
{
  "version": "1.0",
  "sessions": [
    {
      "session_id": "chat_1739520000000_a1b2c3d4",
      "title": "项目 Phoenix 的 GPU 资源审批应该找谁？...",
      "messages": [
        {
          "role": "user",
          "content": "项目 Phoenix 的 GPU 资源审批应该找谁？",
          "timestamp": 1739520001
        },
        {
          "role": "assistant",
          "content": "根据知识库信息，GPU 资源审批需要联系基础设施团队负责人张三...",
          "timestamp": 1739520005,
          "sources": {
            "rag": [{ "kb_name": "22", "content": "..." }],
            "web": []
          }
        }
      ],
      "settings": {
        "kb_name": "22",
        "enable_rag": true,
        "enable_web_search": false
      },
      "created_at": 1739520000,
      "updated_at": 1739520005
    }
  ]
}
```

### 字段说明

| 字段         | 说明                                                                                                |
| ------------ | --------------------------------------------------------------------------------------------------- |
| `session_id` | 唯一 ID，格式：`chat_{毫秒时间戳}_{8位随机hex}`                                                     |
| `title`      | 会话标题，取自第一条用户消息的前 50 字符                                                            |
| `messages`   | 消息列表，每条包含 `role`（user/assistant）、`content`、`timestamp`，assistant 消息可附带 `sources` |
| `settings`   | 该会话使用的 RAG/Web 设置                                                                           |
| `created_at` | 创建时间（Unix 时间戳）                                                                             |
| `updated_at` | 最后更新时间                                                                                        |

### 管理规则

- 最多保留 **100** 个会话，超出自动丢弃最旧的
- 新建/更新的会话会移到列表最前面（最近活跃排前）
- `list_sessions()` 默认不返回完整 messages，只返回摘要（标题、消息数、最后一条消息预览）

### 在 API 路由中的调用顺序

```
WebSocket 收到消息
  ① create_session() / get_session()   ← 获取或创建会话
  ② add_message(role="user")           ← 保存用户消息
  ③ agent.process(stream=True)         ← LLM 生成回答
  ④ add_message(role="assistant")      ← 保存助手回答
```
