#!/usr/bin/env python
"""
Layer 4: AgentCoordinator 完整编排
=========================================
测试 AgentCoordinator 的核心流程（不经过 WebSocket）：
  1. 初始化 Coordinator（配置加载、Agent 工厂方法）
  2. 单题生成：generate_question()
  3. 批量生成：generate_questions_custom()（三阶段流水线）
  4. Plan 生成：_generate_question_plan()
  5. 文件持久化：knowledge.json / plan.json / result.json / question.md

调用链路（generate_questions_custom 三阶段流水线）：
  AgentCoordinator.generate_questions_custom(requirement, num_questions)
    ┌─ Stage 1: Researching ─────────────────────────────────┐
    │ _create_retrieve_agent() → RetrieveAgent               │
    │ retrieve_agent.process(requirement, num_queries=3)      │
    │   → _generate_queries()  # LLM 生成搜索查询            │
    │   → _execute_searches()  # 并行 RAG 检索               │
    │   → _summarize_retrievals()  # 汇总检索结果            │
    │ _save_knowledge_json(batch_dir, retrieval_result)       │
    └────────────────────────────────────────────────────────┘
    ┌─ Stage 2: Planning ────────────────────────────────────┐
    │ _generate_question_plan(requirement, knowledge, n)     │
    │   → llm_complete() 直接调用 LLM（不经过 BaseAgent）    │
    │   → 生成 focuses 列表：每题一个独特的考察角度           │
    │ _save_plan_json(batch_dir, plan)                        │
    └────────────────────────────────────────────────────────┘
    ┌─ Stage 3: Generating ──────────────────────────────────┐
    │ for focus in focuses:                                   │
    │   _create_generate_agent() → GenerateAgent              │
    │   generate_agent.process(requirement, knowledge, focus) │
    │   _create_relevance_analyzer() → RelevanceAnalyzer      │
    │   analyzer.process(question, knowledge)                 │
    │   _save_custom_question_result(batch_dir, result)       │
    │     → result.json + question.md                         │
    └────────────────────────────────────────────────────────┘
    → summary.json（整体摘要）

单题生成 generate_question() 是类似流程，但没有 Planning 阶段。

输入：需求 dict + 题目数量
输出：{success, requested, completed, failed, search_queries, plan, results, failures}
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
# 测试数据
# -------------------------------------------------------
KB_NAME = "js权威指南"

MOCK_REQUIREMENT = {
    "knowledge_point": "JavaScript 原型链",
    "difficulty": "medium",
    "question_type": "choice",
    "additional_requirements": "考察原型链的查找机制和继承",
}

# 输出目录
OUTPUT_DIR = str(project_root / "data" / "debug_output" / "question_test")


async def main():
    print("=" * 60)
    print("Layer 4: AgentCoordinator 完整编排测试")
    print("=" * 60)

    # -------------------------------------------------------
    # Step 1: 初始化 AgentCoordinator
    # -------------------------------------------------------
    print("\n--- Step 1: 初始化 AgentCoordinator ---")

    from src.agents.question import AgentCoordinator
    from src.services.llm import get_llm_config

    llm_config = get_llm_config()

    coordinator = AgentCoordinator(
        api_key=llm_config.api_key,
        base_url=llm_config.base_url,
        api_version=getattr(llm_config, "api_version", None),
        kb_name=KB_NAME,
        language="zh",
        output_dir=OUTPUT_DIR,
    )

    print(f"  kb_name:           {coordinator.kb_name}")
    print(f"  language:          {coordinator.language}")
    print(f"  output_dir:        {coordinator.output_dir}")
    print(f"  rag_query_count:   {coordinator.rag_query_count}")
    print(f"  rag_mode:          {coordinator.rag_mode}")
    print(f"  max_parallel:      {coordinator.max_parallel_questions}")

    # -------------------------------------------------------
    # Step 2: 检查 Agent 工厂方法
    # -------------------------------------------------------
    print("\n--- Step 2: 检查 Agent 工厂方法 ---")

    retrieve_agent = coordinator._create_retrieve_agent()
    print(f"  RetrieveAgent:")
    print(f"    module: {retrieve_agent.module_name}, agent: {retrieve_agent.agent_name}")
    print(f"    kb_name: {retrieve_agent.kb_name}, rag_mode: {retrieve_agent.rag_mode}")

    generate_agent = coordinator._create_generate_agent()
    print(f"  GenerateAgent:")
    print(f"    module: {generate_agent.module_name}, agent: {generate_agent.agent_name}")

    analyzer = coordinator._create_relevance_analyzer()
    print(f"  RelevanceAnalyzer:")
    print(f"    module: {analyzer.module_name}, agent: {analyzer.agent_name}")

    # -------------------------------------------------------
    # Step 3: 单独测试 Plan 生成
    # -------------------------------------------------------
    print("\n--- Step 3: 单独测试 _generate_question_plan ---")
    print(f"  需求: {MOCK_REQUIREMENT}")
    print(f"  题目数: 2")

    # 先做一次快速检索获取知识上下文（供 plan 使用）
    print(f"  正在检索知识（为 plan 生成提供上下文）...")

    try:
        retrieval_result = await retrieve_agent.process(
            requirement=MOCK_REQUIREMENT,
            num_queries=2,
        )
        knowledge_context = retrieval_result["summary"]
        print(f"  检索完成，知识长度: {len(knowledge_context)} chars")
    except Exception as e:
        print(f"  ⚠️ 检索失败，使用默认上下文: {e}")
        knowledge_context = "JavaScript 原型链是实现继承的核心机制。每个对象都有一个内部属性 [[Prototype]]。"

    print(f"  正在生成 Plan...")

    try:
        plan = await coordinator._generate_question_plan(
            requirement=MOCK_REQUIREMENT,
            knowledge_context=knowledge_context,
            num_questions=2,
        )
        print(f"\n  ✅ Plan 生成完成!")
        print(f"  knowledge_point: {plan.get('knowledge_point')}")
        print(f"  difficulty:      {plan.get('difficulty')}")
        print(f"  question_type:   {plan.get('question_type')}")
        print(f"  num_questions:   {plan.get('num_questions')}")
        print(f"\n  --- Focuses ---")
        for i, focus in enumerate(plan.get("focuses", []), 1):
            print(f"  [{i}] id: {focus.get('id')}")
            print(f"      focus: {focus.get('focus')}")
            print(f"      type:  {focus.get('type')}")
    except Exception as e:
        print(f"  ❌ Plan 生成失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 4: 单题生成 generate_question()
    # -------------------------------------------------------
    print("\n--- Step 4: 单题生成 generate_question() ---")
    print(f"  需求: {MOCK_REQUIREMENT}")
    print(f"  正在执行完整单题生成流程...")
    print(f"  （包含：检索 → 生成 → 相关性分析 → 保存）")

    try:
        single_result = await coordinator.generate_question(
            requirement=MOCK_REQUIREMENT,
        )

        print(f"\n  ✅ 单题生成完成!")
        print(f"  success: {single_result['success']}")
        print(f"  rounds:  {single_result.get('rounds', 'N/A')}")

        if single_result["success"]:
            question = single_result["question"]
            validation = single_result["validation"]
            print(f"\n  --- 生成的题目 ---")
            print(f"  题型:     {question.get('question_type')}")
            print(f"  题目:     {question.get('question', '')[:150]}")
            if question.get("options"):
                print(f"  选项:")
                for key, value in question["options"].items():
                    print(f"    {key}. {value}")
            print(f"  正确答案: {question.get('correct_answer')}")
            print(f"\n  --- 验证结果 ---")
            print(f"  decision:    {validation.get('decision')}")
            print(f"  relevance:   {validation.get('relevance')}")
            print(f"  kb_coverage: {validation.get('kb_coverage', '')[:100]}")
        else:
            print(f"  ❌ 生成失败: {single_result.get('error')}")

    except Exception as e:
        print(f"  ❌ 单题生成异常: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 5: 批量生成 generate_questions_custom()
    # -------------------------------------------------------
    print("\n--- Step 5: 批量生成 generate_questions_custom() ---")
    print(f"  需求: {MOCK_REQUIREMENT}")
    print(f"  题目数: 2")
    print(f"  输出目录: {OUTPUT_DIR}")
    print(f"  正在执行三阶段流水线...")
    print(f"  （Stage 1: Researching → Stage 2: Planning → Stage 3: Generating）")

    try:
        batch_result = await coordinator.generate_questions_custom(
            requirement=MOCK_REQUIREMENT,
            num_questions=2,
        )

        print(f"\n  ✅ 批量生成完成!")
        print(f"  success:    {batch_result['success']}")
        print(f"  requested:  {batch_result['requested']}")
        print(f"  completed:  {batch_result['completed']}")
        print(f"  failed:     {batch_result['failed']}")
        print(f"  queries:    {batch_result.get('search_queries', [])}")

        # 显示 plan
        plan = batch_result.get("plan", {})
        print(f"\n  --- Plan ---")
        for focus in plan.get("focuses", []):
            print(f"  {focus.get('id')}: {focus.get('focus')}")

        # 显示结果
        print(f"\n  --- 生成结果 ---")
        for i, result in enumerate(batch_result.get("results", []), 1):
            q = result.get("question", {})
            a = result.get("analysis", {})
            print(f"\n  [{i}] {result.get('question_id', 'N/A')}")
            print(f"      焦点:   {result.get('focus', {}).get('focus', '')[:80]}")
            print(f"      题目:   {q.get('question', '')[:100]}")
            print(f"      答案:   {q.get('correct_answer', 'N/A')}")
            print(f"      相关性: {a.get('relevance', 'N/A')}")

        # 显示失败项
        if batch_result.get("failures"):
            print(f"\n  --- 失败项 ---")
            for f in batch_result["failures"]:
                print(f"  {f.get('question_id')}: {f.get('error')}")

        # 检查输出文件
        output_dir = batch_result.get("output_dir")
        if output_dir:
            output_path = Path(output_dir)
            print(f"\n  --- 输出文件 ---")
            print(f"  目录: {output_path}")
            if output_path.exists():
                for item in sorted(output_path.rglob("*")):
                    rel = item.relative_to(output_path)
                    if item.is_file():
                        print(f"    📄 {rel} ({item.stat().st_size} bytes)")
                    else:
                        print(f"    📁 {rel}/")

    except Exception as e:
        print(f"  ❌ 批量生成异常: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 6: Token 统计
    # -------------------------------------------------------
    print("\n--- Step 6: Token 统计 ---")

    # 从 coordinator 获取
    print(f"  Coordinator token_stats:")
    for k, v in coordinator.token_stats.items():
        print(f"    {k}: {v}")

    # 从 BaseAgent 共享统计获取
    from src.agents.base_agent import BaseAgent
    stats = BaseAgent.get_stats("question")
    print(f"\n  BaseAgent 共享统计:")
    print(f"    总调用次数:   {len(stats.calls)}")
    print(f"    总输入 tokens: {stats.total_prompt_tokens}")
    print(f"    总输出 tokens: {stats.total_completion_tokens}")
    print(f"    总费用:       ${stats.total_cost:.4f}")

    print("\n" + "=" * 60)
    print("Layer 4 测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
