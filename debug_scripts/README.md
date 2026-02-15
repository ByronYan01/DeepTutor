# RAG 链路 Debug 脚本

按 DeepTutor 聊天 RAG 链路的 5 个关键环节，每个环节一个独立可运行的 Python 脚本。

## 使用方法

在项目根目录执行，例如：
```bash
python debug_scripts/01_check_kb.py --kb 22
```

## 脚本列表

| 脚本 | 环节 | 说明 |
|------|------|------|
| `01_check_kb.py` | 知识库元数据 | 检查 KB 目录结构、metadata.json、各存储目录状态 |
| `02_test_llamaindex_retrieval.py` | LlamaIndex 检索 | 直接调用 LlamaIndexPipeline.search()，验证向量检索是否正常 |
| `03_test_rag_service.py` | RAGService 路由 | 测试 provider 解析逻辑，验证是否正确路由到对应 pipeline |
| `04_test_chat_agent.py` | ChatAgent 上下文构建 | 测试 retrieve_context + build_messages，查看发给 LLM 的完整 prompt |
| `05_test_websocket_msg.py` | WebSocket 消息 | 模拟前端 WebSocket 消息，验证 kb_name/enable_rag 是否正确传递 |

## 排查发现的根因

日志 `deeptutor_20260214.log` 第 729-730 行：
```
[RAGService] No provider in metadata, using instance provider: raganything
[RAGService] Searching KB 'yl' with provider 'raganything' ...
```

**问题：前端发送的 `kb_name` 是 `"yl"`（旧知识库）而非 `"22"`（新上传的知识库）。**
- KB `"yl"` 没有 LlamaIndex 索引，其 `rag_storage/` 也为空 → LightRAG 搜索返回 0 结果
- LLM 没有任何参考上下文，只能凭自身知识生成泛泛回答

**修复：在前端确认 RAG 开关已开启，且知识库下拉框选中了 `"22"`。**
