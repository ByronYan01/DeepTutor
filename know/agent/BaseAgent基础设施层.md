# BaseAgent 基础设施层

> 源码位置：`src/agents/base_agent.py`
> 所有 Agent（ChatAgent、CoWriter、Guide 等）的基类

---

## 提供的 5 大能力

### 1. 配置管理

- **LLM 配置**：api_key、base_url、model、api_version，优先级：传入参数 > `get_llm_config()` > 环境变量
- **Agent 参数**：从 `config/agents.yaml` 按模块读取 temperature、max_tokens
- **热刷新**：`refresh_config()` — 用户在前端切换模型后无需重启服务

| 方法 | 作用 |
|------|------|
| `get_model()` | 获取模型名（agent 配置 > llm 配置 > 实例变量 > 环境变量） |
| `get_temperature()` | 从 agents.yaml 读温度参数（默认 0.8） |
| `get_max_tokens()` | 从 agents.yaml 读最大 token 数（默认 4096） |
| `get_max_retries()` | 获取重试次数 |
| `refresh_config()` | 热刷新 LLM 配置 |

### 2. Prompt 加载

通过 `PromptManager` 从 YAML 文件加载模板：

```
src/agents/{module}/prompts/{language}/{agent_name}.yaml
例：src/agents/chat/prompts/zh/chat_agent.yaml
```

| 方法 | 作用 |
|------|------|
| `get_prompt("system")` | 简单查找，获取 system prompt |
| `get_prompt("section", "field", "fallback")` | 嵌套查找 |
| `has_prompts()` | 检查 prompt 是否已加载 |

### 3. LLM 调用

两种模式，都通过统一的 LLM 工厂函数路由到对应 provider（云端/本地）：

| 方法 | 模式 | 说明 |
|------|------|------|
| `call_llm()` | 非流式 | 调用 `llm_complete()`，等待完整响应返回 |
| `stream_llm()` | 流式 | 调用 `llm_stream()`，逐 chunk yield |

流程：准备参数 → 记录输入日志 → 调 LLM 工厂 → 记录 token 用量 → 记录输出日志 → 返回

### 4. Token 追踪

每次 LLM 调用后自动统计 token 消耗：

- **外部 TokenTracker**（可选）— 由调用方传入
- **共享 LLMStats**（始终可用）— 类级别，每个模块一个实例

| 方法 | 作用 |
|------|------|
| `_track_tokens()` | 记录一次调用的 token 用量 |
| `get_stats(module)` | 获取模块的统计实例 |
| `reset_stats()` | 重置统计 |
| `print_stats()` | 打印统计摘要 |

### 5. 日志记录

初始化时创建 logger：`{Module}.{agent_name}`（如 `Chat.chat_agent`）

支持：
- 标准日志（info/warning/error）
- LLM 输入日志（`log_llm_input`）
- LLM 输出日志（`log_llm_output`，含响应长度和耗时）

---

## 抽象方法

```python
@abstractmethod
async def process(self, *args, **kwargs) -> Any:
```

所有子类必须实现。ChatAgent 的 `process()` 就是对它的实现，包含 retrieve_context + build_messages + generate 的完整流程。

---

## 子类继承关系

```
BaseAgent（基础设施）
├── ChatAgent   — 多轮对话，RAG/Web 检索 + 流式回答
├── CoWriter    — 协作写作
└── Guide       — 引导式学习
```

子类只需关注业务逻辑，通用能力（LLM 调用、配置、Prompt、Token 追踪、日志）全部由 BaseAgent 提供。
