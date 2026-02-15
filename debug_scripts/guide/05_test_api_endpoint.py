#!/usr/bin/env python
"""
Layer 5: API 路由层端到端调用（REST + WebSocket）
=========================================
通过 HTTP/WebSocket 请求模拟前端调用 Guide API 端点：

REST API 端点：
  - POST /api/v1/guide/create_session  → GuideManager.create_session()
  - POST /api/v1/guide/start           → GuideManager.start_learning()
  - POST /api/v1/guide/next            → GuideManager.next_knowledge()
  - POST /api/v1/guide/chat            → GuideManager.chat()
  - POST /api/v1/guide/fix_html        → GuideManager.fix_html()
  - GET  /api/v1/guide/session/{id}    → GuideManager.get_session()
  - GET  /api/v1/guide/session/{id}/html → GuideManager.get_current_html()
  - GET  /api/v1/guide/health          → 健康检查

WebSocket 端点：
  - WS /api/v1/guide/ws/{session_id}
    消息类型：start / next / chat / fix_html / get_session

调用链路（以 /create_session 为例）：
  前端 POST /api/v1/guide/create_session
    → FastAPI router (guide.py)
      → get_guide_manager()               # 每次请求创建新实例
        → get_llm_config()                 # 获取 LLM 配置
        → get_ui_language()                # 获取 UI 语言设置
        → GuideManager(api_key, base_url, language, binding)
      → notebook_manager.get_notebook()    # 获取笔记本记录
      → manager.create_session(notebook_id, notebook_name, records)
        → LocateAgent.process()            # 分析知识点
      → TaskIDManager.generate_task_id()   # 生成任务追踪 ID
      → 返回 JSON 结果

路由层关键设计：
  1. **无状态路由**: get_guide_manager() 每次请求创建新实例
     （但会话数据持久化在 JSON 文件中，所以状态不丢失）
  2. **双模式 API**: REST + WebSocket 并存
     - REST 适合简单请求（create_session, get_session）
     - WebSocket 适合实时交互（chat, next_knowledge 连续操作）
  3. **跨笔记本支持**: create_session 支持两种模式
     - notebook_id 模式: 从 notebook_manager 获取记录
     - records 模式: 直接传入记录列表（跨笔记本）
  4. **任务追踪**: TaskIDManager 为每个会话生成唯一 task_id

前置条件：需要 FastAPI 服务运行中（默认 http://localhost:8000）
  如未启动服务，本脚本会回退到直接调用路由层函数。
"""

import asyncio
import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env", override=False)

# 服务端地址（根据你的实际配置修改）
BASE_URL = "http://localhost:8000/api/v1/guide"


# -------------------------------------------------------
# 测试数据
# -------------------------------------------------------
MOCK_RECORDS = [
    {
        "type": "chat",
        "title": "什么是函数？",
        "user_query": "Python 函数是怎么定义的？",
        "output": "使用 def 关键字定义函数：def func_name(params): ...",
    },
    {
        "type": "chat",
        "title": "列表推导式",
        "user_query": "列表推导式怎么用？",
        "output": "列表推导式是创建列表的简洁方式：[expr for item in iterable if condition]",
    },
]


async def check_server():
    """检查服务是否运行"""
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{BASE_URL}/health",
                timeout=aiohttp.ClientTimeout(total=3),
            ) as resp:
                return resp.status == 200
    except Exception:
        return False


