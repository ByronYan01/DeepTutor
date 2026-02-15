# Co-Writer 协作写作模块源码分析

> 第二阶段学习产出，基于 `src/agents/co_writer/` 源码

---

## 模块概览

Co-Writer 是 DeepTutor 的**协作写作**模块，提供两个 Agent：

| Agent | 类 | 功能 |
|-------|-----|------|
| **EditAgent** | `edit_agent.py` | AI 文本编辑：改写/缩写/扩展 + 可选 RAG/Web 上下文增强 + 自动标注 |
| **NarratorAgent** | `narrator_agent.py` | 将文本转为旁白脚本 + TTS 音频生成 |

两个 Agent 的协作模式是**流水线式**（Pipeline）：
```
用户选中文本 → EditAgent 编辑 → NarratorAgent 生成旁白 → 输出脚本/音频
```

---

## 架构图

```
前端 (web/app/co_writer/)
    ↓ HTTP POST
FastAPI Router (src/api/routers/co_writer.py)
    ├── POST /edit     → get_edit_agent()    → EditAgent.process()
    ├── POST /automark → get_edit_agent()    → EditAgent.auto_mark()
    ├── POST /narrate  → get_narrator_agent() → NarratorAgent.narrate()
    ├── GET  /history  → load_history()
    └── GET  /tts/status → get_tts_config()
    ↓
Agent 层 (src/agents/co_writer/)
    ├── EditAgent(BaseAgent)
    │     ├── process()    → rewrite/shorten/expand + 可选 RAG/Web
    │     └── auto_mark()  → AI 自动标注
    └── NarratorAgent(BaseAgent)
          ├── generate_script()     → 生成旁白脚本
          ├── _extract_key_points() → 提取关键要点
          ├── generate_audio()      → TTS 音频生成
          └── narrate()             → 完整流程（脚本+音频）
    ↓
BaseAgent (src/agents/base_agent.py)
    ├── call_llm()   → LLM Factory
    ├── stream_llm() → LLM Factory (streaming)
    ├── get_prompt()  → PromptManager
    └── _track_tokens() → LLMStats
    ↓
LLM Factory (src/services/llm/factory.py)
    ├── cloud_provider → OpenAI/DeepSeek/Anthropic/...
    └── local_provider → Ollama/LM Studio/vLLM/...
```

---

## EditAgent 详解

### 初始化

```python
class EditAgent(BaseAgent):
    def __init__(self, language="en"):
        super().__init__(
            module_name="co_writer",      # 决定 agents.yaml 中的参数组
            agent_name="edit_agent",       # 决定加载哪个 prompt 文件
            language=language,             # 决定 prompts/en/ 或 prompts/zh/
        )
```

### process() 核心流程

```
process(text, instruction, action, source, kb_name)
    │
    ├── source == "rag" ?
    │     → rag_search(query=instruction, kb_name=kb_name, mode="naive")
    │     → context = search_result["answer"]
    │     → save_tool_call()  # 保存 RAG 调用记录
    │
    ├── source == "web" ?
    │     → web_search(instruction)
    │     → context = search_result["answer"]
    │     → save_tool_call()
    │
    ├── 组装 Prompt:
    │     system_prompt ← get_prompt("system")
    │     user_prompt   ← action_template.format(action_verb, instruction)
    │                   + context_template.format(context)  [如果有上下文]
    │                   + user_template.format(text)
    │
    ├── self.call_llm(user_prompt, system_prompt, stage="edit_{action}")
    │
    └── save_history()  → data/user/co-writer/history.json
```

**三种编辑操作**：
- `rewrite`: 按指令改写文本
- `shorten`: 压缩文本，保留核心信息
- `expand`: 扩展文本，补充细节

**上下文增强**（可选）：
- `source="rag"`: 从知识库检索相关内容作为参考
- `source="web"`: 通过 Web 搜索获取参考上下文
- `source=None`: 纯 LLM 编辑

