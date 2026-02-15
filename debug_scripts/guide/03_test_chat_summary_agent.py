#!/usr/bin/env python
"""
Layer 3: ChatAgent 问答 + SummaryAgent 学习总结
=========================================
测试 Guide 模块中两个"消费型" Agent：
  - ChatAgent：在学习某个知识点时，回答用户的提问
  - SummaryAgent：学习全部知识点后，生成个性化学习总结报告

两个 Agent 的对比：
  ┌─────────────────┬─────────────────────┬──────────────────────┐
  │                 │ ChatAgent           │ SummaryAgent         │
  ├─────────────────┼─────────────────────┼──────────────────────┤
  │ module_name     │ guide               │ guide                │
  │ agent_name      │ chat_agent          │ summary_agent        │
  │ Prompt 角色     │ 智能学习助教        │ 学习总结专家         │
  │ 输入            │ 知识点+历史+用户问题│ 笔记本名+所有知识点  │
  │ 输出格式        │ Markdown 回答       │ Markdown 总结报告    │
  │ 调用时机        │ 学习中（每个知识点）│ 学习完成后（一次）   │
  │ LLM 调用次数    │ 每次用户提问 1 次   │ 1 次                 │
  └─────────────────┴─────────────────────┴──────────────────────┘

ChatAgent 调用链路：
  ChatAgent.process(knowledge, chat_history, user_question)
    → _format_chat_history(history)    # 格式化对话历史（最近10条）
    → get_prompt("system")             # 智能学习助教角色
    → get_prompt("user_template")      # 模板含：knowledge_title/summary/difficulty + history + question
    → user_template.format(...)        # 填充参数
    → self.call_llm(user_prompt, system_prompt)
    → 返回 {success, answer}

SummaryAgent 调用链路：
  SummaryAgent.process(notebook_name, knowledge_points, chat_history)
    → _format_knowledge_points(points) # 格式化所有知识点
    → _format_chat_history(history)    # 格式化完整对话历史（含 knowledge_index 分组）
    → get_prompt("system")             # 学习总结专家角色
    → get_prompt("user_template")      # 模板含：notebook_name + points + history
    → self.call_llm(user_prompt, system_prompt)
    → 清理 Markdown 包裹（去掉 ```markdown...```）
    → 返回 {success, summary, total_points, total_interactions}
"""

import asyncio
import sys
import time
from pathlib import Path

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env", override=False)


# -------------------------------------------------------
# 测试数据：模拟知识点和对话历史
# -------------------------------------------------------
MOCK_KNOWLEDGE_POINTS = [
    {
        "knowledge_title": "监督学习基础",
        "knowledge_summary": "监督学习通过带标签数据学习映射关系，常见算法有线性回归、决策树、SVM等。",
        "user_difficulty": "用户可能不理解为什么需要标签数据，以及如何选择合适的算法。",
    },
    {
        "knowledge_title": "线性回归与损失函数",
        "knowledge_summary": "线性回归模型 y=wx+b，通过最小化 MSE 损失函数学习参数，使用梯度下降优化。",
        "user_difficulty": "用户可能对梯度下降的直觉理解不足，不清楚学习率如何影响收敛。",
    },
    {
        "knowledge_title": "决策树与信息增益",
        "knowledge_summary": "决策树通过递归分割数据集进行分类，使用信息增益选择最优特征。",
        "user_difficulty": "用户可能对信息熵的数学公式理解困难，不清楚树的剪枝作用。",
    },
]

# 当前正在学习的知识点（第一个）
CURRENT_KNOWLEDGE = MOCK_KNOWLEDGE_POINTS[0]

# 模拟对话历史（学习过程中的交互）
MOCK_CHAT_HISTORY = [
    {
        "role": "system",
        "content": "开始学习知识点 1: 监督学习基础",
        "knowledge_index": 0,
        "timestamp": time.time() - 300,
    },
    {
        "role": "user",
        "content": "监督学习中的标签具体是什么意思？能举个例子吗？",
        "knowledge_index": 0,
        "timestamp": time.time() - 250,
    },
    {
        "role": "assistant",
        "content": "标签就是数据对应的正确答案。比如图片分类任务中，一张猫的图片，它的标签就是「猫」。",
        "knowledge_index": 0,
        "timestamp": time.time() - 240,
    },
]


