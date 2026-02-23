#!/usr/bin/env python
"""
Layer 2: GenerateAgent 题目生成
=========================================
测试 GenerateAgent 的核心流程：
  1. 初始化（BaseAgent 配置 + Prompt 加载）
  2. 自定义模式：根据需求 + 知识上下文 + focus 生成题目
  3. Mimic 模式：基于参考题目生成类似题目
  4. JSON 解析辅助方法（_parse_question_response 等）

调用链路：
  GenerateAgent.__init__()
    → BaseAgent.__init__(module_name="question", agent_name="generate_agent")
      → PromptManager.load_prompts()  # 加载 prompts/zh/generate_agent.yaml
  GenerateAgent.process(requirement, knowledge_context, focus, reference_question)
    → 如果有 reference_question:
        → _generate_with_reference()  # mimic 模式
      否则:
        → _generate_custom()           # 自定义模式
      两者均：
        → self.get_prompt("system")
        → self.get_prompt("custom_generate" 或 "mimic_generate")
        → self.call_llm(user_prompt, system_prompt, response_format=json)
        → _parse_question_response(response)
          → _extract_json_from_markdown()  # 去除 ```json 包裹
          → _clean_json_string()           # 清理控制字符
          → _fix_common_json_issues()      # 修复常见 JSON 错误
          → json.loads() → 题目 dict

输入：需求 dict + 知识上下文 + 可选 focus/reference
输出：{success, question: {question_type, question, options, correct_answer, explanation, knowledge_point}}
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


# -------------------------------------------------------
# 测试数据
# -------------------------------------------------------
# 模拟题目生成需求
MOCK_REQUIREMENT = {
    "knowledge_point": "JavaScript 闭包",
    "difficulty": "medium",
    "question_type": "choice",
}

# 模拟检索到的知识上下文（硬编码，避免依赖 RetrieveAgent）
MOCK_KNOWLEDGE_CONTEXT = """
=== Query: 闭包 ===
闭包（Closure）是指一个函数能够记住并访问其词法作用域（lexical scope），即使该函数在其词法作用域之外执行。
闭包是由函数及其关联的引用环境组合而成的实体。

闭包的关键特性：
1. 函数嵌套：内部函数可以访问外部函数的变量
2. 变量持久化：外部函数返回后，其局部变量不会被销毁
3. 作用域链：内部函数沿着作用域链查找变量

示例：
function createCounter() {
    let count = 0;
    return function() {
        return ++count;
    };
}
const counter = createCounter();
counter(); // 1
counter(); // 2

=== Query: 作用域链 ===
JavaScript 使用词法作用域（静态作用域），变量的作用域在编写代码时就确定了。
作用域链是指当访问一个变量时，JavaScript 引擎会从当前作用域开始，
逐级向上查找父级作用域，直到找到该变量或到达全局作用域。

=== Query: 变量捕获 ===
闭包捕获变量的方式是通过引用（by reference），而非通过值（by value）。
这意味着如果被捕获的变量发生变化，闭包内访问到的值也会改变。

经典陷阱：for 循环中的闭包
for (var i = 0; i < 3; i++) {
    setTimeout(function() { console.log(i); }, 100);
}
// 输出: 3, 3, 3（而非 0, 1, 2）

