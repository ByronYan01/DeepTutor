#!/usr/bin/env python
"""
Layer 2: Analysis Loop（InvestigateAgent + NoteAgent，调 LLM）
=========================================
测试 Solve 模块分析循环的两个 Agent：
  1. InvestigateAgent — 调查员（生成查询计划，执行工具调用）
  2. NoteAgent — 笔记员（对检索结果生成摘要）

调用链路：

  InvestigateAgent.__init__(config, api_key, base_url)
    → BaseAgent.__init__(module_name="solve", agent_name="investigate_agent")
    → 从 config 读取 max_actions_per_round, max_iterations

  InvestigateAgent.process(question, memory, citation_memory, kb_name)
    → _build_context(question, memory)           # 构建上下文（已有知识摘要）
    → _build_system_prompt()                      # 调查员角色 Prompt
    → _build_user_prompt(context)                 # 用户问题 + 已有知识
    → call_llm()                                   # → JSON: {reasoning, plan: [{tool, query}]}
    → _execute_single_action() × N                # 执行工具调用（RAG/web/query_item）
    → memory.add_knowledge(knowledge_item)        # 追加知识条目
    → citation_memory 注册引用
    → return {reasoning, should_stop, knowledge_item_ids, actions}

  NoteAgent.process(question, memory, new_knowledge_ids, citation_memory)
    → 遍历 new_knowledge_ids
    → 对每个 KnowledgeItem:
      → _build_context(question, knowledge_item, memory)
      → _build_user_prompt(context)
      → call_llm()                               # → JSON: {summary, citations}
      → memory.update_knowledge_summary(cite_id, summary)
      → citation_memory.update_citation(cite_id, content)

输入：硬编码问题（Python 知识点）
输出：InvestigateMemory / CitationMemory 的增长过程
"""

import asyncio
import sys
import tempfile
from pathlib import Path

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env", override=False)


