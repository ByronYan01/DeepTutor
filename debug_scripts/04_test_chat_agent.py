#!/usr/bin/env python
"""
环节 4：测试 ChatAgent 上下文构建和 Prompt 组装
================================================

功能：
- 测试 ChatAgent.retrieve_context() 是否能拿到 RAG 上下文
- 测试 build_messages() 构建的完整 messages 数组
- 打印最终发给 LLM 的完整 prompt（不实际调用 LLM）

用法：
    python debug_scripts/04_test_chat_agent.py --kb 22
    python debug_scripts/04_test_chat_agent.py --kb 22 --query "张三的邮箱是什么"

关键源码位置：
    src/agents/chat/chat_agent.py  →  ChatAgent.retrieve_context()
    src/agents/chat/chat_agent.py  →  ChatAgent.build_messages()
    src/agents/chat/prompts/zh/chat_agent.yaml  →  system prompt 和 context_template
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_QUERY = "项目 Phoenix 的 GPU 资源审批应该找谁？"


async def test_chat_agent(kb_name: str, query: str, enable_rag: bool):
    from src.agents.chat.chat_agent import ChatAgent

    print("=" * 60)
    print("ChatAgent 上下文构建测试")
    print("=" * 60)
    print(f"  KB: {kb_name}")
    print(f"  Query: {query}")
    print(f"  enable_rag: {enable_rag}")
    print()

    # 初始化 ChatAgent
    agent = ChatAgent(language="zh")
    print(f"  Model: {agent.model}")
    print(f"  Base URL: {agent.base_url}")

    # 1. 测试 retrieve_context
    print("\n--- 步骤 1: retrieve_context() ---")
    context, sources = await agent.retrieve_context(
        message=query,
        kb_name=kb_name,
        enable_rag=enable_rag,
        enable_web_search=False,
    )

    print(f"  Context 长度: {len(context)} chars")
    print(f"  RAG sources: {len(sources.get('rag', []))} 条")
    print(f"  Web sources: {len(sources.get('web', []))} 条")

    if context:
        print(f"\n📝 检索到的 Context:")
        print("-" * 40)
        print(context[:600])
        if len(context) > 600:
            print(f"... (共 {len(context)} chars)")
        print("-" * 40)
    else:
        print("\n⚠️  Context 为空！RAG 检索未返回内容。")
        if not enable_rag:
            print("   （enable_rag=False，未启用 RAG）")

    # 2. 测试 build_messages
    print("\n--- 步骤 2: build_messages() ---")
    history = []  # 空历史
    messages = agent.build_messages(
        message=query,
        history=history,
        context=context,
    )

    print(f"  Messages 数组长度: {len(messages)} 条")
    print()

    for i, msg in enumerate(messages):
        role = msg["role"]
        content = msg["content"]
        print(f"  [{i}] role={role}, 长度={len(content)} chars")
        print(f"      内容预览: {content[:120]}{'...' if len(content) > 120 else ''}")
        print()

    # 3. 打印完整 prompt（可复制到其他 LLM 测试）
    print("\n--- 步骤 3: 完整 Messages JSON ---")
    print("（可复制到 API 测试工具中直接调用 LLM）")
    print("-" * 40)
    # 打印简化版本
    for msg in messages:
        print(f"\n[{msg['role'].upper()}]")
        print(msg["content"])
    print("-" * 40)

    # 4. 关键检查
    print("\n--- 诊断 ---")
    has_context_msg = any("context" in m.get("content", "").lower() or "参考" in m.get("content", "") for m in messages)
    has_kb_content = any("Phoenix" in m.get("content", "") or "张三" in m.get("content", "") for m in messages if m["role"] == "system")

    if enable_rag and has_kb_content:
        print("✅ RAG 上下文已正确注入到 system prompt 中")
    elif enable_rag and not has_kb_content:
        print("❌ RAG 已启用但上下文中没有知识库内容！检索可能失败。")
    elif not enable_rag:
        print("⚠️  RAG 未启用，LLM 将纯靠自身知识回答")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="测试 ChatAgent 上下文构建")
    parser.add_argument("--kb", type=str, default="22", help="知识库名称")
    parser.add_argument("--query", type=str, default=DEFAULT_QUERY, help="查询问题")
    parser.add_argument("--no-rag", action="store_true", help="禁用 RAG（对比测试）")
    args = parser.parse_args()

    asyncio.run(test_chat_agent(args.kb, args.query, enable_rag=not args.no_rag))
