#!/usr/bin/env python
"""
Layer 4: MainSolver 端到端双循环（调 LLM）
=========================================
测试 MainSolver 的完整求解流程：
  1. 两阶段初始化（__init__ + ainit）
  2. Analysis Loop: InvestigateAgent 调查 → NoteAgent 摘要
  3. Solve Loop: ManagerAgent 规划 → SolveAgent 选择 → ToolAgent 执行
  4. Response: ResponseAgent 生成步骤回答
  5. Finalize: 编译最终答案 + 引用列表

调用链路：

  MainSolver.__init__(kb_name)
    → 轻量级同步初始化，存储参数

  MainSolver.ainit()
    → load_config_with_main_async("main.yaml")   # 加载统一配置
    → ConfigValidator.validate(config)            # 验证配置
    → get_llm_config_async()                      # LLM 配置
    → SolveAgentLogger                            # 日志系统
    → PerformanceMonitor                          # 性能监控
    → TokenTracker                                # Token 统计
    → _init_agents()                              # 初始化 Agent

  MainSolver.solve(question)
    → _run_dual_loop_pipeline(question, output_dir)
      ├── Analysis Loop:
      │   for i in range(max_analysis_iterations):
      │     investigate_agent.process()            # 调查
      │     note_agent.process()                   # 摘要
      │     if should_stop: break
      ├── Solve Loop:
      │   manager_agent.process()                  # 规划步骤链
      │   for step in solve_memory.solve_chains:
      │     solve_agent.process()                  # 工具选择
      │     tool_agent.process()                   # 工具执行
      │   for step in solve_memory.solve_chains:
      │     response_agent.process()               # 生成回答
      ├── Finalize:
      │   citation_memory.format_citations_markdown()
      │   precision_answer_agent.process() (可选)
      └── return {final_answer, citations, metadata}

输入：硬编码的 Python 知识点问题
输出：完整的求解答案 + 输出目录结构
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env", override=False)


async def main():
    print("=" * 60)
    print("Layer 4: MainSolver 端到端双循环测试")
    print("=" * 60)

    from src.agents.solve.main_solver import MainSolver

    # -------------------------------------------------------
    # Step 1: 两阶段初始化
    # -------------------------------------------------------
    print("\n--- Step 1: MainSolver 两阶段初始化 ---")

    question = "请解释 Python 中 is 和 == 的区别，并举例说明何时使用哪个。"
    kb_name = "ai_textbook"

    print(f"  问题: {question}")
    print(f"  知识库: {kb_name}")
    print(f"  正在初始化 MainSolver...")

    start_time = time.time()

    # Phase 1: 同步初始化（轻量级）
    solver = MainSolver(kb_name=kb_name)
    print(f"\n  Phase 1 (__init__) 完成:")
    print(f"    config:  {solver.config}")  # 应该是 None
    print(f"    api_key: {solver.api_key}")  # 应该是 None

    # Phase 2: 异步初始化（加载配置、初始化 Agent）
    await solver.ainit()
    init_time = time.time() - start_time

    print(f"\n  Phase 2 (ainit) 完成: {init_time:.2f}s")
    print(f"    config 加载: ✅")
    print(f"    api_key: {solver.api_key[:8]}..." if solver.api_key else "    api_key: None")
    print(f"    base_url: {solver.base_url}")
    print(f"    kb_name: {solver.kb_name}")
    print(f"    language: {solver.config.get('system', {}).get('language', 'N/A')}")

    # 检查 Agent 初始化状态
    print(f"\n  Agent 初始化状态:")
    print(f"    investigate_agent: {'✅' if solver.investigate_agent else '❌'}")
    print(f"    note_agent:        {'✅' if solver.note_agent else '❌'}")
    print(f"    manager_agent:     {'⏳ lazy' if solver.manager_agent is None else '✅'}")
    print(f"    solve_agent:       {'⏳ lazy' if solver.solve_agent is None else '✅'}")
    print(f"    tool_agent:        {'⏳ lazy' if solver.tool_agent is None else '✅'}")
    print(f"    response_agent:    {'⏳ lazy' if solver.response_agent is None else '✅'}")

    # -------------------------------------------------------
    # Step 2: 执行完整求解流程
    # -------------------------------------------------------
    print("\n--- Step 2: 执行 solve() —— 完整双循环 ---")
    print(f"  问题: {question}")
    print(f"  正在求解（Analysis Loop → Solve Loop → Response）...")

    solve_start = time.time()

    try:
        result = await solver.solve(question=question, verbose=True)
        solve_time = time.time() - solve_start

        print(f"\n  ✅ 求解完成! 耗时: {solve_time:.1f}s")

        # -------------------------------------------------------
        # Step 3: 分析结果
        # -------------------------------------------------------
        print("\n--- Step 3: 结果分析 ---")

        print(f"  结果字段:")
        for key in result:
            value = result[key]
            if isinstance(value, str) and len(value) > 100:
                print(f"    {key}: ({len(value)} chars)")
            elif isinstance(value, dict):
                print(f"    {key}: {{{', '.join(value.keys())}}}")
            elif isinstance(value, list):
                print(f"    {key}: [{len(value)} items]")
            else:
                print(f"    {key}: {value}")

        # 流程统计
        print(f"\n  流程统计:")
        print(f"    Analysis 迭代:  {result.get('analysis_iterations', 'N/A')}")
        print(f"    Solve 步骤:     {result.get('solve_steps', 'N/A')}/{result.get('total_steps', 'N/A')}")
        print(f"    引用数量:       {len(result.get('citations', []))}")
        print(f"    Pipeline:       {result.get('pipeline', 'N/A')}")

        # 最终答案预览
        final_answer = result.get("final_answer", "")
        print(f"\n  最终答案预览 ({len(final_answer)} chars):")
        lines = final_answer.split("\n")
        for line in lines[:20]:
            print(f"    {line}")
        if len(lines) > 20:
            print(f"    ... (共 {len(lines)} 行)")

        # -------------------------------------------------------
        # Step 4: 检查输出目录
        # -------------------------------------------------------
        print("\n--- Step 4: 检查输出目录 ---")

        output_dir = result.get("metadata", {}).get("output_dir") or result.get("output_dir", "")
        if output_dir and Path(output_dir).exists():
            print(f"  输出目录: {output_dir}")
            for f in sorted(Path(output_dir).iterdir()):
                if f.is_file():
                    print(f"    {f.name} ({f.stat().st_size:,} bytes)")
                elif f.is_dir():
                    child_count = sum(1 for _ in f.iterdir())
                    print(f"    {f.name}/ ({child_count} files)")
        else:
            print(f"  ⚠️ 输出目录不存在或未返回: {output_dir}")

    except Exception as e:
        solve_time = time.time() - solve_start
        print(f"\n  ❌ 求解失败 (耗时 {solve_time:.1f}s): {e}")
        import traceback
        traceback.print_exc()
        return

    # -------------------------------------------------------
    # 总结
    # -------------------------------------------------------
    total_time = time.time() - start_time
    print("\n" + "=" * 60)
    print("Layer 4 测试完成!")
    print("=" * 60)
    print(f"\n  总耗时:       {total_time:.1f}s")
    print(f"  初始化:       {init_time:.1f}s")
    print(f"  求解:         {solve_time:.1f}s")
    print(f"  Analysis 轮数: {result.get('analysis_iterations', 'N/A')}")
    print(f"  Solve 步骤:    {result.get('solve_steps', 'N/A')}")
    print(f"  答案长度:      {len(result.get('final_answer', ''))} chars")
    print(f"\n关键发现:")
    print("  1. MainSolver 采用两阶段初始化：__init__ 同步 + ainit 异步")
    print("  2. Analysis Loop Agent 立即初始化，Solve Loop Agent 惰性初始化")
    print("  3. 双循环串行执行：先 Analysis（调查+笔记），再 Solve（规划+执行+响应）")
    print("  4. 每个步骤可能有多轮 SolveAgent → ToolAgent 迭代（max_correction_iterations）")
    print("  5. 最终答案由各步骤 ResponseAgent 的输出拼接而成 + 引用列表")
    if output_dir:
        print(f"\n  输出目录: {output_dir}")


if __name__ == "__main__":
    asyncio.run(main())
