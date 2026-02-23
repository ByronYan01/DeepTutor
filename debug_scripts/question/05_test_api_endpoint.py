#!/usr/bin/env python
"""
Layer 5: WebSocket API 端到端调用
=========================================
通过 WebSocket 模拟前端调用 Question 生成 API 端点：

WebSocket 端点：
  - WS /question/generate  → 自定义模式批量题目生成
  - WS /question/mimic     → mimic 模式仿真试卷题目生成

调用链路（以 /question/generate 为例）：
  前端 WebSocket → /question/generate
    → websocket.accept()
    → websocket.receive_json()                # 接收配置消息
    → TaskIDManager.generate_task_id()        # 生成任务 ID
    → get_llm_config()                        # 获取 LLM 配置
    → AgentCoordinator(api_key, base_url, kb_name, language, output_dir)
    → coordinator.set_ws_callback(ws_callback)  # 设置 WebSocket 回调
    → LogInterceptor(target_logger, log_queue)  # 拦截日志输出
    → coordinator.generate_questions_custom(requirement, count)
      → Stage 1: Researching → ws: progress(researching)
      → Stage 2: Planning → ws: progress(planning), plan_ready
      → Stage 3: Generating → ws: question_update, result
    → ws: token_stats, batch_summary, complete

WebSocket 消息协议（前端 → 后端）：
  {
    "requirement": {                    # 题目生成需求
      "knowledge_point": "xxx",
      "difficulty": "medium",
      "question_type": "choice"
    },
    "kb_name": "知识库名",              # 知识库名称
    "count": 2                          # 生成题目数量
  }

WebSocket 消息协议（后端 → 前端）：
  {type: "task_id", task_id: "xxx"}          → 任务 ID
  {type: "status", content: "started"}       → 状态更新
  {type: "progress", stage: "researching"}   → 阶段进度
  {type: "knowledge_saved", queries: [...]}  → 知识检索完成
  {type: "plan_ready", plan: {...}}          → Plan 生成完成
  {type: "question_update", question_id, status}  → 单题状态
  {type: "result", question_id, question, validation}  → 最终结果
  {type: "token_stats", stats: {...}}        → Token 统计
  {type: "batch_summary", ...}               → 批量摘要
  {type: "complete"}                         → 全部完成
  {type: "log", content: "xxx"}              → 日志消息

前置条件：需要 FastAPI 服务运行中（默认 http://localhost:8000）
  启动方式：uv run python src/api/main.py
  如未启动服务，本脚本会回退到直接调用 Coordinator。
"""

import asyncio
import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env", override=False)


# -------------------------------------------------------
# 配置
# -------------------------------------------------------
BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/question/generate"

KB_NAME = "js权威指南"
MOCK_REQUIREMENT = {
    "knowledge_point": "JavaScript Promise",
    "difficulty": "medium",
    "question_type": "choice",
}
QUESTION_COUNT = 1   # 端到端测试生成 1 题即可


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


