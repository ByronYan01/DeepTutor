#!/usr/bin/env python
"""
Layer 4: ResearchPipeline 三阶段编排（端到端，使用 quick 预设）
=========================================
测试 ResearchPipeline 的完整三阶段流程：
  Phase 1: Planning — RephraseAgent(禁用) + DecomposeAgent → 队列初始化
  Phase 2: Researching — ManagerAgent 调度 + ResearchAgent 循环 + NoteAgent 记录
  Phase 3: Reporting — ReportingAgent 生成报告

调用链路：
  ResearchPipeline.__init__(config, api_key, base_url, kb_name)
    → _init_logger()                    # 初始化日志
    → _init_agents()                    # 初始化 6 个 Agent
    → CitationManager(research_id)       # 引用管理器
    → DynamicTopicQueue(research_id)     # 动态队列

  ResearchPipeline.run(topic)
    → _phase1_planning(topic)
      → RephraseAgent.process()          # (禁用时跳过)
      → DecomposeAgent.process()         # 分解主题 → sub_topics
      → queue.add_block() × N           # 添加到队列

    → _phase2_researching()
      → _phase2_researching_series()     # 串行模式
        → while not complete:
          → manager.get_next_task()      # 获取下一个任务
          → research.process()           # 研究循环 (包含多轮 LLM 调用)
          → manager.complete_task()      # 标记完成

    → _phase3_reporting(topic)
      → reporting.process(queue, topic)  # 生成报告
        → _deduplicate_blocks()          # 去重
        → _generate_outline()            # 生成大纲
        → _write_introduction()          # 写引言
        → _write_section_body() × N     # 写各章节
        → _write_conclusion()            # 写结论
        → _generate_references()         # 生成参考文献

    → 保存报告 .md / metadata .json / queue .json / outline .json

输入：研究主题 + quick 预设配置
输出：完整的 Markdown 研究报告
"""

import asyncio
import json
import sys
from pathlib import Path

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env", override=False)


