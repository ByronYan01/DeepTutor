#!/usr/bin/env python
"""
环节 5：模拟前端 WebSocket 消息，验证完整链路
===============================================

功能：
- 模拟前端发送 WebSocket 消息到 /api/v1/chat
- 验证 kb_name、enable_rag 是否正确传递
- 打印后端返回的所有消息（session、status、stream、sources、result）
- 可对比 enable_rag=True vs False 的结果差异

用法：
    python debug_scripts/05_test_websocket_msg.py --kb 22
    python debug_scripts/05_test_websocket_msg.py --kb 22 --no-rag   # 对比：不开 RAG
    python debug_scripts/05_test_websocket_msg.py --kb 22 --port 8001

关键源码位置：
    src/api/routers/chat.py  →  websocket_chat()
    - 第 120-128 行解析 WebSocket 消息中的 kb_name、enable_rag
    - 第 241-248 行调用 ChatAgent.process()

⚡ 这是本次 bug 的前端入口！
   日志显示实际发送的 kb_name='yl' 而非 '22'，
   说明前端 chatState.selectedKb 的值不对。
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_QUERY = "项目 Phoenix 的 GPU 资源审批应该找谁？"


async def test_websocket_chat(
    kb_name: str, query: str, enable_rag: bool, port: int, host: str
):
    try:
        import websockets
    except ImportError:
        print("❌ 需要安装 websockets: pip install websockets")
        return

    ws_url = f"ws://{host}:{port}/api/v1/chat"

    print("=" * 60)
    print("WebSocket 完整链路测试")
    print("=" * 60)
    print(f"  URL: {ws_url}")
    print(f"  KB: {kb_name}")
    print(f"  Query: {query}")
    print(f"  enable_rag: {enable_rag}")
    print()

    # 构造前端发送的消息（和 ChatContext.tsx 中 ws.send 一致）
    payload = {
        "message": query,
        "session_id": None,
        "history": [],
        "kb_name": kb_name,
        "enable_rag": enable_rag,
        "enable_web_search": False,
    }

    print("📤 发送消息:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print()

    try:
        async with websockets.connect(ws_url, open_timeout=10) as ws:
            # 发送消息
            await ws.send(json.dumps(payload))
            print("✅ 消息已发送，等待响应...\n")

            # 接收所有响应
            full_response = ""
            sources = None

            async for msg_str in ws:
                data = json.loads(msg_str)
                msg_type = data.get("type", "unknown")

                if msg_type == "session":
                    print(f"  📋 [session] session_id={data.get('session_id')}")

                elif msg_type == "status":
                    stage = data.get("stage", "")
                    message = data.get("message", "")
                    print(f"  ⏳ [status] stage={stage}, message={message}")

                elif msg_type == "stream":
                    content = data.get("content", "")
                    full_response += content
                    # 只显示前 50 个 chunk 的进度
                    if len(full_response) <= 200:
                        sys.stdout.write(f"\r  🔄 [stream] 已接收 {len(full_response)} chars...")
                        sys.stdout.flush()

                elif msg_type == "sources":
                    sources = data
                    rag_count = len(data.get("rag", []))
                    web_count = len(data.get("web", []))
                    print(f"\n  📚 [sources] rag={rag_count}, web={web_count}")

                elif msg_type == "result":
                    full_response = data.get("content", full_response)
                    print(f"\n  ✅ [result] 响应完成，共 {len(full_response)} chars")

                elif msg_type == "error":
                    print(f"\n  ❌ [error] {data.get('message', '')}")
                    break

            # 显示完整响应
            print("\n" + "=" * 60)
            print("完整响应:")
            print("=" * 60)
            print(full_response[:800])
            if len(full_response) > 800:
                print(f"\n... (共 {len(full_response)} chars)")

            # 诊断
            print("\n--- 诊断 ---")
            keywords = ["Phoenix", "A100", "基础设施", "张三", "zhangsan"]
            found = [kw for kw in keywords if kw in full_response]
            missing = [kw for kw in keywords if kw not in full_response]

            if found:
                print(f"✅ 响应中包含知识库关键词: {found}")
            if missing:
                print(f"⚠️  响应中缺失关键词: {missing}")

            if not found and enable_rag:
                print("\n❌ RAG 已开启但响应完全没有引用知识库内容！")
                print("   可能原因：")
                print(f"   1. kb_name='{kb_name}' 对应的知识库索引为空或不匹配")
                print("   2. RAGService 路由到了错误的 pipeline")
                print("   3. 检索结果为空，LLM 只用自身知识回答")
                print("   → 运行 03_test_rag_service.py 排查 provider 路由")
            elif found and enable_rag:
                print("\n🎉 端到端测试通过！RAG 检索和 LLM 回答都正常。")

            if sources:
                print(f"\n📚 Sources 详情:")
                print(json.dumps(sources, indent=2, ensure_ascii=False)[:500])

    except ConnectionRefusedError:
        print(f"❌ 无法连接到 {ws_url}")
        print(f"   请确认后端服务正在运行: python scripts/start_web.py")
    except Exception as e:
        print(f"❌ 连接错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="模拟 WebSocket 消息测试完整链路")
    parser.add_argument("--kb", type=str, default="22", help="知识库名称")
    parser.add_argument("--query", type=str, default=DEFAULT_QUERY, help="查询问题")
    parser.add_argument("--no-rag", action="store_true", help="禁用 RAG")
    parser.add_argument("--port", type=int, default=8001, help="后端端口")
    parser.add_argument("--host", type=str, default="localhost", help="后端地址")
    args = parser.parse_args()

    asyncio.run(
        test_websocket_chat(
            kb_name=args.kb,
            query=args.query,
            enable_rag=not args.no_rag,
            port=args.port,
            host=args.host,
        )
    )