async def main():
    print("=" * 60)
    print("Layer 2: Analysis Loop 测试（InvestigateAgent + NoteAgent）")
    print("=" * 60)

    # -------------------------------------------------------
    # Step 1: 初始化配置和 Agent
    # -------------------------------------------------------
    print("\n--- Step 1: 初始化配置和 Agent ---")

    from src.agents.solve.analysis_loop import InvestigateAgent, NoteAgent
    from src.agents.solve.memory import CitationMemory, InvestigateMemory
    from src.services.llm import get_llm_config

    llm_config = get_llm_config()
    print(f"  LLM 配置:")
    print(f"    api_key:  {llm_config.api_key[:8]}..." if llm_config.api_key else "    api_key: None")
    print(f"    base_url: {llm_config.base_url}")

    # 构造 config（模拟从 main.yaml 加载的配置）
    config = {
        "system": {"language": "zh"},
        "tools": {"web_search": {"enabled": False}},  # 关闭 web_search 避免外部依赖
        "solve": {
            "agents": {
                "investigate_agent": {
                    "max_actions_per_round": 2,
                    "max_iterations": 3,
                },
            },
        },
    }

    investigate_agent = InvestigateAgent(
        config=config,
        api_key=llm_config.api_key,
        base_url=llm_config.base_url,
        api_version=getattr(llm_config, "api_version", None),
    )
    print(f"\n  InvestigateAgent 属性:")
    print(f"    module_name:           {investigate_agent.module_name}")
    print(f"    agent_name:            {investigate_agent.agent_name}")
    print(f"    language:              {investigate_agent.language}")
    print(f"    max_actions_per_round: {investigate_agent.max_actions_per_round}")
    print(f"    max_iterations:        {investigate_agent.max_iterations}")
    print(f"    enable_web_search:     {investigate_agent.enable_web_search}")

    note_agent = NoteAgent(
        config=config,
        api_key=llm_config.api_key,
        base_url=llm_config.base_url,
        api_version=getattr(llm_config, "api_version", None),
    )
    print(f"\n  NoteAgent 属性:")
    print(f"    module_name: {note_agent.module_name}")
    print(f"    agent_name:  {note_agent.agent_name}")

    # -------------------------------------------------------
    # Step 2: 检查 Prompt 加载
    # -------------------------------------------------------
    print("\n--- Step 2: 检查 Prompt 加载 ---")

    # InvestigateAgent Prompt
    inv_sys = investigate_agent.get_prompt("system") if investigate_agent.has_prompts() else None
    inv_user = investigate_agent.get_prompt("user_template") if investigate_agent.has_prompts() else None
    print(f"  InvestigateAgent:")
    print(f"    system prompt:     {'✅' if inv_sys else '❌'} ({len(inv_sys)} chars)" if inv_sys else "    system prompt:     ❌")
    print(f"    user_template:     {'✅' if inv_user else '❌'} ({len(inv_user)} chars)" if inv_user else "    user_template:     ❌")
    if inv_sys:
        print(f"    角色定位预览: {inv_sys[:80].replace(chr(10), ' ')}...")

    # NoteAgent Prompt
    note_sys = note_agent.get_prompt("system") if note_agent.has_prompts() else None
    note_user = note_agent.get_prompt("user_template") if note_agent.has_prompts() else None
    print(f"\n  NoteAgent:")
    print(f"    system prompt:     {'✅' if note_sys else '❌'} ({len(note_sys)} chars)" if note_sys else "    system prompt:     ❌")
    print(f"    user_template:     {'✅' if note_user else '❌'} ({len(note_user)} chars)" if note_user else "    user_template:     ❌")

    # -------------------------------------------------------
    # Step 3: 创建 Memory 实例
    # -------------------------------------------------------
    print("\n--- Step 3: 创建 Memory 实例 ---")

    tmpdir = tempfile.mkdtemp(prefix="solve_debug_")
    print(f"  临时目录: {tmpdir}")

    question = "Python 中如何使用 asyncio 实现异步并发？请解释 async/await 的工作原理。"
    print(f"  测试问题: {question}")

    inv_memory = InvestigateMemory(
        user_question=question,
        output_dir=tmpdir,
    )
    cit_memory = CitationMemory(output_dir=tmpdir)

    print(f"\n  InvestigateMemory:")
    print(f"    task_id:         {inv_memory.task_id}")
    print(f"    knowledge_chain: {len(inv_memory.knowledge_chain)} 条")
    print(f"  CitationMemory:")
    print(f"    citations:       {len(cit_memory.citations)} 条")

    # -------------------------------------------------------
    # Step 4: 调用 InvestigateAgent.process() — 第一轮
    # -------------------------------------------------------
    print("\n--- Step 4: InvestigateAgent.process() — 第一轮 ---")
    print(f"  问题: {question[:60]}...")
    print(f"  kb_name: ai_textbook")
    print(f"  正在调用 LLM 生成查询计划...")

    try:
        result_1 = await investigate_agent.process(
            question=question,
            memory=inv_memory,
            citation_memory=cit_memory,
            kb_name="ai_textbook",
            output_dir=tmpdir,
            verbose=True,
        )

        print(f"\n  ✅ 第一轮调查完成!")
        print(f"    reasoning:    {result_1['reasoning'][:100]}...")
        print(f"    should_stop:  {result_1['should_stop']}")
        print(f"    actions:      {len(result_1['actions'])} 个")
        for action in result_1["actions"]:
            print(f"      - {action['tool_type']}: {action.get('query', '')[:50]}... → cite_id={action.get('cite_id')}")
        print(f"    knowledge_ids: {result_1['knowledge_item_ids']}")

        print(f"\n  Memory 状态:")
        print(f"    knowledge_chain: {len(inv_memory.knowledge_chain)} 条")
        for k in inv_memory.knowledge_chain:
            print(f"      {k.cite_id}: {k.tool_type} — {k.query[:40]}...")
            print(f"        raw_result 长度: {len(k.raw_result)} chars")
            print(f"        summary: '{k.summary[:30]}...' " if k.summary else "        summary: (空)")
        print(f"    citations: {len(cit_memory.citations)} 条")

    except Exception as e:
        print(f"  ❌ 第一轮调查失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # -------------------------------------------------------
    # Step 5: 调用 NoteAgent.process() — 对第一轮知识生成摘要
    # -------------------------------------------------------
    print("\n--- Step 5: NoteAgent.process() — 生成摘要 ---")

    new_ids = result_1["knowledge_item_ids"]
    if new_ids:
        print(f"  待处理 knowledge_ids: {new_ids}")
        print(f"  正在调用 LLM 生成摘要...")

        try:
            note_result = await note_agent.process(
                question=question,
                memory=inv_memory,
                new_knowledge_ids=new_ids,
                citation_memory=cit_memory,
                output_dir=tmpdir,
                verbose=True,
            )

            print(f"\n  ✅ 摘要生成完成!")
            print(f"    success:         {note_result['success']}")
            print(f"    processed_items: {note_result['processed_items']}")
            print(f"    failed:          {note_result.get('failed', [])}")

            for detail in note_result.get("details", []):
                print(f"\n    cite_id={detail['cite_id']}:")
                print(f"      summary: {detail['summary'][:80]}...")
                print(f"      citations_count: {detail['citations_count']}")

            # 验证摘要已更新到 InvestigateMemory
            for k in inv_memory.knowledge_chain:
                if k.cite_id in new_ids:
                    assert k.summary != "", f"  ❌ {k.cite_id} 的 summary 未更新!"
                    print(f"\n    {k.cite_id} summary 已更新: {k.summary[:60]}...")
            print("  ✅ NoteAgent 摘要写入 InvestigateMemory 成功")

        except Exception as e:
            print(f"  ❌ 摘要生成失败: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("  ⚠️ 第一轮无新知识条目，跳过 NoteAgent")

    # -------------------------------------------------------
    # Step 6: 调用 InvestigateAgent.process() — 第二轮
    # -------------------------------------------------------
    print("\n--- Step 6: InvestigateAgent.process() — 第二轮 ---")
    print(f"  已有知识: {len(inv_memory.knowledge_chain)} 条")
    print(f"  正在调用 LLM 判断是否需要继续调查...")

    try:
        result_2 = await investigate_agent.process(
            question=question,
            memory=inv_memory,
            citation_memory=cit_memory,
            kb_name="ai_textbook",
            output_dir=tmpdir,
            verbose=True,
        )

        print(f"\n  ✅ 第二轮调查完成!")
        print(f"    reasoning:    {result_2['reasoning'][:100]}...")
        print(f"    should_stop:  {result_2['should_stop']}")
        print(f"    actions:      {len(result_2['actions'])} 个")
        if result_2["actions"]:
            for action in result_2["actions"]:
                print(f"      - {action['tool_type']}: {action.get('query', '')[:50]}...")
        print(f"    knowledge_ids: {result_2['knowledge_item_ids']}")

        # 如果有新知识，也用 NoteAgent 处理
        new_ids_2 = result_2["knowledge_item_ids"]
        if new_ids_2:
            note_result_2 = await note_agent.process(
                question=question,
                memory=inv_memory,
                new_knowledge_ids=new_ids_2,
                citation_memory=cit_memory,
                output_dir=tmpdir,
                verbose=True,
            )
            print(f"    NoteAgent 处理: {note_result_2['processed_items']} 条")

    except Exception as e:
        print(f"  ❌ 第二轮调查失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 7: 最终状态检查
    # -------------------------------------------------------
    print("\n--- Step 7: 最终状态检查 ---")

    print(f"  InvestigateMemory 最终状态:")
    print(f"    knowledge_chain: {len(inv_memory.knowledge_chain)} 条")
    for k in inv_memory.knowledge_chain:
        has_summary = "✅" if k.summary else "❌"
        print(f"      {k.cite_id} [{k.tool_type}] summary={has_summary} — {k.query[:40]}...")

    print(f"\n  CitationMemory 最终状态:")
    print(f"    citations: {len(cit_memory.citations)} 条")
    for c in cit_memory.citations:
        print(f"      {c.cite_id} [{c.tool_type}] stage={c.stage} — {c.query[:40]}...")

    # 保存
    inv_memory.save()
    cit_memory.save()
    print(f"\n  文件保存:")
    for f in sorted(Path(tmpdir).glob("*.json")):
        print(f"    {f.name} ({f.stat().st_size} bytes)")

    # -------------------------------------------------------
    # 总结
    # -------------------------------------------------------
    print("\n" + "=" * 60)
    print("Layer 2 测试完成!")
    print("=" * 60)
    print("\n关键发现:")
    print("  1. InvestigateAgent 是调查员：LLM 决定查什么 → 工具调用 → 返回 KnowledgeItem")
    print("  2. NoteAgent 是笔记员：接收 KnowledgeItem → LLM 生成摘要 → 更新到 Memory")
    print("  3. CitationMemory 在 Analysis 阶段也参与：InvestigateAgent 注册引用，NoteAgent 更新内容")
    print("  4. InvestigateAgent 支持 should_stop=True 提前终止（当 LLM 认为信息足够时）")
    print("  5. max_actions_per_round 限制每轮最多执行的工具调用数量")
    print(f"\n  临时目录（可查看中间文件）: {tmpdir}")


if __name__ == "__main__":
    asyncio.run(main())
