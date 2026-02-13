# DeepTutor 后端架构分析

## 概述

DeepTutor 后端基于 **FastAPI** 构建，采用多 Agent 协作架构，提供 RESTful API 和 WebSocket 实时通信支持。

---

## 1. 技术栈

| 技术      | 版本   | 用途        |
| --------- | ------ | ----------- |
| Python    | 3.10+  | 主语言      |
| FastAPI   | 0.100+ | Web 框架    |
| Uvicorn   | -      | ASGI 服务器 |
| Pydantic  | -      | 数据验证    |
| WebSocket | -      | 实时通信    |

---

## 2. 项目结构

```
src/
├── api/                    # API 层
│   ├── main.py            # FastAPI 应用入口
│   ├── routers/           # 路由模块 (14个)
│   │   ├── solve.py       # 问题求解
│   │   ├── chat.py        # 聊天会话
│   │   ├── question.py    # 题目生成
│   │   ├── research.py    # 深度研究
│   │   ├── guide.py       # 引导学习
│   │   ├── knowledge.py   # 知识库管理
│   │   ├── co_writer.py   # 协作写作
│   │   ├── ideagen.py     # 创意生成
│   │   ├── notebook.py    # 笔记本
│   │   ├── dashboard.py   # 仪表盘
│   │   ├── settings.py    # 设置
│   │   ├── system.py      # 系统状态
│   │   ├── config.py      # 配置管理
│   │   └── agent_config.py # Agent 配置
│   └── utils/             # API 工具函数
├── agents/                 # Agent 系统
│   ├── base_agent.py      # 统一基类
│   ├── solve/             # 问题求解 (41个文件)
│   ├── research/          # 深度研究 (27个文件)
│   ├── guide/             # 引导学习 (16个文件)
│   ├── question/          # 题目生成 (16个文件)
│   ├── ideagen/           # 创意生成 (8个文件)
│   ├── co_writer/         # 协作写作 (8个文件)
│   └── chat/              # 聊天 (6个文件)
├── services/              # 服务层
│   ├── llm/               # LLM 客户端 (16个文件)
│   ├── embedding/         # 向量嵌入 (10个文件)
│   ├── rag/               # RAG 检索 (38个文件)
│   ├── prompt/            # 提示词管理
│   ├── search/            # 网络搜索 (11个文件)
│   ├── tts/               # 文字转语音
│   ├── config/            # 配置加载
│   └── setup/             # 初始化工具
├── config/                # 配置访问器
├── core/                  # 核心错误处理
└── logging/               # 统一日志系统
```

---

## 3. API 路由架构

### 3.1 路由注册 (`src/api/main.py`)

```python
app.include_router(solve.router, prefix="/api/v1", tags=["solve"])
app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
app.include_router(question.router, prefix="/api/v1/question", tags=["question"])
app.include_router(research.router, prefix="/api/v1/research", tags=["research"])
app.include_router(knowledge.router, prefix="/api/v1/knowledge", tags=["knowledge"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["dashboard"])
app.include_router(co_writer.router, prefix="/api/v1/co_writer", tags=["co_writer"])
app.include_router(notebook.router, prefix="/api/v1/notebook", tags=["notebook"])
app.include_router(guide.router, prefix="/api/v1/guide", tags=["guide"])
app.include_router(ideagen.router, prefix="/api/v1/ideagen", tags=["ideagen"])
app.include_router(settings.router, prefix="/api/v1/settings", tags=["settings"])
app.include_router(system.router, prefix="/api/v1/system", tags=["system"])
app.include_router(config.router, prefix="/api/v1/config", tags=["config"])
app.include_router(agent_config.router, prefix="/api/v1/agent-config", tags=["agent-config"])
```

### 3.2 主要 API 端点

| 模块      | 前缀                | 功能                      |
| --------- | ------------------- | ------------------------- |
| solve     | `/api/v1/solve`     | 问题求解 (WebSocket 流式) |
| chat      | `/api/v1/chat`      | 会话聊天                  |
| question  | `/api/v1/question`  | 题目生成                  |
| research  | `/api/v1/research`  | 深度研究                  |
| guide     | `/api/v1/guide`     | 引导学习                  |
| knowledge | `/api/v1/knowledge` | 知识库 CRUD               |
| co_writer | `/api/v1/co_writer` | 协作写作                  |
| ideagen   | `/api/v1/ideagen`   | 创意生成                  |

---

