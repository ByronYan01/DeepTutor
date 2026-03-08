# 方案 A 设计文档：基于请求上下文的模型选择（去参数透传）

## 1. 背景与问题

当前后端在“按请求指定模型”场景下，主要依赖 `model` 参数逐层透传（Router → Orchestrator → Agent）。

这种方式的核心问题：

1. **链路脆弱**：任意一层漏传都会静默回退全局配置。
2. **维护成本高**：新增模块/重构流程时容易再次漏传。
3. **行为不透明**：排障时很难定位“本次调用到底用了哪个模型”。

你现在的判断是对的：
- 一旦某层断掉，最终会走全局或环境默认模型（现状回退逻辑）。
- 参考：
  - `src/agents/base_agent.py:372`（`model = model or self.get_model()`）
  - `src/agents/base_agent.py:153-185`（`get_model` 回退链）
  - `src/services/llm/factory.py:156,286`（`model = model or config.model`）

---

## 2. 方案 A 目标（最小改造、快速生效）

**目标**：实现“单请求单模型（request-level model）”，不再依赖多层参数透传。

**边界**：
- ✅ 支持：每个请求可选 `model`。
- ✅ 保持兼容：不传 `model` 时完全沿用现有行为。
- ❌ 暂不支持：同一请求内按不同 Agent 指定不同模型（这属于后续增强）。

---

## 3. 核心设计思想

将“模型选择”从**参数传输问题**改为**上下文解析问题**。

- 引入请求级 `ModelContext`（基于 `ContextVar`，协程隔离）。
- 请求入口只设置一次上下文。
- Agent/LLM 层按统一优先级读取上下文并决策。

### 3.1 优先级（方案 A）

最终生效模型优先级建议：

1. `call_llm(..., model=...)` 显式传参
2. `ModelContext.request_model`（请求上下文）
3. 现有逻辑（agent_config / llm_config / self.model / env）

> 这样既保留现有能力，也保证“请求级模型”不会因中间漏传而失效。

---

## 4. 设计细节

## 4.1 新增上下文模块（新增文件）

建议新增：`src/services/llm/model_context.py`

### 结构设计

```python
from dataclasses import dataclass
from contextvars import ContextVar, Token
from contextlib import contextmanager
from typing import Optional

@dataclass
class ModelContext:
    request_id: str | None = None
    request_model: str | None = None
    source: str = "request"

_model_ctx: ContextVar[ModelContext | None] = ContextVar("model_ctx", default=None)

def get_model_context() -> ModelContext | None:
    return _model_ctx.get()

@contextmanager
def use_model_context(ctx: ModelContext):
    token: Token = _model_ctx.set(ctx)
    try:
        yield
    finally:
        _model_ctx.reset(token)
```

### 设计要点

- 使用 `ContextVar`，天然支持 asyncio 并发隔离。
- 必须通过 `Token` reset，避免上下文泄漏到后续请求。

---

## 4.2 BaseAgent 增强（少量改动）

改造点：`src/agents/base_agent.py:153-185` 的 `get_model()`。

在现有回退链前增加上下文读取：

```python
ctx = get_model_context()
if ctx and ctx.request_model:
    return ctx.request_model
```

保持原逻辑不变，确保兼容。

---

## 4.3 LLM Factory 兜底（关键兜底）

改造点：
- `src/services/llm/factory.py:116-160` (`complete`)
- `src/services/llm/factory.py:243-290` (`stream`)

当 `model is None` 时，优先尝试从 `ModelContext` 取 `request_model`，再回退 `config.model`。

这样即使部分调用不走 BaseAgent，也能吃到请求级模型。

---

## 4.4 API 入口设置上下文（避免透传）

在 Router 入口（REST/WebSocket）读取 `model` 并设置 `ModelContext`：

