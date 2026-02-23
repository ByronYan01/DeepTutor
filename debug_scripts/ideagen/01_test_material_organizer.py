#!/usr/bin/env python
"""
Layer 1: MaterialOrganizerAgent 知识点提取（底层）
=========================================
测试 MaterialOrganizerAgent 的核心流程：
  1. 初始化（BaseAgent 配置 + Prompt 加载）
  2. 构造素材文本（records → materials_text）
  3. 调用 LLM 提取知识点（JSON 格式）
  4. 验证和过滤知识点（knowledge_point + description）
  5. 降级提取（_fallback_extract）

调用链路：
  MaterialOrganizerAgent.__init__()
    → BaseAgent.__init__(module_name="ideagen", agent_name="material_organizer")
      → get_llm_config()              # 从 .env 获取 LLM 配置
      → get_agent_params("ideagen")   # 从 agents.yaml 获取 temperature/max_tokens
      → PromptManager.load_prompts()  # 加载 prompts/zh/material_organizer.yaml
  MaterialOrganizerAgent.process(records, user_thoughts)
    → 遍历 records 提取 type/title/user_query/output
    → 拼接 materials_text（每条记录带编号和字段标签）
    → 拼接 user_thoughts_text（可选）
    → self._prompts.get("system")          # 知识整理专家角色
    → self._prompts.get("user_template")   # {materials_text}{user_thoughts_text}
    → self.call_llm(response_format=json)
    → json.loads(response) → {"knowledge_points": [...]}
    → 验证每个知识点：必须有 knowledge_point + description，description ≥ 10 字
    → 验证失败时 → _fallback_extract()     # 降级策略

输入：笔记本记录列表（包含 type、title、user_query、output 字段）
输出：知识点列表 [{"knowledge_point": str, "description": str}, ...]
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
# 测试数据：模拟笔记本记录
# -------------------------------------------------------
MOCK_RECORDS = [
    {
        "type": "solve",
        "title": "机器学习中的过拟合问题",
        "user_query": "什么是过拟合？如何防止过拟合？",
        "output": "过拟合（Overfitting）是指模型在训练数据上表现很好，但在未见过的测试数据上表现差。"
                  "主要原因包括：模型过于复杂、训练数据不足、特征噪声过多。"
                  "防止方法：1. 正则化（L1/L2）2. Dropout 3. 数据增强 4. 早停法（Early Stopping）"
                  "5. 交叉验证。正则化通过在损失函数中添加惩罚项来约束模型参数的大小，"
                  "L1 正则化倾向于产生稀疏解，L2 正则化倾向于让参数值较小但不为零。",
    },
    {
        "type": "research",
        "title": "Transformer 注意力机制",
        "user_query": "解释 Transformer 中的自注意力机制是如何工作的",
        "output": "Transformer 的自注意力（Self-Attention）机制通过 Query、Key、Value 三个矩阵计算。"
                  "核心公式：Attention(Q,K,V) = softmax(QK^T / √d_k) V。"
                  "多头注意力（Multi-Head Attention）将注意力计算分成多个头并行进行，"
                  "每个头关注不同的语义子空间，最后拼接结果。这种设计使模型能够在不同的表示子空间中"
                  "同时关注来自不同位置的信息。位置编码（Positional Encoding）用于引入序列顺序信息。",
    },
    {
        "type": "question",
        "title": "梯度消失与梯度爆炸",
        "user_query": "深度神经网络中梯度消失和梯度爆炸问题的原因和解决方案",
        "output": "梯度消失：在反向传播中，梯度经过多层连乘后趋近于零，导致深层参数无法有效更新。"
                  "常见于 Sigmoid/Tanh 激活函数。解决方案：ReLU 激活函数、残差连接（ResNet）、"
                  "Batch Normalization。梯度爆炸：梯度连乘后指数级增长。"
                  "解决方案：梯度裁剪（Gradient Clipping）、权重正则化、LSTM 的门控机制。",
    },
]

MOCK_USER_THOUGHTS = "我对深度学习的基础理论很感兴趣，特别是训练优化方面"


async def main():
    print("=" * 60)
    print("Layer 1: MaterialOrganizerAgent 知识点提取测试")
    print("=" * 60)

    # -------------------------------------------------------
    # Step 1: 初始化 MaterialOrganizerAgent
    # -------------------------------------------------------
    print("\n--- Step 1: 初始化 MaterialOrganizerAgent ---")

    from src.agents.ideagen.material_organizer_agent import MaterialOrganizerAgent
    from src.services.llm import get_llm_config

    llm_config = get_llm_config()
    print(f"  LLM 配置:")
    print(f"    api_key:    {llm_config.api_key[:8]}..." if llm_config.api_key else "    api_key: None")
    print(f"    base_url:   {llm_config.base_url[:50]}..." if llm_config.base_url else "    base_url: None")
    print(f"    binding:    {llm_config.binding}")

    agent = MaterialOrganizerAgent(
        language="zh",
        api_key=llm_config.api_key,
        base_url=llm_config.base_url,
        api_version=getattr(llm_config, "api_version", None),
        model=llm_config.model,
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

    prompt_keys = list(agent._prompts.keys()) if agent._prompts else []
    print(f"  prompt keys: {prompt_keys}")

    # 检查每个 prompt
    expected_keys = ["system", "user_template", "fallback_system", "fallback_user_template"]
    for key in expected_keys:
        value = agent._prompts.get(key, "")
        if value:
            print(f"  ✅ {key}: {len(value)} chars")
            print(f"     预览: {value[:80].replace(chr(10), ' ')}...")
        else:
            print(f"  ❌ {key}: 未加载!")

    # -------------------------------------------------------
    # Step 3: 观察素材文本构造过程
    # -------------------------------------------------------
    print("\n--- Step 3: 观察素材文本构造过程 ---")
    print(f"  输入记录数: {len(MOCK_RECORDS)}")

    # 还原 process() 中的素材构造逻辑
    materials = []
    for record in MOCK_RECORDS:
        materials.append({
            "type": record.get("type", ""),
            "title": record.get("title", ""),
            "user_query": record.get("user_query", ""),
            "output": record.get("output", ""),
        })

    materials_text = ""
    for i, mat in enumerate(materials, 1):
        materials_text += f"\n\n=== Record {i} ===\n"
        materials_text += f"Type: {mat['type']}\n"
        materials_text += f"Title: {mat['title']}\n"
        materials_text += f"User Query: {mat['user_query']}\n"
        materials_text += f"System Response: {mat['output']}\n"

    print(f"  materials_text 长度: {len(materials_text)} chars")
    print(f"  前 300 字预览:")
    for line in materials_text[:300].split("\n"):
        print(f"    {line}")
    if len(materials_text) > 300:
        print(f"    ...（省略 {len(materials_text) - 300} chars）")

    user_thoughts_text = f"\n\nUser Additional Thoughts:\n{MOCK_USER_THOUGHTS}"
    print(f"\n  user_thoughts_text: {user_thoughts_text}")

    # 展示最终 user_prompt
    user_template = agent._prompts.get("user_template", "")
    if user_template:
        user_prompt = user_template.format(
            materials_text=materials_text,
            user_thoughts_text=user_thoughts_text,
        )
        print(f"\n  最终 user_prompt 长度: {len(user_prompt)} chars")

    # -------------------------------------------------------
    # Step 4: 调用 process() 提取知识点
    # -------------------------------------------------------
    print("\n--- Step 4: 调用 process() 提取知识点 ---")
    print(f"  records 数量: {len(MOCK_RECORDS)}")
    print(f"  user_thoughts: {MOCK_USER_THOUGHTS}")
    print(f"  正在调用 LLM 提取知识点...")

    try:
        knowledge_points = await agent.process(
            records=MOCK_RECORDS,
            user_thoughts=MOCK_USER_THOUGHTS,
        )

        print(f"\n  ✅ 提取完成! 共 {len(knowledge_points)} 个知识点:")
        for i, kp in enumerate(knowledge_points, 1):
            name = kp.get("knowledge_point", "未知")
            desc = kp.get("description", "")
            print(f"\n  [{i}] 知识点: {name}")
            print(f"      描述长度: {len(desc)} chars")
            print(f"      描述预览: {desc[:150]}...")

    except Exception as e:
        print(f"  ❌ 提取失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 5: 测试无 user_thoughts 的情况
    # -------------------------------------------------------
    print("\n--- Step 5: 测试无 user_thoughts 的情况 ---")
    print(f"  records 数量: {len(MOCK_RECORDS)}")
    print(f"  user_thoughts: None")
    print(f"  正在调用 LLM...")

    try:
        knowledge_points_no_thoughts = await agent.process(
            records=MOCK_RECORDS,
            user_thoughts=None,
        )

        print(f"\n  ✅ 提取完成! 共 {len(knowledge_points_no_thoughts)} 个知识点:")
        for i, kp in enumerate(knowledge_points_no_thoughts, 1):
            print(f"  [{i}] {kp.get('knowledge_point', '未知')}")

    except Exception as e:
        print(f"  ❌ 提取失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 6: Token 统计
    # -------------------------------------------------------
    print("\n--- Step 6: Token 统计 ---")

    from src.agents.base_agent import BaseAgent
    stats = BaseAgent.get_stats("ideagen")
    print(f"  总调用次数:   {len(stats.calls)}")
    print(f"  总输入 tokens: {stats.total_prompt_tokens}")
    print(f"  总输出 tokens: {stats.total_completion_tokens}")
    print(f"  总费用:       ${stats.total_cost:.4f}")

    print("\n" + "=" * 60)
    print("Layer 1 测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
