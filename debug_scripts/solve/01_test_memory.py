#!/usr/bin/env python
"""
Layer 1: Memory 数据结构（底层，无 LLM）
=========================================
测试 Solve 模块的三种 Memory 系统：
  1. InvestigateMemory — 分析阶段知识链（KnowledgeItem + Reflections）
  2. SolveMemory — 求解阶段步骤链（SolveChainStep + ToolCallRecord）
  3. CitationMemory — 全局引用管理（CitationItem）

调用链路：

  KnowledgeItem(cite_id, tool_type, query, raw_result)
    → to_dict() / from_dict()          # 序列化 / 反序列化
    → 向下兼容旧字段名(knowledge_id → cite_id)

  InvestigateMemory(task_id, user_question, output_dir)
    → add_knowledge(item)              # 追加知识条目
    → update_knowledge_summary(cite_id, summary)  # NoteAgent 更新摘要
    → get_available_knowledge(tool_types, cite_ids)  # 按条件过滤
    → save() / load_or_create()        # JSON 持久化

  ToolCallRecord(tool_type, query, cite_id)
    → mark_running()                   # pending → running
    → mark_result(raw_answer, summary) # → success

  SolveChainStep(step_id, step_target)
    → append_tool_call(record)         # 追加工具调用，undone → in_progress
    → mark_waiting_response()          # → waiting_response
    → update_response(response)        # → done

  SolveMemory(task_id, user_question, output_dir)
    → create_chains([steps])           # 设置步骤链
    → append_tool_call(step_id, ...)   # 追加工具调用
    → update_tool_call_result(...)     # 更新工具结果
    → mark_step_waiting_response(...)  # 标记等待响应
    → submit_step_response(...)        # 提交步骤响应
    → save() / load_or_create()        # JSON 持久化

  CitationItem(cite_id, tool_type, query)
    → to_dict() / from_dict()          # 序列化 / 反序列化

  CitationMemory(output_dir)
    → add_citation(tool_type, query)   # 添加引用，自动生成 cite_id
    → get_citation(cite_id)            # 获取引用
    → update_citation(cite_id, ...)    # 更新引用信息
    → format_citations_markdown()      # 格式化为 Markdown
    → save() / load_or_create()        # JSON 持久化

输入：硬编码的测试数据（Python 知识点相关）
输出：各数据结构的字段值和状态变化
"""

import json
import sys
import tempfile
from pathlib import Path

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.agents.solve.memory import (
    CitationItem,
    CitationMemory,
    InvestigateMemory,
    KnowledgeItem,
    Reflections,
    SolveChainStep,
    SolveMemory,
    ToolCallRecord,
)


