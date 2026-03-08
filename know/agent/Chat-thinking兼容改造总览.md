# Chat Thinking 兼容改造总览（前后端）

> 目的：给后续 AI/开发同学一个快速上下文，理解当前项目已完成的 thinking 兼容思路、涉及文件、协议约定与后续可扩展点。
>
> 说明：本文聚焦“改动思路 + 涉及文件”，不展开逐行代码细节。

---

## 1. 改造目标与总体思路

### 1.1 目标

针对不同模型的流式输出差异，统一支持“思考流 + 正文流”并保证前后端兼容：

- 兼容 `<think>...</think>` 内嵌在 content 的模型；
- 兼容 DeepSeek / Qwen 一类分字段输出的模型（`reasoning_content/reasoning/thought` 与 `content` 分离）；
- 前端可选展示思考流，不影响未对接场景。

### 1.2 核心策略

1. **后端先统一协议**：
   - 正文继续走既有链路（`stream`）；
   - 思考新增旁路事件（`type: "thinking"`）。

2. **Provider 层做兼容吸收**：
   - 从流式 delta 中抽取 `reasoning_content/reasoning/thought`；
   - 保留 `<think>` 状态机逻辑，避免已有模型回归。

3. **Agent 层透传结构化 chunk**：
   - 流式接口从“仅字符串”扩展为“字符串 + 结构化事件(dict)”混合流。

4. **Router 层落协议与日志**：
   - 对 thinking 事件做日志（长度+预览）；
   - 透传给前端 WebSocket。

5. **前端渐进式接入**：
   - 数据层先能接收/存储 thinking；
   - UI 通过复用组件统一渲染；
   - 再做交互体验优化（自动展开/折叠、抗抖动）。

---

## 2. 后端改造要点

### 2.1 LLM Provider 兼容层

#### `src/services/llm/cloud_provider.py`
- 增加 reasoning 字段抽取函数（统一处理 `reasoning_content/reasoning/thought`）。
- 在 OpenAI 兼容流式解析中：
  - 抽取到 reasoning 就产出 `{"type":"thinking","content":...}`；
  - content 继续走原正文逻辑；
  - `<think>` 状态机逻辑保留。
- 非流式与流式保留 thinking debug 日志能力（`DEBUG_LOG_THINKING`）。
- 流式返回类型调整为可承载结构化事件。

#### `src/services/llm/local_provider.py`
- 同步 cloud provider 的兼容策略：
  - reasoning 字段抽取；
  - SSE 与非标准流式 JSON 两条分支都兼容 thinking；
  - 保留 `<think>` 状态机；
  - 保留 debug 日志。
- 流式返回类型同样升级为“字符串 + 结构化事件”。

---

### 2.2 LLM 工厂层

#### `src/services/llm/factory.py`
- `stream()` 返回类型从纯字符串扩展为 `Union[str, Dict[str, Any]]`。
- 仅做透传，不在工厂层做 thinking 业务处理（保持单一职责）。

---

### 2.3 Agent 层

#### `src/agents/base_agent.py`
- `stream_llm()` 支持处理 dict chunk：
  - `type == "thinking"` 直接透传；
  - 正文字符串继续累积到 `full_response`。
- 补传 `binding=self.binding`，避免 provider 能力判断偏差。

#### `src/agents/chat/chat_agent.py`
- `generate_stream()` / `process(stream=True)` 支持 mixed chunk：
  - thinking 事件透传；
  - 正文包装为 `{"type":"chunk","content":...}`。
- 非流式 complete 路径补传 `binding=self.binding`。

---

### 2.4 Chat Router 协议层

#### `src/api/routers/chat.py`
- WebSocket 流式处理新增 `thinking` 分支：
  - 可选日志打印（长度+预览）；
  - 下发 `{"type":"thinking","content":...}`。
- 继续保持原协议：`status/stream/sources/result/error`。
- 文档注释中补充 thinking 事件类型说明。

---

## 3. 前端改造要点

### 3.1 状态层接入

