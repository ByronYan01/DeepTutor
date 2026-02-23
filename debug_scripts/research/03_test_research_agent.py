#!/usr/bin/env python
"""
Layer 3: ResearchAgent 研究决策循环（多组件协作）
=========================================
测试 ResearchAgent 的核心流程：
  1. 初始化 ResearchAgent + NoteAgent + ManagerAgent + CitationManager
  2. 构造 TopicBlock 和 DynamicTopicQueue
  3. 单独调用 check_sufficiency() — 判断当前知识是否充分
  4. 单独调用 generate_query_plan() — 选择工具 + 生成查询
  5. 完整调用 ResearchAgent.process() — 单 TopicBlock 研究循环
     - 使用模拟 call_tool_callback，返回硬编码 RAG 结果（不依赖真实 RAG）
     - 观察迭代次数、工具选择、知识积累过程

调用链路（ResearchAgent.process 内循环）：
  while iteration < max_iterations:
    ① check_sufficiency(topic, overview, current_knowledge, iteration)
       → LLM 判断知识是否充分 → {is_sufficient, reason, covered_dimensions}
       → 充分则 break

    ② generate_query_plan(topic, overview, current_knowledge, iteration)
       → LLM 选择工具 + 生成查询 → {query, tool_type, rationale}
       → 可能发现新主题 → manager_agent.add_new_topic()

    ③ call_tool_callback(tool_type, query) → raw_answer

    ④ citation_manager.get_next_citation_id(stage="research", block_id=...)

    ⑤ note_agent.process(tool_type, query, raw_answer, citation_id, topic)
       → LLM 生成摘要 → ToolTrace

    ⑥ topic_block.add_tool_trace(trace)
    ⑦ current_knowledge += trace.summary

输入：硬编码的主题和模拟工具返回
输出：研究结果字典 {block_id, iterations, final_knowledge, tools_used, status}
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env", override=False)


# -------------------------------------------------------
# 模拟工具回调：返回硬编码结果（不依赖真实 RAG/Web）
# -------------------------------------------------------
MOCK_TOOL_RESPONSES = {
    "rag_hybrid": json.dumps({
        "answer": (
            "自注意力（Self-Attention）是 Transformer 的核心机制。"
            "核心公式：Attention(Q,K,V) = softmax(QK^T / √d_k) V。"
            "Q、K、V 由输入 X 经线性变换得到：Q=XW_Q, K=XW_K, V=XW_V。"
            "缩放因子 √d_k 防止点积过大导致 softmax 梯度消失。"
            "多头注意力将 Q/K/V 分成 h 个头并行计算，每个头 d_k = d_model/h，"
            "最后拼接：MultiHead = Concat(head_1,...,head_h) W_O。"
            "优势：1) 并行计算 2) 全局依赖建模 3) 可解释性。"
        ),
        "chunks": [
            {"id": "ch_1", "content": "注意力机制基本原理", "score": 0.95},
            {"id": "ch_2", "content": "多头注意力实现", "score": 0.88},
        ],
        "mode": "hybrid",
    }, ensure_ascii=False),

    "rag_naive": json.dumps({
        "answer": (
            "位置编码（Positional Encoding）为 Transformer 引入序列顺序信息。"
            "Sinusoidal 编码使用正弦和余弦函数：PE(pos,2i) = sin(pos/10000^(2i/d_model))，"
            "PE(pos,2i+1) = cos(pos/10000^(2i/d_model))。"
            "也可使用可学习位置编码（Learnable PE），效果相似但更灵活。"
            "RoPE（Rotary Position Embedding）通过旋转矩阵编码相对位置，"
            "被 LLaMA、GPT-NeoX 等现代模型广泛采用。"
        ),
        "chunks": [{"id": "ch_3", "content": "位置编码", "score": 0.82}],
        "mode": "naive",
    }, ensure_ascii=False),

    "paper_search": json.dumps({
        "papers": [{
            "title": "Attention Is All You Need",
            "authors": ["Vaswani et al."],
            "year": 2017,
            "abstract": "We propose the Transformer, a model architecture based solely on attention mechanisms.",
            "venue": "NeurIPS 2017",
        }]
    }, ensure_ascii=False),

    "web_search": json.dumps({
        "results": [{
            "title": "Transformer 最新进展",
            "url": "https://example.com/transformer-advances",
            "snippet": "Vision Transformer (ViT) 将 Transformer 应用于计算机视觉领域...",
        }]
    }, ensure_ascii=False),
}

# 调用计数器
call_counter = {"count": 0}

async def mock_call_tool(tool_type: str, query: str) -> str:
    """模拟工具调用回调"""
    call_counter["count"] += 1
    print(f"    🔧 [模拟] 工具调用 #{call_counter['count']}: tool={tool_type}, query={query[:60]}...")

    # 根据 tool_type 返回对应的模拟数据
    result = MOCK_TOOL_RESPONSES.get(tool_type, MOCK_TOOL_RESPONSES["rag_hybrid"])
    return result


async def main():
    print("=" * 60)
    print("Layer 3: ResearchAgent 研究决策循环测试")
    print("=" * 60)

    # -------------------------------------------------------
    # Step 1: 初始化所有组件
    # -------------------------------------------------------
    print("\n--- Step 1: 初始化所有组件 ---")

    from src.agents.research.agents.manager_agent import ManagerAgent
    from src.agents.research.agents.note_agent import NoteAgent
    from src.agents.research.agents.research_agent import ResearchAgent
    from src.agents.research.data_structures import DynamicTopicQueue, TopicBlock
    from src.agents.research.utils.citation_manager import CitationManager
    from src.services.llm import get_llm_config

    llm_config = get_llm_config()
    print(f"  LLM: {llm_config.api_key[:8]}... @ {llm_config.base_url[:50]}...")

    # 构造配置（模拟 quick 预设：1 次迭代，仅 RAG 工具）
    config = {
        "system": {"language": "zh"},
        "researching": {
            "max_iterations": 2,       # 限制迭代次数以快速测试
            "iteration_mode": "fixed",
            "enable_rag_hybrid": True,
            "enable_rag_naive": True,
            "enable_paper_search": False,  # 关闭以简化测试
            "enable_web_search": False,
            "enable_run_code": False,
            "new_topic_min_score": 0.85,
        },
        "tools": {"web_search": {"enabled": False}},
    }

    # 初始化各组件
    research_agent = ResearchAgent(
        config=config,
        api_key=llm_config.api_key,
        base_url=llm_config.base_url,
    )
    note_agent = NoteAgent(
        config=config,
        api_key=llm_config.api_key,
        base_url=llm_config.base_url,
    )
    manager_agent = ManagerAgent(
        config=config,
        api_key=llm_config.api_key,
        base_url=llm_config.base_url,
    )

    # 创建队列和 CitationManager
    with tempfile.TemporaryDirectory() as tmp_dir:
        cache_dir = Path(tmp_dir)

        queue = DynamicTopicQueue(research_id="test_research_layer3", max_length=5)
        manager_agent.set_queue(queue)

        citation_manager = CitationManager(
            research_id="test_research_layer3",
            cache_dir=cache_dir,
        )

        print(f"\n  组件初始化完成:")
        print(f"    ResearchAgent: model={research_agent.get_model()}, max_iter={research_agent.max_iterations}, mode={research_agent.iteration_mode}")
        print(f"    NoteAgent:     model={note_agent.get_model()}")
        print(f"    ManagerAgent:  queue={queue.research_id}")
        print(f"    CitationManager: cache_dir={cache_dir}")

        # -------------------------------------------------------
        # Step 2: 检查 Prompt 加载
        # -------------------------------------------------------
        print("\n--- Step 2: 检查 ResearchAgent Prompt ---")

        system_prompt = research_agent.get_prompt("system", "role")
        check_suff_prompt = research_agent.get_prompt("process", "check_sufficiency")
        gen_plan_prompt = research_agent.get_prompt("process", "generate_query_plan")

        prompts = {
            "system.role": system_prompt,
            "process.check_sufficiency": check_suff_prompt,
            "process.generate_query_plan": gen_plan_prompt,
        }
        for name, p in prompts.items():
            if p:
                print(f"  ✅ {name}: {len(p)} chars")
            else:
                print(f"  ❌ {name}: 未加载!")

        # -------------------------------------------------------
        # Step 3: 观察辅助方法输出
        # -------------------------------------------------------
        print("\n--- Step 3: 观察辅助方法输出 ---")

        # 可用工具列表
        tools_text = research_agent._generate_available_tools_text()
        print(f"  可用工具列表:")
        for line in tools_text.split("\n"):
            print(f"    {line}")

        # 工具阶段指导
        phase_guidance = research_agent._generate_tool_phase_guidance()
        print(f"\n  工具阶段指导（前 200 字）:")
        for line in phase_guidance[:200].split("\n"):
            print(f"    {line}")

        # 研究深度指导
        depth_guidance = research_agent._generate_research_depth_guidance(iteration=1, used_tools=[])
        print(f"\n  研究深度指导（iteration=1）:")
        for line in depth_guidance[:300].split("\n"):
            print(f"    {line}")

        # -------------------------------------------------------
        # Step 4: 构造 TopicBlock 并添加到队列
        # -------------------------------------------------------
        print("\n--- Step 4: 构造 TopicBlock ---")

        block = queue.add_block(
            sub_topic="Transformer 自注意力机制",
            overview="深入研究 Transformer 中自注意力（Self-Attention）的计算原理、多头注意力及其变体",
        )
        queue.mark_researching(block.block_id)
        manager_agent.set_primary_topic("Transformer 架构深度研究")

        print(f"  block_id:    {block.block_id}")
        print(f"  sub_topic:   {block.sub_topic}")
        print(f"  overview:    {block.overview[:50]}...")
        print(f"  status:      {block.status.value}")

        # -------------------------------------------------------
        # Step 5: 调用 ResearchAgent.process() 完整循环
        # -------------------------------------------------------
        print("\n--- Step 5: 调用 ResearchAgent.process() ---")
        print(f"  max_iterations: {research_agent.max_iterations}")
        print(f"  iteration_mode: {research_agent.iteration_mode}")
        print(f"  使用模拟工具回调（不调用真实 RAG）")
        print(f"  开始研究循环...\n")

        try:
            result = await research_agent.process(
                topic_block=block,
                call_tool_callback=mock_call_tool,
                note_agent=note_agent,
                citation_manager=citation_manager,
                queue=queue,
                manager_agent=manager_agent,
                config=config,
            )

            print(f"\n  ✅ 研究循环完成!")
            print(f"    block_id:        {result['block_id']}")
            print(f"    iterations:      {result['iterations']}")
            print(f"    status:          {result['status']}")
            print(f"    tools_used:      {result['tools_used']}")
            print(f"    final_knowledge: {len(result['final_knowledge'])} chars")

            # 查看查询历史
            if result.get("queries_used"):
                print(f"\n  查询历史:")
                for i, q in enumerate(result["queries_used"], 1):
                    print(f"    [{i}] tool={q['tool_type']}, query={q['query'][:50]}...")
                    print(f"        rationale: {q.get('rationale', '')[:80]}...")

        except Exception as e:
            print(f"\n  ❌ 研究循环失败: {e}")
            import traceback
            traceback.print_exc()

        # -------------------------------------------------------
        # Step 6: 检查研究结果
        # -------------------------------------------------------
        print("\n--- Step 6: 检查研究结果 ---")

        # TopicBlock 状态
        print(f"  TopicBlock 状态:")
        print(f"    tool_traces: {len(block.tool_traces)} 条")
        print(f"    iteration_count: {block.iteration_count}")
        for i, trace in enumerate(block.tool_traces):
            print(f"    [{i+1}] {trace.citation_id} | {trace.tool_type} | summary={len(trace.summary)} chars")

        # 引用管理器状态
        all_citations = citation_manager.get_all_citations()
        print(f"\n  CitationManager 状态:")
        print(f"    总引用数: {len(all_citations)}")
        for cid, info in all_citations.items():
            print(f"    {cid}: tool={info.get('tool_type', '?')}, query={info.get('query', '')[:50]}...")

        # 队列状态
        stats = queue.get_statistics()
        print(f"\n  队列状态:")
        for k, v in stats.items():
            print(f"    {k}: {v}")

        # -------------------------------------------------------
        # Step 7: Token 统计
        # -------------------------------------------------------
        print("\n--- Step 7: Token 统计 ---")

        from src.agents.base_agent import BaseAgent
        stats = BaseAgent.get_stats("research")
        print(f"  总调用次数:    {len(stats.calls)}")
        print(f"  总输入 tokens: {stats.total_prompt_tokens}")
        print(f"  总输出 tokens: {stats.total_completion_tokens}")
        print(f"  总费用:        ${stats.total_cost:.4f}")

    print("\n" + "=" * 60)
    print("Layer 3 测试完成!")
    print("=" * 60)
    print("\n关键发现:")
    print("  1. ResearchAgent.process() 是研究循环的核心，每次迭代执行 7 步")
    print("  2. check_sufficiency 和 generate_query_plan 各调一次 LLM，加上 NoteAgent 共 3 次/迭代")
    print("  3. 工具选择受 _generate_tool_phase_guidance() 引导：早期 RAG → 中期外部 → 晚期补全")
    print("  4. 动态分裂：generate_query_plan 可能发现新主题并加入队列")
    print("  5. CitationManager 为每次工具调用分配唯一 ID（CIT-块号-序号）")
    print("  6. 知识通过 current_knowledge += trace.summary 逐轮积累")


if __name__ == "__main__":
    asyncio.run(main())
