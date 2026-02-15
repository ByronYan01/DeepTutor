#!/usr/bin/env python
"""
Layer 1: EditAgent 基础编辑
=========================================
测试 EditAgent 的核心流程：
  1. 初始化（BaseAgent 配置 + Prompt 加载）
  2. 三种编辑操作：rewrite / shorten / expand
  3. 不使用外部上下文（source=None），纯 LLM 编辑

调用链路：
  EditAgent.__init__()
    → BaseAgent.__init__(module_name="co_writer", agent_name="edit_agent")
      → get_llm_config()          # 从 .env / unified config 获取 LLM 配置
      → get_agent_params("co_writer")  # 从 agents.yaml 获取 temperature/max_tokens
      → get_prompt_manager().load_prompts()  # 加载 prompts/en/edit_agent.yaml
  EditAgent.process(text, instruction, action)
    → self.get_prompt("system")       # 获取 system prompt
    → self.get_prompt("action_template")  # 获取 action 模板
    → self.get_prompt("user_template")    # 获取 user 模板
    → self.call_llm(user_prompt, system_prompt)  # 调用 LLM
      → llm_complete() (LLM Factory)
        → cloud_provider.complete() 或 local_provider.complete()
    → save_history()  # 保存操作历史到 data/user/co-writer/history.json
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env", override=False)


async def main():
    print("=" * 60)
    print("Layer 1: EditAgent 基础编辑测试")
    print("=" * 60)

    # -------------------------------------------------------
    # Step 1: 初始化 EditAgent，观察 BaseAgent 配置加载
    # -------------------------------------------------------
    print("\n--- Step 1: 初始化 EditAgent ---")

    from src.agents.co_writer.edit_agent import EditAgent

    agent = EditAgent(language="zh")

    print(f"  module_name:  {agent.module_name}")
    print(f"  agent_name:   {agent.agent_name}")
    print(f"  language:     {agent.language}")
    print(f"  model:        {agent.get_model()}")
    print(f"  temperature:  {agent.get_temperature()}")
    print(f"  max_tokens:   {agent.get_max_tokens()}")
    print(f"  base_url:     {agent.base_url[:50]}..." if agent.base_url else "  base_url: None")
    print(f"  enabled:      {agent.is_enabled()}")

    # -------------------------------------------------------
    # Step 2: 检查 Prompt 加载
    # -------------------------------------------------------
    print("\n--- Step 2: 检查 Prompt 加载 ---")

    print(f"  has_prompts:  {agent.has_prompts()}")
    print(f"  prompts keys: {list(agent.prompts.keys()) if agent.prompts else 'None'}")

    system_prompt = agent.get_prompt("system")
    print(f"  system prompt: {system_prompt[:80]}..." if system_prompt else "  system prompt: None")

    action_template = agent.get_prompt("action_template")
    print(f"  action_template: {action_template[:80]}..." if action_template else "  action_template: None")

    user_template = agent.get_prompt("user_template")
    print(f"  user_template: {user_template[:80]}..." if user_template else "  user_template: None")

    # -------------------------------------------------------
    # Step 3: 测试 rewrite 操作（核心流程）
    # -------------------------------------------------------
    print("\n--- Step 3: 测试 rewrite 操作 ---")

    test_text = "Machine learning is a type of AI that lets computers learn from data without being explicitly programmed."
    test_instruction = "Make it more formal and academic"

    print(f"  原始文本:  {test_text}")
    print(f"  编辑指令:  {test_instruction}")
    print(f"  操作类型:  rewrite")
    print(f"  外部上下文: None（纯 LLM 编辑）")
    print()

    try:
        result = await agent.process(
            text=test_text,
            instruction=test_instruction,
            action="rewrite",
            source=None,  # 不使用外部上下文
        )

        print(f"  ✅ 编辑成功!")
        print(f"  operation_id: {result['operation_id']}")
        print(f"  编辑结果:")
        print(f"    {result['edited_text'][:200]}")
    except Exception as e:
        print(f"  ❌ 编辑失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 4: 测试 shorten 操作
    # -------------------------------------------------------
    print("\n--- Step 4: 测试 shorten 操作 ---")

    long_text = (
        "Machine learning is a fundamental branch of artificial intelligence that focuses on "
        "building systems that can learn from and make decisions based on data. It encompasses "
        "a wide range of techniques, including supervised learning, unsupervised learning, "
        "and reinforcement learning, each with its own set of algorithms and applications."
    )

    try:
        result = await agent.process(
            text=long_text,
            instruction="Compress to one sentence",
            action="shorten",
            source=None,
        )

        print(f"  ✅ 缩写成功!")
        print(f"  原始长度: {len(long_text)} chars")
        print(f"  结果长度: {len(result['edited_text'])} chars")
        print(f"  缩写结果: {result['edited_text'][:200]}")
    except Exception as e:
        print(f"  ❌ 缩写失败: {e}")

    # -------------------------------------------------------
    # Step 5: 检查操作历史
    # -------------------------------------------------------
    print("\n--- Step 5: 检查操作历史 ---")

    from src.agents.co_writer.edit_agent import load_history

    history = load_history()
    print(f"  历史记录总数: {len(history)}")
    if history:
        last = history[-1]
        print(f"  最近一条:")
        print(f"    id:        {last['id']}")
        print(f"    action:    {last['action']}")
        print(f"    model:     {last['model']}")
        print(f"    source:    {last['source']}")
        print(f"    timestamp: {last['timestamp']}")

    # -------------------------------------------------------
    # Step 6: 查看 Token 统计
    # -------------------------------------------------------
    print("\n--- Step 6: Token 统计 ---")

    from src.agents.co_writer.edit_agent import get_stats
    stats = get_stats()
    print(f"  总调用次数:   {stats.total_calls}")
    print(f"  总输入 tokens: {stats.total_input_tokens}")
    print(f"  总输出 tokens: {stats.total_output_tokens}")

    print("\n" + "=" * 60)
    print("Layer 1 测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
