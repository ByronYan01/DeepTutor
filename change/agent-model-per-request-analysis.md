# 后端 `src/agents` 支持按请求传入模型名的改造分析

> 目标：评估“从仅全局设置模型”升级为“可按请求/按 Agent 指定模型”的改造难度、影响面与风险。

## 1. 结论先行

**结论：整体难度为「中等偏高」**。

- **不是底层能力不足**：底层 `BaseAgent` 与 LLM Factory 已支持按调用传 `model`。
- **主要难点在“多层透传”**：API Router（WebSocket/DTO）→ Orchestrator → 子 Agent 构造链条较长，且分散在多个模块。
- **最稳妥路径**：先做“单请求单模型（request-level）”，再升级到“单请求内多 Agent 多模型（agent-level policy）”。

---

## 2. 当前模型配置与调用链路（现状）

### 2.1 配置来源（全局）

- LLM 环境变量映射定义在：
  - `src/services/config/unified_config.py:57`
  - `src/services/config/unified_config.py:58-64`
- 当前激活配置入口：
  - `src/services/config/unified_config.py:632-634`

### 2.2 运行时获取配置

- `get_llm_config()` 优先级：active config → `.env`
  - `src/services/llm/config.py:107-141`
- `LLMConfig` 数据结构（含 `model`）
  - `src/services/llm/config.py:61-70`

### 2.3 Agent 抽象层能力（关键）

- `BaseAgent.__init__` 已支持 `model`
  - `src/agents/base_agent.py:53-66`
- 初始化时会将传入 model 覆盖到实例：
  - `src/agents/base_agent.py:102-104`
- `call_llm(..., model=...)` 与 `stream_llm(..., model=...)` 均支持调用时覆盖
  - `src/agents/base_agent.py:340-349`
  - `src/agents/base_agent.py:460-468`
- 如果调用时未传，走 `model = model or self.get_model()`
  - `src/agents/base_agent.py:372`
  - `src/agents/base_agent.py:488`

### 2.4 LLM Factory 层能力（关键）

- `complete(..., model=None)` 支持传 model
  - `src/services/llm/factory.py:116-123`
- 未传时回退配置 `model = model or config.model`
  - `src/services/llm/factory.py:154-160`
  - `src/services/llm/factory.py:156`
- `stream(..., model=None)` 同理
  - `src/services/llm/factory.py:243-250`
  - `src/services/llm/factory.py:284-290`

**结论**：底层已经具备 request-level model 覆盖能力。

---

## 3. `src/agents` 各模块支持情况盘点

> 判定标准：
> - 显式支持：`__init__` 有 `model` 参数并传给 `super`
> - 间接支持：`**kwargs` 透传到 `super`
> - 未显式支持：构造器与 `super` 都未出现 `model`

## 3.1 显式支持（少量）

1. `IdeaGenerationWorkflow`
   - `src/agents/ideagen/idea_generation_workflow.py:26-35`
   - `src/agents/ideagen/idea_generation_workflow.py:48-56`
2. `MaterialOrganizerAgent`
   - `src/agents/ideagen/material_organizer_agent.py:23-30`
   - `src/agents/ideagen/material_organizer_agent.py:31-39`

## 3.2 间接支持（通过 `**kwargs`）

1. `chat.ChatAgent`
   - `src/agents/chat/chat_agent.py:45-51`
   - `src/agents/chat/chat_agent.py:61-67`
2. `question.RetrieveAgent`
   - `src/agents/question/agents/retrieve_agent.py:27-33`
   - `src/agents/question/agents/retrieve_agent.py:43-48`
3. `question.GenerateAgent`
   - `src/agents/question/agents/generate_agent.py:26-30`
   - `src/agents/question/agents/generate_agent.py:38-43`
4. `question.RelevanceAnalyzer`
   - `src/agents/question/agents/relevance_analyzer.py:32-36`
   - `src/agents/question/agents/relevance_analyzer.py:44-49`

## 3.3 未显式支持（主流）

### solve
- `InvestigateAgent` `src/agents/solve/analysis_loop/investigate_agent.py:27-34`
- `NoteAgent` `src/agents/solve/analysis_loop/note_agent.py:26-33`
- `ManagerAgent` `src/agents/solve/solve_loop/manager_agent.py:25-32`
- `SolveAgent` `src/agents/solve/solve_loop/solve_agent.py:35-42`
- `ToolAgent` `src/agents/solve/solve_loop/tool_agent.py:30-37`
- `ResponseAgent` `src/agents/solve/solve_loop/response_agent.py:25-32`
- `PrecisionAnswerAgent` `src/agents/solve/solve_loop/precision_answer_agent.py:21-28`

