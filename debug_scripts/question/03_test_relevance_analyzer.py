#!/usr/bin/env python
"""
Layer 3: RelevanceAnalyzer 相关性分析
=========================================
测试 RelevanceAnalyzer 的核心流程：
  1. 初始化（BaseAgent 配置 + Prompt 加载）
  2. 分析题目与知识库内容的相关性
  3. JSON 解析和相关性分类（high / partial）

调用链路：
  RelevanceAnalyzer.__init__()
    → BaseAgent.__init__(module_name="question", agent_name="relevance_analyzer")
      → PromptManager.load_prompts()  # 加载 prompts/zh/relevance_analyzer.yaml
  RelevanceAnalyzer.process(question, knowledge_context)
    → json.dumps(question)                    # 格式化题目为 JSON 字符串
    → 截断知识上下文（最大 4000 chars）
    → self.get_prompt("system")
    → self.get_prompt("analyze_relevance")    # 分析模板
    → self.call_llm(user_prompt, system_prompt, response_format=json, temperature=0.3)
    → _parse_analysis_response(response)
      → _extract_json_from_markdown()
      → _clean_json_string()
      → json.loads() → 分析结果 dict
    → 归一化 relevance 值（只允许 "high" 或 "partial"）

关键设计：
  - 没有拒绝（rejection）机制 — 所有题目都会被接受
  - 单次分析（single-pass）— 没有迭代循环
  - temperature=0.3 — 较低温度确保分析一致性

输入：题目 dict + 知识上下文
输出：{relevance: "high"|"partial", kb_coverage: str, extension_points: str}
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
# 模拟知识上下文
MOCK_KNOWLEDGE_CONTEXT = """
=== Query: 闭包 ===
闭包（Closure）是指一个函数能够记住并访问其词法作用域，即使该函数在其词法作用域之外执行。
闭包的关键特性：函数嵌套、变量持久化、作用域链。

