#!/usr/bin/env python
"""
Layer 3: Solve Loop 核心三 Agent（调 LLM）
=========================================
测试 Solve Loop 中的三个核心 Agent：
  1. ManagerAgent — 战略规划师（规划解题步骤链）
  2. SolveAgent — 工具策略家（为每步选择工具）
  3. ToolAgent — 工具执行器（执行实际工具调用）

调用链路：

  ManagerAgent.process(question, investigate_memory, solve_memory)
    → _build_context(question, investigate_memory)   # 问题 + 知识链摘要
    → _build_system_prompt()                          # 战略规划师角色
    → _build_user_prompt(context)                     # 问题 + 可用知识链 + 反思
    → call_llm()                                       # → JSON: {steps: [{step_id, role, target, cite_ids}]}
    → _parse_response(response, investigate_memory)   # 创建 SolveChainStep 列表
    → solve_memory.create_chains(steps)               # 写入步骤链
    → return {steps_count, num_steps}

  SolveAgent.process(question, current_step, solve_memory, investigate_memory, citation_memory)
    → _build_context()                                # 问题 + 步骤目标 + 已有引用 + 历史轨迹
    → _build_system_prompt()                          # 工具策略家角色
    → _build_user_prompt(context)
    → call_llm()                                       # → JSON: {thoughts, tool_calls: [{type, intent}]}
    → _parse_tool_plan(response)                      # 解析工具计划
    → solve_memory.append_tool_call() + citation_memory.add_citation()
    → return {step_id, requested_calls, finish_requested}

  ToolAgent.process(step, solve_memory, citation_memory, kb_name)
    → 遍历 step.tool_calls 中 pending 的调用
    → _execute_single_call(record, ...)               # 实际执行 RAG/web/code
    → _summarize_tool_result(tool_type, query, raw)   # LLM 摘要工具结果
    → solve_memory.update_tool_call_result()          # 更新调用记录
    → citation_memory.update_citation()               # 更新引用内容

前置条件：使用预构建的 InvestigateMemory（硬编码知识链），跳过 Analysis Loop
输入：硬编码问题（Python 知识点）
输出：SolveMemory 的步骤链规划和工具调用结果
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


def build_mock_investigate_memory(output_dir: str):
    """构建模拟的 InvestigateMemory（预填充知识链，跳过 Analysis Loop）"""
    from src.agents.solve.memory import InvestigateMemory, KnowledgeItem

    memory = InvestigateMemory(
        user_question="Python 列表推导式和生成器表达式有什么区别？各自适用什么场景？",
        output_dir=output_dir,
    )

    # 模拟 InvestigateAgent 的检索结果
    memory.add_knowledge(KnowledgeItem(
        cite_id="[rag-1]",
        tool_type="rag_naive",
        query="Python 列表推导式 list comprehension 语法和用法",
        raw_result=(
            "列表推导式（List Comprehension）是 Python 中快速创建列表的语法糖。"
            "基本语法：[expression for item in iterable if condition]。"
            "例如：squares = [x**2 for x in range(10)]。"
            "列表推导式会一次性将所有元素加载到内存中，立即计算所有值。"
            "嵌套推导式：[(x, y) for x in range(3) for y in range(3)]。"
            "条件过滤：[x for x in range(20) if x % 2 == 0]。"
        ),
        summary="列表推导式是一次性生成完整列表的语法糖，所有元素立即计算并加载到内存中。",
    ))

    memory.add_knowledge(KnowledgeItem(
        cite_id="[rag-2]",
        tool_type="rag_hybrid",
        query="Python 生成器表达式 generator expression 与 yield",
        raw_result=(
            "生成器表达式（Generator Expression）使用圆括号代替方括号。"
            "语法：(expression for item in iterable if condition)。"
            "生成器是惰性求值（lazy evaluation），只有在迭代时才计算下一个值。"
            "内存效率高，不会一次性生成所有元素。"
            "一次性消费：生成器只能遍历一次，遍历完后为空。"
            "例如：gen = (x**2 for x in range(10))，next(gen) 返回 0，next(gen) 返回 1。"
            "在处理大数据集时，生成器表达式比列表推导式更节省内存。"
        ),
        summary="生成器表达式是惰性求值的迭代器，按需计算值，内存效率高但只能遍历一次。",
    ))

    memory.metadata["total_iterations"] = 2
    memory.metadata["total_knowledge_items"] = 2
    memory.metadata["coverage_rate"] = 1.0
    memory.metadata["avg_confidence"] = 0.9
    memory.save()
    return memory


def build_mock_citation_memory(output_dir: str):
    """构建模拟的 CitationMemory"""
    from src.agents.solve.memory import CitationMemory

    cm = CitationMemory(output_dir=output_dir)
    cm.add_citation(
        tool_type="rag_naive",
        query="Python 列表推导式 list comprehension 语法和用法",
        content="列表推导式是一次性生成完整列表的语法糖",
        stage="analysis",
        cite_id="[rag-1]",
    )
    cm.add_citation(
        tool_type="rag_hybrid",
        query="Python 生成器表达式 generator expression 与 yield",
        content="生成器表达式是惰性求值的迭代器",
        stage="analysis",
        cite_id="[rag-2]",
    )
    cm.save()
    return cm


async def main():
    print("=" * 60)
    print("Layer 3: Solve Loop 核心三 Agent 测试")
    print("=" * 60)

    # -------------------------------------------------------
    # Step 1: 初始化
    # -------------------------------------------------------
    print("\n--- Step 1: 初始化配置和 Agent ---")

    from src.agents.solve.memory import CitationMemory, SolveMemory
    from src.agents.solve.solve_loop import ManagerAgent, SolveAgent, ToolAgent
    from src.services.llm import get_llm_config

    llm_config = get_llm_config()
    print(f"  LLM: {llm_config.base_url}")

    config = {
        "system": {"language": "zh"},
        "tools": {"web_search": {"enabled": False}},
        "solve": {"agents": {}},
    }

    manager = ManagerAgent(config, llm_config.api_key, llm_config.base_url,
                           api_version=getattr(llm_config, "api_version", None))
    solver = SolveAgent(config, llm_config.api_key, llm_config.base_url,
                        api_version=getattr(llm_config, "api_version", None))
    tool_agent = ToolAgent(config, llm_config.api_key, llm_config.base_url,
                           api_version=getattr(llm_config, "api_version", None))

    print(f"  ManagerAgent: {manager.module_name}/{manager.agent_name}")
    print(f"  SolveAgent:   {solver.module_name}/{solver.agent_name}")
    print(f"  ToolAgent:    {tool_agent.module_name}/{tool_agent.agent_name}")

    # -------------------------------------------------------
    # Step 2: 准备预填充的 Memory
    # -------------------------------------------------------
    print("\n--- Step 2: 准备预填充的 Memory ---")

    tmpdir = tempfile.mkdtemp(prefix="solve_loop_debug_")
    question = "Python 列表推导式和生成器表达式有什么区别？各自适用什么场景？"

    inv_memory = build_mock_investigate_memory(tmpdir)
    cit_memory = build_mock_citation_memory(tmpdir)
    sol_memory = SolveMemory(user_question=question, output_dir=tmpdir)

    print(f"  临时目录: {tmpdir}")
    print(f"  测试问题: {question}")
    print(f"  InvestigateMemory: {len(inv_memory.knowledge_chain)} 条知识")
    for k in inv_memory.knowledge_chain:
        print(f"    {k.cite_id}: {k.summary[:50]}...")
    print(f"  CitationMemory: {len(cit_memory.citations)} 条引用")

    # -------------------------------------------------------
    # Step 3: ManagerAgent.process() — 规划步骤链
    # -------------------------------------------------------
    print("\n--- Step 3: ManagerAgent.process() — 规划步骤链 ---")
    print(f"  正在调用 LLM 生成解题步骤...")

    try:
        plan_result = await manager.process(
            question=question,
            investigate_memory=inv_memory,
            solve_memory=sol_memory,
            verbose=True,
        )

        print(f"\n  ✅ 步骤链规划完成!")
        print(f"    steps_count: {plan_result['steps_count']}")
        print(f"    步骤详情:")
        for step in sol_memory.solve_chains:
            cites = ", ".join(step.available_cite) if step.available_cite else "(无)"
            print(f"      {step.step_id}: {step.step_target}")
            print(f"        available_cite: {cites}")
            print(f"        status: {step.status}")

    except Exception as e:
        print(f"  ❌ 步骤链规划失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # -------------------------------------------------------
    # Step 4: SolveAgent.process() — 为第一步选择工具
    # -------------------------------------------------------
    print("\n--- Step 4: SolveAgent.process() — 第一步工具选择 ---")

    first_step = sol_memory.solve_chains[0]
    print(f"  当前步骤: {first_step.step_id} — {first_step.step_target}")
    print(f"  available_cite: {first_step.available_cite}")
    print(f"  正在调用 LLM 选择工具...")

    try:
        solve_result = await solver.process(
            question=question,
            current_step=first_step,
            solve_memory=sol_memory,
            investigate_memory=inv_memory,
            citation_memory=cit_memory,
            kb_name="ai_textbook",
            output_dir=tmpdir,
            verbose=True,
        )

        print(f"\n  ✅ 工具选择完成!")
        print(f"    step_id:          {solve_result['step_id']}")
        print(f"    finish_requested: {solve_result['finish_requested']}")
        print(f"    requested_calls:  {len(solve_result['requested_calls'])} 个")
        for call in solve_result["requested_calls"]:
            print(f"      - type={call['tool_type']}, query={call['query'][:50]}...")
            print(f"        cite_id={call.get('cite_id')}, status={call['status']}")

        # 查看 SolveMemory 状态
        step = sol_memory.get_step(first_step.step_id)
        print(f"\n    SolveMemory 状态:")
        print(f"      {step.step_id} status: {step.status}")
        print(f"      tool_calls: {len(step.tool_calls)} 条")
        for tc in step.tool_calls:
            print(f"        {tc.call_id}: {tc.tool_type} [{tc.status}] — {tc.query[:40]}...")

    except Exception as e:
        print(f"  ❌ 工具选择失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # -------------------------------------------------------
    # Step 5: ToolAgent.process() — 执行工具调用
    # -------------------------------------------------------
    print("\n--- Step 5: ToolAgent.process() — 执行工具调用 ---")

    # 只在有 pending 工具调用时执行
    pending_calls = [tc for tc in first_step.tool_calls if tc.status in ("pending", "running")]
    has_real_tool = any(tc.tool_type not in ("none", "finish") for tc in pending_calls)

    if pending_calls and has_real_tool:
        print(f"  待执行工具调用: {len(pending_calls)} 个")
        print(f"  正在执行工具...")

        try:
            tool_result = await tool_agent.process(
                step=first_step,
                solve_memory=sol_memory,
                citation_memory=cit_memory,
                kb_name="ai_textbook",
                output_dir=tmpdir,
                verbose=True,
            )

            print(f"\n  ✅ 工具执行完成!")
            print(f"    结果:")
            for tc in first_step.tool_calls:
                print(f"      {tc.call_id}: [{tc.status}] {tc.tool_type}")
                if tc.summary:
                    print(f"        summary: {tc.summary[:60]}...")
                if tc.raw_answer:
                    print(f"        raw_answer 长度: {len(tc.raw_answer)} chars")

        except Exception as e:
            print(f"  ⚠️ 工具执行异常（可能是 RAG 未配置）: {e}")
            import traceback
            traceback.print_exc()
    else:
        if pending_calls:
            print(f"  工具类型为 none/finish，无需实际执行")
            for tc in first_step.tool_calls:
                print(f"    {tc.call_id}: [{tc.status}] {tc.tool_type} — {tc.query[:50]}...")
        else:
            print(f"  无待执行工具调用")

    # -------------------------------------------------------
    # Step 6: 完整循环 — 遍历所有步骤
    # -------------------------------------------------------
    print("\n--- Step 6: 完整循环 — 遍历所有步骤 ---")

    for step_idx, step in enumerate(sol_memory.solve_chains[1:], 2):
        if step.status in ("waiting_response", "done"):
            continue

        print(f"\n  步骤 {step_idx}/{len(sol_memory.solve_chains)}: {step.step_id} — {step.step_target[:50]}...")

        try:
            # SolveAgent 选择工具
            solve_result = await solver.process(
                question=question,
                current_step=step,
                solve_memory=sol_memory,
                investigate_memory=inv_memory,
                citation_memory=cit_memory,
                kb_name="ai_textbook",
                output_dir=tmpdir,
                verbose=False,
            )
            print(f"    SolveAgent: {len(solve_result['requested_calls'])} calls, finish={solve_result['finish_requested']}")

            # 如果有实际工具调用（非 none/finish）
            real_pending = [tc for tc in step.tool_calls
                           if tc.status in ("pending", "running") and tc.tool_type not in ("none", "finish")]
            if real_pending:
                try:
                    await tool_agent.process(
                        step=step,
                        solve_memory=sol_memory,
                        citation_memory=cit_memory,
                        kb_name="ai_textbook",
                        output_dir=tmpdir,
                        verbose=False,
                    )
                    print(f"    ToolAgent: 执行完成")
                except Exception as e:
                    print(f"    ToolAgent: ⚠️ {str(e)[:60]}...")

            # 标记等待响应
            if solve_result["finish_requested"]:
                sol_memory.mark_step_waiting_response(step.step_id)
                print(f"    状态: → waiting_response")

        except Exception as e:
            print(f"    ⚠️ 步骤处理失败: {str(e)[:80]}...")

    # 标记第一步（如果尚未标记）
    if first_step.status not in ("waiting_response", "done"):
        sol_memory.mark_step_waiting_response(first_step.step_id)

    sol_memory.save()

    # -------------------------------------------------------
    # Step 7: 最终状态
    # -------------------------------------------------------
    print("\n--- Step 7: 最终状态 ---")

    print(f"  SolveMemory 摘要:")
    print(f"    {sol_memory.get_summary()}")
    print(f"\n  CitationMemory: {len(cit_memory.citations)} 条引用")
    for c in cit_memory.citations:
        print(f"    {c.cite_id} [{c.tool_type}] stage={c.stage} step={c.step_id or '-'}")

    print(f"\n  文件:")
    for f in sorted(Path(tmpdir).glob("*.json")):
        print(f"    {f.name} ({f.stat().st_size} bytes)")

    # -------------------------------------------------------
    # 总结
    # -------------------------------------------------------
    print("\n" + "=" * 60)
    print("Layer 3 测试完成!")
    print("=" * 60)
    print("\n关键发现:")
    print("  1. ManagerAgent 是规划者：将问题拆解为带角色的步骤链（计算/推导/分析/画图/整合）")
    print("  2. SolveAgent 是策略家：为每步选择工具（code_execution/rag_naive/rag_hybrid/web_search/none）")
    print("  3. ToolAgent 是执行者：实际调用 RAG/web/code 工具，生成摘要并写入 Memory")
    print("  4. SolveAgent 的 intent 字段是一句话描述，不是代码（代码由 ToolAgent 生成）")
    print("  5. none 类型表示 LLM 认为已有信息足够，直接给出结论")
    print(f"\n  临时目录（可查看中间文件）: {tmpdir}")


if __name__ == "__main__":
    asyncio.run(main())