解决方案：使用 let 或 IIFE
for (let i = 0; i < 3; i++) {
    setTimeout(function() { console.log(i); }, 100);
}
// 输出: 0, 1, 2
"""

# 模拟 focus（通常由 coordinator 的 plan 阶段生成）
MOCK_FOCUS = {
    "id": "q_1",
    "focus": "闭包在 for 循环中的变量捕获陷阱",
    "type": "choice",
}

# 模拟参考题目（用于 mimic 模式测试）
MOCK_REFERENCE_QUESTION = """
下列代码的输出结果是什么？
```javascript
var funcs = [];
for (var i = 0; i < 3; i++) {
    funcs.push(function() { return i; });
}
console.log(funcs[0]());
```
A. 0
B. 1
C. 2
D. 3
答案：D
"""


async def main():
    print("=" * 60)
    print("Layer 2: GenerateAgent 题目生成测试")
    print("=" * 60)

    # -------------------------------------------------------
    # Step 1: 初始化 GenerateAgent
    # -------------------------------------------------------
    print("\n--- Step 1: 初始化 GenerateAgent ---")

    from src.agents.question.agents.generate_agent import GenerateAgent
    from src.services.llm import get_llm_config

    llm_config = get_llm_config()
    agent = GenerateAgent(
        language="zh",
        api_key=llm_config.api_key,
        base_url=llm_config.base_url,
        api_version=getattr(llm_config, "api_version", None),
    )

    print(f"  module_name:  {agent.module_name}")
    print(f"  agent_name:   {agent.agent_name}")
    print(f"  language:     {agent.language}")
    print(f"  model:        {agent.get_model()}")
    print(f"  temperature:  {agent.get_temperature()}")
    print(f"  max_tokens:   {agent.get_max_tokens()}")

    # -------------------------------------------------------
    # Step 2: 检查 Prompt 加载
    # -------------------------------------------------------
    print("\n--- Step 2: 检查 Prompt 加载 ---")

    print(f"  has_prompts:  {agent.has_prompts()}")
    print(f"  prompts keys: {list(agent.prompts.keys()) if agent.prompts else 'None'}")

    system_prompt = agent.get_prompt("system")
    if system_prompt:
        print(f"  system prompt 长度: {len(system_prompt)} chars")
        print(f"  system prompt 预览: {system_prompt[:120]}...")
    else:
        print(f"  ❌ system prompt 未加载!")

    # 检查自定义模式 prompt
    custom_prompt = agent.get_prompt("custom_generate")
    if custom_prompt:
        print(f"  custom_generate 长度: {len(custom_prompt)} chars")
    else:
        print(f"  ⚠️ custom_generate 未加载（可能使用其他 key）")

    # 检查 mimic 模式 prompt
    mimic_prompt = agent.get_prompt("mimic_generate")
    if mimic_prompt:
        print(f"  mimic_generate 长度: {len(mimic_prompt)} chars")
    else:
        print(f"  ⚠️ mimic_generate 未加载（可能使用其他 key）")

    # 列出所有可用 prompt keys
    if agent.prompts:
        print(f"  所有 prompt keys: {list(agent.prompts.keys())}")

    # -------------------------------------------------------
    # Step 3: 测试 JSON 解析辅助方法
    # -------------------------------------------------------
    print("\n--- Step 3: 测试 JSON 解析辅助方法 ---")

    # 3a: _extract_json_from_markdown
    print("\n  [3a] _extract_json_from_markdown:")
    test_cases = [
        ("带 ```json 包裹", '```json\n{"question": "test"}\n```'),
        ("带 ``` 包裹", '```\n{"question": "test"}\n```'),
        ("裸 JSON", '{"question": "test"}'),
        ("混合文本 + JSON", '这是一个题目：\n```json\n{"question": "test"}\n```\n完毕'),
    ]
    for name, text in test_cases:
        result = agent._extract_json_from_markdown(text)
        print(f"    {name}: {result[:60]}...")

    # 3b: _clean_json_string
    print("\n  [3b] _clean_json_string:")
    dirty = '{"q": "含控制字符\x00\x01的文本"}'
    clean = agent._clean_json_string(dirty)
    print(f"    清理前: {repr(dirty[:40])}")
    print(f"    清理后: {repr(clean[:40])}")

    # 3c: _fix_common_json_issues
    print("\n  [3c] _fix_common_json_issues:")
    broken_json = '{"a": 1, "b": 2,}'  # 末尾多余逗号
    fixed = agent._fix_common_json_issues(broken_json)
    print(f"    修复前: {broken_json}")
    print(f"    修复后: {fixed}")

    # -------------------------------------------------------
    # Step 4: 自定义模式生成题目（不带 reference）
    # -------------------------------------------------------
    print("\n--- Step 4: 自定义模式生成题目 ---")
    print(f"  需求: {MOCK_REQUIREMENT}")
    print(f"  focus: {MOCK_FOCUS}")
    print(f"  知识上下文长度: {len(MOCK_KNOWLEDGE_CONTEXT)} chars")
    print(f"  正在调用 LLM 生成题目...")

    try:
        result = await agent.process(
            requirement=MOCK_REQUIREMENT,
            knowledge_context=MOCK_KNOWLEDGE_CONTEXT,
            focus=MOCK_FOCUS,
            reference_question=None,   # 自定义模式
        )

        print(f"\n  ✅ 生成完成!")
        print(f"  success: {result['success']}")

        if result["success"]:
            question = result["question"]
            print(f"\n  --- 生成的题目 ---")
            print(f"  题型:   {question.get('question_type', 'N/A')}")
            print(f"  题目:   {question.get('question', '')[:200]}")

            if question.get("options"):
                print(f"  选项:")
                for key, value in question["options"].items():
                    print(f"    {key}. {value}")

            print(f"  正确答案: {question.get('correct_answer', 'N/A')}")
            print(f"  解释:   {question.get('explanation', '')[:200]}...")
            print(f"  知识点: {question.get('knowledge_point', 'N/A')}")
        else:
            print(f"  ❌ 生成失败: {result.get('error', 'Unknown')}")

    except Exception as e:
        print(f"  ❌ 生成异常: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 5: Mimic 模式生成题目（带 reference）
    # -------------------------------------------------------
    print("\n--- Step 5: Mimic 模式生成题目（带参考题目）---")
    print(f"  参考题目预览: {MOCK_REFERENCE_QUESTION[:100]}...")
    print(f"  正在调用 LLM 基于参考题目生成类似题目...")

    try:
        result_mimic = await agent.process(
            requirement=MOCK_REQUIREMENT,
            knowledge_context=MOCK_KNOWLEDGE_CONTEXT,
            focus=None,                    # mimic 模式通常不需要 focus
            reference_question=MOCK_REFERENCE_QUESTION,
        )

        print(f"\n  ✅ 生成完成!")
        print(f"  success: {result_mimic['success']}")

        if result_mimic["success"]:
            question = result_mimic["question"]
            print(f"\n  --- Mimic 生成的题目 ---")
            print(f"  题型:   {question.get('question_type', 'N/A')}")
            print(f"  题目:   {question.get('question', '')[:200]}")

            if question.get("options"):
                print(f"  选项:")
                for key, value in question["options"].items():
                    print(f"    {key}. {value}")

            print(f"  正确答案: {question.get('correct_answer', 'N/A')}")
            print(f"  解释:   {question.get('explanation', '')[:200]}...")
        else:
            print(f"  ❌ 生成失败: {result_mimic.get('error', 'Unknown')}")

    except Exception as e:
        print(f"  ❌ 生成异常: {e}")
        import traceback
        traceback.print_exc()

    # -------------------------------------------------------
    # Step 6: Token 统计
    # -------------------------------------------------------
    print("\n--- Step 6: Token 统计 ---")

    from src.agents.base_agent import BaseAgent
    stats = BaseAgent.get_stats("question")
    print(f"  总调用次数:   {len(stats.calls)}")
    print(f"  总输入 tokens: {stats.total_prompt_tokens}")
    print(f"  总输出 tokens: {stats.total_completion_tokens}")
    print(f"  总费用:       ${stats.total_cost:.4f}")

    print("\n" + "=" * 60)
    print("Layer 2 测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
