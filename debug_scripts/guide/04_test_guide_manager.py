#!/usr/bin/env python
"""
Layer 4: GuideManager 完整会话生命周期（4个 Agent 流水线协作）
=========================================
测试 GuideManager 的完整流程，这是 Guide 模块的核心调度层：
  1. create_session  → LocateAgent 分析知识点 + 创建会话
  2. start_learning  → InteractiveAgent 生成第一个知识点的 HTML
  3. chat            → ChatAgent 回答用户问题
  4. next_knowledge  → InteractiveAgent 生成下一个知识点 HTML
  5. next_knowledge  → 到最后一个时 SummaryAgent 生成总结

4 个 Agent 的流水线协作方式：
  ┌──────────────────────────────────────────────────────────────┐
  │                    GuideManager                              │
  │                                                              │
  │  create_session()                                            │
  │    └→ [LocateAgent]  笔记本记录 → 知识点列表                │
  │                                                              │
  │  start_learning()                                            │
  │    └→ [InteractiveAgent]  知识点[0] → HTML 页面              │
  │                                                              │
  │  chat() ─── 可多次调用 ───                                   │
  │    └→ [ChatAgent]  知识点 + 历史 + 问题 → 回答              │
  │                                                              │
  │  next_knowledge() ─── 循环直到完成 ───                       │
  │    ├→ [InteractiveAgent]  知识点[i] → HTML 页面              │
  │    └→ (最后一个) [SummaryAgent]  全部知识点 + 历史 → 总结   │
  └──────────────────────────────────────────────────────────────┘

  协作模式：**有状态的流水线**（Stateful Pipeline）
    - 通过 GuidedSession 数据类维护状态（知识点列表、当前索引、对话历史）
    - 会话持久化到 JSON 文件（data/user/guide/session_xxx.json）
    - 每个 Agent 之间通过 GuideManager 传递数据，不直接通信

数据结构：
  GuidedSession:
    session_id:       str          # 会话 ID（uuid[:8]）
    notebook_id:      str          # 笔记本 ID
    notebook_name:    str          # 笔记本名称
    knowledge_points: list[dict]   # 知识点列表（LocateAgent 输出）
    current_index:    int          # 当前学习到的知识点索引
    chat_history:     list[dict]   # 完整对话历史（含 knowledge_index 标记）
    status:           str          # initialized → learning → completed
    current_html:     str          # 当前 HTML 页面
    summary:          str          # 学习总结（完成后填充）
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
# 测试数据：模拟笔记本记录
# -------------------------------------------------------
MOCK_NOTEBOOK_ID = "test-guide-session"
MOCK_NOTEBOOK_NAME = "Python 基础学习笔记"
MOCK_RECORDS = [
    {
        "type": "chat",
        "title": "变量与数据类型",
        "user_query": "Python 中有哪些基本数据类型？",
        "output": "Python 的基本数据类型包括：int（整数）、float（浮点数）、str（字符串）、"
                  "bool（布尔值）、list（列表）、tuple（元组）、dict（字典）、set（集合）。",
    },
    {
        "type": "chat",
        "title": "条件语句",
        "user_query": "if-elif-else 怎么用？",
        "output": "Python 使用 if-elif-else 结构进行条件判断：\n"
                  "if condition1:\n    do_something()\n"
                  "elif condition2:\n    do_other()\n"
                  "else:\n    do_default()",
    },
    {
        "type": "chat",
        "title": "循环结构",
        "user_query": "for 循环和 while 循环有什么区别？",
        "output": "for 循环用于遍历可迭代对象（已知迭代次数），while 循环用于条件循环（未知次数）。"
                  "for 更常用于列表遍历，while 适合需要条件控制的场景。",
    },
]


async def main():
    print("=" * 60)
    print("Layer 4: GuideManager 完整会话生命周期测试")
    print("=" * 60)

    # -------------------------------------------------------
    # Step 1: 初始化 GuideManager
    # -------------------------------------------------------
    print("\n--- Step 1: 初始化 GuideManager ---")

    from src.agents.guide.guide_manager import GuideManager
    from src.services.llm import get_llm_config

    llm_config = get_llm_config()
    manager = GuideManager(
        api_key=llm_config.api_key,
        base_url=llm_config.base_url,
        language="zh",
        api_version=getattr(llm_config, "api_version", None),
        binding=llm_config.binding,
    )

    print(f"  language:   {manager.language}")
    print(f"  output_dir: {manager.output_dir}")
    print(f"  4 个 Agent 初始化状态:")
    print(f"    locate_agent:      {manager.locate_agent.agent_name} (model={manager.locate_agent.get_model()})")
    print(f"    interactive_agent: {manager.interactive_agent.agent_name} (model={manager.interactive_agent.get_model()})")
    print(f"    chat_agent:        {manager.chat_agent.agent_name} (model={manager.chat_agent.get_model()})")
    print(f"    summary_agent:     {manager.summary_agent.agent_name} (model={manager.summary_agent.get_model()})")

    # -------------------------------------------------------
    # Step 2: create_session（调用 LocateAgent）
    # -------------------------------------------------------
    print("\n--- Step 2: create_session → LocateAgent 分析知识点 ---")
    print(f"  notebook_id:   {MOCK_NOTEBOOK_ID}")
    print(f"  notebook_name: {MOCK_NOTEBOOK_NAME}")
    print(f"  records 数量:  {len(MOCK_RECORDS)}")
    print(f"  正在调用 LocateAgent 分析知识点...")

    try:
        create_result = await manager.create_session(
            notebook_id=MOCK_NOTEBOOK_ID,
            notebook_name=MOCK_NOTEBOOK_NAME,
            records=MOCK_RECORDS,
        )

        print(f"\n  ✅ 会话创建完成!")
        print(f"  success:      {create_result['success']}")
        session_id = create_result.get("session_id")
        print(f"  session_id:   {session_id}")
        print(f"  total_points: {create_result.get('total_points', 0)}")
        print(f"  message:      {create_result.get('message', '')}")

        if create_result["success"]:
            knowledge_points = create_result.get("knowledge_points", [])
            for i, kp in enumerate(knowledge_points, 1):
                print(f"\n  知识点 [{i}]: {kp['knowledge_title']}")
                print(f"    摘要: {kp['knowledge_summary'][:80]}...")
        else:
            print(f"  ❌ 创建失败: {create_result.get('error')}")
            return

    except Exception as e:
        print(f"  ❌ 创建失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # -------------------------------------------------------
    # Step 3: 查看会话持久化文件
    # -------------------------------------------------------
    print("\n--- Step 3: 会话持久化检查 ---")

    session_file = manager._get_session_file(session_id)
    print(f"  会话文件路径: {session_file}")
    print(f"  文件存在:     {session_file.exists()}")

    if session_file.exists():
        import json
        with open(session_file, encoding="utf-8") as f:
            session_data = json.load(f)
        print(f"  会话状态:     {session_data['status']}")
        print(f"  知识点数量:   {len(session_data['knowledge_points'])}")
        print(f"  当前索引:     {session_data['current_index']}")
        print(f"  对话历史数:   {len(session_data['chat_history'])}")

    # -------------------------------------------------------
    # Step 4: start_learning（调用 InteractiveAgent）
    # -------------------------------------------------------
    print("\n--- Step 4: start_learning → InteractiveAgent 生成 HTML ---")
    print(f"  正在为第一个知识点生成交互式 HTML...")

    try:
        start_result = await manager.start_learning(session_id)

        print(f"\n  ✅ 开始学习!")
        print(f"  success:       {start_result['success']}")
        print(f"  current_index: {start_result.get('current_index', 0)}")
        print(f"  progress:      {start_result.get('progress', 0)}%")
        print(f"  total_points:  {start_result.get('total_points', 0)}")

        current_kp = start_result.get("current_knowledge", {})
        print(f"  当前知识点:    {current_kp.get('knowledge_title', '')}")

        html = start_result.get("html", "")
        print(f"  HTML 长度:     {len(html)} chars")
        print(f"  HTML 有效:     {'<html' in html.lower() or '<div' in html.lower()}")

    except Exception as e:
        print(f"  ❌ 开始学习失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # -------------------------------------------------------
    # Step 5: chat（调用 ChatAgent）
    # -------------------------------------------------------
    print("\n--- Step 5: chat → ChatAgent 回答问题 ---")

    test_question = "这个知识点最核心的概念是什么？能用一句话总结吗？"
    print(f"  用户提问: {test_question}")
    print(f"  正在调用 ChatAgent...")

    try:
        chat_result = await manager.chat(session_id, test_question)

        print(f"\n  ✅ 回答完成!")
        print(f"  success: {chat_result['success']}")
        answer = chat_result.get("answer", "")
        print(f"  回答长度: {len(answer)} chars")
        print(f"  回答预览:")
        for line in answer[:200].split("\n"):
            print(f"    {line}")

    except Exception as e:
        print(f"  ❌ 回答失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 6: 检查会话状态变化
    # -------------------------------------------------------
    print("\n--- Step 6: 会话状态检查 ---")

    session = manager.get_session(session_id)
    if session:
        print(f"  status:        {session['status']}")
        print(f"  current_index: {session['current_index']}")
        print(f"  chat_history:  {len(session['chat_history'])} 条")

        # 打印对话历史摘要
        print(f"\n  对话历史摘要:")
        for msg in session["chat_history"]:
            role = msg.get("role", "?")
            content = msg.get("content", "")[:60]
            ki = msg.get("knowledge_index", "N/A")
            print(f"    [{role}] (知识点{ki}): {content}...")

    # -------------------------------------------------------
    # Step 7: next_knowledge → 如果有多个知识点，继续下一个
    # -------------------------------------------------------
    print("\n--- Step 7: next_knowledge ---")
    print(f"  调用 next_knowledge 进入下一个知识点...")

    try:
        next_result = await manager.next_knowledge(session_id)

        print(f"\n  success: {next_result['success']}")
        status = next_result.get("status", "")

        if status == "completed":
            print(f"  🎉 所有知识点学习完成!")
            print(f"  progress: 100%")
            summary = next_result.get("summary", "")
            print(f"  总结长度: {len(summary)} chars")
            print(f"  总结预览:")
            for line in summary[:300].split("\n"):
                print(f"    {line}")
        else:
            current_kp = next_result.get("current_knowledge", {})
            print(f"  current_index: {next_result.get('current_index', 0)}")
            print(f"  当前知识点:    {current_kp.get('knowledge_title', '')}")
            print(f"  progress:      {next_result.get('progress', 0)}%")
            print(f"  remaining:     {next_result.get('remaining_points', 0)}")
            print(f"  HTML 长度:     {len(next_result.get('html', ''))} chars")

    except Exception as e:
        print(f"  ❌ next_knowledge 失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 8: Token 统计
    # -------------------------------------------------------
    print("\n--- Step 8: Token 统计 ---")

    from src.agents.base_agent import BaseAgent
    stats = BaseAgent.get_stats("guide")
    print(f"  Guide 模块总计:")
    print(f"    调用次数:   {len(stats.calls)}")
    print(f"    输入 tokens: {stats.total_prompt_tokens}")
    print(f"    输出 tokens: {stats.total_completion_tokens}")
    print(f"    总费用:       ${stats.total_cost:.4f}")
    print(f"  （本次测试涉及: LocateAgent + InteractiveAgent×2 + ChatAgent + 可能的 SummaryAgent）")

    # -------------------------------------------------------
    # Step 9: 清理测试文件
    # -------------------------------------------------------
    print("\n--- Step 9: 清理 ---")
    if session_file.exists():
        print(f"  会话文件保留在: {session_file}")
        print(f"  （可手动删除或查看 JSON 内容）")

    print("\n" + "=" * 60)
    print("Layer 4 测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