## 4. Agent 系统架构

### 4.1 BaseAgent 统一基类

```python
class BaseAgent(ABC):
    """
    所有 Agent 的统一基类，提供:
    - LLM 配置管理 (api_key, base_url, model)
    - Agent 参数 (temperature, max_tokens) 从 agents.yaml 加载
    - 提示词加载 (PromptManager)
    - 统一 LLM 调用接口
    - Token 跟踪
    - 日志记录
    """
```

**核心方法:**

- `process()` - 抽象方法，子类必须实现
- `call_llm()` - 统一 LLM 调用
- `call_llm_stream()` - 流式 LLM 调用

### 4.2 Solve 模块 - 双循环架构

```
┌─────────────────────────────────────────────────────────┐
│                    MainSolver                            │
├─────────────────────────────────────────────────────────┤
│  Analysis Loop          │  Solve Loop                   │
│  ┌─────────────────┐    │  ┌─────────────────────────┐  │
│  │ InvestigateAgent│    │  │ ManagerAgent            │  │
│  │ (工具调用决策)   │    │  │ (步骤规划)              │  │
│  └────────┬────────┘    │  └───────────┬─────────────┘  │
│           ↓             │              ↓                │
│  ┌─────────────────┐    │  ┌─────────────────────────┐  │
│  │ NoteAgent       │    │  │ SolveAgent              │  │
│  │ (信息压缩)       │    │  │ (推理求解)              │  │
│  └─────────────────┘    │  └───────────┬─────────────┘  │
│                         │              ↓                │
│                         │  ┌─────────────────────────┐  │
│                         │  │ PrecisionAnswerAgent    │  │
│                         │  │ (精确答案提取)           │  │
│                         │  └───────────┬─────────────┘  │
│                         │              ↓                │
│                         │  ┌─────────────────────────┐  │
│                         │  │ ResponseAgent           │  │
│                         │  │ (格式化输出)             │  │
│                         │  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 4.3 Research 模块 - 三阶段流水线

```
Planning Phase          Researching Phase         Reporting Phase
┌──────────────┐       ┌──────────────────┐      ┌──────────────┐
│RephraseAgent │──────▶│ DynamicTopicQueue│─────▶│ReportingAgent│
│(主题优化)     │       │   ┌──────────┐   │      │(报告生成)     │
└──────────────┘       │   │ManagerAgt│   │      └──────────────┘
       ↓               │   └────┬─────┘   │
┌──────────────┐       │        ↓         │
│DecomposeAgent│       │   ┌──────────┐   │
│(子主题分解)   │       │   │ResearchAgt│  │
└──────────────┘       │   └────┬─────┘   │
                       │        ↓         │
                       │   ┌──────────┐   │
                       │   │ NoteAgent│   │
                       │   └──────────┘   │
                       └──────────────────┘
```

### 4.4 其他模块

| 模块     | 主要 Agent                                             | 功能               |
| -------- | ------------------------------------------------------ | ------------------ |
| Guide    | LocateAgent, InteractiveAgent, ChatAgent, SummaryAgent | 引导式学习         |
| Question | RetrieveAgent, GenerateAgent, RelevanceAnalyzer        | 题目生成与验证     |
| IdeaGen  | IdeaGenerationWorkflow                                 | 创意生成流程       |
| CoWriter | EditAgent, NarratorAgent                               | 写作辅助与播客生成 |
| Chat     | ChatAgent, SessionManager                              | 轻量级对话         |

---

## 5. 服务层架构

### 5.1 LLM 服务 (`src/services/llm/`)

**支持的提供商 (Bindings):**

- `openai` - OpenAI API
- `azure_openai` - Azure OpenAI
- `anthropic` - Claude
- `deepseek` - DeepSeek
- `openrouter` - OpenRouter
- `groq` - Groq
- `together` - Together AI
- `mistral` - Mistral AI
- `ollama` - Ollama (本地)
- `lm_studio` - LM Studio (本地)
- `vllm` - vLLM
- `llama_cpp` - llama.cpp

**核心函数:**

```python
from src.services.llm import get_llm_client, complete, stream

llm = get_llm_client()
response = await complete(prompt, system_prompt)
async for chunk in stream(prompt, system_prompt):
    yield chunk