### auto_mark() 自动标注

使用专用的 `auto_mark_system` Prompt，给文本添加 5 种 HTML 注释标签：

| 标签 | 用途 | 频率限制 |
|------|------|----------|
| `circle` | 核心术语、模型名（≤5 字符） | 每 100 字最多 1 个 |
| `highlight` | 定义性陈述、核心概念 | 每段最多 2 个 |
| `box` | 公式、数据、代码 | 每段最多 1 个 |
| `underline` | 结论、因果关系 | 每段最多 1 个 |
| `bracket` | 整段核心总结 | 全文最多 1-2 个 |

标签格式: `<span data-rough-notation="circle">内容</span>`

---

## NarratorAgent 详解

### 初始化特殊之处

```python
class NarratorAgent(BaseAgent):
    def __init__(self, language="en"):
        super().__init__(
            module_name="narrator",        # 用独立的 module_name 获取独立参数
            agent_name="narrator_agent",
            language=language,
        )
        # 覆盖 Prompt 加载：从 co_writer 模块读取
        self.prompts = get_prompt_manager().load_prompts(
            module_name="co_writer",       # Prompt 文件在 co_writer 目录下
            agent_name="narrator_agent",
            language=language,
        )
        self._load_tts_config()           # 加载 TTS 配置
```

**关键设计**：
- `module_name="narrator"` → 在 `agents.yaml` 中有独立的 temperature/max_tokens
- Prompt 从 `co_writer/prompts/` 加载（与 EditAgent 共用目录，但不同文件）

### generate_script() 脚本生成

```
generate_script(content, style="friendly")
    │
    ├── 判断内容长度（>5000 chars 为长内容）
    │
    ├── 加载风格 Prompt:
    │     style_friendly  → 友好导师风格
    │     style_academic  → 学术讲座风格
    │     style_concise   → 高效精简风格
    │
    ├── 组装 system_prompt:
    │     generate_script_system_template
    │       + {style_prompt}
    │       + {length_instruction}  (长/短内容不同)
    │
    ├── 组装 user_prompt:
    │     长内容 → generate_script_user_long (截取前 8000 chars)
    │     短内容 → generate_script_user_short
    │
    ├── self.call_llm()  # 第 1 次 LLM 调用
    │
    ├── 截断脚本到 4000 chars（TTS 限制 4096）
    │     → 智能截断：在句号/感叹号/问号处断开
    │
    └── self._extract_key_points(content)  # 第 2 次 LLM 调用
          → 返回 JSON 数组（3-5 个要点字符串）
```

### generate_audio() TTS 音频生成

```
generate_audio(script, voice="alloy")
    │
    ├── 验证 TTS 配置（model, api_key, base_url）
    ├── 截断脚本到 4096 chars
    │
    ├── 根据 TTS_BINDING 选择客户端：
    │     "azure_openai" → AsyncAzureOpenAI
    │     "openai"       → AsyncOpenAI
    │
    ├── client.audio.speech.create(model, voice, input=script)
    ├── response.stream_to_file(audio_path)
    │
    └── 返回 audio_url: /api/outputs/co-writer/audio/{filename}
```

**可用语音**（OpenAI TTS）：alloy, echo, fable, onyx, nova, shimmer

### narrate() 完整流程

```python
async def narrate(content, style, voice, skip_audio=False):
    script_result = await self.generate_script(content, style)  # 脚本+要点
    if not skip_audio and self.tts_config:
        audio_result = await self.generate_audio(script, voice)  # TTS
    return {script, key_points, audio_url, ...}
```

---

## 路由层设计要点

### 单例模式 + 配置热刷新

```python
_edit_agent: EditAgent | None = None

def get_edit_agent() -> EditAgent:
    global _edit_agent
    lang = _current_language()
    if _edit_agent is None or _edit_agent.language != lang:
        _edit_agent = EditAgent(language=lang)   # 语言变化时重建
    _edit_agent.refresh_config()                  # 每次请求都刷新 LLM 配置
    return _edit_agent
```

