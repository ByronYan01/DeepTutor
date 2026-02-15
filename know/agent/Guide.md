# Guide 引导式学习模块源码分析

> 第三阶段学习产出，基于 `src/agents/guide/` 源码

---

## 模块概览

Guide 是 DeepTutor 的**引导式学习**模块，提供 4 个 Agent + 1 个管理器：

| Agent | 类 | 功能 |
|-------|-----|------|
| **LocateAgent** | `agents/locate_agent.py` | 分析笔记本内容，提取知识点，生成递进式学习计划 |
| **InteractiveAgent** | `agents/interactive_agent.py` | 将知识点转化为可交互的 HTML 学习页面 |
| **ChatAgent** | `agents/chat_agent.py` | 在学习特定知识点时回答用户提问 |
| **SummaryAgent** | `agents/summary_agent.py` | 学习完成后生成个性化学习总结报告 |
| **GuideManager** | `guide_manager.py` | 会话管理 + 4 个 Agent 的流水线调度 |

协作模式是**有状态的流水线**（Stateful Pipeline）：
```
笔记本记录 → LocateAgent 提取知识点
  → InteractiveAgent 生成 HTML（逐个知识点）
  → ChatAgent 回答问题（学习过程中）
  → SummaryAgent 生成总结（全部完成后）
```

---

## 架构图

```
前端 (web/app/guide/)
    ↓ HTTP POST / WebSocket
FastAPI Router (src/api/routers/guide.py)
    ├── POST /create_session  → manager.create_session()
    ├── POST /start           → manager.start_learning()
    ├── POST /next            → manager.next_knowledge()
    ├── POST /chat            → manager.chat()
    ├── POST /fix_html        → manager.fix_html()
    ├── GET  /session/{id}    → manager.get_session()
    ├── GET  /session/{id}/html → manager.get_current_html()
    └── WS  /ws/{session_id}  → 实时交互（start/next/chat/fix_html）
    ↓
GuideManager (src/agents/guide/guide_manager.py)
    ├── create_session()  → LocateAgent.process()
    ├── start_learning()  → InteractiveAgent.process()
    ├── chat()            → ChatAgent.process()
    ├── next_knowledge()  → InteractiveAgent.process() / SummaryAgent.process()
    ├── fix_html()        → InteractiveAgent.process(retry_with_bug=...)
    ├── _save_session()   → JSON 文件持久化
    └── _load_session()   → JSON 文件加载
    ↓
4 个 Agent (src/agents/guide/agents/)
    ├── LocateAgent(BaseAgent)
    ├── InteractiveAgent(BaseAgent)
    ├── ChatAgent(BaseAgent)
    └── SummaryAgent(BaseAgent)
    ↓
BaseAgent (src/agents/base_agent.py)
    ├── call_llm()   → LLM Factory
    ├── get_prompt()  → PromptManager
    └── _track_tokens() → LLMStats
```

---

## 会话状态机

Guide 模块围绕 `GuidedSession` 数据类运行，有明确的状态流转：

```
initialized → learning → completed
     ↑            │
     │     chat() 不改变状态
     │     next_knowledge() 推进索引
     │            │
     │            ↓ (所有知识点学完)
     └── completed
```

### GuidedSession 数据结构

```python
@dataclass
class GuidedSession:
    session_id:       str              # uuid[:8]
    notebook_id:      str              # 笔记本 ID
    notebook_name:    str              # 笔记本名称
    created_at:       float            # 创建时间戳
    knowledge_points: list[dict]       # 知识点列表（LocateAgent 输出）
    current_index:    int              # 当前知识点索引
    chat_history:     list[dict]       # 完整对话历史（含 knowledge_index 标记）
    status:           str              # initialized / learning / completed
    current_html:     str              # 当前交互式 HTML 页面
    summary:          str              # 学习总结（completed 后填充）
```

### 对话历史中的 knowledge_index 标记

每条对话记录都附带 `knowledge_index`，标记该对话属于哪个知识点：

```python
{
    "role": "user",            # user / assistant / system
    "content": "...",
    "knowledge_index": 0,      # 学习第几个知识点时的对话
    "timestamp": 1234567890.0
}
```

这样 ChatAgent 可以只取当前知识点的历史，SummaryAgent 可以按知识点分组分析。

---

## LocateAgent 详解

### 职责

分析笔记本中的学习记录，提取核心知识点，生成递进式学习计划。