async def main():
    print("=" * 60)
    print("Layer 3: ChatAgent + SummaryAgent 测试")
    print("=" * 60)

    from src.agents.guide.agents.chat_agent import ChatAgent
    from src.agents.guide.agents.summary_agent import SummaryAgent
    from src.services.llm import get_llm_config

    llm_config = get_llm_config()

    # -------------------------------------------------------
    # Part A: ChatAgent 测试
    # -------------------------------------------------------
    print("\n" + "=" * 40)
    print("Part A: ChatAgent 学习问答")
    print("=" * 40)

    # Step 1: 初始化 ChatAgent
    print("\n--- Step 1: 初始化 ChatAgent ---")

    chat_agent = ChatAgent(
        api_key=llm_config.api_key,
        base_url=llm_config.base_url,
        language="zh",
        api_version=getattr(llm_config, "api_version", None),
        binding=llm_config.binding,
    )

    print(f"  module_name:  {chat_agent.module_name}")
    print(f"  agent_name:   {chat_agent.agent_name}")
    print(f"  model:        {chat_agent.get_model()}")

    # Step 2: 检查 Prompt
    print("\n--- Step 2: ChatAgent Prompt 检查 ---")

    system_prompt = chat_agent.get_prompt("system")
    user_template = chat_agent.get_prompt("user_template")
    print(f"  system prompt: {len(system_prompt)} chars" if system_prompt else "  ❌ system prompt 缺失")
    print(f"  user_template: {len(user_template)} chars" if user_template else "  ❌ user_template 缺失")

    if user_template:
        import re
        placeholders = re.findall(r"\{(\w+)\}", user_template)
        print(f"  user_template 占位符: {placeholders}")

    # Step 3: 测试 _format_chat_history
    print("\n--- Step 3: _format_chat_history ---")

    formatted_history = chat_agent._format_chat_history(MOCK_CHAT_HISTORY)
    print(f"  输入历史条数: {len(MOCK_CHAT_HISTORY)}")
    print(f"  格式化结果预览:")
    print(f"    {formatted_history[:200]}...")

    # Step 4: 调用 ChatAgent.process()
    print("\n--- Step 4: ChatAgent.process() ---")

    test_question = "监督学习和无监督学习在实际项目中怎么选择？有没有什么经验法则？"
    print(f"  当前知识点: {CURRENT_KNOWLEDGE['knowledge_title']}")
    print(f"  用户提问:   {test_question}")
    print(f"  历史条数:   {len(MOCK_CHAT_HISTORY)}")
    print(f"  正在调用 LLM...")

    try:
        chat_result = await chat_agent.process(
            knowledge=CURRENT_KNOWLEDGE,
            chat_history=MOCK_CHAT_HISTORY,
            user_question=test_question,
        )

        print(f"\n  ✅ 回答完成!")
        print(f"  success: {chat_result['success']}")
        answer = chat_result.get("answer", "")
        print(f"  回答长度: {len(answer)} chars")
        print(f"  回答预览:")
        # 打印前300字
        for line in answer[:300].split("\n"):
            print(f"    {line}")
        if len(answer) > 300:
            print(f"    ...")

    except Exception as e:
        print(f"  ❌ 回答失败: {e}")
        import traceback
        traceback.print_exc()

    # Step 5: 测试边界情况 - 空问题
    print("\n--- Step 5: 边界情况 - 空问题 ---")

    empty_result = await chat_agent.process(
        knowledge=CURRENT_KNOWLEDGE,
        chat_history=[],
        user_question="   ",
    )
    print(f"  空问题结果: success={empty_result['success']}, error={empty_result.get('error', 'None')}")

    # -------------------------------------------------------
    # Part B: SummaryAgent 测试
    # -------------------------------------------------------
    print("\n" + "=" * 40)
    print("Part B: SummaryAgent 学习总结")
    print("=" * 40)

    # Step 6: 初始化 SummaryAgent
    print("\n--- Step 6: 初始化 SummaryAgent ---")

    summary_agent = SummaryAgent(
        api_key=llm_config.api_key,
        base_url=llm_config.base_url,
        language="zh",
        api_version=getattr(llm_config, "api_version", None),
        binding=llm_config.binding,
    )

    print(f"  module_name:  {summary_agent.module_name}")
    print(f"  agent_name:   {summary_agent.agent_name}")
    print(f"  model:        {summary_agent.get_model()}")

    # Step 7: 检查 Prompt
    print("\n--- Step 7: SummaryAgent Prompt 检查 ---")

    system_prompt = summary_agent.get_prompt("system")
    user_template = summary_agent.get_prompt("user_template")
    print(f"  system prompt: {len(system_prompt)} chars" if system_prompt else "  ❌ system prompt 缺失")
    print(f"  user_template: {len(user_template)} chars" if user_template else "  ❌ user_template 缺失")

    # Step 8: 测试格式化方法
    print("\n--- Step 8: 格式化方法测试 ---")

    formatted_points = summary_agent._format_knowledge_points(MOCK_KNOWLEDGE_POINTS)
    print(f"  _format_knowledge_points 结果 ({len(formatted_points)} chars):")
    print(f"    {formatted_points[:200]}...")

    # 构建完整的对话历史（含多个知识点的交互）
    full_chat_history = MOCK_CHAT_HISTORY + [
        {
            "role": "system",
            "content": "进入知识点 2: 线性回归与损失函数",
            "knowledge_index": 1,
            "timestamp": time.time() - 180,
        },
        {
            "role": "user",
            "content": "梯度下降中的学习率设太大会怎样？",
            "knowledge_index": 1,
            "timestamp": time.time() - 150,
        },
        {
            "role": "assistant",
            "content": "学习率太大会导致参数在最优值附近来回震荡，甚至发散，无法收敛到最小值。",
            "knowledge_index": 1,
            "timestamp": time.time() - 140,
        },
    ]

    formatted_history = summary_agent._format_chat_history(full_chat_history)
    print(f"\n  _format_chat_history 结果 ({len(formatted_history)} chars):")
    print(f"    {formatted_history[:300]}...")

    # Step 9: 调用 SummaryAgent.process()
    print("\n--- Step 9: SummaryAgent.process() ---")
    print(f"  笔记本名称: Python 机器学习入门")
    print(f"  知识点数量: {len(MOCK_KNOWLEDGE_POINTS)}")
    print(f"  对话历史数: {len(full_chat_history)}")
    print(f"  正在调用 LLM 生成总结报告...")

    try:
        summary_result = await summary_agent.process(
            notebook_name="Python 机器学习入门",
            knowledge_points=MOCK_KNOWLEDGE_POINTS,
            chat_history=full_chat_history,
        )

        print(f"\n  ✅ 总结完成!")
        print(f"  success:          {summary_result['success']}")
        print(f"  total_points:     {summary_result.get('total_points', 0)}")
        print(f"  total_interactions: {summary_result.get('total_interactions', 0)}")

        summary = summary_result.get("summary", "")
        print(f"  总结长度:         {len(summary)} chars")
        print(f"\n  --- 总结报告预览 ---")
        for line in summary[:500].split("\n"):
            print(f"  {line}")
        if len(summary) > 500:
            print(f"  ...")

    except Exception as e:
        print(f"  ❌ 总结失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 10: Token 统计对比
    # -------------------------------------------------------
    print("\n--- Step 10: Token 统计 ---")

    from src.agents.base_agent import BaseAgent
    stats = BaseAgent.get_stats("guide")
    print(f"  Guide 模块总计:")
    print(f"    调用次数:   {stats.total_calls}")
    print(f"    输入 tokens: {stats.total_input_tokens}")
    print(f"    输出 tokens: {stats.total_output_tokens}")

    print("\n" + "=" * 60)
    print("Layer 3 测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