async def main():
    print("=" * 60)
    print("Layer 4: ResearchPipeline 三阶段编排测试")
    print("=" * 60)

    # -------------------------------------------------------
    # Step 1: 加载配置
    # -------------------------------------------------------
    print("\n--- Step 1: 加载配置 ---")

    from src.agents.research.main import load_config
    from src.services.llm import get_llm_config

    llm_config = get_llm_config()
    print(f"  LLM: {llm_config.api_key[:8]}... @ {llm_config.base_url[:50]}...")

    # 加载配置并应用 quick 预设
    config = load_config(preset="quick")

    # ============================================================
    # 最小化配置覆盖（加速调试，可自行微调数值）
    # ============================================================

    # --- Planning 阶段 ---
    # 禁用 rephrase：跳过主题改写环节，省 1 次 LLM 调用，也避免 CLI 交互确认
    config.setdefault("planning", {}).setdefault("rephrase", {})["enabled"] = False
    # 分解模式：manual = 固定数量（1 次 LLM），auto = LLM 自决数量（2+ 次 LLM）
    config.setdefault("planning", {}).setdefault("decompose", {})["mode"] = "manual"
    # 子主题数量：决定 Phase 2 要研究几个 TopicBlock（改大 = 更多循环）
    config["planning"]["decompose"]["initial_subtopics"] = 2  # 最小 1 个

    # --- Researching 阶段 ---
    # 每个子主题的最大研究迭代数（每轮 = check_sufficiency + query_plan + note = 3 次 LLM）
    config.setdefault("researching", {})["max_iterations"] = 2   # 最小 1 轮
    # 禁用外部搜索工具（减少外部依赖和超时风险）
    config["researching"]["enable_web_search"] = False
    config["researching"]["enable_paper_search"] = False

    # --- Reporting 阶段 ---
    # 每个章节的最小字数要求（改小 = LLM 生成 token 更少，速度更快）
    config.setdefault("reporting", {})["min_section_length"] = 200  # 默认 500

    # ============================================================
    # 预估 LLM 调用：约 7 次（分解1 + 充分性1 + 查询1 + 摘要1 + 去重1 + 大纲1 + 报告1）
    # 微调建议：
    #   initial_subtopics=2, max_iterations=2 → 约 16 次 LLM
    #   initial_subtopics=3, max_iterations=3 → 约 35 次 LLM
    # ============================================================

    print(f"\n  配置详情:")
    planning = config.get("planning", {})
    researching = config.get("researching", {})
    reporting = config.get("reporting", {})

    print(f"    [Planning]")
    print(f"      rephrase enabled:  {planning.get('rephrase', {}).get('enabled', True)}")
    print(f"      decompose mode:    {planning.get('decompose', {}).get('mode', 'manual')}")
    print(f"      initial_subtopics: {planning.get('decompose', {}).get('initial_subtopics', 5)}")

    print(f"    [Researching]")
    print(f"      max_iterations:    {researching.get('max_iterations', 5)}")
    print(f"      iteration_mode:    {researching.get('iteration_mode', 'fixed')}")
    print(f"      execution_mode:    {researching.get('execution_mode', 'series')}")
    print(f"      enable_rag:        {researching.get('enable_rag_hybrid', True)}")
    print(f"      enable_web:        {researching.get('enable_web_search', False)}")
    print(f"      enable_paper:      {researching.get('enable_paper_search', False)}")

    print(f"    [Reporting]")
    print(f"      min_section_length: {reporting.get('min_section_length', 500)}")

    # -------------------------------------------------------
    # Step 2: 初始化 Pipeline
    # -------------------------------------------------------
    print("\n--- Step 2: 初始化 ResearchPipeline ---")

    from src.agents.research.research_pipeline import ResearchPipeline

    # 使用已有知识库
    kb_name = config.get("rag", {}).get("kb_name", "ai_textbook")
    print(f"  知识库: {kb_name}")

    pipeline = ResearchPipeline(
        config=config,
        api_key=llm_config.api_key,
        base_url=llm_config.base_url,
        kb_name=kb_name,
    )

    print(f"  research_id:  {pipeline.research_id}")
    print(f"  cache_dir:    {pipeline.cache_dir}")
    print(f"  reports_dir:  {pipeline.reports_dir}")
    print(f"  agents 数量:  {len(pipeline.agents)}")
    for name, agent in pipeline.agents.items():
        print(f"    {name:12s}: {agent.__class__.__name__} (model={agent.get_model()})")

    # -------------------------------------------------------
    # Step 3: 执行完整研究流程
    # -------------------------------------------------------
    print("\n--- Step 3: 执行 pipeline.run() ---")
    topic = "深度学习中的注意力机制"
    print(f"  研究主题: {topic}")
    print(f"  预设模式: quick（1 子主题 × 1 迭代）")
    print(f"  开始执行...\n")

    try:
        result = await pipeline.run(topic=topic)

        print(f"\n{'=' * 60}")
        print(f"  ✅ 研究完成!")
        print(f"    research_id:    {result['research_id']}")
        print(f"    topic:          {result['topic']}")
        print(f"    report_path:    {result['final_report_path']}")

        # 检查报告内容
        report_path = Path(result['final_report_path'])
        if report_path.exists():
            report_content = report_path.read_text(encoding="utf-8")
            print(f"    报告字数:       {len(report_content)} chars")
            print(f"\n  报告内容预览（前 500 字）:")
            print(f"  {'─' * 50}")
            for line in report_content[:500].split("\n"):
                print(f"    {line}")
            if len(report_content) > 500:
                print(f"    ...（省略 {len(report_content) - 500} chars）")
            print(f"  {'─' * 50}")

    except Exception as e:
        print(f"\n  ❌ 研究失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 4: 检查产出文件
    # -------------------------------------------------------
    print("\n--- Step 4: 检查产出文件 ---")

    cache_dir = pipeline.cache_dir
    reports_dir = pipeline.reports_dir

    expected_files = [
        ("报告",      reports_dir / f"{pipeline.research_id}.md"),
        ("元数据",    reports_dir / f"{pipeline.research_id}_metadata.json"),
        ("队列状态",  cache_dir / "queue.json"),
        ("规划数据",  cache_dir / "step1_planning.json"),
        ("大纲",      cache_dir / "outline.json"),
        ("引用",      cache_dir / "citations.json"),
    ]

    for label, fpath in expected_files:
        if fpath.exists():
            size = fpath.stat().st_size
            print(f"  ✅ {label:8s}: {fpath.name} ({size} bytes)")
        else:
            print(f"  ⚠️ {label:8s}: {fpath.name} (未生成)")

    # 查看 metadata 内容
    metadata_path = reports_dir / f"{pipeline.research_id}_metadata.json"
    if metadata_path.exists():
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        print(f"\n  元数据详情:")
        print(f"    research_id:     {metadata.get('research_id')}")
        print(f"    topic:           {metadata.get('topic')}")
        print(f"    optimized_topic: {metadata.get('optimized_topic', '')[:80]}...")
        print(f"    report_words:    {metadata.get('report_word_count', 0)}")
        stats = metadata.get("statistics", {})
        print(f"    统计:")
        for k, v in stats.items():
            print(f"      {k}: {v}")

    # 查看 queue.json 内容
    queue_path = cache_dir / "queue.json"
    if queue_path.exists():
        with open(queue_path, "r", encoding="utf-8") as f:
            queue_data = json.load(f)
        print(f"\n  队列详情:")
        for b in queue_data.get("blocks", []):
            traces_count = len(b.get("tool_traces", []))
            print(f"    {b['block_id']}: {b['sub_topic']} [{b['status']}] traces={traces_count}")

    # -------------------------------------------------------
    # Step 5: Token 统计
    # -------------------------------------------------------
    print("\n--- Step 5: Token 统计 ---")

    from src.agents.base_agent import BaseAgent
    stats = BaseAgent.get_stats("research")
    print(f"  总调用次数:    {len(stats.calls)}")
    print(f"  总输入 tokens: {stats.total_prompt_tokens}")
    print(f"  总输出 tokens: {stats.total_completion_tokens}")
    print(f"  总费用:        ${stats.total_cost:.4f}")

    if stats.calls:
        print(f"\n  各阶段 LLM 调用:")
        for i, call in enumerate(stats.calls):
            stage = call.get("stage", "?")
            prompt = call.get("prompt_tokens", 0)
            compl = call.get("completion_tokens", 0)
            print(f"    [{i+1}] {stage:30s} prompt={prompt}, completion={compl}")

    print("\n" + "=" * 60)
    print("Layer 4 测试完成!")
    print("=" * 60)
    print("\n关键发现:")
    print("  1. ResearchPipeline 通过 load_config + preset 灵活控制研究深度")
    print("  2. 三阶段严格顺序执行：Planning → Researching → Reporting")
    print("  3. Phase 1 产出 step1_planning.json（含分解结果和 RAG 上下文）")
    print("  4. Phase 2 每个 TopicBlock 独立研究，结果存入 queue.json")
    print("  5. Phase 3 生成带引用的 Markdown 报告（含引言/正文/结论/参考文献）")
    print("  6. 所有中间数据持久化到 cache_dir，报告存到 reports_dir")


if __name__ == "__main__":
    asyncio.run(main())