- Agent 实例全局复用（避免每次请求都初始化）
- `refresh_config()` 保证用户在 Settings 中修改 LLM 配置后立即生效
- 语言切换时重建实例（Prompt 需要重新加载）

### API 端点汇总

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/edit` | 文本编辑（rewrite/shorten/expand） |
| POST | `/automark` | AI 自动标注 |
| POST | `/narrate` | 完整旁白（脚本+音频） |
| POST | `/narrate/script` | 仅生成脚本（快速预览） |
| GET | `/history` | 操作历史列表 |
| GET | `/history/{id}` | 单条操作详情 |
| GET | `/tool_calls/{id}` | 工具调用详情（RAG/Web） |
| POST | `/export/markdown` | 导出 Markdown |
| GET | `/tts/status` | TTS 服务状态 |
| GET | `/tts/voices` | 可用语音列表 |

---

## 数据存储

```
data/user/co-writer/
├── history.json          # 编辑操作历史（EditAgent 写入）
├── tool_calls/           # RAG/Web Search 调用记录
│   └── {operation_id}_{rag|web}.json
└── audio/                # TTS 音频文件
    └── narration_{audio_id}.mp3
```

---

## 与 ChatAgent 的对比

| 维度 | ChatAgent | Co-Writer |
|------|-----------|-----------|
| Agent 数量 | 1 个 | 2 个（EditAgent + NarratorAgent） |
| 通信协议 | WebSocket（流式） | HTTP REST（非流式） |
| 会话状态 | 有（SessionManager） | 无（每次请求独立） |
| RAG 使用 | 必须（核心能力） | 可选（上下文增强） |
| LLM 调用 | 1 次/请求 | EditAgent 1 次, NarratorAgent 2 次 |
| 额外服务 | 无 | TTS 音频生成 |
| 协作模式 | 单 Agent | 流水线式（Edit → Narrate） |

---

## 调试脚本

```
debug_scripts/coWriter/
├── 01_test_edit_agent.py          → EditAgent 基础编辑（初始化+Prompt+LLM）
├── 02_test_edit_automark.py       → EditAgent 自动标注
├── 03_test_narrator_script.py     → NarratorAgent 脚本生成（不含 TTS）
├── 04_test_agent_collaboration.py → 两个 Agent 协作流水线
└── 05_test_api_endpoint.py        → API 路由层端到端
```

---

## 支撑层笔记：LLM Factory

Co-Writer 阶段顺带了解的 `services/llm/` LLM 工厂：

```
BaseAgent.call_llm()
    → llm_complete() (factory.py)
        → _should_use_local(base_url)?
            是 → local_provider.complete()   # Ollama/LM Studio/vLLM
            否 → cloud_provider.complete()   # OpenAI/DeepSeek/Anthropic
        → 自动重试（tenacity，指数退避）
        → 错误映射（error_mapping.py）
```

**Factory 路由逻辑**：
- 通过 `is_local_llm_server(base_url)` 检测 URL
- localhost / 127.0.0.1 / 本地端口 → local_provider
- 已知云服务域名 → cloud_provider
- cloud_provider 内部根据 `binding` 再分流：openai / anthropic

**重试机制**（complete）：
- 使用 `tenacity` 库，指数退避
- 可重试：429（限流）、5xx（服务端错误）、超时
- 不重试：401（认证）、400（请求错误）
- 最大重试 5 次，最大延迟 120s

**重试机制**（stream）：
- 手动循环重试（因为 tenacity 不直接支持 async generator）
- 同样的重试策略

**TTS 配置加载**（`services/tts/config.py`）：
1. 优先从 UnifiedConfigManager 获取活跃 TTS 配置
2. 回退到 .env 环境变量：TTS_MODEL / TTS_API_KEY / TTS_URL
3. 缺少必要配置时抛出 ValueError
