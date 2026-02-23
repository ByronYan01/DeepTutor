#!/usr/bin/env python
"""
Layer 1: Data Structures 数据结构（底层，无 LLM）
=========================================
测试 Research 模块的三个核心数据结构：
  1. ToolTrace — 单次工具调用记录
  2. TopicBlock — 最小调度单元（含状态机 + ToolTrace 列表）
  3. DynamicTopicQueue — 动态主题队列（核心调度中心）

调用链路：
  ToolTrace(tool_id, citation_id, tool_type, query, raw_answer, summary)
    → __post_init__()                 # 自动截断 raw_answer(>50KB)
    → to_dict() / from_dict()          # 序列化 / 反序列化

  TopicBlock(block_id, sub_topic, overview)
    → add_tool_trace(trace)            # 追加工具记录
    → get_latest_trace()               # 获取最新记录
    → get_all_summaries()              # 拼接所有摘要
    → to_dict() / from_dict()          # 序列化（含状态枚举处理）

  DynamicTopicQueue(research_id, max_length, state_file)
    → add_block(sub_topic, overview)    # 添加主题块，自增 block_counter
    → get_pending_block()              # 获取第一个 PENDING 块
    → mark_researching(block_id)       # PENDING → RESEARCHING
    → mark_completed(block_id)         # → COMPLETED
    → mark_failed(block_id)            # → FAILED
    → has_topic(sub_topic)             # 去重检查（大小写不敏感）
    → get_statistics()                 # 统计信息
    → save_to_json() / load_from_json() # JSON 持久化

输入：硬编码的测试数据
输出：各数据结构的字段值和状态变化
"""

import json
import sys
import tempfile
from pathlib import Path

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.agents.research.data_structures import (
    DynamicTopicQueue,
    ToolTrace,
    ToolType,
    TopicBlock,
    TopicStatus,
)


