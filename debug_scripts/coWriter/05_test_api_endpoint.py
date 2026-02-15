#!/usr/bin/env python
"""
Layer 5: API 路由层端到端调用
=========================================
通过 HTTP 请求模拟前端调用 Co-Writer API 端点：
  - POST /api/v1/co_writer/edit     → EditAgent.process()
  - POST /api/v1/co_writer/automark → EditAgent.auto_mark()
  - POST /api/v1/co_writer/narrate  → NarratorAgent.narrate()
  - GET  /api/v1/co_writer/history  → load_history()
  - GET  /api/v1/co_writer/tts/status → get_tts_config()

调用链路（以 /edit 为例）：
  前端 POST /api/v1/co_writer/edit
    → FastAPI router (co_writer.py)
      → get_edit_agent()  # 单例模式 + refresh_config()
        → EditAgent(language=_current_language())
        → agent.refresh_config()  # 刷新 LLM 配置
      → agent.process(text, instruction, action, source, kb_name)
        → ... (同 Layer 1)
      → print_stats()
      → 返回 EditResponse(edited_text, operation_id)

路由层关键设计：
  1. **单例模式**: _edit_agent / _narrator_agent 全局实例复用
  2. **refresh_config()**: 每次请求前刷新 LLM 配置，支持热更新
  3. **语言切换**: _current_language() 从 UI settings 获取，支持中英文切换
  4. **Pydantic 校验**: EditRequest / NarrateRequest 等模型做入参校验

前置条件：需要 FastAPI 服务运行中（默认 http://localhost:8000）
  如未启动服务，本脚本会提示跳过。
"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env", override=False)

# 服务端地址（根据你的实际配置修改）
BASE_URL = "http://localhost:8000/api/v1/co_writer"


async def check_server():
    """检查服务是否运行"""
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BASE_URL}/tts/status", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                return resp.status == 200
    except Exception:
        return False


async def test_with_http():
    """通过 HTTP 请求测试 API 端点"""
    import aiohttp

    print("\n--- 通过 HTTP 端到端测试 ---")

    async with aiohttp.ClientSession() as session:
        # Test 1: TTS 状态
        print("\n  [1] GET /tts/status")
        async with session.get(f"{BASE_URL}/tts/status") as resp:
            data = await resp.json()
            print(f"      状态码: {resp.status}")
            print(f"      TTS 可用: {data.get('available')}")
            if not data.get('available'):
                print(f"      原因: {data.get('error', 'N/A')}")

        # Test 2: 可用语音列表
        print("\n  [2] GET /tts/voices")
        async with session.get(f"{BASE_URL}/tts/voices") as resp:
            data = await resp.json()
            voices = [v['id'] for v in data.get('voices', [])]
            print(f"      可用语音: {voices}")

        # Test 3: 编辑文本
        print("\n  [3] POST /edit (rewrite)")
        edit_payload = {
            "text": "AI is cool and can do many things.",
            "instruction": "Make it more professional",
            "action": "rewrite",
        }
        async with session.post(f"{BASE_URL}/edit", json=edit_payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                print(f"      ✅ 编辑成功!")
                print(f"      operation_id: {data['operation_id']}")
                print(f"      结果: {data['edited_text'][:150]}...")
            else:
                error = await resp.text()
                print(f"      ❌ 失败 ({resp.status}): {error[:200]}")

        # Test 4: 自动标注
        print("\n  [4] POST /automark")
        automark_payload = {
            "text": "Deep learning achieved 95.7% accuracy on the MNIST benchmark dataset."
        }
        async with session.post(f"{BASE_URL}/automark", json=automark_payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                print(f"      ✅ 标注成功!")
                print(f"      结果: {data['marked_text'][:200]}")
            else:
                error = await resp.text()
                print(f"      ❌ 失败 ({resp.status}): {error[:200]}")

        # Test 5: 生成旁白脚本（skip_audio）
        print("\n  [5] POST /narrate (skip_audio=true)")
        narrate_payload = {
            "content": "Neural networks learn through backpropagation, adjusting weights to minimize error.",
            "style": "friendly",
            "skip_audio": True,
        }
        async with session.post(f"{BASE_URL}/narrate", json=narrate_payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                print(f"      ✅ 旁白生成成功!")
                print(f"      脚本长度: {data['script_length']} chars")
                print(f"      关键要点: {data['key_points']}")
                print(f"      has_audio: {data['has_audio']}")
            else:
                error = await resp.text()
                print(f"      ❌ 失败 ({resp.status}): {error[:200]}")

        # Test 6: 操作历史
        print("\n  [6] GET /history")
        async with session.get(f"{BASE_URL}/history") as resp:
            data = await resp.json()
            print(f"      历史记录总数: {data['total']}")
            if data['total'] > 0:
                last = data['history'][-1]
                print(f"      最近: id={last['id']}, action={last['action']}")


async def test_without_http():
    """不启动服务，直接测试路由层逻辑"""
    print("\n--- 直接调用路由层函数（无需服务） ---")

    from src.api.routers.co_writer import (
        EditRequest,
        NarrateRequest,
        AutoMarkRequest,
        get_edit_agent,
        get_narrator_agent,
        edit_text,
        auto_mark_text,
        get_tts_status,
        get_available_voices,
    )

    # Test 1: 单例 Agent 获取
    print("\n  [1] get_edit_agent() 单例模式")
    agent1 = get_edit_agent()
    agent2 = get_edit_agent()
    print(f"      同一实例: {agent1 is agent2}")
    print(f"      model: {agent1.get_model()}")
    print(f"      language: {agent1.language}")

    # Test 2: TTS 状态
    print("\n  [2] get_tts_status()")
    status = await get_tts_status()
    print(f"      TTS 可用: {status.get('available')}")

    # Test 3: 语音列表
    print("\n  [3] get_available_voices()")
    voices = await get_available_voices()
    print(f"      语音: {[v['id'] for v in voices['voices']]}")

    # Test 4: 编辑请求
    print("\n  [4] edit_text() 端到端")
    request = EditRequest(
        text="AI is transforming the world.",
        instruction="Make it more academic",
        action="rewrite",
    )
    try:
        result = await edit_text(request)
        print(f"      ✅ 成功! operation_id={result['operation_id']}")
        print(f"      结果: {result['edited_text'][:150]}...")
    except Exception as e:
        print(f"      ❌ 失败: {e}")

    # Test 5: 自动标注请求
    print("\n  [5] auto_mark_text() 端到端")
    request = AutoMarkRequest(text="GPT-4 achieved 86.4% on the MMLU benchmark.")
    try:
        result = await auto_mark_text(request)
        print(f"      ✅ 成功!")
        print(f"      结果: {result['marked_text'][:200]}")
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
    else:
        print(f"\n  ⚠️  服务未运行 ({BASE_URL})")
        print(f"  将直接调用路由层函数进行测试...")
        await test_without_http()

    print("\n" + "=" * 60)
    print("Layer 5 测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
