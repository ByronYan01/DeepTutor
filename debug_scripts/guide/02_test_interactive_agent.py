#!/usr/bin/env python
"""
Layer 2: InteractiveAgent 交互式 HTML 页面生成
=========================================
测试 InteractiveAgent 的核心流程：
  1. 初始化（BaseAgent 配置 + Prompt 加载）
  2. 根据知识点信息生成交互式 HTML 学习页面
  3. HTML 提取与验证（_extract_html, _validate_html）
  4. 降级处理（_generate_fallback_html）
  5. Bug 修复模式（retry_with_bug）

调用链路：
  InteractiveAgent.__init__()
    → BaseAgent.__init__(module_name="guide", agent_name="interactive_agent")
      → PromptManager.load_prompts()  # 加载 prompts/zh/interactive_agent.yaml
                                       # 这个 prompt 非常长（627行），包含大量 HTML 模板指南
  InteractiveAgent.process(knowledge, retry_with_bug=None)
    → self.get_prompt("system")          # 交互式教学设计师角色
    → self.get_prompt("user_template")   # 知识点 → HTML 的任务模板
    → user_template.format(knowledge_title=..., knowledge_summary=..., user_difficulty=...)
    → self.call_llm(user_prompt, system_prompt)
    → _extract_html(response)            # 从 LLM 响应中提取 HTML（regex: ```html...```)
    → _validate_html(html)               # 验证 HTML 基本结构（<html>, <body>, <div>等）
    → 如果验证失败 → _generate_fallback_html(knowledge)  # 生成降级 HTML

输入：知识点 dict {knowledge_title, knowledge_summary, user_difficulty}
输出：{success, html, is_fallback}
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env", override=False)


# -------------------------------------------------------
# 测试数据：模拟知识点（通常由 LocateAgent 输出）
# -------------------------------------------------------
MOCK_KNOWLEDGE = {
    "knowledge_title": "监督学习与无监督学习",
    "knowledge_summary": (
        "监督学习是一种机器学习方法，通过使用带标签的训练数据来学习输入到输出的映射关系。"
        "常见的监督学习算法包括线性回归、逻辑回归、决策树、支持向量机和神经网络。\n\n"
        "无监督学习则使用没有标签的数据，模型需要自己发现数据中的模式和结构。"
        "常见算法包括 K-Means 聚类、层次聚类、PCA 降维和自编码器。\n\n"
        "两者的核心区别在于：监督学习有明确的「正确答案」用于指导学习，"
        "而无监督学习需要自主发现数据中的隐藏结构。"
    ),
    "user_difficulty": (
        "用户可能难以理解：\n"
        "1. 为什么需要标签？标签的作用是什么？\n"
        "2. 无监督学习如何评估模型好坏（没有标签作为参考）？\n"
        "3. 何时选择监督学习，何时选择无监督学习？"
    ),
}


async def main():
    print("=" * 60)
    print("Layer 2: InteractiveAgent HTML 页面生成测试")
    print("=" * 60)

    # -------------------------------------------------------
    # Step 1: 初始化 InteractiveAgent
    # -------------------------------------------------------
    print("\n--- Step 1: 初始化 InteractiveAgent ---")

    from src.agents.guide.agents.interactive_agent import InteractiveAgent
    from src.services.llm import get_llm_config

    llm_config = get_llm_config()
    agent = InteractiveAgent(
        api_key=llm_config.api_key,
        base_url=llm_config.base_url,
        language="zh",
        api_version=getattr(llm_config, "api_version", None),
        binding=llm_config.binding,
    )

    print(f"  module_name:  {agent.module_name}")
    print(f"  agent_name:   {agent.agent_name}")
    print(f"  language:     {agent.language}")
    print(f"  model:        {agent.get_model()}")
    print(f"  temperature:  {agent.get_temperature()}")
    print(f"  max_tokens:   {agent.get_max_tokens()}")

    # -------------------------------------------------------
    # Step 2: 检查 Prompt（这个 prompt 非常长，包含大量模板）
    # -------------------------------------------------------
    print("\n--- Step 2: 检查 Prompt 加载 ---")

    print(f"  has_prompts:  {agent.has_prompts()}")
    print(f"  prompts keys: {list(agent.prompts.keys()) if agent.prompts else 'None'}")

    system_prompt = agent.get_prompt("system")
    if system_prompt:
        print(f"  system prompt 长度: {len(system_prompt)} chars （注意：这是最长的 prompt）")
        # 统计包含的 HTML 模板数量
        template_count = system_prompt.count("## 模板")
        print(f"  包含 HTML 模板数: {template_count} 个")
        print(f"  system prompt 预览: {system_prompt[:120]}...")
    else:
        print(f"  ❌ system prompt 未加载!")

    user_template = agent.get_prompt("user_template")
    if user_template:
        print(f"  user_template 长度: {len(user_template)} chars")
    else:
        print(f"  ❌ user_template 未加载!")

    # -------------------------------------------------------
    # Step 3: 测试内部辅助方法
    # -------------------------------------------------------
    print("\n--- Step 3: 测试辅助方法 ---")

    # 3a: _extract_html - 从 LLM 响应中提取 HTML
    print("\n  [3a] _extract_html 测试:")

    test_responses = [
        ('带 ```html 包裹', '```html\n<html><body>Hello</body></html>\n```'),
        ('带 ``` 包裹', '```\n<!DOCTYPE html><html><body>Hi</body></html>\n```'),
        ('裸 HTML', '<!DOCTYPE html>\n<html><body>Bare</body></html>'),
        ('纯文本', 'This is not HTML at all'),
    ]

    for name, resp in test_responses:
        extracted = agent._extract_html(resp)
        print(f"    {name}: {extracted[:60]}...")

    # 3b: _validate_html - 验证 HTML 基本结构
    print("\n  [3b] _validate_html 测试:")

    test_htmls = [
        ('有效 HTML', '<html><body><div>content</div></body></html>'),
        ('DOCTYPE HTML', '<!DOCTYPE html><html><body></body></html>'),
        ('只有 div', '<div>simple content</div>'),
        ('纯文本', 'not html'),
    ]

    for name, html in test_htmls:
        valid = agent._validate_html(html)
        print(f"    {name}: {'✅ 有效' if valid else '❌ 无效'}")

    # 3c: _generate_fallback_html - 降级 HTML
    print("\n  [3c] _generate_fallback_html 测试:")

    fallback = agent._generate_fallback_html(MOCK_KNOWLEDGE)
    print(f"    降级 HTML 长度: {len(fallback)} chars")
    print(f"    包含标题: {'监督学习' in fallback}")
    print(f"    包含 KaTeX: {'katex' in fallback.lower()}")

    # -------------------------------------------------------
    # Step 4: 调用 process() 完整流程（调用 LLM 生成 HTML）
    # -------------------------------------------------------
    print("\n--- Step 4: 调用 InteractiveAgent.process() ---")
    print(f"  知识点: {MOCK_KNOWLEDGE['knowledge_title']}")
    print(f"  正在调用 LLM 生成交互式 HTML...")

    try:
        result = await agent.process(knowledge=MOCK_KNOWLEDGE)

        print(f"\n  ✅ 生成完成!")
        print(f"  success:     {result['success']}")
        print(f"  is_fallback: {result.get('is_fallback', 'N/A')}")
        print(f"  HTML 长度:   {len(result.get('html', ''))} chars")

        html = result.get("html", "")
        if html:
            # 分析 HTML 结构
            print(f"\n  --- HTML 结构分析 ---")
            print(f"    包含 <!DOCTYPE>: {'<!doctype' in html.lower() or '<!DOCTYPE' in html}")
            print(f"    包含 <style>:    {'<style' in html.lower()}")
            print(f"    包含 <script>:   {'<script' in html.lower()}")
            print(f"    包含交互元素:    {'addEventListener' in html or 'onclick' in html}")
            print(f"    包含知识标题:    {'监督学习' in html}")

            # 保存 HTML 到文件方便查看
            output_dir = project_root / "data" / "debug_output"
            output_dir.mkdir(parents=True, exist_ok=True)
            html_path = output_dir / "guide_interactive_test.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"\n  📄 HTML 已保存到: {html_path}")
            print(f"     可在浏览器中打开查看效果")

    except Exception as e:
        print(f"  ❌ 生成失败: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 5: Token 统计
    # -------------------------------------------------------
    print("\n--- Step 5: Token 统计 ---")

    from src.agents.base_agent import BaseAgent
    stats = BaseAgent.get_stats("guide")
    print(f"  总调用次数:   {len(stats.calls)}")
    print(f"  总输入 tokens: {stats.total_prompt_tokens}")
    print(f"  总输出 tokens: {stats.total_completion_tokens}")
    print(f"  总费用:       ${stats.total_cost:.4f}")
    print(f"  （注意：InteractiveAgent 的 prompt 很长，输入 token 消耗较大）")

    print("\n" + "=" * 60)
    print("Layer 2 测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
