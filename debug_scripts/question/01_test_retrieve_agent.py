#!/usr/bin/env python
"""
Layer 1: RetrieveAgent 知识检索（最底层）
=========================================
测试 RetrieveAgent 的核心流程：
  1. 初始化（BaseAgent 配置 + Prompt 加载）
  2. 生成搜索查询（_generate_queries → LLM 调用）
  3. 执行单条 RAG 检索（_single_rag_search → rag_tool.rag_search）
  4. 并行执行多条检索（_execute_searches）
  5. 汇总检索结果（_summarize_retrievals）
  6. 完整流程 process()

调用链路：
  RetrieveAgent.__init__()
    → BaseAgent.__init__(module_name="question", agent_name="retrieve_agent")
      → get_llm_config()              # 从 .env 获取 LLM 配置
      → get_agent_params("question")  # 从 agents.yaml 获取 temperature/max_tokens
      → PromptManager.load_prompts()  # 加载 prompts/zh/retrieve_agent.yaml
  RetrieveAgent.process(requirement, num_queries=3)
    → _generate_queries(requirement_text, num_queries)
      → self.get_prompt("system")              # 知识库检索助手角色
      → self.get_prompt("generate_queries")    # 查询生成模板
      → self.call_llm(user_prompt, system_prompt, response_format=json)
      → json.loads(response) → {"queries": [...]}
    → _execute_searches(queries)
      → asyncio.gather(*[_single_rag_search(q) for q in queries])  # 并行
        → rag_search(query, kb_name, mode, only_need_context=True)
          → RAGService → 向量检索 pipeline
    → _summarize_retrievals(retrievals)
      → 拼接每条检索结果为文本摘要

输入：题目生成需求 dict（knowledge_point, difficulty, question_type 等）
输出：{queries, retrievals, summary, has_content}
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
# 测试数据：模拟题目生成需求
# -------------------------------------------------------
MOCK_REQUIREMENT = {
    "knowledge_point": "JavaScript 闭包",
    "difficulty": "medium",
    "question_type": "choice",
    "additional_requirements": "考察闭包的作用域链和变量捕获机制",
}

# 使用已有知识库（根据你的实际知识库名称修改）
KB_NAME = "js权威指南"


async def main():
    print("=" * 60)
    print("Layer 1: RetrieveAgent 知识检索测试")
    print("=" * 60)

    # -------------------------------------------------------
    # Step 1: 初始化 RetrieveAgent，观察 BaseAgent 配置加载
    # -------------------------------------------------------
    print("\n--- Step 1: 初始化 RetrieveAgent ---")

    from src.agents.question.agents.retrieve_agent import RetrieveAgent
    from src.services.llm import get_llm_config

    llm_config = get_llm_config()
    print(f"  LLM 配置:")
    print(f"    api_key:    {llm_config.api_key[:8]}..." if llm_config.api_key else "    api_key: None")
    print(f"    base_url:   {llm_config.base_url[:50]}..." if llm_config.base_url else "    base_url: None")
    print(f"    binding:    {llm_config.binding}")

    agent = RetrieveAgent(
        kb_name=KB_NAME,
        rag_mode="naive",      # 使用 naive 模式（纯向量检索）
        language="zh",
        api_key=llm_config.api_key,
        base_url=llm_config.base_url,
        api_version=getattr(llm_config, "api_version", None),
    )

    print(f"\n  Agent 属性:")
    print(f"    module_name:  {agent.module_name}")
    print(f"    agent_name:   {agent.agent_name}")
    print(f"    language:     {agent.language}")
    print(f"    kb_name:      {agent.kb_name}")
    print(f"    rag_mode:     {agent.rag_mode}")
    print(f"    model:        {agent.get_model()}")
    print(f"    temperature:  {agent.get_temperature()}")
    print(f"    max_tokens:   {agent.get_max_tokens()}")

    # -------------------------------------------------------
    # Step 2: 检查 Prompt 加载
    # -------------------------------------------------------
    print("\n--- Step 2: 检查 Prompt 加载 ---")

    print(f"  has_prompts:  {agent.has_prompts()}")
    print(f"  prompts keys: {list(agent.prompts.keys()) if agent.prompts else 'None'}")

    system_prompt = agent.get_prompt("system")
    if system_prompt:
        print(f"  system prompt 长度: {len(system_prompt)} chars")
        print(f"  system prompt 预览: {system_prompt[:120]}...")
    else:
        print(f"  ❌ system prompt 未加载!")

    query_template = agent.get_prompt("generate_queries")
    if query_template:
        print(f"  generate_queries 长度: {len(query_template)} chars")
        # 检查模板变量
        import re
        placeholders = re.findall(r"\{(\w+)\}", query_template)
        print(f"  generate_queries 占位符: {placeholders}")
    else:
        print(f"  ❌ generate_queries 未加载!")

    # -------------------------------------------------------
    # Step 3: 测试 _generate_queries（LLM 生成搜索查询）
    # -------------------------------------------------------
    print("\n--- Step 3: 测试 _generate_queries ---")
    print(f"  输入需求: {json.dumps(MOCK_REQUIREMENT, ensure_ascii=False, indent=2)}")
    print(f"  请求查询数: 3")
    print(f"  正在调用 LLM 生成搜索查询...")

    try:
        requirement_text = json.dumps(MOCK_REQUIREMENT, ensure_ascii=False, indent=2)
        queries = await agent._generate_queries(requirement_text, num_queries=3)
        print(f"\n  ✅ 生成了 {len(queries)} 个查询:")
        for i, q in enumerate(queries, 1):
            print(f"    [{i}] {q}")
    except Exception as e:
        print(f"  ❌ 查询生成失败: {e}")
        import traceback
        traceback.print_exc()
        queries = ["JavaScript 闭包"]  # 降级：使用原始知识点名称

    # -------------------------------------------------------
    # Step 4: 测试 _single_rag_search（单条 RAG 检索）
    # -------------------------------------------------------
    print("\n--- Step 4: 测试 _single_rag_search ---")

    test_query = queries[0] if queries else "JavaScript 闭包"
    print(f"  查询: {test_query}")
    print(f"  kb_name: {agent.kb_name}")
    print(f"  rag_mode: {agent.rag_mode}")
    print(f"  正在执行 RAG 检索...")

    try:
        single_result = await agent._single_rag_search(test_query)
        print(f"\n  ✅ 检索成功!")
        print(f"  query:  {single_result['query']}")
        print(f"  mode:   {single_result.get('mode', 'N/A')}")
        answer = single_result.get("answer", "")
        print(f"  answer 长度: {len(answer)} chars")
        if answer:
            print(f"  answer 预览: {answer[:200]}...")
        else:
            print(f"  ⚠️ answer 为空（知识库可能没有相关内容）")
    except Exception as e:
        print(f"  ❌ 检索失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 5: 测试 _execute_searches（并行检索）
    # -------------------------------------------------------
    print("\n--- Step 5: 测试 _execute_searches（并行检索）---")
    print(f"  查询列表: {queries}")
    print(f"  正在并行执行 {len(queries)} 条检索...")

    try:
        retrievals = await agent._execute_searches(queries)
        print(f"\n  ✅ 并行检索完成!")
        print(f"  成功检索数: {len(retrievals)} / {len(queries)}")
        for i, r in enumerate(retrievals, 1):
            print(f"\n  [{i}] query:  {r['query']}")
            print(f"      answer 长度: {len(r.get('answer', ''))} chars")
            print(f"      answer 预览: {r.get('answer', '')[:100]}...")
    except Exception as e:
        print(f"  ❌ 并行检索失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 6: 测试 _summarize_retrievals（汇总结果）
    # -------------------------------------------------------
    print("\n--- Step 6: 测试 _summarize_retrievals ---")

    if 'retrievals' in dir():
        summary = agent._summarize_retrievals(retrievals)
        print(f"  汇总文本长度: {len(summary)} chars")
        print(f"  汇总预览:")
        # 只打印前 500 字
        for line in summary[:500].split("\n"):
            print(f"    {line}")
        if len(summary) > 500:
            print(f"    ...（省略 {len(summary) - 500} chars）")
    else:
        print(f"  ⚠️ 跳过（前面步骤未成功获取 retrievals）")

    # -------------------------------------------------------
    # Step 7: 调用 process() 完整流程
    # -------------------------------------------------------
    print("\n--- Step 7: 调用 RetrieveAgent.process() 完整流程 ---")
    print(f"  requirement: {MOCK_REQUIREMENT}")
    print(f"  num_queries: 3")
    print(f"  正在执行完整检索流程...")

    try:
        result = await agent.process(
            requirement=MOCK_REQUIREMENT,
            num_queries=3,
        )
        print(f"\n  ✅ 完整流程执行成功!")
        print(f"  queries:     {result['queries']}")
        print(f"  retrievals 数: {len(result['retrievals'])}")
        print(f"  has_content: {result['has_content']}")
        print(f"  summary 长度: {len(result['summary'])} chars")
        print(f"  summary 预览: {result['summary'][:200]}...")
    except Exception as e:
        print(f"  ❌ 完整流程失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 8: Token 统计
    # -------------------------------------------------------
    print("\n--- Step 8: Token 统计 ---")

    from src.agents.base_agent import BaseAgent
    stats = BaseAgent.get_stats("question")
    print(f"  总调用次数:   {len(stats.calls)}")
    print(f"  总输入 tokens: {stats.total_prompt_tokens}")
    print(f"  总输出 tokens: {stats.total_completion_tokens}")
    print(f"  总费用:       ${stats.total_cost:.4f}")

    print("\n" + "=" * 60)
    print("Layer 1 测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