### process() 流程

```
process(notebook_id, notebook_name, records)
    │
    ├── _format_records(records)
    │     → 将每条记录格式化为可读文本
    │     → 截断过长内容（>2000 chars）
    │
    ├── get_prompt("system")  # 学习规划师角色
    │     → 知识点数量决策规则（1-8个，根据内容复杂度）
    │     → 分析维度：knowledge_title / knowledge_summary / user_difficulty
    │
    ├── get_prompt("user_template")
    │     → 填充：notebook_id, notebook_name, record_count, records_content
    │
    ├── self.call_llm(response_format={"type": "json_object"})
    │     → 强制 JSON 输出格式
    │
    ├── json.loads(response)
    │     → 兼容多种 JSON 结构：数组 / {"knowledge_points": [...]} / {"points": [...]}
    │
    └── 验证每个知识点字段：
          knowledge_title    → 默认 "Unnamed knowledge point"
          knowledge_summary  → 默认 ""
          user_difficulty    → 默认 ""
```

### 知识点数量决策规则（Prompt 中定义）

| 内容特征 | 数量 | 场景 |
|---------|------|------|
| 单一主题，简单 | 1-2 | 一个概念或问题 |
| 单一主题，深入 | 2-3 | 多层次（基础→应用→拓展） |
| 多主题，独立 | 3-5 | 多个独立知识点 |
| 多主题，关联 | 4-6 | 复杂系统，需系统学习 |
| 大量记录 | 5-8 | 完整知识体系 |

---

## InteractiveAgent 详解

### 职责

将知识点转化为**完整、可独立运行的交互式 HTML 页面**。

### Prompt 特点

这是所有 Agent 中 **Prompt 最长的**（627 行），包含：
- 10 个 HTML 模板（信息卡片、步骤进度条、问答卡片、对比表格、时间线、公式展示、代码块等）
- 容器约束（iframe 适配、响应式设计）
- 交互功能实现模板（展开/折叠、标签切换、参数调节）
- 完整的 CSS 样式规范

### process() 流程

```
process(knowledge, retry_with_bug=None)
    │
    ├── retry_with_bug 不为空？
    │     是 → 构造 bug 修复 prompt（附上原始知识点信息）
    │     否 → user_template.format(knowledge_title, knowledge_summary, user_difficulty)
    │
    ├── self.call_llm(user_prompt, system_prompt)
    │     → LLM 输出完整 HTML 代码
    │
    ├── _extract_html(response)
    │     → regex 匹配 ```html ... ``` 包裹
    │     → 回退：匹配 ``` ... ``` 包裹
    │     → 再回退：检测裸 HTML（以 <!DOCTYPE 或 <html 开头）
    │     → 最终：原样返回
    │
    ├── _validate_html(html)
    │     → 检查是否包含 <html / <!doctype / <body / <div
    │
    └── 验证失败？
          → _generate_fallback_html(knowledge)
          → 使用预定义的简约 HTML 模板（含 KaTeX 公式支持）
          → 标记 is_fallback=True
```

### 降级机制

当 LLM 返回无效 HTML 或调用失败时，自动使用 `_generate_fallback_html()` 生成简约页面：
- 包含知识点标题、内容、难点
- 使用卡片式布局
- 引入 KaTeX CDN（支持数学公式）

---

## ChatAgent 详解

### 职责

在用户学习某个知识点的过程中，回答用户提问。

### process() 流程

```
process(knowledge, chat_history, user_question)
    │
    ├── 空问题检测 → 直接返回 error
    │
    ├── _format_chat_history(history)
    │     → 取最近 10 条
    │     → 格式化为 **User**: ... / **Assistant**: ... / _System: ..._
    │
    ├── user_template.format(
    │     knowledge_title, knowledge_summary, user_difficulty,
    │     chat_history, user_question
    │   )
    │
    └── self.call_llm()
          → 返回 Markdown 格式回答
```

### Prompt 角色

**智能学习助教**：
- 聚焦当前知识点（不跑题）
- 循序渐进（根据问题深度调整解释级别）
- 鼓励思考（引导用户）
- 关联困难（主动提供相关澄清）

---

## SummaryAgent 详解

### 职责

学习完成后，基于**全部知识点 + 完整对话历史**生成个性化学习总结报告。

### process() 流程