### research
- `RephraseAgent` `src/agents/research/agents/rephrase_agent.py:23-29`
- `DecomposeAgent` `src/agents/research/agents/decompose_agent.py:27-34`
- `ManagerAgent` `src/agents/research/agents/manager_agent.py:23-29`
- `ResearchAgent` `src/agents/research/agents/research_agent.py:27-33`
- `NoteAgent` `src/agents/research/agents/note_agent.py:25-31`
- `ReportingAgent` `src/agents/research/agents/reporting_agent.py:62-68`

### guide
- `LocateAgent` `src/agents/guide/agents/locate_agent.py:16-23`
- `InteractiveAgent` `src/agents/guide/agents/interactive_agent.py:17-24`
- `ChatAgent` `src/agents/guide/agents/chat_agent.py:15-22`
- `SummaryAgent` `src/agents/guide/agents/summary_agent.py:16-23`

### co_writer
- `EditAgent` `src/agents/co_writer/edit_agent.py:59`
- `NarratorAgent` `src/agents/co_writer/narrator_agent.py:36`

---

## 4. API 入口与 DTO 层现状（为什么“不灵活”）

## 4.1 WebSocket 入口多数手工解析 JSON，当前无 `model` 字段

- solve: `src/api/routers/solve.py:149-153`
- research: `src/api/routers/research.py:95-105`
- question(generate): `src/api/routers/question.py:339-343`
- question(mimic): `src/api/routers/question.py:74-77`
- chat: `src/api/routers/chat.py:120-129`
- ideagen: `src/api/routers/ideagen.py:119-123`

## 4.2 DTO（BaseModel）入口也基本无 `model`

- research: `OptimizeRequest` `src/api/routers/research.py:39-44`
- guide: `CreateSessionRequest/ChatRequest/FixHtmlRequest/NextKnowledgeRequest`
  - `src/api/routers/guide.py:39,46,53,60`
- ideagen: `IdeaGenRequest` `src/api/routers/ideagen.py:37-40`
- co_writer: `EditRequest/AutoMarkRequest/NarrateRequest...`
  - `src/api/routers/co_writer.py:82,95,205,229`

## 4.3 Router 到编排层当前主要传的是 api_key/base_url/api_version

- solve → `MainSolver`：`src/api/routers/solve.py:206-213`
- research → `ResearchPipeline`：`src/api/routers/research.py:280-288`
- question → `AgentCoordinator`：`src/api/routers/question.py:381-389`
- chat → `ChatAgent`：`src/api/routers/chat.py:202-208`
- guide → `GuideManager`：`src/api/routers/guide.py:81-87`

这导致：即使底层支持 `model`，上层请求也很难把模型名“带下去”。

---

## 5. Orchestrator 透传断点（改造的主工程量）

1. `MainSolver` 无 `model` 构造参数
   - `src/agents/solve/main_solver.py:40-49`
   - 子 Agent 初始化在 `src/agents/solve/main_solver.py:288-303,518-559`
2. `ResearchPipeline` 无 `model` 构造参数
   - `src/agents/research/research_pipeline.py:69-78`
   - `_init_agents` 批量创建子 Agent：`src/agents/research/research_pipeline.py:164-188`
3. `GuideManager` 无 `model` 构造参数
   - `src/agents/guide/guide_manager.py:49-58`
   - 子 Agent 初始化：`src/agents/guide/guide_manager.py:119-146`
4. `AgentCoordinator` 无 `model` 构造参数
   - `src/agents/question/coordinator.py:42-51`
   - 子 Agent 创建：`src/agents/question/coordinator.py:132-159`

---

## 6. 已有“局部成功实践”与“现存分叉”

## 6.1 局部成功实践：ideagen

ideagen Router 已显式把 `llm_config.model` 传给 workflow/organizer：
- `src/api/routers/ideagen.py:198-204`
- `src/api/routers/ideagen.py:258-264`

这说明“从 Router 透传到 Agent”在当前架构下可行。

## 6.2 现存分叉：question coordinator 中存在直调 `llm_complete`

- `src/agents/question/coordinator.py:533-542`

这段逻辑直接使用 `llm_config.model`，意味着后续改造若只改 Agent 构造透传，仍可能漏掉此类“直调路径”。

