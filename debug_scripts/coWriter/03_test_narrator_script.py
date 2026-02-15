#!/usr/bin/env python
"""
Layer 3: NarratorAgent 脚本生成（不含 TTS）
=========================================
测试 NarratorAgent 的脚本生成能力：
  1. 初始化（BaseAgent + TTS 配置加载）
  2. generate_script() — 将文本转换为旁白脚本
  3. _extract_key_points() — 提取关键要点
  4. 三种风格：friendly / academic / concise

调用链路：
  NarratorAgent.__init__()
    → BaseAgent.__init__(module_name="narrator", agent_name="narrator_agent")
      → get_llm_config()
      → get_agent_params("narrator")  # narrator 独立的 temperature/max_tokens
    → get_prompt_manager().load_prompts("co_writer", "narrator_agent")
      # 注意：Prompt 文件在 co_writer 模块下，但 module_name 用 "narrator"
    → self._load_tts_config()  # 加载 TTS 配置（可能失败，不影响脚本生成）

  NarratorAgent.generate_script(content, style)
    → 判断长短内容（>5000 chars 为长内容）
    → 加载风格 prompt: style_friendly / style_academic / style_concise
    → 加载长度指令: length_instruction_long / length_instruction_short
    → 组装 system_prompt (generate_script_system_template)
    → 组装 user_prompt (generate_script_user_long / generate_script_user_short)
    → self.call_llm() → LLM Factory
    → 截断到 4000 chars（OpenAI TTS 限制 4096）
    → self._extract_key_points(content)  # 第二次 LLM 调用，提取要点

关键设计：
  - NarratorAgent 用 module_name="narrator" 以获取独立的 temperature/max_tokens 配置
  - 但 Prompt 从 co_writer 模块加载（覆盖了 BaseAgent 的默认加载）
  - 脚本长度硬限制 4000 chars（为 TTS 的 4096 限制留余量）
  - 每次 generate_script 会调用 LLM 两次：一次生成脚本，一次提取要点
"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env", override=False)


async def main():
    print("=" * 60)
    print("Layer 3: NarratorAgent 脚本生成测试")
    print("=" * 60)

    # -------------------------------------------------------
    # Step 1: 初始化 NarratorAgent
    # -------------------------------------------------------
    print("\n--- Step 1: 初始化 NarratorAgent ---")

    from src.agents.co_writer.narrator_agent import NarratorAgent

    try:
        agent = NarratorAgent(language="en")
        print(f"  ✅ 初始化成功")
    except Exception as e:
        print(f"  ⚠️  初始化时有警告（TTS 配置可能缺失，不影响脚本生成）: {e}")
        agent = NarratorAgent.__new__(NarratorAgent)
        # 手动调用 BaseAgent.__init__ 跳过 TTS
        from src.agents.base_agent import BaseAgent
        BaseAgent.__init__(agent, module_name="narrator", agent_name="narrator_agent", language="en")
        from src.services.prompt import get_prompt_manager
        agent.prompts = get_prompt_manager().load_prompts(
            module_name="co_writer", agent_name="narrator_agent", language="en"
        )
        agent.tts_config = None
        agent.default_voice = "alloy"

    print(f"  module_name:   {agent.module_name}")
    print(f"  agent_name:    {agent.agent_name}")
    print(f"  model:         {agent.get_model()}")
    print(f"  temperature:   {agent.get_temperature()}")
    print(f"  max_tokens:    {agent.get_max_tokens()}")
    print(f"  tts_config:    {'已配置' if agent.tts_config else '未配置（不影响脚本生成）'}")
    print(f"  default_voice: {agent.default_voice}")

    # -------------------------------------------------------
    # Step 2: 检查 Prompt 加载
    # -------------------------------------------------------
    print("\n--- Step 2: 检查 Narrator Prompt ---")

    print(f"  has_prompts: {agent.has_prompts()}")
    if agent.prompts:
        print(f"  prompts keys: {list(agent.prompts.keys())}")

        # 检查风格 prompts
        for style in ["friendly", "academic", "concise"]:
            p = agent.get_prompt(f"style_{style}")
            preview = p.strip().split("\n")[0][:80] if p else "None"
            print(f"  style_{style}: {preview}...")

    # -------------------------------------------------------
    # Step 3: 测试 friendly 风格脚本生成
    # -------------------------------------------------------
    print("\n--- Step 3: 测试 friendly 风格脚本生成 ---")

    test_content = """
# Introduction to Neural Networks

Neural networks are computing systems inspired by biological neural networks in the brain.
They consist of layers of interconnected nodes (neurons) that process information.

## Key Components
- **Input Layer**: Receives the raw data
- **Hidden Layers**: Process and transform data through weighted connections
- **Output Layer**: Produces the final result

## Training Process
Neural networks learn through a process called **backpropagation**:
1. Forward pass: Data flows through the network
2. Loss calculation: Compare output with expected result
3. Backward pass: Adjust weights based on the error
4. Repeat until convergence
"""

    print(f"  输入内容长度: {len(test_content)} chars")
    print(f"  风格: friendly")
    print()

    try:
        result = await agent.generate_script(content=test_content, style="friendly")

        print(f"  ✅ 脚本生成成功!")
        print(f"  脚本长度:    {result['script_length']} chars")
        print(f"  原始内容长度: {result['original_length']} chars")
        print(f"  风格:        {result['style']}")
        print(f"  关键要点:    {result['key_points']}")
        print(f"\n  脚本预览（前 300 chars）:")
        print(f"  ---")
        print(f"  {result['script'][:300]}...")
        print(f"  ---")

    except Exception as e:
        print(f"  ❌ 脚本生成失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 4: 测试 concise 风格
    # -------------------------------------------------------
    print("\n--- Step 4: 测试 concise 风格 ---")

    try:
        result = await agent.generate_script(content=test_content, style="concise")

        print(f"  ✅ concise 风格脚本生成成功!")
        print(f"  脚本长度: {result['script_length']} chars")
        print(f"  脚本预览（前 200 chars）:")
        print(f"  {result['script'][:200]}...")

    except Exception as e:
        print(f"  ❌ 失败: {e}")

    # -------------------------------------------------------
    # Step 5: 测试 narrate() 完整流程（skip_audio=True）
    # -------------------------------------------------------
    print("\n--- Step 5: 测试 narrate() 完整流程（skip_audio） ---")

    try:
        result = await agent.narrate(
            content=test_content,
            style="friendly",
            skip_audio=True,  # 跳过音频生成
        )

        print(f"  ✅ narrate() 成功!")
        print(f"  has_audio:    {result.get('has_audio')}")
        print(f"  audio_error:  {result.get('audio_error', 'N/A')}")
        print(f"  script 长度:  {result['script_length']} chars")
        print(f"  key_points:   {result['key_points']}")
        print(f"  返回字段:     {list(result.keys())}")

    except Exception as e:
        print(f"  ❌ 失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("Layer 3 测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