```
process(notebook_name, knowledge_points, chat_history)
    │
    ├── _format_knowledge_points(points)
    │     → 格式化每个知识点：标题 + 内容摘要 + 难点
    │
    ├── _format_chat_history(history)
    │     → 按 knowledge_index 分组（"--- 学习知识点 X 期间 ---"）
    │     → 格式化所有对话
    │
    ├── user_template.format(
    │     notebook_name, total_points,
    │     all_knowledge_points, full_chat_history
    │   )
    │
    ├── self.call_llm()
    │
    └── 清理 Markdown 包裹
          → regex 去掉 ```markdown ... ```
          → 返回纯 Markdown 文本
```

### Prompt 角色

**学习总结专家**，强调**具体化**：
- 必须列出每个知识点的具体标题
- 必须引用用户的具体问题
- 避免空泛评价（"掌握良好"之类）
- 提供可操作建议

### 总结报告结构

```markdown
# 📊 学习总结报告
## 🎯 学习概览       → 知识点数量、互动次数、学习特点
## 📚 知识点回顾     → 逐个回顾核心内容和学习情况
## 💬 学习互动分析   → 提问频率、类型、学习模式
## 📈 掌握程度评估   → 基于具体互动的评估
## 🚀 后续学习建议   → 复习重点、拓展方向、实践建议
## 🌟 结语           → 鼓励性结束语
```

---

## GuideManager 调度逻辑

### 完整会话生命周期

```
1. create_session(notebook_id, notebook_name, records)
     → LocateAgent.process() → 知识点列表
     → 创建 GuidedSession(status="initialized")
     → _save_session() → JSON 文件

2. start_learning(session_id)
     → _get_learning_state(points, 0) → 当前知识点
     → InteractiveAgent.process(knowledge) → HTML
     → session.status = "learning"
     → 追加 system 消息到 chat_history
     → _save_session()

3. chat(session_id, user_message)  ← 可多次调用
     → 取当前知识点 + 过滤当前知识点的历史
     → 追加 user 消息到 chat_history
     → ChatAgent.process(knowledge, history, question)
     → 追加 assistant 消息到 chat_history
     → _save_session()

4. next_knowledge(session_id)  ← 循环调用
     → new_index = current_index + 1
     → _get_learning_state(points, new_index)
     │
     ├── 未完成:
     │     → InteractiveAgent.process(knowledge) → 新 HTML
     │     → 更新 current_index、current_html
     │     → 追加 system 消息
     │
     └── 已完成 (index >= total):
           → SummaryAgent.process(name, points, history) → 总结
           → session.status = "completed"
           → session.summary = 总结内容

5. fix_html(session_id, bug_description)  ← 可选
     → InteractiveAgent.process(knowledge, retry_with_bug=bug_description)
     → 更新 current_html
```

### 会话持久化

```
data/user/guide/
└── session_{session_id}.json    # 完整会话数据（JSON 格式）
```

每次状态变更后调用 `_save_session()` 写入文件。支持服务重启后恢复会话。

---

## 路由层设计要点

### 双模式 API：REST + WebSocket

**REST 端点**适合独立操作：

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/create_session` | 创建会话（LocateAgent） |
| POST | `/start` | 开始学习 |
| POST | `/next` | 下一个知识点 |
| POST | `/chat` | 发送聊天消息 |
| POST | `/fix_html` | 修复 HTML |
| GET | `/session/{id}` | 获取会话信息 |
| GET | `/session/{id}/html` | 获取当前 HTML |
| GET | `/health` | 健康检查 |

**WebSocket 端点**适合连续交互（一个连接完成整个学习过程）：

```
WS /ws/{session_id}
  ← {"type": "task_id", "task_id": "..."}       # 连接后立即发送
  ← {"type": "session_info", "data": {...}}       # 发送会话初始状态
  → {"type": "start"}                             # 客户端：开始学习
  ← {"type": "start_result", "data": {...}}
  → {"type": "chat", "message": "..."}            # 客户端：提问
  ← {"type": "chat_result", "data": {...}}
  → {"type": "next"}                              # 客户端：下一个
  ← {"type": "next_result", "data": {...}}
  → {"type": "fix_html", "bug_description": "..."} # 客户端：修复 HTML
  ← {"type": "fix_result", "data": {...}}
  → {"type": "get_session"}                        # 客户端：获取状态
  ← {"type": "session_info", "data": {...}}