- solve: `src/api/routers/solve.py:149-153`
- research: `src/api/routers/research.py:95-105`
- question: `src/api/routers/question.py:74-77,339-343`
- chat: `src/api/routers/chat.py:120-129`
- ideagen: `src/api/routers/ideagen.py:119-123`
- guide: `src/api/routers/guide.py`（REST 请求模型 + WS 消息）
- co_writer: `src/api/routers/co_writer.py:82,95,205,229`（REST DTO 可加可选 `model`）

### WebSocket 注意点

- 每条消息都可能是不同模型。
- 应该“**每条消息一个上下文作用域**”，处理完成立即 reset。

---

## 4.5 统一日志（最小可观测性）

在 LLM 调用日志中增加：

- `effective_model`
- `model_source`（call_arg / request_context / config）
- `request_id`

建议打点位置：
- `src/agents/base_agent.py:405-414`
- `src/services/llm/factory.py` 调用前（`complete/stream`）

---

## 5. 兼容性与回退策略

## 5.1 向后兼容

- 请求不带 `model`：行为与当前完全一致。
- 历史接口无需立刻重写 orchestrator 签名。

## 5.2 错误处理

- `request_model` 非法时：
  - 方案 A 默认采用“警告 + 回退全局”（不阻断主流程）
  - 并记录结构化告警日志

---

## 6. 实施步骤（建议顺序）

1. 新增 `model_context.py` 与单测。
2. 改 `BaseAgent.get_model()` 支持上下文读取。
3. 改 `llm/factory.complete/stream` 做上下文兜底。
4. 在高频 Router 先接入 `model`：`solve/research/chat/question`。
5. 扩到 `guide/ideagen/co_writer`。
6. 增加日志字段与回归测试。

---

## 7. 测试设计（方案 A 必测）

1. **上下文隔离测试**：并发请求 A/B 不串模型。
2. **优先级测试**：`call_llm(model=...)` 覆盖 `request_model`。
3. **回归测试**：无 `model` 请求行为不变。
4. **WebSocket 测试**：同连接多消息不同 `model` 生效。
5. **兜底测试**：不经 BaseAgent 的 `llm_factory` 路径仍可解析上下文模型。

---

## 8. 进一步完善方案（在 A 稳定后）

## 方案 B：按 Agent 精细模型策略（agent-level）

在请求体中扩展：

```json
{
  "model": "gpt-4o-mini",
  "agent_models": {
    "solve.manager_agent": "o3-mini",
    "solve.solve_agent": "gpt-4.1"
  }
}
```

新增 `ModelPolicy` 解析器：
- 支持 `agent_key` 精确匹配
- 支持模块级通配（如 `solve.*`）
- 支持默认模型兜底

**收益**：同一请求内可做质量/成本分层调度。

---

## 方案 C：企业级治理与路由

在 B 基础上引入 `ModelResolver`：

1. **严格模式**（strict）：请求模型不兼容直接报错，不回退。
2. **能力感知路由**：结合 `supports_response_format` 等能力自动换路由。
   - 参考现有能力判断：`src/services/llm/capabilities.py:228-241`
3. **预算/配额路由**：按请求成本预算自动降级模型。
4. **灰度发布**：按用户/租户/实验组动态选模型。
5. **观测面板**：模型命中率、回退率、失败率、成本趋势。

---

## 9. 方案 A 的价值总结

对比“层层透传 model”方式，方案 A 的优势：

- **低入侵**：不需要大范围改 orchestrator/agent 构造签名。
- **高鲁棒**：减少“漏传即回退”的隐式错误。
- **易演进**：可自然升级到 B/C，不推翻现有架构。

---

## 10. 本文对应的现有代码锚点（便于评审）

- `src/agents/base_agent.py:153-185,340-349,372,460-468,488`
- `src/services/llm/factory.py:116-160,243-290`
- `src/services/llm/config.py:107-141`
- `src/api/routers/solve.py:149-153`
- `src/api/routers/research.py:95-105`
- `src/api/routers/question.py:74-77,339-343`
- `src/api/routers/chat.py:120-129`
- `src/api/routers/ideagen.py:119-123`
- `src/api/routers/guide.py:39,46,53,60`
- `src/api/routers/co_writer.py:82,95,205,229`
