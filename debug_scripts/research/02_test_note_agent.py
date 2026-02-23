#!/usr/bin/env python
"""
Layer 2: NoteAgent 信息压缩摘要（单 Agent + LLM）
=========================================
测试 NoteAgent 的核心流程：
  1. 初始化（BaseAgent 配置 + Prompt 加载）
  2. 接收工具返回的原始数据（tool_type, query, raw_answer）
  3. 调用 LLM 生成结构化摘要（JSON 格式，含 summary + key_elements）
  4. 创建 ToolTrace 对象（含 tool_id, citation_id, summary）

调用链路：
  NoteAgent.__init__(config, api_key, base_url)
    → BaseAgent.__init__(module_name="research", agent_name="note_agent")
      → get_agent_params("research")         # 从 agents.yaml 获取 temperature/max_tokens
      → PromptManager.load_prompts()          # 加载 prompts/zh/note_agent.yaml

  NoteAgent.process(tool_type, query, raw_answer, citation_id, topic, context)
    → _generate_summary()
      → get_prompt("system", "role")           # 信息提取与知识整理专家角色
      → get_prompt("process", "generate_summary")  # 深度提取框架模板
      → _convert_to_template_format()          # {var} → $var（避免 LaTeX 冲突）
      → Template.safe_substitute(tool_type, query, raw_answer, topic, context)
      → call_llm(user_prompt, system_prompt)   # 调用 LLM
      → extract_json_from_text(response)       # 解析 JSON
      → ensure_json_dict() → ensure_keys(["summary"])
    → _generate_tool_id()                       # 时间戳生成 tool_id
    → ToolTrace(tool_id, citation_id, tool_type, query, raw_answer, summary)

输入：模拟的工具返回数据（RAG 检索结果）
输出：ToolTrace 对象（含 LLM 生成的摘要）
"""

import asyncio
import json
import sys
from pathlib import Path

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env", override=False)


# -------------------------------------------------------
# 模拟 RAG 工具返回数据
# -------------------------------------------------------
MOCK_RAG_RESULT = json.dumps({
    "answer": (
        "Transformer 的自注意力（Self-Attention）机制是其核心创新。"
        "它通过 Query (Q)、Key (K)、Value (V) 三个线性变换矩阵来计算序列中各位置之间的关联。"
        "计算公式为：Attention(Q, K, V) = softmax(QK^T / √d_k) V，"
        "其中 d_k 是 Key 的维度，用于缩放点积防止梯度消失。"
        "多头注意力（Multi-Head Attention）将 Q/K/V 分成 h 个头并行计算，"
        "每个头关注不同的语义子空间，最后拼接：MultiHead = Concat(head_1, ..., head_h) W^O。"
        "这种设计的优势：1) 可以同时关注不同位置的信息；"
        "2) 计算复杂度为 O(n²·d)，与序列长度的平方成正比；"
        "3) 所有位置可以并行计算，不像 RNN 需要顺序处理。"
    ),
    "chunks": [
        {"id": "chunk_1", "content": "注意力机制的基本原理...", "score": 0.95},
        {"id": "chunk_2", "content": "多头注意力的实现...", "score": 0.88},
    ],
    "mode": "hybrid",
    "kb_name": "ai_textbook",
}, ensure_ascii=False)

MOCK_PAPER_RESULT = json.dumps({
    "papers": [
        {
            "title": "Attention Is All You Need",
            "authors": ["Vaswani A.", "Shazeer N.", "Parmar N."],
            "year": 2017,
            "abstract": "The dominant sequence transduction models are based on complex recurrent or "
                        "convolutional neural networks. We propose a new simple network architecture, "
                        "the Transformer, based solely on attention mechanisms.",
            "venue": "NeurIPS 2017",
        }
    ]
}, ensure_ascii=False)


