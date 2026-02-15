#!/usr/bin/env python
"""
Layer 4: 两个 Agent 协作流水线（Edit → Narrate）
=========================================
测试 Co-Writer 模块两个 Agent 的协作模式：
  1. EditAgent 先编辑/改写文本
  2. NarratorAgent 将编辑后的文本转换为旁白脚本

这是 Co-Writer 的典型使用场景：
  用户选中一段文本 → 用 EditAgent 改写/扩展/缩写
  → 将结果传给 NarratorAgent 生成旁白脚本（可选生成音频）

协作模式：**流水线式**（Pipeline），非对话式
  - EditAgent 和 NarratorAgent 之间没有直接通信
  - 通过数据传递协作：EditAgent 的输出 → NarratorAgent 的输入
  - 前端负责编排这个流水线

调用链路：
  Step 1: EditAgent.process(text, instruction, action="expand", source="rag")
    → rag_search(query, kb_name)  # 可选：从知识库获取上下文
    → 组装 prompt（含 RAG 上下文）
    → self.call_llm() → 编辑后的文本
    → save_tool_call() + save_history()

  Step 2: NarratorAgent.narrate(edited_text, style, skip_audio=True)
    → generate_script() → 旁白脚本
    → _extract_key_points() → 关键要点

两个 Agent 的对比：
  ┌─────────────────┬────────────────────┬────────────────────┐
  │                 │ EditAgent          │ NarratorAgent      │
  ├─────────────────┼────────────────────┼────────────────────┤
  │ module_name     │ co_writer          │ narrator           │
  │ agent_name      │ edit_agent         │ narrator_agent     │
  │ Prompt 来源     │ co_writer/edit     │ co_writer/narrator │
  │ 功能            │ 文本编辑           │ 脚本生成 + TTS     │
  │ LLM 调用次数    │ 1 次               │ 2 次（脚本+要点）  │
  │ 额外能力        │ RAG / Web Search   │ TTS 音频生成       │
  │ 操作历史        │ history.json       │ 无                 │
  └─────────────────┴────────────────────┴────────────────────┘
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
    print("Layer 4: 两个 Agent 协作流水线测试")
    print("=" * 60)

    # -------------------------------------------------------
    # Step 1: 初始化两个 Agent
    # -------------------------------------------------------
    print("\n--- Step 1: 初始化两个 Agent ---")

    from src.agents.co_writer.edit_agent import EditAgent
    from src.agents.co_writer.narrator_agent import NarratorAgent

    edit_agent = EditAgent(language="en")
    print(f"  EditAgent:    module={edit_agent.module_name}, model={edit_agent.get_model()}")

    try:
        narrator_agent = NarratorAgent(language="en")
    except Exception:
        # TTS 配置可能缺失，手动初始化
        narrator_agent = NarratorAgent.__new__(NarratorAgent)
        from src.agents.base_agent import BaseAgent
        BaseAgent.__init__(narrator_agent, module_name="narrator", agent_name="narrator_agent", language="en")
        from src.services.prompt import get_prompt_manager
        narrator_agent.prompts = get_prompt_manager().load_prompts(
            module_name="co_writer", agent_name="narrator_agent", language="en"
        )
        narrator_agent.tts_config = None
        narrator_agent.default_voice = "alloy"

    print(f"  NarratorAgent: module={narrator_agent.module_name}, model={narrator_agent.get_model()}")

    # -------------------------------------------------------
    # Step 2: 模拟完整协作流水线
    # -------------------------------------------------------
    print("\n--- Step 2: 协作流水线 - Edit → Narrate ---")

    original_text = (
        "Neural networks are good at recognizing patterns. "
        "They work by processing data through layers of nodes."
    )

    print(f"  📝 原始文本: {original_text}")
    print()

    # Step 2a: EditAgent 扩展文本
    print("  [Phase 1] EditAgent.process() - 扩展文本...")
    try:
        edit_result = await edit_agent.process(
            text=original_text,
            instruction="Expand with more technical details about how neural networks process data",
            action="expand",
            source=None,  # 不使用外部上下文（如需测试 RAG 可改为 source="rag", kb_name="xxx"）
        )

        edited_text = edit_result["edited_text"]
        print(f"  ✅ 编辑完成! operation_id={edit_result['operation_id']}")
        print(f"  原始长度: {len(original_text)} → 编辑后: {len(edited_text)} chars")
        print(f"  编辑结果预览: {edited_text[:200]}...")
        print()

    except Exception as e:
        print(f"  ❌ 编辑失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 2b: NarratorAgent 生成旁白脚本
    print("  [Phase 2] NarratorAgent.narrate() - 生成旁白脚本...")
    try:
        narrate_result = await narrator_agent.narrate(
            content=edited_text,  # 使用 EditAgent 的输出作为输入
            style="friendly",
            skip_audio=True,
        )

        print(f"  ✅ 旁白脚本生成完成!")
        print(f"  脚本长度:   {narrate_result['script_length']} chars")
        print(f"  关键要点:   {narrate_result['key_points']}")
        print(f"  has_audio:  {narrate_result['has_audio']}")
        print(f"  脚本预览: {narrate_result['script'][:200]}...")

    except Exception as e:
        print(f"  ❌ 旁白生成失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 3: 打印完整数据流
    # -------------------------------------------------------
    print("\n--- Step 3: 完整数据流总结 ---")
    print(f"  原始文本      → {len(original_text)} chars")
    if 'edited_text' in dir():
        print(f"  EditAgent 输出 → {len(edited_text)} chars (action=expand)")
    if 'narrate_result' in locals():
        print(f"  旁白脚本      → {narrate_result['script_length']} chars (style=friendly)")
        print(f"  关键要点      → {len(narrate_result['key_points'])} 条")

    # -------------------------------------------------------
    # Step 4: Token 使用统计
    # -------------------------------------------------------
    print("\n--- Step 4: Token 使用统计 ---")

    from src.agents.co_writer.edit_agent import get_stats as get_edit_stats
    edit_stats = get_edit_stats()
    print(f"  EditAgent (co_writer):")
    print(f"    调用次数: {edit_stats.total_calls}")
    print(f"    输入 tokens: {edit_stats.total_input_tokens}")
    print(f"    输出 tokens: {edit_stats.total_output_tokens}")

    from src.agents.base_agent import BaseAgent
    narrator_stats = BaseAgent.get_stats("narrator")
    print(f"  NarratorAgent (narrator):")
    print(f"    调用次数: {narrator_stats.total_calls}")
    print(f"    输入 tokens: {narrator_stats.total_input_tokens}")
    print(f"    输出 tokens: {narrator_stats.total_output_tokens}")

    print("\n" + "=" * 60)
    print("Layer 4 测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
