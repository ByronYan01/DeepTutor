# DeepTutor 源码学习文档

> 🎯 目标：1小时跑通Demo，3小时看懂核心模块

---

## 一、项目全局概览（10分钟快速了解）

### 1. 核心技术栈

| 技术 | 作用 | 对应文件 |
|:---|:---|:---|
| **FastAPI** | 后端Web框架，提供REST API和WebSocket实时通信 | `src/api/main.py` |
| **OpenAI SDK** | 调用大语言模型（GPT等），核心推理引擎 | `src/services/llm/` |
| **RAGAnything** | 默认RAG引擎，负责文档解析、向量化和检索 | `src/services/rag/` |
| **LlamaIndex** | 可选RAG引擎，提供另一种文档索引和检索方案 | `requirements.txt` |
| **PyMuPDF** | PDF文件解析（快速提取文本） | `src/knowledge/` |
| **Docling** | 复杂文档解析（Office/HTML等格式） | `requirements.txt` |
| **Next.js + React** | 前端框架，提供Web交互界面 | `web/` |
| **WebSocket** | 实现求解过程的实时流式输出 | `src/api/routers/solve.py` |
| **PyYAML** | 加载Agent配置文件（温度、Token上限等） | `config/agents.yaml` |
| **tiktoken** | Token计数（估算API调用费用） | `src/agents/solve/utils/` |

### 2. 源码目录结构

```
DeepTutor/
├── src/                          # 🔥 核心源码（重点看这里）
│   ├── api/                      # API层：FastAPI入口和路由
│   │   ├── main.py               # ⭐ 应用入口，注册所有路由
│   │   └── routers/              # 各功能模块的API路由
│   │       ├── solve.py          # ⭐ 求解功能的WebSocket端点
│   │       ├── chat.py           # 聊天功能路由
│   │       ├── knowledge.py      # 知识库管理路由
│   │       └── ...               # 其他：question/research/guide等
│   ├── agents/                   # Agent层：核心智能体
│   │   ├── base_agent.py         # ⭐ 所有Agent的基类（LLM调用封装）
│   │   ├── solve/                # ⭐⭐ 核心求解模块（双循环架构）
│   │   │   ├── main_solver.py    # 🔥 主控制器（调度所有Agent）
│   │   │   ├── analysis_loop/    # 分析循环（调研+笔记）
│   │   │   │   ├── investigate_agent.py  # 调研Agent
│   │   │   │   └── note_agent.py         # 笔记Agent
│   │   │   ├── solve_loop/       # 求解循环（规划+执行+校验）
│   │   │   │   ├── manager_agent.py      # 规划Agent
│   │   │   │   ├── solve_agent.py        # 执行Agent
│   │   │   │   ├── tool_agent.py         # 工具调用Agent
│   │   │   │   └── response_agent.py     # 输出格式化Agent
│   │   │   ├── memory/           # 记忆系统（JSON持久化）
│   │   │   └── prompts/          # 提示词模板
│   │   ├── chat/                 # 聊天Agent
│   │   ├── research/             # 深度研究Agent
│   │   ├── question/             # 题目生成Agent
│   │   └── guide/                # 学习引导Agent
│   ├── services/                 # 服务层：基础设施
│   │   ├── rag/                  # ⭐ RAG服务（检索增强生成）
│   │   │   ├── service.py        # 统一RAG入口
│   │   │   ├── pipeline.py       # 可组合Pipeline
│   │   │   └── factory.py        # Pipeline工厂
│   │   ├── llm/                  # LLM服务（大模型调用）
│   │   ├── embedding/            # 嵌入向量服务
│   │   └── search/               # Web搜索服务
│   ├── tools/                    # 工具层：Agent可调用的工具
│   │   ├── rag_tool.py           # RAG检索工具
│   │   ├── web_search.py         # Web搜索工具
│   │   └── code_executor.py      # 代码执行工具
│   └── knowledge/                # 知识库管理
│       ├── manager.py            # 知识库CRUD
│       └── add_documents.py      # 文档导入
├── config/                       # 配置文件
│   ├── main.yaml                 # 主配置
│   └── agents.yaml               # Agent参数配置
├── web/                          # 前端（Next.js）
├── data/                         # 数据存储（知识库+用户输出）
└── scripts/                      # 启动脚本
```