def main():
    print("=" * 60)
    print("Layer 1: Data Structures 数据结构测试")
    print("=" * 60)

    # -------------------------------------------------------
    # Step 1: ToolTrace — 工具调用记录
    # -------------------------------------------------------
    print("\n--- Step 1: ToolTrace 工具调用记录 ---")

    trace1 = ToolTrace(
        tool_id="tool_1001",
        citation_id="CIT-1-01",
        tool_type="rag_hybrid",
        query="什么是 Transformer 的自注意力机制？",
        raw_answer='{"answer": "自注意力通过 Q/K/V 矩阵计算...", "chunks": ["chunk1", "chunk2"]}',
        summary="Transformer 自注意力机制通过 Query、Key、Value 三个矩阵，计算每个 token 与其他 token 的相关性权重。",
    )

    print(f"  tool_id:       {trace1.tool_id}")
    print(f"  citation_id:   {trace1.citation_id}")
    print(f"  tool_type:     {trace1.tool_type}")
    print(f"  query:         {trace1.query}")
    print(f"  raw_answer 长度: {len(trace1.raw_answer)} chars")
    print(f"  summary 长度:   {len(trace1.summary)} chars")
    print(f"  timestamp:     {trace1.timestamp}")
    print(f"  truncated:     {trace1.raw_answer_truncated}")
    print(f"  original_size: {trace1.raw_answer_original_size}")

    # 测试序列化
    trace_dict = trace1.to_dict()
    trace_restored = ToolTrace.from_dict(trace_dict)
    assert trace_restored.tool_id == trace1.tool_id
    assert trace_restored.citation_id == trace1.citation_id
    assert trace_restored.summary == trace1.summary
    print("  ✅ ToolTrace 序列化 / 反序列化通过")

    # 测试大数据截断
    big_answer = "x" * 60000  # 超过 50KB 限制
    trace_big = ToolTrace(
        tool_id="tool_big",
        citation_id="CIT-BIG",
        tool_type="web_search",
        query="测试大数据",
        raw_answer=big_answer,
        summary="大数据摘要",
    )
    print(f"\n  大数据截断测试:")
    print(f"    原始长度:   {trace_big.raw_answer_original_size} chars")
    print(f"    截断后长度: {len(trace_big.raw_answer)} chars")
    print(f"    被截断:     {trace_big.raw_answer_truncated}")
    assert trace_big.raw_answer_truncated is True
    assert len(trace_big.raw_answer) <= 50 * 1024 + 100  # 允许截断标记的额外长度
    print("  ✅ 大数据截断通过")

    # -------------------------------------------------------
    # Step 2: TopicBlock — 主题块
    # -------------------------------------------------------
    print("\n--- Step 2: TopicBlock 主题块 ---")

    block = TopicBlock(
        block_id="block_1",
        sub_topic="Transformer 注意力机制",
        overview="深入研究 Transformer 中自注意力和多头注意力的工作原理及其变体",
    )

    print(f"  block_id:    {block.block_id}")
    print(f"  sub_topic:   {block.sub_topic}")
    print(f"  overview:    {block.overview[:50]}...")
    print(f"  status:      {block.status} (值: {block.status.value})")
    print(f"  tool_traces: {len(block.tool_traces)} 条")
    print(f"  iteration:   {block.iteration_count}")
    print(f"  created_at:  {block.created_at}")

    # 添加 ToolTrace
    block.add_tool_trace(trace1)

    trace2 = ToolTrace(
        tool_id="tool_1002",
        citation_id="CIT-1-02",
        tool_type="paper_search",
        query="Attention Is All You Need",
        raw_answer='{"papers": [{"title": "Attention Is All You Need", "year": 2017}]}',
        summary="Vaswani 等人 2017 年提出 Transformer 架构，用自注意力完全替代了 RNN/CNN。",
    )
    block.add_tool_trace(trace2)

    print(f"\n  添加 2 条 ToolTrace 后:")
    print(f"    tool_traces: {len(block.tool_traces)} 条")
    print(f"    最新记录:    {block.get_latest_trace().tool_type} — {block.get_latest_trace().citation_id}")
    print(f"    全部摘要:")
    for line in block.get_all_summaries().split("\n"):
        print(f"      {line}")

    # 测试序列化（含枚举处理）
    block_dict = block.to_dict()
    assert block_dict["status"] == "pending"  # 枚举应转为字符串
    block_restored = TopicBlock.from_dict(block_dict)
    assert block_restored.status == TopicStatus.PENDING
    assert len(block_restored.tool_traces) == 2
    print("  ✅ TopicBlock 序列化 / 反序列化通过")

    # -------------------------------------------------------
    # Step 3: TopicStatus 状态枚举
    # -------------------------------------------------------
    print("\n--- Step 3: TopicStatus 状态枚举 ---")
    for s in TopicStatus:
        print(f"  {s.name:15s} → value: {s.value}")
    print("  ✅ 状态枚举正常")

    # -------------------------------------------------------
    # Step 4: ToolType 工具类型枚举
    # -------------------------------------------------------
    print("\n--- Step 4: ToolType 工具类型枚举 ---")
    for t in ToolType:
        print(f"  {t.name:15s} → value: {t.value}")
    print("  ✅ 工具类型枚举正常")

    # -------------------------------------------------------
    # Step 5: DynamicTopicQueue — 队列操作
    # -------------------------------------------------------
    print("\n--- Step 5: DynamicTopicQueue 队列操作 ---")

    queue = DynamicTopicQueue(research_id="test_research_001", max_length=5)
    print(f"  research_id: {queue.research_id}")
    print(f"  max_length:  {queue.max_length}")
    print(f"  blocks:      {len(queue.blocks)}")

    # 5.1 添加主题块
    print("\n  [5.1] 添加主题块:")
    b1 = queue.add_block("Transformer 注意力机制", "研究自注意力和多头注意力原理")
    b2 = queue.add_block("位置编码", "Sinusoidal 和可学习位置编码方案")
    b3 = queue.add_block("Layer Normalization", "Pre-LN vs Post-LN 的区别")
    print(f"    添加 3 个主题后:")
    for b in queue.blocks:
        print(f"      {b.block_id}: {b.sub_topic} [{b.status.value}]")

    # 5.2 去重检查
    print("\n  [5.2] 去重检查:")
    has_exact = queue.has_topic("Transformer 注意力机制")
    has_case = queue.has_topic("transformer 注意力机制")  # 大小写不敏感
    has_new = queue.has_topic("残差连接")
    print(f"    精确匹配 'Transformer 注意力机制': {has_exact}")
    print(f"    大小写不敏感 'transformer 注意力机制': {has_case}")
    print(f"    不存在的 '残差连接': {has_new}")
    assert has_exact is True
    assert has_case is True
    assert has_new is False
    print("  ✅ 去重检查通过")

    # 5.3 状态流转：PENDING → RESEARCHING → COMPLETED
    print("\n  [5.3] 状态流转:")
    print(f"    初始: {b1.status.value}")

    queue.mark_researching(b1.block_id)
    print(f"    mark_researching 后: {b1.status.value}")
    assert b1.status == TopicStatus.RESEARCHING

    queue.mark_completed(b1.block_id)
    print(f"    mark_completed 后:   {b1.status.value}")
    assert b1.status == TopicStatus.COMPLETED

    # 另一个块标记为失败
    queue.mark_researching(b3.block_id)
    queue.mark_failed(b3.block_id)
    print(f"    b3 mark_failed 后:   {b3.status.value}")
    assert b3.status == TopicStatus.FAILED
    print("  ✅ 状态流转通过")

    # 5.4 获取下一个待处理块
    print("\n  [5.4] 获取下一个待处理块:")
    pending = queue.get_pending_block()
    print(f"    下一个待处理: {pending.block_id if pending else 'None'} — {pending.sub_topic if pending else ''}")
    assert pending is not None
    assert pending.block_id == b2.block_id
    print("  ✅ 获取待处理块通过")

    # 5.5 统计信息
    print("\n  [5.5] 队列统计:")
    stats = queue.get_statistics()
    for k, v in stats.items():
        print(f"    {k:20s}: {v}")
    assert stats["total_blocks"] == 3
    assert stats["completed"] == 1
    assert stats["pending"] == 1
    assert stats["failed"] == 1
    print("  ✅ 统计信息通过")

    # 5.6 容量限制测试
    print("\n  [5.6] 容量限制测试:")
    queue.add_block("编码器-解码器架构", "编码器和解码器的堆叠结构")
    queue.add_block("前馈网络", "FFN 在 Transformer 中的作用")
    print(f"    当前 {len(queue.blocks)}/{queue.max_length} 块")
    try:
        queue.add_block("超出限制的主题", "这个应该被拒绝")
        print("    ❌ 应该抛出 RuntimeError 但没有!")
    except RuntimeError as e:
        print(f"    ✅ 正确拒绝: {e}")

    # 5.7 is_all_completed 判断
    print("\n  [5.7] is_all_completed 判断:")
    print(f"    当前 is_all_completed: {queue.is_all_completed()}")
    assert queue.is_all_completed() is False

    # 把所有块都标记为完成
    for b in queue.blocks:
        if b.status != TopicStatus.COMPLETED:
            queue.mark_completed(b.block_id)
    print(f"    全部完成后 is_all_completed: {queue.is_all_completed()}")
    assert queue.is_all_completed() is True
    print("  ✅ is_all_completed 通过")

    # -------------------------------------------------------
    # Step 6: JSON 持久化
    # -------------------------------------------------------
    print("\n--- Step 6: JSON 持久化 ---")

    # 给 b2 添加一条 ToolTrace 以丰富持久化测试数据
    b2.add_tool_trace(trace1)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp_path = f.name

    queue.save_to_json(tmp_path)
    file_size = Path(tmp_path).stat().st_size
    print(f"  保存到: {tmp_path}")
    print(f"  文件大小: {file_size} bytes")

    # 加载并验证
    queue_loaded = DynamicTopicQueue.load_from_json(tmp_path)
    print(f"  加载后 research_id: {queue_loaded.research_id}")
    print(f"  加载后 blocks:      {len(queue_loaded.blocks)}")
    print(f"  加载后 block_counter: {queue_loaded.block_counter}")
    assert queue_loaded.research_id == queue.research_id
    assert len(queue_loaded.blocks) == len(queue.blocks)

    # 验证 ToolTrace 也被正确还原
    loaded_b2 = queue_loaded.get_block_by_id("block_2")
    assert loaded_b2 is not None
    assert len(loaded_b2.tool_traces) == 1
    assert loaded_b2.tool_traces[0].citation_id == "CIT-1-01"
    print("  ✅ JSON 持久化通过")

    # 预览 JSON 内容
    with open(tmp_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"\n  JSON 结构预览:")
    print(f"    research_id: {data['research_id']}")
    print(f"    blocks 数量: {len(data['blocks'])}")
    print(f"    statistics:  {data['statistics']}")
    for b_data in data["blocks"][:2]:
        print(f"    - {b_data['block_id']}: {b_data['sub_topic']} [{b_data['status']}] traces={len(b_data['tool_traces'])}")
    if len(data["blocks"]) > 2:
        print(f"    ... 还有 {len(data['blocks']) - 2} 个主题块")

    # 清理临时文件
    Path(tmp_path).unlink()

    # -------------------------------------------------------
    # Step 7: auto_save 功能测试
    # -------------------------------------------------------
    print("\n--- Step 7: auto_save 功能测试 ---")

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        auto_save_path = f.name

    auto_queue = DynamicTopicQueue(
        research_id="test_auto_save",
        max_length=10,
        state_file=auto_save_path,
    )
    auto_queue.add_block("自动保存测试主题", "验证 state_file 参数是否在每次操作后自动保存")

    # 检查文件是否已创建
    assert Path(auto_save_path).exists()
    with open(auto_save_path, "r", encoding="utf-8") as f:
        auto_data = json.load(f)
    print(f"  auto_save 文件已创建: {auto_save_path}")
    print(f"  blocks: {len(auto_data['blocks'])}")
    assert len(auto_data["blocks"]) == 1
    print("  ✅ auto_save 功能通过")

    # 清理
    Path(auto_save_path).unlink()

    # -------------------------------------------------------
    # 总结
    # -------------------------------------------------------
    print("\n" + "=" * 60)
    print("Layer 1 测试完成! 所有数据结构测试通过 ✅")
    print("=" * 60)
    print("\n关键发现:")
    print("  1. ToolTrace: 自动截断 >50KB 的 raw_answer，支持 JSON 智能截断")
    print("  2. TopicBlock: 状态机 PENDING→RESEARCHING→COMPLETED/FAILED")
    print("  3. DynamicTopicQueue: 自增 block_id、去重检查、容量限制、JSON 持久化")
    print("  4. auto_save: 设置 state_file 后每次操作自动保存")


if __name__ == "__main__":
    main()
