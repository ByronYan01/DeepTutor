#!/usr/bin/env python
"""
Layer 2: IdeaGenerationWorkflow 完整管道（编排层）
=========================================
测试 IdeaGenerationWorkflow 的 4 步管道：
  1. loose_filter()        — 宽松过滤知识点
  2. explore_ideas()       — 为每个知识点生成 ≥5 个研究想法
  3. strict_filter()       — 严格过滤（保≥1、淘汰≥2）
  4. generate_statement()  — 生成 Markdown 陈述
  5. process()             — 完整流程

调用链路：
  IdeaGenerationWorkflow.__init__()
    → BaseAgent.__init__(module_name="ideagen", agent_name="idea_generation")
      → get_llm_config()
      → PromptManager.load_prompts()  # 加载 prompts/zh/idea_generation.yaml
  IdeaGenerationWorkflow.loose_filter(knowledge_points)
    → _prompts.get("loose_filter_system")           # 研究筛选专家
    → _prompts.get("loose_filter_user_template")     # {points_text}
    → call_llm(response_format=json)
    → json.loads() → {"filtered_points": [...]}
    → 空结果降级：返回原始列表
  IdeaGenerationWorkflow.explore_ideas(knowledge_point)
    → _prompts.get("explore_ideas_system")           # 研究想法生成专家
    → _prompts.get("explore_ideas_user_template")    # {knowledge_point, description}
    → call_llm(response_format=json)
    → json.loads() → {"research_ideas": [...]}
    → 最多返回 10 个
  IdeaGenerationWorkflow.strict_filter(knowledge_point, research_ideas)
    → _prompts.get("strict_filter_system")           # 严格研究评审专家
    → _prompts.get("strict_filter_user_template")    # {knowledge_point, description, ideas_text}
    → call_llm(response_format=json)
    → json.loads() → {"kept_ideas": [...], "rejected_ideas": [...], "reasons": {...}}
    → 验证：至少保留 1 个，至少淘汰 2 个
  IdeaGenerationWorkflow.generate_statement(knowledge_point, research_ideas)
    → _prompts.get("generate_statement_system")      # 研究陈述生成专家
    → _prompts.get("generate_statement_user_template")
    → call_llm()（不要求 JSON 格式，返回 Markdown）
  IdeaGenerationWorkflow.process(knowledge_points)
    → loose_filter() → explore_ideas() × N → strict_filter() × N → generate_statement() × N
    → 拼接所有陈述为最终 Markdown

输入：知识点列表 [{"knowledge_point": str, "description": str}, ...]
输出：最终 Markdown 文档
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
# 测试数据：模拟知识点（跳过 Layer 1，直接硬编码）
# -------------------------------------------------------
MOCK_KNOWLEDGE_POINTS = [
    {
        "knowledge_point": "过拟合与正则化",
        "description": "过拟合是指模型在训练数据上表现很好但在测试数据上表现差。"
                       "防止方法包括 L1/L2 正则化、Dropout、数据增强、早停法。"
                       "L1 正则化倾向于产生稀疏解，L2 正则化倾向于让参数值较小但不为零。",
    },
    {
        "knowledge_point": "Transformer 自注意力机制",
        "description": "自注意力通过 Query/Key/Value 三个矩阵计算，"
                       "核心公式 Attention(Q,K,V) = softmax(QK^T/√d_k)V。"
                       "多头注意力将注意力分成多个头并行计算，每个头关注不同的语义子空间。"
                       "位置编码用于引入序列顺序信息。",
    },
    {
        "knowledge_point": "梯度消失与梯度爆炸",
        "description": "梯度消失：梯度经过多层连乘趋近于零，常见于 Sigmoid/Tanh。"
                       "解决方案：ReLU、残差连接（ResNet）、Batch Normalization。"
                       "梯度爆炸：梯度连乘后指数级增长。"
                       "解决方案：梯度裁剪、权重正则化、LSTM 门控机制。",
    },
]


async def main():
    print("=" * 60)
    print("Layer 2: IdeaGenerationWorkflow 完整管道测试")
    print("=" * 60)

    # -------------------------------------------------------
    # Step 1: 初始化 IdeaGenerationWorkflow
    # -------------------------------------------------------
    print("\n--- Step 1: 初始化 IdeaGenerationWorkflow ---")

    from src.agents.ideagen.idea_generation_workflow import IdeaGenerationWorkflow
    from src.services.llm import get_llm_config

    llm_config = get_llm_config()
    print(f"  LLM 配置:")
    print(f"    api_key:    {llm_config.api_key[:8]}..." if llm_config.api_key else "    api_key: None")
    print(f"    base_url:   {llm_config.base_url[:50]}..." if llm_config.base_url else "    base_url: None")

    # 进度回调：打印进度事件
    async def progress_callback(stage: str, data):
        print(f"    📡 进度事件: stage={stage}, data={data}")

    workflow = IdeaGenerationWorkflow(
        api_key=llm_config.api_key,
        base_url=llm_config.base_url,
        api_version=getattr(llm_config, "api_version", None),
        model=llm_config.model,
        progress_callback=progress_callback,
        language="zh",
    )

    print(f"\n  Workflow 属性:")
    print(f"    module_name:  {workflow.module_name}")
    print(f"    agent_name:   {workflow.agent_name}")
    print(f"    language:     {workflow.language}")
    print(f"    model:        {workflow.get_model()}")
    print(f"    has_callback: {workflow.progress_callback is not None}")

    # -------------------------------------------------------
    # Step 2: 检查 Prompt 加载
    # -------------------------------------------------------
    print("\n--- Step 2: 检查 Prompt 加载 ---")

    prompt_keys = list(workflow._prompts.keys()) if workflow._prompts else []
    print(f"  prompt keys: {prompt_keys}")

    expected_keys = [
        "loose_filter_system", "loose_filter_user_template",
        "explore_ideas_system", "explore_ideas_user_template",
        "strict_filter_system", "strict_filter_user_template",
        "generate_statement_system", "generate_statement_user_template",
    ]
    for key in expected_keys:
        value = workflow._prompts.get(key, "")
        status = "✅" if value else "❌"
        print(f"  {status} {key}: {len(value)} chars" if value else f"  {status} {key}: 未加载!")

    # -------------------------------------------------------
    # Step 3: 测试 loose_filter()（宽松过滤）
    # -------------------------------------------------------
    print("\n--- Step 3: 测试 loose_filter() ---")
    print(f"  输入知识点数: {len(MOCK_KNOWLEDGE_POINTS)}")
    for i, kp in enumerate(MOCK_KNOWLEDGE_POINTS, 1):
        print(f"  [{i}] {kp['knowledge_point']}")
    print(f"  正在调用 LLM 进行宽松过滤...")

    try:
        filtered_points = await workflow.loose_filter(MOCK_KNOWLEDGE_POINTS)
        print(f"\n  ✅ 过滤完成! {len(MOCK_KNOWLEDGE_POINTS)} → {len(filtered_points)} 个知识点")
        for i, kp in enumerate(filtered_points, 1):
            print(f"  [{i}] {kp['knowledge_point']}")
    except Exception as e:
        print(f"  ❌ 过滤失败: {e}")
        import traceback
        traceback.print_exc()
        filtered_points = MOCK_KNOWLEDGE_POINTS  # 降级：使用原始列表

    # -------------------------------------------------------
    # Step 4: 测试 explore_ideas()（创意探索，只测试第一个知识点）
    # -------------------------------------------------------
    print("\n--- Step 4: 测试 explore_ideas() ---")
    test_point = filtered_points[0]
    print(f"  知识点: {test_point['knowledge_point']}")
    print(f"  描述: {test_point['description'][:100]}...")
    print(f"  正在调用 LLM 生成研究想法...")

    try:
        research_ideas = await workflow.explore_ideas(test_point)
        print(f"\n  ✅ 生成了 {len(research_ideas)} 个研究想法:")
        for i, idea in enumerate(research_ideas, 1):
            print(f"  [{i}] {idea[:120]}{'...' if len(idea) > 120 else ''}")
    except Exception as e:
        print(f"  ❌ 生成失败: {e}")
        import traceback
        traceback.print_exc()
        research_ideas = []

    # -------------------------------------------------------
    # Step 5: 测试 strict_filter()（严格过滤）
    # -------------------------------------------------------
    print("\n--- Step 5: 测试 strict_filter() ---")

    if research_ideas:
        print(f"  输入想法数: {len(research_ideas)}")
        print(f"  知识点: {test_point['knowledge_point']}")
        print(f"  正在调用 LLM 进行严格过滤...")

        try:
            kept_ideas = await workflow.strict_filter(test_point, research_ideas)
            print(f"\n  ✅ 过滤完成! {len(research_ideas)} → {len(kept_ideas)} 个想法")
            print(f"\n  保留的想法:")
            for i, idea in enumerate(kept_ideas, 1):
                print(f"  ✅ [{i}] {idea[:120]}{'...' if len(idea) > 120 else ''}")
            print(f"\n  被淘汰的想法:")
            rejected = [idea for idea in research_ideas if idea not in kept_ideas]
            for i, idea in enumerate(rejected, 1):
                print(f"  ❌ [{i}] {idea[:120]}{'...' if len(idea) > 120 else ''}")
        except Exception as e:
            print(f"  ❌ 过滤失败: {e}")
            import traceback
            traceback.print_exc()
            kept_ideas = research_ideas[:2]  # 降级
    else:
        print(f"  ⚠️ 跳过（前面步骤未成功生成研究想法）")
        kept_ideas = []

    # -------------------------------------------------------
    # Step 6: 测试 generate_statement()（生成陈述）
    # -------------------------------------------------------
    print("\n--- Step 6: 测试 generate_statement() ---")

    if kept_ideas:
        print(f"  知识点: {test_point['knowledge_point']}")
        print(f"  保留想法数: {len(kept_ideas)}")
        print(f"  正在调用 LLM 生成 Markdown 陈述...")

        try:
            statement = await workflow.generate_statement(test_point, kept_ideas)
            print(f"\n  ✅ 陈述生成完成! 长度: {len(statement)} chars")
            print(f"\n  --- Markdown 陈述预览 ---")
            # 打印前 500 字
            for line in statement[:500].split("\n"):
                print(f"  {line}")
            if len(statement) > 500:
                print(f"  ...（省略 {len(statement) - 500} chars）")
            print(f"  --- 预览结束 ---")
        except Exception as e:
            print(f"  ❌ 生成失败: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"  ⚠️ 跳过（前面步骤未成功保留研究想法）")

    # -------------------------------------------------------
    # Step 7: 测试 process() 完整流程
    # -------------------------------------------------------
    print("\n--- Step 7: 测试 process() 完整流程 ---")
    print(f"  输入知识点数: {len(MOCK_KNOWLEDGE_POINTS)}")
    print(f"  正在执行完整 4 步管道...")
    print(f"  （loose_filter → explore_ideas × N → strict_filter × N → generate_statement × N）")

    try:
        final_markdown = await workflow.process(MOCK_KNOWLEDGE_POINTS)
        print(f"\n  ✅ 完整流程执行成功!")
        print(f"  最终 Markdown 长度: {len(final_markdown)} chars")
        print(f"\n  --- 最终 Markdown 预览（前 800 字）---")
        for line in final_markdown[:800].split("\n"):
            print(f"  {line}")
        if len(final_markdown) > 800:
            print(f"  ...（省略 {len(final_markdown) - 800} chars）")
        print(f"  --- 预览结束 ---")
    except Exception as e:
        print(f"  ❌ 完整流程失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 8: Token 统计
    # -------------------------------------------------------
    print("\n--- Step 8: Token 统计 ---")

    from src.agents.base_agent import BaseAgent
    stats = BaseAgent.get_stats("ideagen")
    print(f"  总调用次数:   {len(stats.calls)}")
    print(f"  总输入 tokens: {stats.total_prompt_tokens}")
    print(f"  总输出 tokens: {stats.total_completion_tokens}")
    print(f"  总费用:       ${stats.total_cost:.4f}")

    # 打印每次调用的详情
    if stats.calls:
        print(f"\n  --- 调用明细 ---")
        for i, call in enumerate(stats.calls, 1):
            print(f"  [{i}] agent={call.get('agent_name', 'N/A')}, "
                  f"prompt_tokens={call.get('prompt_tokens', 0)}, "
                  f"completion_tokens={call.get('completion_tokens', 0)}")

    print("\n" + "=" * 60)
    print("Layer 2 测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