async def test_with_http():
    """通过 HTTP 请求测试 REST API 端点"""
    import aiohttp

    print("\n--- 通过 HTTP 端到端测试 ---")

    async with aiohttp.ClientSession() as session:
        # Test 1: 健康检查
        print("\n  [1] GET /health")
        async with session.get(f"{BASE_URL}/health") as resp:
            data = await resp.json()
            print(f"      状态码: {resp.status}")
            print(f"      结果: {data}")

        # Test 2: 创建会话（使用 records 模式）
        print("\n  [2] POST /create_session (records 模式)")
        create_payload = {"records": MOCK_RECORDS}
        async with session.post(f"{BASE_URL}/create_session", json=create_payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                print(f"      ✅ 会话创建成功!")
                session_id = data.get("session_id")
                print(f"      session_id:   {session_id}")
                print(f"      total_points: {data.get('total_points', 0)}")
                if data.get("knowledge_points"):
                    for i, kp in enumerate(data["knowledge_points"], 1):
                        print(f"      知识点[{i}]: {kp.get('knowledge_title', '')}")
            else:
                error = await resp.text()
                print(f"      ❌ 失败 ({resp.status}): {error[:200]}")
                return

        if not session_id:
            print("      ❌ 未获取到 session_id，终止测试")
            return

        # Test 3: 获取会话信息
        print(f"\n  [3] GET /session/{session_id}")
        async with session.get(f"{BASE_URL}/session/{session_id}") as resp:
            if resp.status == 200:
                data = await resp.json()
                print(f"      状态: {data.get('status')}")
                print(f"      当前索引: {data.get('current_index')}")
                print(f"      知识点数: {len(data.get('knowledge_points', []))}")
            else:
                error = await resp.text()
                print(f"      ❌ 失败: {error[:200]}")

        # Test 4: 开始学习
        print(f"\n  [4] POST /start")
        start_payload = {"session_id": session_id}
        async with session.post(f"{BASE_URL}/start", json=start_payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                print(f"      ✅ 开始学习!")
                print(f"      当前知识点: {data.get('current_knowledge', {}).get('knowledge_title', '')}")
                print(f"      进度: {data.get('progress', 0)}%")
                print(f"      HTML 长度: {len(data.get('html', ''))} chars")
            else:
                error = await resp.text()
                print(f"      ❌ 失败: {error[:200]}")

        # Test 5: 发送聊天消息
        print(f"\n  [5] POST /chat")
        chat_payload = {
            "session_id": session_id,
            "message": "这个知识点最关键的内容是什么？",
        }
        async with session.post(f"{BASE_URL}/chat", json=chat_payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                print(f"      ✅ 回答成功!")
                answer = data.get("answer", "")
                print(f"      回答预览: {answer[:150]}...")
            else:
                error = await resp.text()
                print(f"      ❌ 失败: {error[:200]}")

        # Test 6: 获取当前 HTML
        print(f"\n  [6] GET /session/{session_id}/html")
        async with session.get(f"{BASE_URL}/session/{session_id}/html") as resp:
            if resp.status == 200:
                data = await resp.json()
                html = data.get("html", "")
                print(f"      HTML 长度: {len(html)} chars")
                print(f"      HTML 有效: {'<html' in html.lower() or '<div' in html.lower()}")
            else:
                error = await resp.text()
                print(f"      ❌ 失败: {error[:200]}")

        # Test 7: 下一个知识点
        print(f"\n  [7] POST /next")
        next_payload = {"session_id": session_id}
        async with session.post(f"{BASE_URL}/next", json=next_payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                status = data.get("status", "")
                if status == "completed":
                    print(f"      🎉 学习完成!")
                    print(f"      总结预览: {data.get('summary', '')[:150]}...")
                else:
                    print(f"      ✅ 进入下一个知识点!")
                    print(f"      知识点: {data.get('current_knowledge', {}).get('knowledge_title', '')}")
                    print(f"      进度: {data.get('progress', 0)}%")
            else:
                error = await resp.text()
                print(f"      ❌ 失败: {error[:200]}")


async def test_websocket():
    """测试 WebSocket 端点"""
    import aiohttp

    print("\n--- WebSocket 实时交互测试 ---")

    # 先通过 REST 创建会话
    async with aiohttp.ClientSession() as session:
        create_payload = {"records": MOCK_RECORDS}
        async with session.post(f"{BASE_URL}/create_session", json=create_payload) as resp:
            if resp.status != 200:
                print("  ❌ 创建会话失败，跳过 WebSocket 测试")
                return
            data = await resp.json()
            session_id = data.get("session_id")
            if not session_id:
                print("  ❌ 未获取到 session_id，跳过 WebSocket 测试")
                return
            print(f"  会话已创建: {session_id}")

    # WebSocket 连接
    ws_url = f"ws://localhost:8000/api/v1/guide/ws/{session_id}"
    print(f"  连接: {ws_url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url) as ws:
                # 接收初始消息（task_id + session_info）
                msg = await asyncio.wait_for(ws.receive_json(), timeout=5)
                print(f"  收到: type={msg.get('type')}")

                msg = await asyncio.wait_for(ws.receive_json(), timeout=5)
                print(f"  收到: type={msg.get('type')}, status={msg.get('data', {}).get('status', '')}")

                # 发送 start 消息
                print(f"\n  发送: type=start")
                await ws.send_json({"type": "start"})
                msg = await asyncio.wait_for(ws.receive_json(), timeout=30)
                print(f"  收到: type={msg.get('type')}")
                start_data = msg.get("data", {})
                print(f"    知识点: {start_data.get('current_knowledge', {}).get('knowledge_title', '')}")
                print(f"    HTML长度: {len(start_data.get('html', ''))} chars")

                # 发送 chat 消息
                print(f"\n  发送: type=chat, message='简单解释一下？'")
                await ws.send_json({"type": "chat", "message": "简单解释一下？"})
                msg = await asyncio.wait_for(ws.receive_json(), timeout=30)
                print(f"  收到: type={msg.get('type')}")
                chat_data = msg.get("data", {})
                print(f"    回答预览: {chat_data.get('answer', '')[:100]}...")

                # 发送 next 消息
                print(f"\n  发送: type=next")
                await ws.send_json({"type": "next"})
                msg = await asyncio.wait_for(ws.receive_json(), timeout=30)
                print(f"  收到: type={msg.get('type')}")
                next_data = msg.get("data", {})
                if next_data.get("status") == "completed":
                    print(f"    🎉 学习完成!")
                else:
                    print(f"    知识点: {next_data.get('current_knowledge', {}).get('knowledge_title', '')}")
                    print(f"    进度: {next_data.get('progress', 0)}%")

                await ws.close()
                print(f"\n  WebSocket 连接已关闭")

    except asyncio.TimeoutError:
        print(f"  ⚠️ WebSocket 超时")
    except Exception as e:
        print(f"  ❌ WebSocket 错误: {e}")
        import traceback
        traceback.print_exc()


async def test_without_http():
    """不启动服务，直接调用路由层函数"""
    print("\n--- 直接调用路由层函数（无需服务） ---")

    from src.api.routers.guide import (
        CreateSessionRequest,
        ChatRequest,
        NextKnowledgeRequest,
        get_guide_manager,
        create_session,
        start_learning,
        next_knowledge,
        chat,
        get_session,
        get_current_html,
        health_check,
    )

    # Test 1: 健康检查
    print("\n  [1] health_check()")
    result = await health_check()
    print(f"      结果: {result}")

    # Test 2: get_guide_manager 工厂函数
    print("\n  [2] get_guide_manager()")
    manager = get_guide_manager()
    print(f"      language: {manager.language}")
    print(f"      output_dir: {manager.output_dir}")

    # Test 3: 创建会话（直接传 records，跳过 notebook_manager）
    print("\n  [3] create_session() - records 模式")
    request = CreateSessionRequest(records=MOCK_RECORDS)
    try:
        result = await create_session(request)
        print(f"      ✅ 成功!")
        session_id = result.get("session_id")
        print(f"      session_id: {session_id}")
        print(f"      total_points: {result.get('total_points', 0)}")
    except Exception as e:
        print(f"      ❌ 失败: {e}")
        return

    if not session_id:
        print("      ❌ 未获取 session_id，终止")
        return

    # Test 4: 开始学习
    print(f"\n  [4] start_learning()")
    try:
        result = await start_learning(NextKnowledgeRequest(session_id=session_id))
        print(f"      ✅ 成功!")
        print(f"      知识点: {result.get('current_knowledge', {}).get('knowledge_title', '')}")
        print(f"      HTML 长度: {len(result.get('html', ''))} chars")
    except Exception as e:
        print(f"      ❌ 失败: {e}")

    # Test 5: 聊天
    print(f"\n  [5] chat()")
    try:
        result = await chat(ChatRequest(session_id=session_id, message="请用一句话总结"))
        print(f"      ✅ 成功!")
        print(f"      回答: {result.get('answer', '')[:150]}...")
    except Exception as e:
        print(f"      ❌ 失败: {e}")

    # Test 6: 获取会话
    print(f"\n  [6] get_session()")
    try:
        result = await get_session(session_id)
        print(f"      状态: {result.get('status')}")
        print(f"      对话历史: {len(result.get('chat_history', []))} 条")
    except Exception as e:
        print(f"      ❌ 失败: {e}")

    # Test 7: 获取当前 HTML
    print(f"\n  [7] get_current_html()")
    try:
        result = await get_current_html(session_id)
        html = result.get("html", "")
        print(f"      HTML 长度: {len(html)} chars")
    except Exception as e:
        print(f"      ❌ 失败: {e}")


async def main():
    print("=" * 60)
    print("Layer 5: API 路由层端到端测试")
    print("=" * 60)

    server_running = await check_server()

    if server_running:
        print(f"\n  ✅ 服务运行中 ({BASE_URL})")
        await test_with_http()

        print("\n" + "-" * 40)
        await test_websocket()
    else:
        print(f"\n  ⚠️  服务未运行 ({BASE_URL})")
        print(f"  将直接调用路由层函数进行测试...")
        await test_without_http()

    print("\n" + "=" * 60)
    print("Layer 5 测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
