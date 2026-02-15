#!/usr/bin/env python
"""
环节 2：直接测试 LlamaIndex 向量检索
======================================

功能：
- 绕过 RAGService，直接调用 LlamaIndexPipeline
- 加载指定 KB 的 llamaindex_storage 索引
- 执行向量检索并展示 Top-K 结果
- 可自定义 query 和 top_k

用法：
    python debug_scripts/02_test_llamaindex_retrieval.py --kb 22
    python debug_scripts/02_test_llamaindex_retrieval.py --kb 22 --query "张三是谁" --top_k 3

关键源码位置：
    src/services/rag/pipelines/llamaindex.py  →  LlamaIndexPipeline.search()
    - 在 search() 方法中打断点可以看到 retriever.retrieve(query) 返回的 nodes
"""

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_QUERY = "项目 Phoenix 的 GPU 资源审批应该找谁？"


async def test_llamaindex_retrieval(kb_name: str, query: str, top_k: int):
    from src.services.rag.pipelines.llamaindex import LlamaIndexPipeline

    print("=" * 60)
    print("LlamaIndex 直接检索测试")
    print("=" * 60)
    print(f"  KB: {kb_name}")
    print(f"  Query: {query}")
    print(f"  Top-K: {top_k}")
    print()

    pipeline = LlamaIndexPipeline()

    # 检查索引目录
    storage_dir = Path(pipeline.kb_base_dir) / kb_name / "llamaindex_storage"
    if not storage_dir.exists():
        print(f"❌ LlamaIndex 索引目录不存在: {storage_dir}")
        print("   该 KB 可能不是用 LlamaIndex 构建的")
        return

    files = list(storage_dir.iterdir())
    print(f"📂 索引目录: {storage_dir}")
    print(f"   索引文件数: {len(files)}")
    for f in files:
        print(f"   - {f.name} ({f.stat().st_size:,} bytes)")
    print()

    # 执行检索
    print("🔍 执行检索...")
    result = await pipeline.search(query=query, kb_name=kb_name, mode="hybrid", top_k=top_k)
    # result = await pipeline.search(query=query, kb_name=kb_name, mode="vector", top_k=top_k)

    print(f"\n--- 检索结果 ---")
    print(f"  Provider: {result.get('provider')}")
    print(f"  Answer 长度: {len(result.get('answer', ''))} chars")
    print(f"\n📝 Answer 内容:")
    print("-" * 40)
    print(result.get("answer", "(空)"))
    print("-" * 40)

    # 如果答案包含知识库内容，说明检索成功
    answer = result.get("answer", "")
    keywords = ["Phoenix", "A100", "基础设施", "张三", "zhangsan"]
    found = [kw for kw in keywords if kw in answer]
    missing = [kw for kw in keywords if kw not in answer]

    print(f"\n✅ 命中关键词: {found}")
    if missing:
        print(f"⚠️  缺失关键词: {missing}")

    if len(found) >= 3:
        print("\n🎉 LlamaIndex 检索正常！三份文档都被召回。")
    elif len(found) > 0:
        print("\n⚠️  LlamaIndex 检索部分正常，未召回全部文档。")
    else:
        print("\n❌ LlamaIndex 检索异常！未召回任何相关内容。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="直接测试 LlamaIndex 检索")
    parser.add_argument("--kb", type=str, default="22", help="知识库名称")
    parser.add_argument("--query", type=str, default=DEFAULT_QUERY, help="查询问题")
    parser.add_argument("--top_k", type=int, default=5, help="返回 Top-K 结果")
    args = parser.parse_args()

    asyncio.run(test_llamaindex_retrieval(args.kb, args.query, args.top_k))