```

### 无状态路由 vs 有状态会话

路由层每次请求都调用 `get_guide_manager()` 创建新 GuideManager 实例（无状态），但会话数据持久化在 JSON 文件中，所以实际是有状态的。这和 Co-Writer 的单例模式不同。

### 跨笔记本支持

`create_session` 支持两种输入模式：
- **notebook_id 模式**：通过 `notebook_manager.get_notebook()` 获取记录
- **records 模式**：直接传入记录列表（支持跨笔记本组合学习）

---

## 4 个 Agent 的对比

| 维度 | LocateAgent | InteractiveAgent | ChatAgent | SummaryAgent |
|------|-------------|------------------|-----------|--------------|
| **Prompt 角色** | 学习规划师 | 交互式教学设计师 | 智能学习助教 | 学习总结专家 |
| **Prompt 长度** | ~70 行 | ~627 行（最长） | ~42 行 | ~158 行 |
| **输入** | 笔记本记录 | 单个知识点 | 知识点+历史+问题 | 全部知识点+历史 |
| **输出格式** | JSON（结构化） | HTML（完整页面） | Markdown（回答） | Markdown（报告） |
| **调用时机** | 创建会话时 1 次 | 每个知识点 1 次 | 用户每次提问 | 学习完成后 1 次 |
| **response_format** | json_object | 无 | 无 | 无 |
| **特殊处理** | JSON 解析+验证 | HTML 提取+验证+降级 | 空问题检测 | Markdown 包裹清理 |

---

## 与其他模块的对比

| 维度 | ChatAgent (第一阶段) | Co-Writer | Guide |
|------|---------------------|-----------|-------|
| **Agent 数量** | 1 个 | 2 个 | 4 个 |
| **协作模式** | 单 Agent | 无状态流水线 | 有状态流水线 |
| **通信协议** | WebSocket（流式） | HTTP REST | REST + WebSocket |
| **会话管理** | SessionManager（内存） | 无 | GuidedSession（JSON 文件） |
| **RAG 依赖** | 核心 | 可选 | 无 |
| **LLM 调用** | 1 次/请求 | 1-3 次 | 1-N 次（贯穿会话） |
| **输出类型** | 文本流 | 编辑文本/音频 | HTML页面 + 文本 |

---

## 支撑层笔记：PromptManager

Guide 阶段顺带了解的 `services/prompt/` PromptManager：

### 加载机制

```
BaseAgent.__init__()
    → get_prompt_manager().load_prompts(module_name, agent_name, language)
        → 查找路径: src/agents/{module_name}/prompts/{language}/{agent_name}.yaml
        → yaml.safe_load() → dict
        → 返回 {"system": "...", "user_template": "...", ...}
```

### Prompt 文件组织

```
src/agents/guide/prompts/
├── en/                       # 英文 Prompt
│   ├── locate_agent.yaml
│   ├── interactive_agent.yaml
│   ├── chat_agent.yaml
│   └── summary_agent.yaml
└── zh/                       # 中文 Prompt
    ├── locate_agent.yaml     # ~70 行
    ├── interactive_agent.yaml # ~627 行（含 HTML 模板库）
    ├── chat_agent.yaml       # ~42 行
    └── summary_agent.yaml    # ~158 行
```

### 模板变量替换

每个 Agent 的 `user_template` 使用 Python f-string 风格的 `{变量名}` 占位符：

| Agent | user_template 变量 |
|-------|--------------------|
| LocateAgent | `notebook_id`, `notebook_name`, `record_count`, `records_content` |
| InteractiveAgent | `knowledge_title`, `knowledge_summary`, `user_difficulty` |
| ChatAgent | `knowledge_title`, `knowledge_summary`, `user_difficulty`, `chat_history`, `user_question` |
| SummaryAgent | `notebook_name`, `total_points`, `all_knowledge_points`, `full_chat_history` |

---

## 调试脚本

```
debug_scripts/guide/
├── 01_test_locate_agent.py       → LocateAgent 知识点定位（Prompt + JSON 解析）
├── 02_test_interactive_agent.py  → InteractiveAgent HTML 生成（提取 + 验证 + 降级）
├── 03_test_chat_summary_agent.py → ChatAgent 问答 + SummaryAgent 总结
├── 04_test_guide_manager.py      → GuideManager 完整会话生命周期（4 Agent 协作）
└── 05_test_api_endpoint.py       → API 路由层端到端（REST + WebSocket）
```