---

## 7. 难度分级（按模块）

## 7.1 低

- **ideagen**：已有显式 `model` 参数与透传路径，改动相对集中。

## 7.2 中

- **chat / question**：子 Agent 多为 `**kwargs` 透传，技术改造不重；但 Router + Coordinator 的请求链路仍需补齐。

## 7.3 中高

- **solve / research / guide**：存在 orchestrator + 多子 Agent 的级联初始化，透传链条长、漏传风险高。

---

## 8. 主要风险点

1. **透传遗漏导致“静默回退全局 model”**
   - 表现：部分调用按请求模型，部分调用仍走默认模型，行为不一致且不易发现。
2. **请求隔离风险**
   - 若错误地把请求模型写回全局配置，会出现并发串扰。
3. **provider/model 兼容性差异**
   - `response_format` 与不同 provider/model 能力不一致：
     - 能力判断入口：`src/services/llm/capabilities.py:228-241`
     - cloud provider 处理：`src/services/llm/cloud_provider.py:180-182,285-286`
4. **观测性不足**
   - 若日志不标注“最终生效模型来源（request/agent/global）”，线上排障成本高。

---

## 9. 测试影响面（当前覆盖缺口）

当前测试集中在 config/prompt/rag，缺少这 7 个模块的接口透传验证：

- `tests/core/test_config_manager.py`
- `tests/core/test_prompt_manager.py`
- `tests/core/test_prompt_parity.py`
- `tests/services/rag/test_pipeline_integration.py`
- `tests/services/rag/test_rag_pipelines.py`
- `tests/agents/solve/utils/test_json_utils.py`

因此，若引入请求级 `model`，至少会新增/改动以下类型测试：

1. Router 层：传/不传 model 的请求路径
2. Orchestrator 层：model 是否向下传递
3. Agent 层：`call_llm(..., model=...)` 生效路径
4. 回归：不传 model 保持旧行为

---

## 10. 推荐改造路径（两阶段）

## 阶段 A：最小可用（建议先做）

目标：**单请求单模型（request-level model）**

- Router 请求中新增可选 `model`
- Orchestrator 构造新增可选 `model`
- Orchestrator 创建子 Agent 时统一下传 `model`
- 保持默认行为：未传 `model` 时完全沿用当前全局配置

**价值**：改动小、收益高、风险可控。

## 阶段 B：完整灵活（后续演进）

目标：**单请求内按 Agent 指定模型（agent-level policy）**

- 请求支持 `default_model + agent_models`
- 建立统一 model policy，并在编排层执行
- 日志明确记录每次调用的 effective model 与来源

**价值**：灵活性最大，可做质量/成本混合调度。

---

## 11. 对你问题的直接回答

你问“后端如果 `src/agents` 下所有 agents 接口支持传入模型名称，难度大吗？”

**回答**：

- 从“技术可行性”看：**可行且已有基础**（BaseAgent/Factory 已支持）。
- 从“工程改造量”看：**中等偏高**，因为要打通 **API 入参 → orchestrator → 子 Agent** 的整条链路，并补齐测试与观测。
- 从“实施策略”看：建议先做 request-level（阶段 A），确认稳定后再上 agent-level（阶段 B）。

---

## 12. 关键证据清单（便于快速跳转）

- `src/agents/base_agent.py:53-66,102-104,340-349,372,460-468,488`
- `src/services/llm/factory.py:116-123,154-160,243-250,284-290`
- `src/services/llm/config.py:61-70,107-141`
- `src/services/config/unified_config.py:57-64,632-634`
- `src/agents/solve/main_solver.py:40-49,283-303,518-559`
- `src/agents/research/research_pipeline.py:69-78,164-188`
- `src/agents/guide/guide_manager.py:49-58,119-146`
- `src/agents/question/coordinator.py:42-51,132-159,533-542`
- `src/api/routers/solve.py:149-153,206-213`
- `src/api/routers/research.py:39-44,95-105,280-288`
- `src/api/routers/question.py:74-77,339-343,381-389`
- `src/api/routers/chat.py:120-129,202-208`
- `src/api/routers/guide.py:39,46,53,60,81-87`
- `src/api/routers/ideagen.py:37-40,119-123,198-204,258-264`
- `src/api/routers/co_writer.py:82,95,205,229`
- `src/services/llm/capabilities.py:228-241`
- `src/services/llm/cloud_provider.py:180-182,285-286`
