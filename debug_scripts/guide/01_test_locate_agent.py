#!/usr/bin/env python
"""
Layer 1: LocateAgent 知识点定位（最底层）
=========================================
测试 LocateAgent 的核心流程：
  1. 初始化（BaseAgent 配置 + Prompt 加载）
  2. 格式化笔记本记录（_format_records）
  3. 调用 LLM 分析笔记本内容，提取知识点（JSON 输出）
  4. 验证并规范化知识点结构

调用链路：
  LocateAgent.__init__()
    → BaseAgent.__init__(module_name="guide", agent_name="locate_agent")
      → get_llm_config()              # 从 .env 获取 LLM 配置
      → get_agent_params("guide")     # 从 agents.yaml 获取 temperature/max_tokens
      → PromptManager.load_prompts()  # 加载 prompts/zh/locate_agent.yaml
  LocateAgent.process(notebook_id, notebook_name, records)
    → _format_records(records)           # 格式化笔记本记录为可读文本
    → self.get_prompt("system")          # 获取 system prompt（学习规划师角色）
    → self.get_prompt("user_template")   # 获取 user 模板
    → user_template.format(...)          # 填充模板参数
    → self.call_llm(user_prompt, system_prompt, response_format=json)  # 调用 LLM
      → llm_complete() → cloud/local provider
    → json.loads(response)               # 解析 JSON 响应
    → 验证每个知识点：knowledge_title, knowledge_summary, user_difficulty

输入：笔记本记录列表（模拟用户在 notebook 中的学习记录）
输出：知识点列表 [{knowledge_title, knowledge_summary, user_difficulty}, ...]
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
# 测试数据：模拟笔记本中的学习记录
# -------------------------------------------------------
MOCK_NOTEBOOK_ID = "test-notebook-001"
MOCK_NOTEBOOK_NAME = "Python 机器学习入门"
MOCK_RECORDS = [
    {
        "type": "chat",
        "title": "什么是监督学习？",
        "user_query": "请解释一下什么是监督学习，它和无监督学习有什么区别？",
        "output": "监督学习是一种机器学习方法，通过使用带标签的训练数据来学习输入到输出的映射关系。"
                  "在监督学习中，每个训练样本都有对应的正确答案（标签），模型通过最小化预测值和真实值之间的差距来学习。\n\n"
                  "与之相对的无监督学习，训练数据没有标签，模型需要自己发现数据中的模式和结构，"
                  "常见的无监督学习方法包括聚类（K-Means）和降维（PCA）。",
    },
    {
        "type": "chat",
        "title": "线性回归原理",
        "user_query": "线性回归的数学原理是什么？损失函数是怎么定义的？",
        "output": "线性回归是最基础的监督学习算法，用于预测连续值。其数学模型为：y = wx + b\n\n"
                  "其中 w 是权重，b 是偏置。模型通过最小化均方误差（MSE）损失函数来学习参数：\n"
                  "MSE = (1/n) * Σ(y_pred - y_true)²\n\n"
                  "优化方法通常使用梯度下降：w = w - lr * ∂MSE/∂w",
    },
    {
        "type": "chat",
        "title": "决策树如何工作？",
        "user_query": "决策树是怎么做分类的？什么是信息增益？",
        "output": "决策树通过递归地将数据集分割成子集来进行分类。每次分割选择最优特征，"
                  "使得分割后的子集尽可能「纯」（同类样本聚集）。\n\n"
                  "信息增益是衡量特征重要性的指标，基于信息熵的概念：\n"
                  "H(S) = -Σ p_i * log2(p_i)\n"
                  "信息增益 = H(父节点) - Σ(子节点样本比例 * H(子节点))\n\n"
                  "选择信息增益最大的特征作为分割依据。",
    },
]


async def main():
    print("=" * 60)
    print("Layer 1: LocateAgent 知识点定位测试")
    print("=" * 60)

    # -------------------------------------------------------
    # Step 1: 初始化 LocateAgent，观察 BaseAgent 配置加载
    # -------------------------------------------------------
    print("\n--- Step 1: 初始化 LocateAgent ---")

    from src.agents.guide.agents.locate_agent import LocateAgent
    from src.services.llm import get_llm_config

    llm_config = get_llm_config()
    print(f"  LLM 配置:")
    print(f"    api_key:    {llm_config.api_key[:8]}..." if llm_config.api_key else "    api_key: None")
    print(f"    base_url:   {llm_config.base_url[:50]}..." if llm_config.base_url else "    base_url: None")
    print(f"    binding:    {llm_config.binding}")

    agent = LocateAgent(
        api_key=llm_config.api_key,
        base_url=llm_config.base_url,
        language="zh",
        api_version=getattr(llm_config, "api_version", None),
        binding=llm_config.binding,
    )

    print(f"\n  Agent 属性:")
    print(f"    module_name:  {agent.module_name}")
    print(f"    agent_name:   {agent.agent_name}")
    print(f"    language:     {agent.language}")
    print(f"    model:        {agent.get_model()}")
    print(f"    temperature:  {agent.get_temperature()}")
    print(f"    max_tokens:   {agent.get_max_tokens()}")
    print(f"    enabled:      {agent.is_enabled()}")

    # -------------------------------------------------------
    # Step 2: 检查 Prompt 加载（PromptManager）
    # -------------------------------------------------------
    print("\n--- Step 2: 检查 Prompt 加载 ---")

    print(f"  has_prompts:  {agent.has_prompts()}")
    print(f"  prompts keys: {list(agent.prompts.keys()) if agent.prompts else 'None'}")

    system_prompt = agent.get_prompt("system")
    if system_prompt:
        print(f"  system prompt 长度: {len(system_prompt)} chars")
        print(f"  system prompt 预览: {system_prompt[:100]}...")
    else:
        print(f"  ❌ system prompt 未加载!")

    user_template = agent.get_prompt("user_template")
    if user_template:
        print(f"  user_template 长度: {len(user_template)} chars")
        # 检查模板变量
        import re
        placeholders = re.findall(r"\{(\w+)\}", user_template)
        print(f"  user_template 占位符: {placeholders}")
    else:
        print(f"  ❌ user_template 未加载!")

    # -------------------------------------------------------
    # Step 3: 测试 _format_records（数据预处理）
    # -------------------------------------------------------
    print("\n--- Step 3: 测试 _format_records ---")

    formatted = agent._format_records(MOCK_RECORDS)
    print(f"  输入记录数: {len(MOCK_RECORDS)}")
    print(f"  格式化后长度: {len(formatted)} chars")
    print(f"  格式化预览 (前300字):")
    print(f"    {formatted[:300]}...")

    # -------------------------------------------------------
    # Step 4: 调用 process() 完整流程（调用 LLM）
    # -------------------------------------------------------
    print("\n--- Step 4: 调用 LocateAgent.process() ---")
    print(f"  notebook_id:   {MOCK_NOTEBOOK_ID}")
    print(f"  notebook_name: {MOCK_NOTEBOOK_NAME}")
    print(f"  records 数量:  {len(MOCK_RECORDS)}")
    print(f"  正在调用 LLM 分析知识点...")

    try:
        result = await agent.process(
            notebook_id=MOCK_NOTEBOOK_ID,
            notebook_name=MOCK_NOTEBOOK_NAME,
            records=MOCK_RECORDS,
        )

        print(f"\n  ✅ 分析完成!")
        print(f"  success:      {result['success']}")
        print(f"  total_points: {result.get('total_points', 0)}")

        if result["success"]:
            knowledge_points = result["knowledge_points"]
            print(f"\n  --- 知识点列表 ---")
            for i, point in enumerate(knowledge_points, 1):
                print(f"\n  [{i}] {point['knowledge_title']}")
                print(f"      摘要: {point['knowledge_summary'][:100]}...")
                print(f"      难点: {point['user_difficulty'][:100]}...")
        else:
            print(f"  ❌ 分析失败: {result.get('error', 'Unknown')}")
            if "raw_response" in result:
                print(f"  原始响应: {result['raw_response'][:200]}...")

    except Exception as e:
        print(f"  ❌ 调用失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 5: 测试边界情况 - 空记录
    # -------------------------------------------------------
    print("\n--- Step 5: 测试边界情况 - 空记录 ---")

    empty_result = await agent.process(
        notebook_id="empty-notebook",
        notebook_name="空笔记本",
        records=[],
    )
    print(f"  空记录结果: success={empty_result['success']}, error={empty_result.get('error', 'None')}")

    # -------------------------------------------------------
    # Step 6: Token 统计
    # -------------------------------------------------------
    print("\n--- Step 6: Token 统计 ---")

    from src.agents.base_agent import BaseAgent
    stats = BaseAgent.get_stats("guide")
    print(f"  总调用次数:   {len(stats.calls)}")
    print(f"  总输入 tokens: {stats.total_prompt_tokens}")
    print(f"  总输出 tokens: {stats.total_completion_tokens}")
    print(f"  总费用:       ${stats.total_cost:.4f}")

    print("\n" + "=" * 60)
    print("Layer 1 测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