#### `web/context/GlobalContext.tsx`
- 聊天消息结构增加 `thinking?: string`。
- WebSocket 处理新增 `data.type === "thinking"`：
  - 对当前 assistant streaming 消息累加 thinking；
  - 若顺序异常无 assistant 消息，则创建占位 assistant streaming 消息。
- 加载历史会话时兼容 `msg.thinking` 字段（若后端后续持久化即可直接回显）。

#### `web/types/chat.ts`
- `HomeChatMessage` 类型增加 `thinking?: string`。

---

### 3.2 复用组件化渲染

#### `web/components/chat/ThinkingBlock.tsx`
- 新增“思考过程”可折叠组件：
  - 支持流式状态标识（Thinking...）；
  - Markdown 渲染思考内容；
  - 支持自动展开/折叠策略。

#### `web/components/chat/AssistantMessageContent.tsx`
- 新增 assistant 统一渲染组件：
  - thinking block + 正文 markdown + streaming 状态 + sources；
  - 作为首页与历史详情的复用入口。

#### `web/components/chat/index.ts`
- 组件出口统一管理。

---

### 3.3 页面接入

#### `web/app/page.tsx`
- assistant 消息渲染切换为 `AssistantMessageContent` 复用组件。
- 抖动优化：
  - 去掉消息行高频入场动画；
  - 流式阶段滚动改为 `auto`（非流式保留 smooth）。

#### `web/components/ChatSessionDetail.tsx`
- assistant 消息渲染切换为 `AssistantMessageContent`，与首页保持一致。
- 消息类型补充 `thinking?: string`。

---

### 3.4 i18n

#### `web/locales/zh/app.json`
#### `web/locales/en/app.json`
- 新增文案键：
  - `Thinking Process`
  - `Thinking...`

---

## 4. 当前前后端协议约定（聊天 WebSocket）

### 4.1 已使用事件
- `session`
- `status`
- `stream`（正文增量）
- `thinking`（思考增量）
- `sources`
- `result`
- `error`

### 4.2 兼容性说明
- 前端若未处理 `thinking`，不会影响正文输出链路；
- 前端处理 `thinking` 后，可提升可解释性与用户体验。

---

## 5. 交互体验策略（已落地）

### 5.1 思考块展开折叠
- 流式早期（仅 thinking，正文未出现）默认展开；
- 正文出现后自动折叠；
- 历史消息默认折叠。

### 5.2 抗抖动
- 避免流式高频更新触发入场动画重放；
- 避免流式高频 smooth scroll 打断造成视觉抖动。

---

## 6. 后续扩展建议（给其他 AI 的明确方向）

1. **会话持久化 thinking**
   - 当前 router 保存 assistant 消息时主要存正文与 sources；
   - 若需要历史完整复现思考流，建议在 session_manager 存储 thinking。

2. **用户手动折叠优先**
   - 可增加“用户手动折叠/展开后不再自动覆盖”的状态策略。

3. **节流策略（可选）**
   - 若某些模型 thinking chunk 粒度极细，可在前端对 thinking 更新做轻量节流，进一步降低重排频率。

4. **全链路测试矩阵**
   - 纯 content 模型；
   - `<think>` 模型；
   - `reasoning_content + content` 分字段模型。

---

## 7. 涉及文件总览（便于快速定位）

### 后端
- `src/services/llm/cloud_provider.py`
- `src/services/llm/local_provider.py`
- `src/services/llm/factory.py`
- `src/agents/base_agent.py`
- `src/agents/chat/chat_agent.py`
- `src/api/routers/chat.py`

### 前端
- `web/context/GlobalContext.tsx`
- `web/types/chat.ts`
- `web/components/chat/ThinkingBlock.tsx`
- `web/components/chat/AssistantMessageContent.tsx`
- `web/components/chat/index.ts`
- `web/app/page.tsx`
- `web/components/ChatSessionDetail.tsx`
- `web/locales/zh/app.json`
- `web/locales/en/app.json`

---

## 8. 给后续 AI 的一句话上下文

> 本项目已完成后端 reasoning 字段兼容与 thinking 事件下发，前端已完成 thinking 状态接收与复用组件渲染，并做了流式抗抖动优化。后续重点是 thinking 持久化与交互细化，不要破坏现有 stream/result/sources 兼容链路。
