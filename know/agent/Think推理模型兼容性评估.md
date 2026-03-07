# Agent 对带 think 思考推理模型的兼容性评估

> 评估时间：2026-03-06
> 评估范围：`src/agents/**`、`src/services/llm/**`、`config/agents.yaml`

---

## 一句话结论

当前实现为 **部分兼容**：
- ✅ 能接入并调用多数“会输出 `<think>...</think>`”或“reasoning 字段”的推理模型，并返回最终答案。
- ⚠️ 但缺少对“显式推理参数”（如 `reasoning_effort` / `enable_thinking`）的透传与统一处理，且 Anthropic thinking block 场景处理不完整。

---

## 关键调用链（Agent → LLM）

1. 所有核心 Agent 继承 `BaseAgent`（如 `src/agents/chat/chat_agent.py:31`、`src/agents/solve/solve_loop/solve_agent.py:23`、`src/agents/research/agents/research_agent.py:24`）。
2. `BaseAgent.call_llm()` 统一走 `llm_complete`（`src/agents/base_agent.py:340`、`src/agents/base_agent.py:419`）。
3. `BaseAgent.stream_llm()` 统一走 `llm_stream`（`src/agents/base_agent.py:460`、`src/agents/base_agent.py:518`）。
4. `factory` 根据 URL 路由 cloud/local provider（`src/services/llm/factory.py:163`、`src/services/llm/factory.py:293`）。

---

## 已具备的兼容能力（正向）

1. **推理标签识别能力有集中配置**
   - `has_thinking_tags` 能力位存在（`src/services/llm/capabilities.py:273`）。
   - DeepSeek/Qwen/QwQ 被标注为可能带 thinking 标签（`src/services/llm/capabilities.py:63`、`src/services/llm/capabilities.py:150`、`src/services/llm/capabilities.py:154`）。

2. **非流式响应可提取 reasoning 兼容字段**
   - `extract_response_content()` 会回退读取 `reasoning_content/reasoning/thought`（`src/services/llm/utils.py:276`-`src/services/llm/utils.py:283`）。

3. **`<think>...</think>` 清洗逻辑已实现**
   - `clean_thinking_tags()` 统一清洗（`src/services/llm/utils.py:176`-`src/services/llm/utils.py:210`）。
   - Cloud 完成态返回前清洗（`src/services/llm/cloud_provider.py:260`-`src/services/llm/cloud_provider.py:261`）。
   - Local 完成态返回前清洗（`src/services/llm/local_provider.py:109`-`src/services/llm/local_provider.py:111`）。

4. **流式输出对 think 标签有处理**
   - Cloud 流式维护 `in_thinking_block` 并清洗（`src/services/llm/cloud_provider.py:331`-`src/services/llm/cloud_provider.py:366`）。
   - Local 流式同样维护 thinking block（`src/services/llm/local_provider.py:186`-`src/services/llm/local_provider.py:227`）。

5. **新推理模型 token 参数兼容已考虑**
   - `o1/o3/gpt-5` 系列切换到 `max_completion_tokens`（`src/services/llm/config.py:176`-`src/services/llm/config.py:223`）。

6. **部分推理模型温度限制已处理**
   - `gpt-5/o1/o3` 强制温度能力位（`src/services/llm/capabilities.py:166`-`src/services/llm/capabilities.py:176`）。
   - `get_effective_temperature()` 生效（`src/services/llm/capabilities.py:315`-`src/services/llm/capabilities.py:337`）。

---

## 当前阻塞点（为什么是“部分兼容”）

1. **缺少“显式推理参数”透传**（核心）
   - `BaseAgent.call_llm()` 仅构造了 `temperature` + token limit + 可选 `response_format`（`src/agents/base_agent.py:381`-`src/agents/base_agent.py:399`）。
   - Provider 侧请求体也仅见 `model/messages/temperature/(max_tokens|max_completion_tokens)/response_format`（`src/services/llm/cloud_provider.py:223`-`src/services/llm/cloud_provider.py:240`，`src/services/llm/local_provider.py:79`-`src/services/llm/local_provider.py:88`）。
   - 未见 `reasoning_effort` / `enable_thinking` / `thinking_budget` 等参数通道。

2. **配置层没有推理参数位**
   - `config/agents.yaml` 仅温度与 token（`config/agents.yaml:13`-`config/agents.yaml:14` 等）。
   - `LLMConfig` 仅 `model/api_key/base_url/binding/api_version/max_tokens/temperature`（`src/services/llm/config.py:64`-`src/services/llm/config.py:70`）。

3. **Anthropic thinking block 场景处理不完整**
   - 非流式 Anthropic 直接取 `result["content"][0]["text"]`（`src/services/llm/cloud_provider.py:423`-`src/services/llm/cloud_provider.py:424`），对多 block（含 thinking/text 混合）不稳健。
   - 流式 Anthropic 仅处理 `content_block_delta.delta.text`（`src/services/llm/cloud_provider.py:493`-`src/services/llm/cloud_provider.py:498`），未对“thinking 类型增量”做显式兼容逻辑。

4. **流式 reasoning 字段兼容不完整（OpenAI-compatible）**
   - Cloud/Local 流式均主要读取 `delta.content`（`src/services/llm/cloud_provider.py:348`-`src/services/llm/cloud_provider.py:349`，`src/services/llm/local_provider.py:207`-`src/services/llm/local_provider.py:208`）。
   - 若某些推理模型将思维/答案拆到非 `content` 字段，当前逻辑可能漏读或仅部分显示。

---

## 结论细化（按“能不能用”）

- **能用（基础可运行）**：大多数输出最终答案在 `content` 或带 `<think>` 标签的模型。
- **可用但有折损**：需要严格控制推理预算/思考强度的模型（目前无法从 Agent 层配置透传）。
- **风险较高**：Anthropic thinking block 或某些 provider 的非标准流式 reasoning 字段场景。

---

## 最小改动建议（按优先级）

1. **先打通参数通道（最小且收益最大）**
   在 `BaseAgent.call_llm()/stream_llm()` 增加可选 `reasoning_options`（或透传白名单），并下发到 provider 请求体。

2. **配置对齐**
   在 `LLMConfig` 与 `config/agents.yaml`（或统一配置）增加可选推理字段，做到“可配置、可回退”。

3. **补 Anthropic thinking block 解析**
   非流式遍历 `content[]` 聚合 text block；流式补充 thinking 类型事件兼容，保证最终展示与统计一致。

4. **补流式非 content 字段兼容**
   对 OpenAI-compatible 流式增量增加 `reasoning_content/reasoning/thought` 兼容读取策略（按 provider capability 控制）。

---

## 附：本次判定的证据清单（节选）

- `src/agents/base_agent.py:29`
- `src/agents/base_agent.py:340`
- `src/agents/base_agent.py:381`
- `src/agents/base_agent.py:419`
- `src/agents/base_agent.py:460`
- `src/services/llm/factory.py:163`
- `src/services/llm/factory.py:293`
- `src/services/llm/capabilities.py:63`
- `src/services/llm/capabilities.py:150`
- `src/services/llm/capabilities.py:273`
- `src/services/llm/utils.py:176`
- `src/services/llm/utils.py:276`
- `src/services/llm/cloud_provider.py:260`
- `src/services/llm/cloud_provider.py:331`
- `src/services/llm/cloud_provider.py:423`
- `src/services/llm/local_provider.py:109`
- `src/services/llm/local_provider.py:186`
- `src/services/llm/config.py:176`
- `config/agents.yaml:13`
