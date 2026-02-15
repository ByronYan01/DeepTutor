# DeepTutor 源码学习计划

> 以 ChatAgent 为起点，逐步扩展到全部 Agent 和数据处理流程

---

## 第一阶段：ChatAgent 完整链路 ✅

- [x] 01 — 知识库文件存储结构
- [x] 02 — LlamaIndex 向量检索
- [x] 03 — RAG Service 工具层（rag_search）
- [x] 04 — ChatAgent.retrieve_context + build_messages
- [x] 05 — 端到端 WebSocket 调用
- [x] SessionManager 会话管理
- [x] BaseAgent 基础设施层（配置、Prompt、LLM 调用、Token 追踪、日志）
- [x] FastAPI WebSocket 路由层（chat.py）
- [x] 流式传输机制（generator + async for + 事件循环）

---

## 第二阶段：Co-Writer 协作写作（2 个 Agent）

- [x] edit_agent — 编辑 Agent
- [x] narrator_agent — 叙述 Agent
- [x] 两个 Agent 之间的协作模式
- [x] 顺带了解：`services/llm/` LLM 工厂和 cloud/local provider

---

## 第三阶段：Guide 引导式学习（4 个 Agent）

- [ ] locate_agent — 定位 Agent（定位学习内容在文档中的位置）
- [ ] interactive_agent — 互动 Agent（生成引导式问题）
- [ ] summary_agent — 总结 Agent
- [ ] chat_agent — Guide 模块的对话 Agent（与 ChatAgent 的区别）
- [ ] 4 个 Agent 的流水线协作方式
- [ ] 顺带了解：`services/prompt/` PromptManager

---

## 第四阶段：Question 题目生成（2 个 Agent）

- [ ] generate_agent — 题目生成
- [ ] retrieve_agent — 题目检索
- [ ] 与 RAG 的关系
- [ ] 顺带了解：LightRAG pipeline（补充 LlamaIndex 之外的 RAG 方案）

---

## 第五阶段：IdeaGen 素材整理（1 个 Agent）

- [ ] material_organizer_agent — 素材整理 Agent

---

## 第六阶段：Research 深度研究（6 个 Agent）

- [ ] manager_agent — 研究管理器（调度中心）
- [ ] decompose_agent — 任务分解
- [ ] research_agent — 执行研究
- [ ] rephrase_agent — 查询改写
- [ ] note_agent — 研究笔记
- [ ] reporting_agent — 报告生成
- [ ] 多 Agent 协作调度模式

---

## 第七阶段：Solve 问题求解（5 个 Agent）

- [ ] analysis_loop/investigate_agent — 调查分析
- [ ] analysis_loop/note_agent — 分析笔记
- [ ] solve_loop/manager_agent — 求解管理器
- [ ] solve_loop/solve_agent — 求解执行
- [ ] solve_loop/tool_agent — 工具调用
- [ ] solve_loop/precision_answer_agent — 精确回答
- [ ] solve_loop/response_agent — 最终响应
- [ ] 双循环架构（analysis_loop + solve_loop）

---

## 第八阶段：文件上传与数据处理

- [ ] 文件上传 API（上传入口）
- [ ] 文档解析（PDF/MD/DOCX 等格式处理）
- [ ] 文本切分（chunking 策略）
- [ ] Embedding 向量化
- [ ] 知识库构建流程（LlamaIndex / LightRAG / RAGAnything）
- [ ] 构建进度管理（.progress.json）

---

## 支撑层（穿插学习）

| 支撑层              | 位置                      | 建议阶段   |
| ------------------- | ------------------------- | ---------- |
| LLM 工厂 + Provider | `services/llm/`           | 第二阶段   |
| PromptManager       | `services/prompt/`        | 第三阶段   |
| LightRAG Pipeline   | `services/rag/pipelines/` | 第四阶段   |
| 配置管理            | `services/config/`        | 已基本了解 |
| 日志系统            | `src/logging/`            | 按需       |
| 前端交互            | `web/`                    | 按需       |

---

## 学习产出

| 文件                                    | 状态   |
| --------------------------------------- | ------ |
| `know/DeepTutor源码学习文档.md`         | ✅     |
| `know/Python与JS语法对照速查.md`        | ✅     |
| `know/agent/BaseAgent基础设施层.md`     | ✅     |
| `know/生产环境存储层改造方向.md`        | ✅     |
| `debug_scripts/kb_storage_structure.md` | ✅     |
| `debug_scripts/01-05 调试脚本`          | ✅     |
| `know/agent/CoWriter.md`                | ✅     |
| `know/agent/Guide.md`                   | ✅     |
| `know/agent/Question.md`                | 待创建 |
| `know/agent/Research.md`                | 待创建 |
| `know/agent/Solve.md`                   | 待创建 |