```

### 5.2 RAG 服务 (`src/services/rag/`)

**支持的 Pipeline (4 种):**

| Pipeline              | 底层技术              | 检索方式        | 适用场景                  |
| --------------------- | --------------------- | --------------- | ------------------------- |
| `llamaindex`          | LlamaIndex            | 纯向量检索      | 简单文本，最快            |
| `lightrag`            | LightRAG              | 知识图谱 + 向量 | 文本文档，中速            |
| `raganything`         | RAGAnything + MinerU  | 多模态 + 图谱   | 学术 PDF (公式/表格/图片) |
| `raganything_docling` | RAGAnything + Docling | 多模态 + 图谱   | Office/HTML 文档          |

**检索模式 (LightRAG/RAGAnything 内部):**

- `naive` - 纯向量检索 (Query → Embedding → 相似度搜索)
- `hybrid` - 混合检索 (向量 + BM25 关键词)
- `local` - 局部图谱检索 (实体关系)
- `global` - 全局图谱检索 (社区摘要)

**核心函数:**

```python
from src.services.rag import get_pipeline

# 获取 pipeline (选择四种之一)
pipeline = get_pipeline("lightrag")  # 或 llamaindex/raganything/raganything_docling
result = await pipeline.search("query", "kb_name", top_k=10)
```

### 5.3 Embedding 服务 (`src/services/embedding/`)

**支持的提供商:**

- `openai` - text-embedding-3-small/large
- `azure_openai` - Azure 嵌入模型
- `jina` - Jina Embeddings
- `cohere` - Cohere Embed
- `huggingface` - HuggingFace 模型
- `ollama` - Ollama 嵌入
- `lm_studio` - LM Studio 嵌入

### 5.4 Prompt 服务 (`src/services/prompt/`)

```python
from src.services.prompt import get_prompt_manager

pm = get_prompt_manager()
prompts = pm.load_prompts(
    module_name="solve",
    agent_name="investigate_agent",
    language="zh"
)
```

---

## 6. 配置系统

### 6.1 配置文件

| 文件                 | 用途                                 |
| -------------------- | ------------------------------------ |
| `config/main.yaml`   | 主配置 (路径、工具、日志、模块参数)  |
| `config/agents.yaml` | Agent 参数 (temperature, max_tokens) |
| `.env`               | 环境变量 (API Keys, Ports)           |

### 6.2 配置加载

```python
from src.services.config import load_config_with_main, get_agent_params

# 加载主配置
config = load_config_with_main("main.yaml", project_root)

# 获取 Agent 参数
params = get_agent_params("solve")
# → {"temperature": 0.5, "max_tokens": 4096}
```

---

## 7. 关键特性

### 7.1 WebSocket 流式输出

Solve 模块通过 WebSocket 实现实时推理过程展示:

```python
@router.websocket("/ws/solve/{session_id}")
async def websocket_solve(websocket: WebSocket, session_id: str):
    await websocket.accept()
    async for event in solver.solve_stream(question):
        await websocket.send_json(event)
```

### 7.2 静态文件服务

生成的文件 (代码执行结果、图片等) 通过静态路由提供:

```python
app.mount("/api/outputs", StaticFiles(directory="data/user"), name="outputs")
```

### 7.3 配置一致性验证

启动时验证 Agent 工具配置与主配置一致:

```python
def validate_tool_consistency():
    main_tools = set(main_config.get("solve", {}).get("valid_tools", []))
    agent_tools = set(agents_config.get("investigate", {}).get("valid_tools", []))
    if not agent_tools.issubset(main_tools):
        raise RuntimeError("Configuration Drift Detected")
```

---

## 8. 数据存储

```
data/
├── knowledge_bases/        # 知识库存储
└── user/                   # 用户数据
    ├── solve/              # 求解结果
    ├── question/           # 生成题目
    ├── research/           # 研究报告
    ├── guide/              # 学习会话
    ├── notebook/           # 笔记本
    ├── co-writer/          # 写作内容
    ├── logs/               # 系统日志
    └── run_code_workspace/ # 代码执行
```

---

## 总结

DeepTutor 后端采用 **多 Agent 协作 + 服务层抽象** 的架构设计:

1. **API 层** - FastAPI 提供 RESTful 和 WebSocket 接口
2. **Agent 层** - 统一 BaseAgent 基类，模块化 Agent 实现
3. **服务层** - 抽象 LLM/Embedding/RAG/Search 等能力
4. **配置层** - YAML + 环境变量，支持热重载

这种架构实现了**高内聚低耦合**，便于扩展新 Agent 和切换底层服务提供商。