def main():
    print("=" * 60)
    print("Layer 1: Solve Memory 数据结构测试（无 LLM）")
    print("=" * 60)

    # -------------------------------------------------------
    # Step 1: KnowledgeItem — 知识条目
    # -------------------------------------------------------
    print("\n--- Step 1: KnowledgeItem 知识条目 ---")

    k1 = KnowledgeItem(
        cite_id="[rag-1]",
        tool_type="rag_naive",
        query="Python 装饰器的工作原理是什么？",
        raw_result='{"answer": "装饰器本质上是一个接受函数作为参数的高阶函数...", "chunks": ["chunk1"]}',
        summary="",  # 初始为空，NoteAgent 稍后填充
    )

    print(f"  cite_id:    {k1.cite_id}")
    print(f"  tool_type:  {k1.tool_type}")
    print(f"  query:      {k1.query}")
    print(f"  raw_result 长度: {len(k1.raw_result)} chars")
    print(f"  summary:    '{k1.summary}' (初始为空)")
    print(f"  created_at: {k1.created_at}")

    # 序列化 / 反序列化
    k1_dict = k1.to_dict()
    k1_restored = KnowledgeItem.from_dict(k1_dict)
    assert k1_restored.cite_id == k1.cite_id
    assert k1_restored.tool_type == k1.tool_type
    assert k1_restored.query == k1.query
    print("  ✅ KnowledgeItem 序列化 / 反序列化通过")

    # 向下兼容旧字段名
    old_format = {
        "knowledge_id": "old-k-001",
        "source_type": "rag_hybrid",
        "query_text": "旧版查询",
        "answer_raw": "旧版原始答案",
        "citations": [{"ref": "old"}],  # 旧版 citations 字段应被丢弃
    }
    k_old = KnowledgeItem.from_dict(old_format)
    assert k_old.cite_id == "old-k-001"  # knowledge_id → cite_id
    assert k_old.tool_type == "rag_hybrid"  # source_type → tool_type
    assert k_old.query == "旧版查询"  # query_text → query
    assert k_old.raw_result == "旧版原始答案"  # answer_raw → raw_result
    print("  ✅ 向下兼容旧字段名通过")

    # -------------------------------------------------------
    # Step 2: Reflections — 反思
    # -------------------------------------------------------
    print("\n--- Step 2: Reflections 反思 ---")

    reflections = Reflections(
        remaining_questions=["Python GIL 的具体实现机制？", "async/await 和多线程的性能对比？"]
    )
    print(f"  remaining_questions: {reflections.remaining_questions}")
    print(f"  updated_at: {reflections.updated_at}")

    r_dict = reflections.to_dict()
    r_restored = Reflections.from_dict(r_dict)
    assert r_restored.remaining_questions == reflections.remaining_questions
    print("  ✅ Reflections 序列化 / 反序列化通过")

    # -------------------------------------------------------
    # Step 3: InvestigateMemory — 调查记忆
    # -------------------------------------------------------
    print("\n--- Step 3: InvestigateMemory 调查记忆 ---")

    with tempfile.TemporaryDirectory() as tmpdir:
        memory = InvestigateMemory(
            task_id="test_investigate_001",
            user_question="Python 中装饰器和闭包有什么区别？",
            output_dir=tmpdir,
        )

        print(f"  task_id:       {memory.task_id}")
        print(f"  user_question: {memory.user_question}")
        print(f"  version:       {memory.version}")
        print(f"  knowledge_chain: {len(memory.knowledge_chain)} 条")

        # 3.1 添加知识条目
        k2 = KnowledgeItem(
            cite_id="[rag-2]",
            tool_type="rag_hybrid",
            query="Python 闭包 closure 定义和用法",
            raw_result='{"answer": "闭包是一个函数值，它引用了其外部作用域中的变量..."}',
        )
        memory.add_knowledge(k1)
        memory.add_knowledge(k2)
        print(f"\n  添加 2 条知识后:")
        print(f"    knowledge_chain: {len(memory.knowledge_chain)} 条")
        for k in memory.knowledge_chain:
            print(f"      {k.cite_id}: {k.tool_type} — {k.query[:40]}...")

        # 3.2 更新摘要（模拟 NoteAgent）
        memory.update_knowledge_summary(
            cite_id="[rag-1]",
            summary="装饰器是一种利用闭包特性的语法糖，本质上是接受函数作为参数并返回新函数的高阶函数。"
        )
        assert memory.knowledge_chain[0].summary != ""
        print(f"\n  更新摘要后:")
        print(f"    [rag-1] summary: {memory.knowledge_chain[0].summary[:50]}...")
        print("  ✅ update_knowledge_summary 通过")

        # 3.3 过滤查询
        rag_only = memory.get_available_knowledge(tool_types=["rag_naive"])
        assert len(rag_only) == 1
        assert rag_only[0].cite_id == "[rag-1]"
        print(f"\n  按 tool_type='rag_naive' 过滤: {len(rag_only)} 条")
        print("  ✅ get_available_knowledge 过滤通过")

        # 3.4 持久化
        memory.save()
        loaded = InvestigateMemory.load_or_create(
            output_dir=tmpdir,
            user_question="Python 中装饰器和闭包有什么区别？",
        )
        assert len(loaded.knowledge_chain) == 2
        assert loaded.knowledge_chain[0].summary != ""
        print(f"\n  持久化验证:")
        print(f"    保存路径: {memory.file_path}")
        print(f"    加载后 knowledge_chain: {len(loaded.knowledge_chain)} 条")
        print(f"    加载后 summary 保留: {loaded.knowledge_chain[0].summary[:30]}...")
        print("  ✅ InvestigateMemory 持久化通过")

    # -------------------------------------------------------
    # Step 4: ToolCallRecord — 工具调用记录
    # -------------------------------------------------------
    print("\n--- Step 4: ToolCallRecord 工具调用记录 ---")

    record = ToolCallRecord(
        tool_type="code_execution",
        query="计算斐波那契数列前 10 项",
        cite_id="[code-1]",
    )

    print(f"  tool_type:  {record.tool_type}")
    print(f"  query:      {record.query}")
    print(f"  cite_id:    {record.cite_id}")
    print(f"  status:     {record.status}")
    print(f"  call_id:    {record.call_id}")

    # 状态流转：pending → running → success
    record.mark_running()
    assert record.status == "running"
    print(f"\n  mark_running 后: {record.status}")

    record.mark_result(
        raw_answer="[0, 1, 1, 2, 3, 5, 8, 13, 21, 34]",
        summary="斐波那契数列前 10 项为 [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]",
        status="success",
        metadata={"execution_time_ms": 15},
    )
    assert record.status == "success"
    assert record.raw_answer is not None
    assert record.metadata.get("execution_time_ms") == 15
    print(f"  mark_result 后: {record.status}")
    print(f"  raw_answer: {record.raw_answer[:40]}...")
    print(f"  metadata:   {record.metadata}")
    print("  ✅ ToolCallRecord 状态流转通过")

    # 序列化
    r_dict = record.to_dict()
    r_restored = ToolCallRecord.from_dict(r_dict)
    assert r_restored.status == "success"
    assert r_restored.call_id == record.call_id
    print("  ✅ ToolCallRecord 序列化 / 反序列化通过")

    # -------------------------------------------------------
    # Step 5: SolveChainStep — 步骤链
    # -------------------------------------------------------
    print("\n--- Step 5: SolveChainStep 步骤链 ---")

    step = SolveChainStep(
        step_id="S1",
        step_target="分析 Python 装饰器的执行顺序",
        available_cite=["[rag-1]", "[rag-2]"],
    )

    print(f"  step_id:       {step.step_id}")
    print(f"  step_target:   {step.step_target}")
    print(f"  status:        {step.status}")
    print(f"  available_cite: {step.available_cite}")
    print(f"  tool_calls:    {len(step.tool_calls)} 条")

    # 状态流转：undone → in_progress（通过 append_tool_call）
    step.append_tool_call(record)
    assert step.status == "in_progress"
    print(f"\n  append_tool_call 后:")
    print(f"    status:     {step.status}")
    print(f"    tool_calls: {len(step.tool_calls)} 条")

    # → waiting_response
    step.mark_waiting_response()
    assert step.status == "waiting_response"
    print(f"  mark_waiting_response 后: {step.status}")

    # → done（通过 update_response）
    step.update_response(
        response="装饰器按从内到外的顺序执行：首先执行最内层装饰器...",
        used_citations=["[rag-1]"],
    )
    assert step.status == "done"
    assert step.used_citations == ["[rag-1]"]
    print(f"  update_response 后: {step.status}")
    print(f"  used_citations: {step.used_citations}")
    print("  ✅ SolveChainStep 状态流转通过")

    # 序列化
    s_dict = step.to_dict()
    s_restored = SolveChainStep.from_dict(s_dict)
    assert s_restored.step_id == "S1"
    assert s_restored.status == "done"
    assert len(s_restored.tool_calls) == 1
    print("  ✅ SolveChainStep 序列化 / 反序列化通过")

    # -------------------------------------------------------
    # Step 6: SolveMemory — 完整求解记忆
    # -------------------------------------------------------
    print("\n--- Step 6: SolveMemory 完整求解记忆 ---")

    with tempfile.TemporaryDirectory() as tmpdir:
        sm = SolveMemory(
            task_id="test_solve_001",
            user_question="解释 Python 装饰器的执行顺序和闭包关系",
            output_dir=tmpdir,
        )

        print(f"  task_id:       {sm.task_id}")
        print(f"  user_question: {sm.user_question}")
        print(f"  version:       {sm.version}")

        # 6.1 创建步骤链
        steps = [
            SolveChainStep(
                step_id="S1",
                step_target="分析：理解 Python 闭包的作用域规则",
                available_cite=["[rag-1]"],
            ),
            SolveChainStep(
                step_id="S2",
                step_target="推导：从闭包推导装饰器的执行流程",
                available_cite=["[rag-1]", "[rag-2]"],
            ),
            SolveChainStep(
                step_id="S3",
                step_target="计算：编写代码验证多层装饰器的执行顺序",
                available_cite=[],
            ),
        ]
        sm.create_chains(steps)
        assert sm.metadata["total_steps"] == 3
        print(f"\n  创建 3 个步骤后:")
        print(f"    total_steps: {sm.metadata['total_steps']}")
        for s in sm.solve_chains:
            print(f"      {s.step_id}: {s.step_target[:40]}... [{s.status}]")

        # 6.2 追加工具调用
        tc = sm.append_tool_call(
            step_id="S1",
            tool_type="rag_naive",
            query="Python 闭包作用域 LEGB 规则",
            cite_id="[rag-3]",
        )
        print(f"\n  追加工具调用后:")
        print(f"    S1 status: {sm.get_step('S1').status}")  # → in_progress
        print(f"    call_id:   {tc.call_id}")
        assert sm.get_step("S1").status == "in_progress"

        # 6.3 更新工具结果
        sm.update_tool_call_result(
            step_id="S1",
            call_id=tc.call_id,
            raw_answer="LEGB 规则：Local → Enclosing → Global → Builtin...",
            summary="Python 的变量查找遵循 LEGB 规则，闭包利用 Enclosing 作用域捕获外层变量。",
        )
        updated_tc = sm.get_step("S1").tool_calls[0]
        assert updated_tc.status == "success"
        print(f"    更新结果后 status: {updated_tc.status}")
        print(f"    summary: {updated_tc.summary[:40]}...")

        # 6.4 标记等待响应
        sm.mark_step_waiting_response("S1")
        assert sm.get_step("S1").status == "waiting_response"
        print(f"\n  mark_step_waiting_response 后: {sm.get_step('S1').status}")

        # 6.5 提交步骤响应
        sm.submit_step_response(
            step_id="S1",
            response="Python 闭包通过 LEGB 规则中的 Enclosing 作用域捕获外层函数的变量...",
            used_citations=["[rag-1]", "[rag-3]"],
        )
        assert sm.get_step("S1").status == "done"
        assert sm.metadata["completed_steps"] == 1
        print(f"  submit_step_response 后: {sm.get_step('S1').status}")
        print(f"  completed_steps: {sm.metadata['completed_steps']}")

        # 6.6 获取当前步骤
        current = sm.get_current_step()
        assert current.step_id == "S2"
        print(f"\n  当前步骤: {current.step_id} — {current.step_target[:40]}...")

        # 6.7 摘要
        summary = sm.get_summary()
        print(f"\n  get_summary():")
        for line in summary.split("\n"):
            print(f"    {line}")

        # 6.8 持久化
        sm.save()
        sm_loaded = SolveMemory.load_or_create(
            output_dir=tmpdir,
            user_question="解释 Python 装饰器的执行顺序和闭包关系",
        )
        assert len(sm_loaded.solve_chains) == 3
        assert sm_loaded.get_step("S1").status == "done"
        assert len(sm_loaded.get_step("S1").tool_calls) == 1
        print(f"\n  持久化验证:")
        print(f"    保存路径: {sm.file_path}")
        print(f"    加载后 solve_chains: {len(sm_loaded.solve_chains)} 步")
        print(f"    加载后 S1 status: {sm_loaded.get_step('S1').status}")
        print("  ✅ SolveMemory 持久化通过")

        # 预览 JSON
        with open(sm.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"\n  JSON 结构预览:")
        print(f"    version:      {data['version']}")
        print(f"    task_id:      {data['task_id']}")
        print(f"    solve_chains: {len(data['solve_chains'])} 步")
        for s_data in data["solve_chains"]:
            print(f"      {s_data['step_id']}: [{s_data['status']}] tool_calls={len(s_data['tool_calls'])}")

    # -------------------------------------------------------
    # Step 7: CitationMemory — 引用记忆
    # -------------------------------------------------------
    print("\n--- Step 7: CitationMemory 引用记忆 ---")

    with tempfile.TemporaryDirectory() as tmpdir:
        cm = CitationMemory(output_dir=tmpdir)

        print(f"  version: {cm.version}")
        print(f"  citations: {len(cm.citations)} 条")

        # 7.1 添加引用（自动 cite_id 生成）
        cid1 = cm.add_citation(
            tool_type="rag_naive",
            query="Python 装饰器定义",
            raw_result="装饰器是一种高阶函数...",
            content="装饰器本质是接受函数作为参数的高阶函数",
            stage="analysis",
        )
        cid2 = cm.add_citation(
            tool_type="rag_hybrid",
            query="Python 闭包与装饰器的关系",
            raw_result="闭包是装饰器的底层实现机制...",
            content="闭包提供了装饰器保存外层函数状态的能力",
            stage="analysis",
        )
        cid3 = cm.add_citation(
            tool_type="code_execution",
            query="验证装饰器执行顺序",
            raw_result="output: inner → outer",
            content="多层装饰器从内到外依次包装，从外到内依次执行",
            stage="solve",
            step_id="S3",
        )
        cid4 = cm.add_citation(
            tool_type="web_search",
            query="Python PEP 318 decorator proposal",
            raw_result="PEP 318 introduced the @ syntax...",
            content="PEP 318 在 Python 2.4 中引入了 @decorator 语法",
            stage="solve",
        )

        print(f"\n  添加 4 条引用后:")
        for c in cm.citations:
            print(f"    {c.cite_id}: {c.tool_type} — {c.query[:30]}... [{c.stage}]")

        # 验证 cite_id 格式：[prefix-N]
        assert cid1 == "[rag-1]"
        assert cid2 == "[rag-2]"  # rag_hybrid 和 rag_naive 共享 rag 前缀
        assert cid3 == "[code-1]"
        assert cid4 == "[web-1]"
        print(f"\n  cite_id 生成规则验证:")
        print(f"    rag_naive  → {cid1}")
        print(f"    rag_hybrid → {cid2} (共享 'rag' 前缀)")
        print(f"    code_execution → {cid3}")
        print(f"    web_search → {cid4}")
        print("  ✅ cite_id 生成通过")

        # 7.2 查询引用
        c1 = cm.get_citation("[rag-1]")
        assert c1 is not None
        assert c1.query == "Python 装饰器定义"
        print(f"\n  get_citation('[rag-1]'): {c1.query}")

        rag_cites = cm.get_citations_by_tool_type("rag_naive")
        assert len(rag_cites) == 1
        print(f"  get_citations_by_tool_type('rag_naive'): {len(rag_cites)} 条")
        print("  ✅ 查询引用通过")

        # 7.3 更新引用
        cm.update_citation(
            cite_id="[rag-1]",
            content="更新后的摘要：装饰器是 Python 元编程的核心工具",
            source="知识库 ai_textbook",
        )
        updated = cm.get_citation("[rag-1]")
        assert updated.content.startswith("更新后的摘要")
        assert updated.source == "知识库 ai_textbook"
        print(f"\n  更新引用后:")
        print(f"    content: {updated.content[:30]}...")
        print(f"    source:  {updated.source}")
        print("  ✅ 更新引用通过")

        # 7.4 格式化为 Markdown
        md_all = cm.format_citations_markdown()
        print(f"\n  format_citations_markdown (全部):")
        for line in md_all.split("\n")[:8]:
            print(f"    {line}")
        if md_all.count("\n") > 8:
            print(f"    ... (共 {md_all.count(chr(10)) + 1} 行)")

        md_partial = cm.format_citations_markdown(used_cite_ids=["[rag-1]", "[code-1]"])
        assert "[rag-1]" in md_partial
        assert "[code-1]" in md_partial
        assert "[web-1]" not in md_partial
        print(f"\n  format_citations_markdown (部分 [rag-1],[code-1]):")
        for line in md_partial.split("\n")[:5]:
            print(f"    {line}")
        print("  ✅ Markdown 格式化通过")

        # 7.5 持久化
        cm.save()
        cm_loaded = CitationMemory.load_or_create(output_dir=tmpdir)
        assert len(cm_loaded.citations) == 4
        assert cm_loaded.tool_counters.get("rag") == 2
        assert cm_loaded.tool_counters.get("code") == 1
        assert cm_loaded.tool_counters.get("web") == 1
        print(f"\n  持久化验证:")
        print(f"    保存路径: {cm.file_path}")
        print(f"    加载后 citations: {len(cm_loaded.citations)} 条")
        print(f"    加载后 tool_counters: {cm_loaded.tool_counters}")

        # 持久化后继续添加，验证计数器正确递增
        cid5 = cm_loaded.add_citation(
            tool_type="rag_naive",
            query="Python 装饰器的最佳实践",
            content="使用 functools.wraps 保留元信息",
        )
        assert cid5 == "[rag-3]"
        print(f"    持久化后新增: {cid5} (计数器正确递增)")
        print("  ✅ CitationMemory 持久化通过")

        # 预览 JSON
        with open(cm.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"\n  JSON 结构预览:")
        print(f"    version:       {data['version']}")
        print(f"    citations:     {len(data['citations'])} 条")
        print(f"    tool_counters: {data['tool_counters']}")

    # -------------------------------------------------------
    # Step 8: 三种 Memory 协作模拟
    # -------------------------------------------------------
    print("\n--- Step 8: 三种 Memory 协作模拟 ---")
    print("  模拟场景: 用户问 'Python 生成器和迭代器的区别？'")

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1) 创建三种 Memory
        inv_mem = InvestigateMemory(
            user_question="Python 生成器和迭代器的区别？",
            output_dir=tmpdir,
        )
        cit_mem = CitationMemory(output_dir=tmpdir)
        sol_mem = SolveMemory(
            user_question="Python 生成器和迭代器的区别？",
            output_dir=tmpdir,
        )

        # 2) Analysis Loop — 模拟 InvestigateAgent 检索
        cite_id = cit_mem.add_citation(
            tool_type="rag_naive",
            query="Python 迭代器协议 __iter__ __next__",
            raw_result="迭代器协议要求对象实现 __iter__ 和 __next__ 方法...",
            stage="analysis",
        )
        inv_mem.add_knowledge(KnowledgeItem(
            cite_id=cite_id,
            tool_type="rag_naive",
            query="Python 迭代器协议 __iter__ __next__",
            raw_result="迭代器协议要求对象实现 __iter__ 和 __next__ 方法...",
        ))

        cite_id2 = cit_mem.add_citation(
            tool_type="rag_hybrid",
            query="Python yield 关键字生成器函数",
            raw_result="生成器函数使用 yield 关键字，每次调用 next() 时恢复执行...",
            stage="analysis",
        )
        inv_mem.add_knowledge(KnowledgeItem(
            cite_id=cite_id2,
            tool_type="rag_hybrid",
            query="Python yield 关键字生成器函数",
            raw_result="生成器函数使用 yield 关键字，每次调用 next() 时恢复执行...",
        ))

        # 模拟 NoteAgent 更新摘要
        inv_mem.update_knowledge_summary(cite_id, "迭代器是实现了 __iter__ 和 __next__ 协议的对象。")
        inv_mem.update_knowledge_summary(cite_id2, "生成器是使用 yield 的特殊函数，自动实现迭代器协议。")

        print(f"  Analysis Loop 完成:")
        print(f"    知识条目: {len(inv_mem.knowledge_chain)} 条")
        print(f"    引用条目: {len(cit_mem.citations)} 条")

        # 3) Solve Loop — 模拟 ManagerAgent 规划步骤
        sol_mem.create_chains([
            SolveChainStep(
                step_id="S1",
                step_target="分析：对比迭代器和生成器的核心区别",
                available_cite=[cite_id, cite_id2],
            ),
            SolveChainStep(
                step_id="S2",
                step_target="计算：编写代码演示两者的使用差异",
                available_cite=[],
            ),
        ])

        # 模拟 SolveAgent + ToolAgent
        tc = sol_mem.append_tool_call("S2", "code_execution", "编写迭代器和生成器的对比代码")
        code_cite = cit_mem.add_citation(
            tool_type="code_execution",
            query="编写迭代器和生成器的对比代码",
            raw_result="class Counter: ...\ndef counter_gen(): yield ...",
            content="自定义迭代器需要手动管理状态，生成器通过 yield 自动管理",
            stage="solve",
            step_id="S2",
        )
        sol_mem.update_tool_call_result(
            step_id="S2",
            call_id=tc.call_id,
            raw_answer="class Counter: ...\ndef counter_gen(): yield ...",
            summary="生成器是迭代器的语法糖，代码量减少约 60%",
        )

        # 标记完成
        for s in sol_mem.solve_chains:
            sol_mem.mark_step_waiting_response(s.step_id)
            sol_mem.submit_step_response(
                step_id=s.step_id,
                response=f"步骤 {s.step_id} 的回答内容...",
                used_citations=[cite_id],
            )

        print(f"\n  Solve Loop 完成:")
        print(f"    步骤数: {sol_mem.metadata['total_steps']}")
        print(f"    已完成: {sol_mem.metadata['completed_steps']}")
        print(f"    工具调用: {sol_mem.metadata['total_tool_calls']}")

        # 4) Final — 格式化引用
        used_ids = []
        for s in sol_mem.solve_chains:
            used_ids.extend(s.used_citations)
        used_ids = list(dict.fromkeys(used_ids))
        citations_md = cit_mem.format_citations_markdown(used_cite_ids=used_ids)
        print(f"\n  最终引用 Markdown:")
        for line in citations_md.split("\n")[:5]:
            print(f"    {line}")

        # 5) 全部保存
        inv_mem.save()
        cit_mem.save()
        sol_mem.save()

        # 验证文件
        assert (Path(tmpdir) / "investigate_memory.json").exists()
        assert (Path(tmpdir) / "citation_memory.json").exists()
        assert (Path(tmpdir) / "solve_chain.json").exists()
        print(f"\n  文件全部保存:")
        for f in sorted(Path(tmpdir).glob("*.json")):
            print(f"    {f.name} ({f.stat().st_size} bytes)")
        print("  ✅ 三种 Memory 协作通过")

    # -------------------------------------------------------
    # 总结
    # -------------------------------------------------------
    print("\n" + "=" * 60)
    print("Layer 1 测试完成! 所有 Memory 数据结构测试通过 ✅")
    print("=" * 60)
    print("\n关键发现:")
    print("  1. InvestigateMemory: 管理 KnowledgeItem 知识链，NoteAgent 通过 cite_id 更新摘要")
    print("  2. SolveMemory: 管理 SolveChainStep 步骤链，状态流转 undone→in_progress→waiting_response→done")
    print("  3. CitationMemory: cite_id 按工具类型前缀递增（rag_naive/rag_hybrid 共享 'rag' 前缀）")
    print("  4. 三种 Memory 在 Solve 流程中的协作：Analysis 产出知识 → Solve 消费知识 → Citation 统一引用")


if __name__ == "__main__":
    main()
