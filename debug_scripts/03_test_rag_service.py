#!/usr/bin/env python
"""
环节 3：测试 RAGService 的 provider 路由逻辑
=============================================

功能：
- 测试 _get_provider_for_kb() 是否正确读取 metadata.json 中的 rag_provider
- 测试 RAGService.search() 是否路由到正确的 pipeline
- 对比直接调用 pipeline vs 通过 RAGService 调用的结果差异

用法：
    python debug_scripts/03_test_rag_service.py --kb 22
    python debug_scripts/03_test_rag_service.py --kb 22 --query "基础设施团队负责人是谁"

关键源码位置：
    src/services/rag/service.py   →  RAGService._get_provider_for_kb()
    src/services/rag/service.py   →  RAGService.search()
    src/services/rag/factory.py   →  get_pipeline()

⚡ 这是本次 bug 的关键环节！
   日志显示 _get_provider_for_kb() 返回了 'raganything' 而非 'llamaindex'，
   导致用错了 pipeline。在 _get_provider_for_kb() 方法内打断点可以复现。
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_QUERY = "项目 Phoenix 的 GPU 资源审批应该找谁？"


def test_provider_resolution(kb_name: str):
    """测试 provider 解析逻辑（不执行搜索）"""
    from src.services.rag.service import RAGService

    print("=" * 60)
    print(f"Provider 路由测试 (kb_name='{kb_name}')")
    print("=" * 60)

    service = RAGService()

    # 1. 显示 RAGService 默认 provider
    print(f"\n1️⃣  RAGService 默认 provider: '{service.provider}'")
    print(f"   (来源: RAG_PROVIDER 环境变量 or 默认 'raganything')")

    # 2. 手动模拟 _get_provider_for_kb 逻辑
    import os
    kb_base_dir = service.kb_base_dir
    metadata_file = Path(kb_base_dir) / kb_name / "metadata.json"

    print(f"\n2️⃣  检查 metadata 文件: {metadata_file}")
    print(f"   文件存在: {metadata_file.exists()}")

    if metadata_file.exists():
        with open(metadata_file, encoding="utf-8") as f:
            meta = json.load(f)
        provider_in_meta = meta.get("rag_provider")
        print(f"   metadata 中的 rag_provider: '{provider_in_meta}'")
    else:
        provider_in_meta = None
        print("   ⚠️  metadata.json 不存在，将回退到默认 provider")

    # 3. 调用实际方法
    resolved = service._get_provider_for_kb(kb_name)
    print(f"\n3️⃣  _get_provider_for_kb('{kb_name}') 返回: '{resolved}'")

    # 4. 判断是否正确
    if provider_in_meta and resolved == provider_in_meta:
        print(f"   ✅ 正确！使用了 metadata 中指定的 provider")
    elif provider_in_meta and resolved != provider_in_meta:
        print(f"   ❌ 错误！metadata 指定 '{provider_in_meta}' 但实际用了 '{resolved}'")
    else:
        print(f"   ⚠️  metadata 中无 rag_provider，回退到默认: '{resolved}'")

    # 5. 测试 factory 能否创建对应 pipeline
    print(f"\n4️⃣  测试 pipeline 创建...")
    from src.services.rag.factory import get_pipeline
    try:
        pipeline = get_pipeline(resolved, kb_base_dir=kb_base_dir)
        print(f"   ✅ 成功创建 pipeline: {type(pipeline).__name__}")
    except Exception as e:
        print(f"   ❌ 创建失败: {e}")

    return resolved


async def test_rag_service_search(kb_name: str, query: str):
    """通过 RAGService 执行搜索"""
    from src.services.rag.service import RAGService

    print("\n" + "=" * 60)
    print(f"RAGService.search() 测试")
    print("=" * 60)
    print(f"  KB: {kb_name}")
    print(f"  Query: {query}")

    service = RAGService()

    print(f"\n🔍 执行搜索...")
    try:
        result = await service.search(query=query, kb_name=kb_name, mode="hybrid")

        print(f"\n--- 搜索结果 ---")
        print(f"  Provider: {result.get('provider')}")
        print(f"  Mode: {result.get('mode')}")
        print(f"  Answer 长度: {len(result.get('answer', ''))} chars")
        print(f"\n📝 Answer 内容:")
        print("-" * 40)
        answer = result.get("answer", "(空)")
        print(answer[:500])
        if len(answer) > 500:
            print(f"... (共 {len(answer)} chars)")
        print("-" * 40)

        # 检查是否有实际内容
        if len(result.get("answer", "")) < 20:
            print("\n⚠️  返回内容很短，可能检索失败！")
        else:
            print("\n✅ RAGService 搜索返回了内容")

    except Exception as e:
        print(f"\n❌ 搜索失败: {e}")
        import traceback
        traceback.print_exc()


async def test_rag_search_tool(kb_name: str, query: str):
    """通过 rag_search 工具函数执行搜索（和 ChatAgent 调用路径一致）"""
    from src.tools.rag_tool import rag_search

    print("\n" + "=" * 60)
    print(f"rag_search() 工具函数测试（ChatAgent 实际调用路径）")
    print("=" * 60)
    print(f"  KB: {kb_name}")
    print(f"  Query: {query}")

    print(f"\n🔍 执行搜索...")
    try:
        result = await rag_search(query=query, kb_name=kb_name, mode="hybrid")

        print(f"\n--- 搜索结果 ---")
        print(f"  Provider: {result.get('provider')}")
        print(f"  Answer 长度: {len(result.get('answer', ''))} chars")
        print(f"\n📝 Answer 内容:")
        print("-" * 40)
        answer = result.get("answer", "(空)")
        print(answer[:500])
        print("-" * 40)

    except Exception as e:
        print(f"\n❌ 搜索失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="测试 RAGService provider 路由")
    parser.add_argument("--kb", type=str, default="22", help="知识库名称")
    parser.add_argument("--query", type=str, default=DEFAULT_QUERY, help="查询问题")
    parser.add_argument("--search", action="store_true", help="是否执行实际搜索（默认只测试路由）")
    args = parser.parse_args()

    # 始终测试 provider 路由
    resolved_provider = test_provider_resolution(args.kb)

    # 可选：执行实际搜索
    if args.search:
        asyncio.run(test_rag_service_search(args.kb, args.query))
        asyncio.run(test_rag_search_tool(args.kb, args.query))
    else:
        print("\n💡 加 --search 参数可执行实际搜索测试")