async def test_with_websocket():
    """通过 WebSocket 端到端测试"""
    import aiohttp

    print("\n--- 通过 WebSocket 端到端测试 ---")
    print(f"  连接: {WS_URL}")
    print(f"  kb_name: {KB_NAME}")
    print(f"  requirement: {MOCK_REQUIREMENT}")
    print(f"  count: {QUESTION_COUNT}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(WS_URL) as ws:
                # 发送配置消息
                config = {
                    "requirement": MOCK_REQUIREMENT,
                    "kb_name": KB_NAME,
                    "count": QUESTION_COUNT,
                }
                print(f"\n  → 发送配置: {json.dumps(config, ensure_ascii=False)}")
                await ws.send_json(config)

                # 接收并打印所有消息
                print(f"\n  --- 接收流式消息 ---")
                msg_count = 0
                results = []

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        msg_type = data.get("type", "unknown")
                        msg_count += 1

                        if msg_type == "task_id":
                            print(f"  [{msg_count}] 📋 task_id: {data.get('task_id')}")

                        elif msg_type == "status":
                            print(f"  [{msg_count}] 📊 status: {data.get('content')}")

                        elif msg_type == "progress":
                            stage = data.get("stage", "")
                            progress = data.get("progress", {})
                            current = progress.get("current", "")
                            total = progress.get("total", data.get("total", ""))
                            if current:
                                print(f"  [{msg_count}] 🔄 progress: {stage} ({current}/{total})")
                            else:
                                print(f"  [{msg_count}] 🔄 progress: {stage} - {progress.get('status', '')}")

                        elif msg_type == "knowledge_saved":
                            queries = data.get("queries", [])
                            print(f"  [{msg_count}] 📚 knowledge_saved: {queries}")

                        elif msg_type == "plan_ready":
                            focuses = data.get("focuses", [])
                            print(f"  [{msg_count}] 📝 plan_ready: {len(focuses)} 个 focus")
                            for f in focuses:
                                print(f"        {f.get('id')}: {f.get('focus', '')[:60]}")

                        elif msg_type == "question_update":
                            qid = data.get("question_id", "")
                            status = data.get("status", "")
                            print(f"  [{msg_count}] 🔔 question_update: {qid} → {status}")

                        elif msg_type == "result":
                            qid = data.get("question_id", "")
                            q = data.get("question", {})
                            v = data.get("validation", {})
                            print(f"  [{msg_count}] ✅ result: {qid}")
                            print(f"        题目: {q.get('question', '')[:80]}...")
                            print(f"        答案: {q.get('correct_answer', 'N/A')}")
                            print(f"        相关性: {v.get('relevance', 'N/A')}")
                            results.append(data)

                        elif msg_type == "token_stats":
                            stats = data.get("stats", {})
                            print(f"  [{msg_count}] 💰 token_stats:")
                            print(f"        调用: {stats.get('calls', 0)}, tokens: {stats.get('tokens', 0)}, 费用: ${stats.get('cost', 0):.4f}")

                        elif msg_type == "batch_summary":
                            print(f"  [{msg_count}] 📊 batch_summary:")
                            print(f"        requested: {data.get('requested')}, completed: {data.get('completed')}, failed: {data.get('failed')}")

                        elif msg_type == "complete":
                            print(f"  [{msg_count}] 🎉 complete!")
                            break

                        elif msg_type == "error":
                            print(f"  [{msg_count}] ❌ error: {data.get('content')}")
                            break

                        elif msg_type == "log":
                            # 日志消息，只打印关键的
                            content = data.get("content", "")
                            if any(kw in content.lower() for kw in ["error", "fail", "success", "完成", "stage"]):
                                print(f"  [{msg_count}] 📝 log: {content[:100]}")

                        else:
                            print(f"  [{msg_count}] ❓ {msg_type}: {str(data)[:100]}")

                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        print(f"  ❌ WebSocket 错误")
                        break

                print(f"\n  总消息数: {msg_count}")
                print(f"  生成题目数: {len(results)}")

    except asyncio.TimeoutError:
        print(f"  ⚠️ WebSocket 超时")
    except Exception as e:
        print(f"  ❌ WebSocket 错误: {e}")
        import traceback
        traceback.print_exc()


async def test_without_server():
    """不启动服务，直接调用 Coordinator（回退方案）"""
    print("\n--- 直接调用 Coordinator（无需服务）---")
    print(f"  等效于 Layer 4 的测试，但模拟 WebSocket 回调")

    from src.agents.question import AgentCoordinator
    from src.services.llm import get_llm_config

    llm_config = get_llm_config()

    # 用列表收集回调消息，模拟 WebSocket 推送
    ws_messages = []

    async def mock_ws_callback(data: dict):
        """模拟 WebSocket 回调，收集消息"""
        ws_messages.append(data)
        msg_type = data.get("type", "unknown")
        if msg_type == "progress":
            stage = data.get("stage", "")
            print(f"  → ws: {msg_type} - {stage}")
        elif msg_type == "result":
            qid = data.get("question_id", "")
            print(f"  → ws: {msg_type} - {qid}")
        elif msg_type in ("plan_ready", "knowledge_saved"):
            print(f"  → ws: {msg_type}")
        elif msg_type == "question_update":
            print(f"  → ws: {msg_type} - {data.get('question_id')} → {data.get('status')}")

    coordinator = AgentCoordinator(
        api_key=llm_config.api_key,
        base_url=llm_config.base_url,
        api_version=getattr(llm_config, "api_version", None),
        kb_name=KB_NAME,
        language="zh",
        output_dir=str(project_root / "data" / "debug_output" / "question_ws_test"),
    )

    # 设置 ws 回调
    coordinator.set_ws_callback(mock_ws_callback)

    print(f"\n  正在执行 generate_questions_custom（带回调）...")

    try:
        result = await coordinator.generate_questions_custom(
            requirement=MOCK_REQUIREMENT,
            num_questions=QUESTION_COUNT,
        )

        print(f"\n  ✅ 生成完成!")
        print(f"  success:   {result['success']}")
        print(f"  completed: {result['completed']}")
        print(f"  failed:    {result['failed']}")

        # 显示生成的题目
        for r in result.get("results", []):
            q = r.get("question", {})
            print(f"\n  题目: {q.get('question', '')[:100]}")
            print(f"  答案: {q.get('correct_answer', 'N/A')}")
            print(f"  相关性: {r.get('analysis', {}).get('relevance', 'N/A')}")

        # 分析 WebSocket 消息统计
        print(f"\n  --- WebSocket 消息统计 ---")
        from collections import Counter
        type_counts = Counter(m.get("type", "unknown") for m in ws_messages)
        for t, c in type_counts.most_common():
            print(f"    {t}: {c} 条")
        print(f"    总计: {len(ws_messages)} 条")

    except Exception as e:
        print(f"  ❌ 生成失败: {e}")
        import traceback
        traceback.print_exc()


async def main():
    print("=" * 60)
    print("Layer 5: WebSocket API 端到端测试")
    print("=" * 60)

    server_running = await check_server()

    if server_running:
        print(f"\n  ✅ 服务运行中 ({BASE_URL})")
        await test_with_websocket()
    else:
        print(f"\n  ⚠️  服务未运行 ({BASE_URL})")
        print(f"  将直接调用 Coordinator 并模拟 WebSocket 回调...")
        await test_without_server()

    print("\n" + "=" * 60)
    print("Layer 5 测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
