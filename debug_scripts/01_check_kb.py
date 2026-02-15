#!/usr/bin/env python
"""
环节 1：检查知识库元数据和目录结构
====================================

功能：
- 列出所有知识库
- 检查指定 KB 的 metadata.json（含 rag_provider）
- 检查 raw/、rag_storage/、llamaindex_storage/ 等目录状态
- 读取原始文件内容

用法：
    python debug_scripts/01_check_kb.py --kb 22
    python debug_scripts/01_check_kb.py              # 列出所有 KB
"""

import argparse
import json
import os
import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

KB_BASE_DIR = PROJECT_ROOT / "data" / "knowledge_bases"


def list_all_kbs():
    """列出所有知识库及其基本信息"""
    print("=" * 60)
    print("所有知识库")
    print("=" * 60)

    if not KB_BASE_DIR.exists():
        print(f"❌ 知识库目录不存在: {KB_BASE_DIR}")
        return

    kbs = sorted([d for d in KB_BASE_DIR.iterdir() if d.is_dir()])
    if not kbs:
        print("⚠️  没有找到任何知识库")
        return

    for kb_dir in kbs:
        metadata_file = kb_dir / "metadata.json"
        provider = "unknown"
        if metadata_file.exists():
            try:
                with open(metadata_file, encoding="utf-8") as f:
                    meta = json.load(f)
                provider = meta.get("rag_provider", "未设置")
            except Exception:
                provider = "读取失败"

        raw_count = len(list((kb_dir / "raw").iterdir())) if (kb_dir / "raw").exists() else 0
        rag_count = len(list((kb_dir / "rag_storage").iterdir())) if (kb_dir / "rag_storage").exists() else 0
        llama_count = len(list((kb_dir / "llamaindex_storage").iterdir())) if (kb_dir / "llamaindex_storage").exists() else 0

        print(f"\n📁 {kb_dir.name}")
        print(f"   provider={provider}, raw={raw_count}文件, rag_storage={rag_count}文件, llamaindex_storage={llama_count}文件")


def check_kb(kb_name: str):
    """详细检查指定知识库"""
    kb_dir = KB_BASE_DIR / kb_name
    print("=" * 60)
    print(f"知识库详细检查: {kb_name}")
    print(f"路径: {kb_dir}")
    print("=" * 60)

    if not kb_dir.exists():
        print(f"❌ 知识库目录不存在: {kb_dir}")
        return

    # 1. metadata.json
    print("\n--- metadata.json ---")
    metadata_file = kb_dir / "metadata.json"
    if metadata_file.exists():
        with open(metadata_file, encoding="utf-8") as f:
            meta = json.load(f)
        print(json.dumps(meta, indent=2, ensure_ascii=False))
        provider = meta.get("rag_provider", "未设置")
        print(f"\n✅ rag_provider = {provider}")
    else:
        print("❌ metadata.json 不存在!")

    # 2. .progress.json
    print("\n--- .progress.json ---")
    progress_file = kb_dir / ".progress.json"
    if progress_file.exists():
        with open(progress_file, encoding="utf-8") as f:
            progress = json.load(f)
        print(json.dumps(progress, indent=2, ensure_ascii=False))
    else:
        print("⚠️  .progress.json 不存在")

    # 3. 各子目录状态
    print("\n--- 目录结构 ---")
    subdirs = ["raw", "rag_storage", "llamaindex_storage", "content_list", "images"]
    for subdir in subdirs:
        d = kb_dir / subdir
        if d.exists():
            files = list(d.iterdir())
            total_size = sum(f.stat().st_size for f in files if f.is_file())
            print(f"  📂 {subdir}/: {len(files)} 个文件, 总大小 {total_size:,} bytes")
            for f in files:
                if f.is_file():
                    print(f"      - {f.name} ({f.stat().st_size:,} bytes)")
        else:
            print(f"  ⚠️  {subdir}/ 不存在")

    # 4. 原始文件内容
    raw_dir = kb_dir / "raw"
    if raw_dir.exists():
        raw_files = list(raw_dir.iterdir())
        if raw_files:
            print("\n--- 原始文件内容 ---")
            for f in raw_files:
                if f.is_file():
                    try:
                        content = f.read_text(encoding="utf-8")
                        print(f"\n📄 {f.name} ({len(content)} chars):")
                        print(f"   {content[:200]}{'...' if len(content) > 200 else ''}")
                    except Exception as e:
                        print(f"   ❌ 读取失败: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="检查知识库元数据和目录结构")
    parser.add_argument("--kb", type=str, default=None, help="知识库名称（不指定则列出所有）")
    args = parser.parse_args()

    if args.kb:
        check_kb(args.kb)
    else:
        list_all_kbs()