### 3. 核心工作流（一句话）

```
用户输入问题 → WebSocket接收 → MainSolver调度
→ 【分析循环】InvestigateAgent检索RAG/Web → NoteAgent整理笔记
→ 【求解循环】ManagerAgent规划步骤 → SolveAgent逐步求解 → ResponseAgent格式化输出
→ 附带引用来源 → WebSocket流式返回前端
```

### 4. 本地运行最简步骤

```bash
# 1. 克隆 + 环境
git clone https://github.com/HKUDS/DeepTutor.git && cd DeepTutor
cp .env.example .env    # 编辑.env填入你的LLM API Key

# 2. 安装依赖
pip install -r requirements.txt
cd web && npm install && cd ..

# 3. 启动
python scripts/start_web.py    # 前端+后端一键启动
# 访问 http://localhost:3782
```

---

## 二、分模块源码解析

### 模块1：入口文件（请求怎么进来的）

**核心文件**：[main.py](file:///Users/macbook/Desktop/shensi/DeepTutor/src/api/main.py)

**核心逻辑**：

```python
# src/api/main.py（简化版）

# 1. 创建FastAPI应用
app = FastAPI(title="DeepTutor API")

# 2. 注册所有功能模块的路由
app.include_router(solve.router, prefix="/api/v1")   # 求解
app.include_router(chat.router, prefix="/api/v1")     # 聊天
app.include_router(knowledge.router, prefix="/api/v1/knowledge")  # 知识库
# ... 共14个路由模块

# 3. 启动时校验配置一致性
@asynccontextmanager
async def lifespan(app):
    validate_tool_consistency()  # 检查agents.yaml和main.yaml工具配置是否匹配
    # 初始化LLM客户端（设置环境变量给RAG引擎用）
    llm_client = get_llm_client()
    yield
```

**用户请求如何到达求解Agent**：

```python
# src/api/routers/solve.py（简化版）

@router.websocket("/solve")  # WebSocket端点，支持实时流式输出
async def websocket_solve(websocket):
    data = await websocket.receive_json()     # 接收：{question, kb_name}
    
    solver = MainSolver(kb_name=kb_name)      # 创建主控制器
    await solver.ainit()                       # 异步初始化（加载配置、创建Agent）
    
    result = await solver.solve(question)      # 🔥 执行双循环求解
    
    await websocket.send_json({               # 返回结果
        "type": "result",
        "final_answer": result["final_answer"]
    })
```

**🔍 新手断点建议**：
1. `src/api/routers/solve.py` 第149行 — `data = await websocket.receive_json()` — 看用户输入了什么
2. `src/api/routers/solve.py` 第301行 — `result = await solver.solve(question)` — 求解入口
3. `src/api/main.py` 第132行 — `validate_tool_consistency()` — 理解配置校验

---

### 模块2：RAG基础模块（知识怎么检索的）

**核心文件**：
- [service.py](file:///Users/macbook/Desktop/shensi/DeepTutor/src/services/rag/service.py) — 统一RAG入口
- [pipeline.py](file:///Users/macbook/Desktop/shensi/DeepTutor/src/services/rag/pipeline.py) — 可组合Pipeline
- [rag_tool.py](file:///Users/macbook/Desktop/shensi/DeepTutor/src/tools/rag_tool.py) — Agent调用的工具函数

**核心逻辑**：

```python
# src/services/rag/service.py（简化版）

class RAGService:
    """统一RAG服务入口"""
    
    def __init__(self, provider="raganything"):
        # provider可以是 raganything / llamaindex / lightrag
        self.provider = provider
    
    async def initialize(self, kb_name, file_paths):
        """初始化知识库：解析文档 → 切片 → 向量化 → 存储索引"""
        pipeline = get_pipeline(self.provider)
        return await pipeline.initialize(kb_name, file_paths)
    
    async def search(self, query, kb_name, mode="hybrid"):
        """检索：输入问题 → 向量相似度匹配 → 返回相关文档片段"""
        # 从知识库元数据获取该库使用的RAG引擎
        provider = self._get_provider_for_kb(kb_name)
        pipeline = get_pipeline(provider)
        result = await pipeline.search(query, kb_name, mode=mode)
        return result  # {"query": ..., "answer": ..., "content": ...}
```

**RAG Pipeline的4个阶段**：

```python
# src/services/rag/pipeline.py（简化版）

class RAGPipeline:
    """可组合的RAG管道（像搭积木一样拼接组件）"""
    
    async def initialize(self, kb_name, file_paths):
        # 阶段1：解析文档（PDF用专门解析器，TXT直接读取）
        documents = []
        for path in file_paths:
            doc = await self._parser.process(path)
            documents.append(doc)
        
        # 阶段2：切片（把长文档切成小段落）
        for chunker in self._chunkers:
            for doc in documents:
                doc.chunks = await chunker.process(doc)
        
        # 阶段3：向量化（把文本转成数字向量，方便计算相似度）
        for doc in documents:
            await self._embedder.process(doc)
        
        # 阶段4：建索引（存入向量数据库，供后续检索）
        await asyncio.gather(*[
            indexer.process(kb_name, documents) for indexer in self._indexers
        ])
```

**🧪 新手验证方法（10行复刻RAG检索）**：

```python
import asyncio
from src.tools.rag_tool import rag_search

async def test():
    result = await rag_search(
        query="什么是机器学习？",
        kb_name="你的知识库名",  # 需要先在Web界面创建
        mode="naive"             # naive=简单检索, hybrid=混合检索
    )
    print(f"检索结果: {result['answer'][:200]}")

asyncio.run(test())
```

---

### 模块3：知识增强层（笔记怎么整理的）

**核心文件**：
- [note_agent.py](file:///Users/macbook/Desktop/shensi/DeepTutor/src/agents/solve/analysis_loop/note_agent.py) — 笔记Agent

**核心逻辑**：NoteAgent拿到InvestigateAgent检索回来的原始文本，通过LLM将其压缩成结构化摘要，并提取引用来源。

```python
# src/agents/solve/analysis_loop/note_agent.py（简化版）

class NoteAgent(BaseAgent):
    """笔记Agent：把检索到的原始内容压缩成结构化笔记"""
    
    async def process(self, question, memory, new_knowledge_ids, citation_memory):
        for cite_id in new_knowledge_ids:
            # 1. 从记忆中取出原始检索内容
            knowledge_item = memory.find_by_cite_id(cite_id)
            
            # 2. 构建上下文（问题 + 工具类型 + 原始内容）
            context = {
                "question": question,
                "tool_type": knowledge_item.tool_type,   # 如 "rag_naive"
                "raw_result": knowledge_item.raw_result,  # 检索到的原文
            }
            
            # 3. 调用LLM生成结构化摘要（要求输出JSON格式）
            response = await self.call_llm(
                user_prompt=template.format(**context),
                system_prompt=system_prompt,
                response_format={"type": "json_object"},  # 强制JSON输出
            )
            
            # 4. 解析JSON，更新记忆
            parsed = extract_json_from_text(response)
            # parsed = {"summary": "...", "citations": [{source: ...}]}
            memory.update_knowledge_summary(cite_id, parsed["summary"])
            citation_memory.update_citation(cite_id, content=parsed["summary"])
```

> 💡 **通俗理解**：NoteAgent就像一个"笔记助手"——InvestigateAgent帮你从图书馆找回一堆资料，NoteAgent帮你划重点、写摘要、标注出处。

---

### 模块4：推理增强层 + Agent模块（双循环怎么工作的）

这是DeepTutor最核心的模块，采用**双循环架构**：先调研收集资料，再分步求解。

**核心文件**：
- [main_solver.py](file:///Users/macbook/Desktop/shensi/DeepTutor/src/agents/solve/main_solver.py) — 🔥 主控制器
- [investigate_agent.py](file:///Users/macbook/Desktop/shensi/DeepTutor/src/agents/solve/analysis_loop/investigate_agent.py) — 调研Agent
- [manager_agent.py](file:///Users/macbook/Desktop/shensi/DeepTutor/src/agents/solve/solve_loop/manager_agent.py) — 规划Agent
- [solve_agent.py](file:///Users/macbook/Desktop/shensi/DeepTutor/src/agents/solve/solve_loop/solve_agent.py) — 求解Agent
- [response_agent.py](file:///Users/macbook/Desktop/shensi/DeepTutor/src/agents/solve/solve_loop/response_agent.py) — 输出Agent

**双循环架构图**：

```
┌─────────────────── 分析循环（Analysis Loop）───────────────────┐
│                                                                │
│  InvestigateAgent ──→ NoteAgent ──→ 够了吗？──→ 不够→ 继续循环 │
│  （检索RAG/Web）      （整理笔记）     ↓                        │
│                                     够了                       │
└────────────────────────────────────────┼───────────────────────┘
                                         ↓
┌─────────────────── 求解循环（Solve Loop）──────────────────────┐
│                                                                │
│  ManagerAgent → SolveAgent → ToolAgent → ResponseAgent         │
│  （规划步骤）   （逐步求解）  （调用工具）  （格式化输出）         │
│                     ↑                                          │
│                     └──── 需要更多信息？→ 工具再查一次            │
└────────────────────────────────────────────────────────────────┘
```

**核心代码（双循环Pipeline）**：

```python
# src/agents/solve/main_solver.py（简化版）

class MainSolver:
    async def _run_dual_loop_pipeline(self, question, output_dir):
        
        # ====== 分析循环 ======
        investigate_memory = InvestigateMemory()  # 创建调研记忆
        
        for i in range(max_iterations):  # 默认最多5轮
            # 1. InvestigateAgent：决定用什么工具、查什么内容
            result = await self.investigate_agent.process(
                question=question,
                memory=investigate_memory,
                kb_name=self.kb_name,  # 指定知识库
            )
            # result包含: 用了哪些工具、查询了什么、是否可以停止
            
            # 2. NoteAgent：把检索结果整理成笔记
            if result["knowledge_item_ids"]:
                await self.note_agent.process(
                    question=question,
                    memory=investigate_memory,
                    new_knowledge_ids=result["knowledge_item_ids"],
                )
            
            # 3. 判断是否资料已足够
            if result["should_stop"]:
                break  # 资料够了，进入求解循环
        
        # ====== 求解循环 ======
        solve_memory = SolveMemory()
        
        # 4. ManagerAgent：基于收集的资料，规划求解步骤
        plan = await self.manager_agent.process(
            question=question,
            investigate_memory=investigate_memory,
            solve_memory=solve_memory,
        )
        # plan会在solve_memory中创建多个SolveChainStep
        
        # 5. 逐步执行每个步骤
        for step in solve_memory.solve_chains:
            # SolveAgent：针对当前步骤，决定是否需要额外工具
            solve_result = await self.solve_agent.process(
                question=question,
                current_step=step,
                solve_memory=solve_memory,
            )
            # 如果需要工具（如代码执行），ToolAgent会执行
            if solve_result["requested_calls"]:
                await self._execute_tool_calls(step, solve_memory)
        
        # 6. ResponseAgent：为每个步骤生成正式回答
        for step in solve_memory.solve_chains:
            await self.response_agent.process(
                question=question, step=step,
                solve_memory=solve_memory,
                investigate_memory=investigate_memory,
            )
        
        # 7. 拼接所有步骤的回答 + 引用来源
        final_answer = "\n\n".join(step.step_response for step in completed_steps)
        final_answer += "\n\n---\n\n" + citation_memory.format_citations_markdown()
        
        return {"final_answer": final_answer}
```

**InvestigateAgent可以调用的工具**：

| 工具 | 作用 |
|:---|:---|
| `rag_naive` | 简单RAG检索（关键词匹配） |
| `rag_hybrid` | 混合RAG检索（语义+关键词） |
| `web_search` | 网络搜索（Perplexity/Tavily等） |
| `query_item` | 精确检索知识库中的编号条目 |
| `code_execution` | 执行Python代码（计算/画图） |

**🔍 新手断点建议**：
1. `main_solver.py` 第419行 — `investigate_result = await self.investigate_agent.process(...)` — 看分析循环每轮做了什么
2. `main_solver.py` 第568行 — `plan_result = await self.manager_agent.process(...)` — 看规划出了哪些步骤
3. `main_solver.py` 第632行 — `solve_result = await self.solve_agent.process(...)` — 看每步如何求解

---

### 模块5：输出模块（答案怎么格式化的）

**核心文件**：[response_agent.py](file:///Users/macbook/Desktop/shensi/DeepTutor/src/agents/solve/solve_loop/response_agent.py)

**核心逻辑**：

```python
# src/agents/solve/solve_loop/response_agent.py（简化版）

class ResponseAgent(BaseAgent):
    """输出格式化Agent：把求解过程转为带引用的Markdown回答"""
    
    async def process(self, question, step, solve_memory,
                      investigate_memory, citation_memory, 
                      accumulated_response=""):
        # 1. 收集当前步骤的所有材料（工具调用结果、代码输出等）
        tool_materials = self._format_tool_materials(step)
        
        # 2. 收集可用引用
        available_cites = self._format_available_cite(step, investigate_memory)
        
        # 3. 将之前已生成的回答也传入（避免重复）
        context = {
            "question": question,
            "step_target": step.step_target,
            "tool_materials": tool_materials,
            "available_citations": available_cites,
            "previous_response": accumulated_response,
        }
        
        # 4. 调用LLM生成格式化回答（Markdown格式，含引用标记）
        response = await self.call_llm(...)
        
        # 5. 提取使用了哪些引用
        used_citations = self._extract_used_citations(response, step)
        step.step_response = response
        step.used_citations = used_citations
```

**输出文件结构**（每次求解自动保存）：

```
data/user/solve/solve_20260213_220800/
├── investigate_memory.json    # 分析循环的完整记忆
├── solve_chain.json           # 求解循环的步骤链
├── citation_memory.json       # 引用管理
├── final_answer.md            # 最终答案（Markdown）
├── cost_report.json           # API调用费用
├── task.log                   # 运行日志
└── artifacts/                 # 代码执行产物（图片等）
```

---

## 三、新手学习技巧（避坑指南）

### 🎯 3个高效断点调试位置

| 位置 | 文件 | 行号 | 看什么 |
|:---|:---|:---:|:---|
| ① 请求入口 | `src/api/routers/solve.py` | 149 | 用户发送了什么问题 |
| ② 分析循环 | `src/agents/solve/main_solver.py` | 419 | InvestigateAgent检索了什么 |
| ③ 求解执行 | `src/agents/solve/main_solver.py` | 632 | SolveAgent每步做了什么 |

### 🙈 2个可忽略的非核心细节

1. **前端代码**（`web/`）— 纯UI展示，不影响理解后端逻辑
2. **日志/监控配置**（`src/logging/`、`PerformanceMonitor`）— 辅助功能，可跳过

### 🚀 1个最小化复刻方案

只保留"RAG检索 + 分步推理"两个核心，30行Python即可复刻核心逻辑：

```python
"""DeepTutor核心逻辑极简复刻（伪代码）"""
import asyncio
from openai import AsyncOpenAI

client = AsyncOpenAI(api_key="你的KEY", base_url="你的API地址")

async def mini_deeptutor(question: str, context_docs: str):
    # 第1步：分析循环 —— 让LLM判断需要什么信息
    analysis = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "你是知识调研员，分析回答这个问题还需要什么信息"},
            {"role": "user", "content": f"问题：{question}\n已有资料：{context_docs}"},
        ],
    )
    
    # 第2步：求解循环 —— 基于资料分步回答
    solution = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "基于提供的资料，分步骤回答问题，每步标注引用来源"},
            {"role": "user", "content": f"问题：{question}\n资料：{context_docs}\n分析：{analysis.choices[0].message.content}"},
        ],
    )
    return solution.choices[0].message.content

# 使用示例
result = asyncio.run(mini_deeptutor(
    "什么是RAG？",
    "RAG全称Retrieval-Augmented Generation，是一种结合检索和生成的AI技术..."
))
print(result)
```

> 💡 对比这30行代码和DeepTutor的完整实现，你会发现DeepTutor本质上就是把这个简单逻辑**拆成多个专业Agent**、加上**记忆系统**和**引用追踪**，从而实现更可靠的推理。