=== Query: 作用域链 ===
JavaScript 使用词法作用域（静态作用域），变量的作用域在编写代码时就确定了。
"""

# 高相关性题目（完全基于知识库内容）
MOCK_QUESTION_HIGH = {
    "question_type": "choice",
    "question": "以下关于 JavaScript 闭包的描述，哪个是正确的？",
    "options": {
        "A": "闭包只能在全局作用域中创建",
        "B": "闭包允许函数访问其词法作用域之外的变量",
        "C": "闭包是指函数能够记住并访问其词法作用域",
        "D": "闭包会导致变量在函数返回后立即被销毁",
    },
    "correct_answer": "C",
    "explanation": "闭包是指一个函数能够记住并访问其定义时的词法作用域，即使在其词法作用域之外执行。",
    "knowledge_point": "JavaScript 闭包",
}

# 部分相关性题目（涉及知识库之外的内容）
MOCK_QUESTION_PARTIAL = {
    "question_type": "written",
    "question": "请解释 JavaScript 中闭包与内存泄漏的关系，并说明如何在 React Hooks 中避免闭包导致的 stale state 问题。",
    "correct_answer": "闭包持有对外部变量的引用，可能导致不再使用的对象无法被垃圾回收。在 React 中，useEffect 的回调函数形成闭包...",
    "explanation": "这个问题涉及了闭包的高级应用场景，包括内存管理和 React 框架特定的问题。",
    "knowledge_point": "JavaScript 闭包与内存管理",
}


async def main():
    print("=" * 60)
    print("Layer 3: RelevanceAnalyzer 相关性分析测试")
    print("=" * 60)

    # -------------------------------------------------------
    # Step 1: 初始化 RelevanceAnalyzer
    # -------------------------------------------------------
    print("\n--- Step 1: 初始化 RelevanceAnalyzer ---")

    from src.agents.question.agents.relevance_analyzer import RelevanceAnalyzer
    from src.services.llm import get_llm_config

    llm_config = get_llm_config()
    agent = RelevanceAnalyzer(
        language="zh",
        api_key=llm_config.api_key,
        base_url=llm_config.base_url,
        api_version=getattr(llm_config, "api_version", None),
    )

    print(f"  module_name:  {agent.module_name}")
    print(f"  agent_name:   {agent.agent_name}")
    print(f"  language:     {agent.language}")
    print(f"  model:        {agent.get_model()}")
    print(f"  temperature:  {agent.get_temperature()}")
    print(f"  max_tokens:   {agent.get_max_tokens()}")

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

    analyze_template = agent.get_prompt("analyze_relevance")
    if analyze_template:
        print(f"  analyze_relevance 长度: {len(analyze_template)} chars")
        import re
        placeholders = re.findall(r"\{(\w+)\}", analyze_template)
        print(f"  analyze_relevance 占位符: {placeholders}")
    else:
        print(f"  ⚠️ analyze_relevance 未加载（检查 prompt key 名称）")

    # 列出所有可用 prompt keys
    if agent.prompts:
        print(f"  所有 prompt keys: {list(agent.prompts.keys())}")

    # -------------------------------------------------------
    # Step 3: 测试 JSON 解析辅助方法
    # -------------------------------------------------------
    print("\n--- Step 3: 测试 JSON 解析辅助方法 ---")

    # _extract_json_from_markdown
    test_input = '```json\n{"relevance": "high", "kb_coverage": "test"}\n```'
    extracted = agent._extract_json_from_markdown(test_input)
    print(f"  提取 JSON: {extracted}")

    # _clean_json_string
    dirty = '{"r": "含\x00控制\x01字符"}'
    clean = agent._clean_json_string(dirty)
    print(f"  清理控制字符: {repr(dirty[:30])} → {repr(clean[:30])}")

    # _parse_analysis_response
    print("\n  _parse_analysis_response 测试:")
    test_responses = [
        ("标准 JSON", '{"relevance": "high", "kb_coverage": "全部覆盖", "extension_points": ""}'),
        ("markdown 包裹", '```json\n{"relevance": "partial", "kb_coverage": "部分", "extension_points": "涉及React"}\n```'),
        ("非标准 relevance", '{"relevance": "medium", "kb_coverage": "test"}'),
    ]
    for name, resp in test_responses:
        try:
            parsed = agent._parse_analysis_response(resp)
            print(f"    {name}: relevance={parsed['relevance']}")
        except Exception as e:
            print(f"    {name}: ❌ 失败 - {e}")

    # -------------------------------------------------------
    # Step 4: 分析高相关性题目
    # -------------------------------------------------------
    print("\n--- Step 4: 分析高相关性题目 ---")
    print(f"  题目: {MOCK_QUESTION_HIGH['question'][:80]}...")
    print(f"  正在调用 LLM 分析相关性...")

    try:
        result_high = await agent.process(
            question=MOCK_QUESTION_HIGH,
            knowledge_context=MOCK_KNOWLEDGE_CONTEXT,
        )
        print(f"\n  ✅ 分析完成!")
        print(f"  relevance:        {result_high['relevance']}")
        print(f"  kb_coverage:      {result_high['kb_coverage'][:150]}")
        print(f"  extension_points: {result_high.get('extension_points', '无')}")
    except Exception as e:
        print(f"  ❌ 分析失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 5: 分析部分相关性题目
    # -------------------------------------------------------
    print("\n--- Step 5: 分析部分相关性题目（预期: partial）---")
    print(f"  题目: {MOCK_QUESTION_PARTIAL['question'][:80]}...")
    print(f"  正在调用 LLM 分析相关性...")

    try:
        result_partial = await agent.process(
            question=MOCK_QUESTION_PARTIAL,
            knowledge_context=MOCK_KNOWLEDGE_CONTEXT,
        )
        print(f"\n  ✅ 分析完成!")
        print(f"  relevance:        {result_partial['relevance']}")
        print(f"  kb_coverage:      {result_partial['kb_coverage'][:150]}")
        print(f"  extension_points: {result_partial.get('extension_points', '无')}")
    except Exception as e:
        print(f"  ❌ 分析失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 6: 对比两次分析结果
    # -------------------------------------------------------
    print("\n--- Step 6: 对比分析结果 ---")

    if 'result_high' in dir() and 'result_partial' in dir():
        print(f"  高相关题目:   relevance = {result_high.get('relevance', 'N/A')}")
        print(f"  部分相关题目: relevance = {result_partial.get('relevance', 'N/A')}")
        print(f"\n  设计要点:")
        print(f"    - 两道题都被「接受」（没有 rejection 机制）")
        print(f"    - 只是分类为 high 或 partial")
        print(f"    - partial 题目会有 extension_points 说明超出知识库的部分")

    # -------------------------------------------------------
    # Step 7: Token 统计
    # -------------------------------------------------------
    print("\n--- Step 7: Token 统计 ---")

    from src.agents.base_agent import BaseAgent
    stats = BaseAgent.get_stats("question")
    print(f"  总调用次数:   {len(stats.calls)}")
    print(f"  总输入 tokens: {stats.total_prompt_tokens}")
    print(f"  总输出 tokens: {stats.total_completion_tokens}")
    print(f"  总费用:       ${stats.total_cost:.4f}")
    print(f"  （注意：RelevanceAnalyzer 使用 temperature=0.3，输出更稳定）")

    print("\n" + "=" * 60)
    print("Layer 3 测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