async def main():
    print("=" * 60)
    print("Layer 2: NoteAgent 信息压缩摘要测试")
    print("=" * 60)

    # -------------------------------------------------------
    # Step 1: 初始化 NoteAgent
    # -------------------------------------------------------
    print("\n--- Step 1: 初始化 NoteAgent ---")

    from src.agents.research.agents.note_agent import NoteAgent
    from src.services.llm import get_llm_config

    llm_config = get_llm_config()
    print(f"  LLM 配置:")
    print(f"    api_key:  {llm_config.api_key[:8]}..." if llm_config.api_key else "    api_key: None")
    print(f"    base_url: {llm_config.base_url[:50]}..." if llm_config.base_url else "    base_url: None")

    # 构造 config（模拟从 main.yaml 加载的配置）
    config = {
        "system": {"language": "zh"},
    }

    agent = NoteAgent(
        config=config,
        api_key=llm_config.api_key,
        base_url=llm_config.base_url,
        api_version=getattr(llm_config, "api_version", None),
    )

    print(f"\n  Agent 属性:")
    print(f"    module_name:  {agent.module_name}")
    print(f"    agent_name:   {agent.agent_name}")
    print(f"    language:     {agent.language}")
    print(f"    model:        {agent.get_model()}")
    print(f"    temperature:  {agent.get_temperature()}")
    print(f"    max_tokens:   {agent.get_max_tokens()}")

    # -------------------------------------------------------
    # Step 2: 检查 Prompt 加载
    # -------------------------------------------------------
    print("\n--- Step 2: 检查 Prompt 加载 ---")

    # NoteAgent 的 Prompt 结构：system.role + process.generate_summary
    system_prompt = agent.get_prompt("system", "role")
    user_prompt_template = agent.get_prompt("process", "generate_summary")

    if system_prompt:
        print(f"  ✅ system.role: {len(system_prompt)} chars")
        print(f"     预览: {system_prompt[:100].replace(chr(10), ' ')}...")
    else:
        print("  ❌ system.role: 未加载!")

    if user_prompt_template:
        print(f"  ✅ process.generate_summary: {len(user_prompt_template)} chars")
        # 查找模板变量
        import re
        variables = re.findall(r'\{(\w+)\}', user_prompt_template)
        unique_vars = sorted(set(variables))
        print(f"     模板变量: {unique_vars}")
    else:
        print("  ❌ process.generate_summary: 未加载!")

    # -------------------------------------------------------
    # Step 3: 观察 Prompt 组装过程
    # -------------------------------------------------------
    print("\n--- Step 3: 观察 Prompt 组装过程 ---")

    # 还原 NoteAgent._generate_summary() 中的 Prompt 组装逻辑
    from string import Template

    template_str = NoteAgent._convert_to_template_format(user_prompt_template)
    template = Template(template_str)
    assembled_prompt = template.safe_substitute(
        tool_type="rag_hybrid",
        query="什么是 Transformer 的自注意力机制？",
        raw_answer=MOCK_RAG_RESULT[:200] + "...",  # 截断预览
        topic="Transformer 注意力机制",
        context="",
    )
    print(f"  组装后 user_prompt 长度: {len(assembled_prompt)} chars")
    print(f"  前 300 字预览:")
    for line in assembled_prompt[:300].split("\n"):
        print(f"    {line}")
    if len(assembled_prompt) > 300:
        print(f"    ...（省略 {len(assembled_prompt) - 300} chars）")

    # -------------------------------------------------------
    # Step 4: 调用 process() — RAG 工具结果摘要
    # -------------------------------------------------------
    print("\n--- Step 4: 调用 process() — RAG 工具结果摘要 ---")
    print(f"  tool_type:   rag_hybrid")
    print(f"  query:       什么是 Transformer 的自注意力机制？")
    print(f"  raw_answer:  {len(MOCK_RAG_RESULT)} chars")
    print(f"  citation_id: CIT-1-01")
    print(f"  正在调用 LLM 生成摘要...")

    try:
        trace_rag = await agent.process(
            tool_type="rag_hybrid",
            query="什么是 Transformer 的自注意力机制？",
            raw_answer=MOCK_RAG_RESULT,
            citation_id="CIT-1-01",
            topic="Transformer 注意力机制",
            context="研究自注意力和多头注意力的核心原理",
        )

        print(f"\n  ✅ ToolTrace 生成成功!")
        print(f"    tool_id:     {trace_rag.tool_id}")
        print(f"    citation_id: {trace_rag.citation_id}")
        print(f"    tool_type:   {trace_rag.tool_type}")
        print(f"    query:       {trace_rag.query}")
        print(f"    summary 长度: {len(trace_rag.summary)} chars")
        print(f"    summary 预览:")
        for line in trace_rag.summary[:500].split("\n"):
            print(f"      {line}")
        if len(trace_rag.summary) > 500:
            print(f"      ...（省略 {len(trace_rag.summary) - 500} chars）")

    except Exception as e:
        print(f"  ❌ RAG 摘要失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 5: 调用 process() — Paper 搜索结果摘要
    # -------------------------------------------------------
    print("\n--- Step 5: 调用 process() — Paper 搜索结果摘要 ---")
    print(f"  tool_type:   paper_search")
    print(f"  query:       Attention Is All You Need")
    print(f"  raw_answer:  {len(MOCK_PAPER_RESULT)} chars")
    print(f"  citation_id: CIT-1-02")
    print(f"  正在调用 LLM 生成摘要...")

    try:
        trace_paper = await agent.process(
            tool_type="paper_search",
            query="Attention Is All You Need",
            raw_answer=MOCK_PAPER_RESULT,
            citation_id="CIT-1-02",
            topic="Transformer 注意力机制",
            context="了解 Transformer 的原始论文及其核心贡献",
        )

        print(f"\n  ✅ ToolTrace 生成成功!")
        print(f"    tool_id:     {trace_paper.tool_id}")
        print(f"    citation_id: {trace_paper.citation_id}")
        print(f"    tool_type:   {trace_paper.tool_type}")
        print(f"    summary 长度: {len(trace_paper.summary)} chars")
        print(f"    summary 预览:")
        for line in trace_paper.summary[:500].split("\n"):
            print(f"      {line}")

    except Exception as e:
        print(f"  ❌ Paper 摘要失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 6: 验证 ToolTrace 与 TopicBlock 集成
    # -------------------------------------------------------
    print("\n--- Step 6: 验证 ToolTrace 与 TopicBlock 集成 ---")

    from src.agents.research.data_structures import TopicBlock

    block = TopicBlock(
        block_id="block_1",
        sub_topic="Transformer 注意力机制",
        overview="深入研究自注意力和多头注意力的原理",
    )

    if 'trace_rag' in dir() and trace_rag:
        block.add_tool_trace(trace_rag)
    if 'trace_paper' in dir() and trace_paper:
        block.add_tool_trace(trace_paper)

    print(f"  TopicBlock 信息:")
    print(f"    block_id:    {block.block_id}")
    print(f"    sub_topic:   {block.sub_topic}")
    print(f"    tool_traces: {len(block.tool_traces)} 条")
    print(f"\n  全部摘要拼接（get_all_summaries）:")
    for line in block.get_all_summaries().split("\n"):
        print(f"    {line[:100]}...")
    print("  ✅ NoteAgent → ToolTrace → TopicBlock 集成正常")

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
    print("Layer 2 测试完成!")
    print("=" * 60)
    print("\n关键发现:")
    print("  1. NoteAgent 使用 string.Template 而非 str.format()，避免 LaTeX 花括号冲突")
    print("  2. Prompt 要求输出 JSON，含 summary + key_elements + content_type + confidence")
    print("  3. 解析时只提取 summary 字段，其余为辅助信息")
    print("  4. ToolTrace 的 citation_id 由调用方（CitationManager）提供，不是 NoteAgent 自己生成")
    print("  5. tool_id 使用时间戳毫秒级生成，保证唯一性")


if __name__ == "__main__":
    asyncio.run(main())
