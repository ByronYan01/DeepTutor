#!/usr/bin/env python
"""
Layer 2: EditAgent AutoMark 自动标注
=========================================
测试 EditAgent 的 auto_mark 功能：
  - 使用专用的 auto_mark_system / auto_mark_user_template Prompt
  - 给文本添加 HTML 注释标签（circle/highlight/box/underline/bracket）
  - 不修改原文内容，只插入标注标签

调用链路：
  EditAgent.auto_mark(text)
    → self.get_prompt("auto_mark_system")        # 专用 system prompt（含标注规则和示例）
    → self.get_prompt("auto_mark_user_template")  # 用户模板
    → self.call_llm(user_prompt, system_prompt, stage="auto_mark")
      → LLM Factory → provider
    → save_history()  # action="automark"

Prompt 特点（auto_mark_system）：
  - 定义 5 种标注标签：circle / highlight / box / underline / bracket
  - 每种标签有明确的使用场景和频率限制
  - 核心规则：克制标注、不修改原文、标签放在 Markdown 符号内部
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
    print("Layer 2: EditAgent AutoMark 自动标注测试")
    print("=" * 60)

    from src.agents.co_writer.edit_agent import EditAgent

    agent = EditAgent(language="en")

    # -------------------------------------------------------
    # Step 1: 检查 AutoMark 专用 Prompt
    # -------------------------------------------------------
    print("\n--- Step 1: 检查 AutoMark 专用 Prompt ---")

    auto_mark_system = agent.get_prompt("auto_mark_system")
    print(f"  auto_mark_system prompt 长度: {len(auto_mark_system)} chars")
    # 显示前几行
    lines = auto_mark_system.strip().split("\n")[:5]
    for line in lines:
        print(f"    {line}")
    print(f"    ... (共 {len(auto_mark_system.strip().split(chr(10)))} 行)")

    auto_mark_user = agent.get_prompt("auto_mark_user_template")
    print(f"  auto_mark_user_template: {auto_mark_user.strip()}")

    # -------------------------------------------------------
    # Step 2: 测试英文学术文本标注
    # -------------------------------------------------------
    print("\n--- Step 2: 测试英文学术文本标注 ---")

    academic_text = (
        "Deep learning is a subfield of machine learning that uses neural networks "
        "with multiple layers to learn hierarchical representations of data. "
        "The key innovation of deep learning is the use of backpropagation algorithm "
        "to train networks with many layers, achieving state-of-the-art results "
        "on tasks like image recognition (97.3% accuracy on ImageNet) and "
        "natural language processing."
    )

    print(f"  原始文本: {academic_text[:100]}...")
    print()

    try:
        result = await agent.auto_mark(text=academic_text)

        print(f"  ✅ 标注成功!")
        print(f"  operation_id: {result['operation_id']}")
        print(f"  标注结果:")
        print(f"  ---")
        print(f"  {result['marked_text']}")
        print(f"  ---")

        # 分析标注标签使用情况
        marked = result['marked_text']
        tag_counts = {
            "circle": marked.count('data-rough-notation="circle"'),
            "highlight": marked.count('data-rough-notation="highlight"'),
            "box": marked.count('data-rough-notation="box"'),
            "underline": marked.count('data-rough-notation="underline"'),
            "bracket": marked.count('data-rough-notation="bracket"'),
        }
        print(f"\n  标注统计:")
        for tag, count in tag_counts.items():
            print(f"    {tag}: {count} 处")

    except Exception as e:
        print(f"  ❌ 标注失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 3: 测试无需标注的文本
    # -------------------------------------------------------
    print("\n--- Step 3: 测试无需标注的文本 ---")

    simple_text = "The weather is nice today, perfect for going out for a walk."
    print(f"  原始文本: {simple_text}")

    try:
        result = await agent.auto_mark(text=simple_text)
        print(f"  标注结果: {result['marked_text']}")

        has_tags = "data-rough-notation" in result['marked_text']
        print(f"  是否添加了标注: {'是' if has_tags else '否（符合预期 - 日常文本不需要标注）'}")
    except Exception as e:
        print(f"  ❌ 失败: {e}")

    print("\n" + "=" * 60)
    print("Layer 2 测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
