#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
JSON Utils - JSON parsing and validation utilities
- Robustly extract JSON from LLM text output
- Provide strict structure validation and error messages
"""

import json
import re
from typing import Any, Dict, Iterable, List, Union


def _strip_outer_single_quotes(text: str) -> str:
    """Remove one layer of surrounding single quotes: '...json...'."""
    stripped = text.strip()
    if len(stripped) >= 2 and stripped[0] == "'" and stripped[-1] == "'":
        return stripped[1:-1]
    return stripped


def _escape_unescaped_double_quotes(text: str) -> str:
    """
    Escape likely-unescaped double quotes inside JSON string literals.
    This targets values like: {"k":"RAG+"system"}.
    """
    out: List[str] = []
    in_string = False
    escaped = False
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]
        if not in_string:
            out.append(ch)
            if ch == '"':
                in_string = True
            i += 1
            continue

        if escaped:
            out.append(ch)
            escaped = False
            i += 1
            continue

        if ch == "\\":
            out.append(ch)
            escaped = True
            i += 1
            continue

        if ch == '"':
            # If next non-space token is a JSON delimiter, treat as closing quote.
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            nxt = text[j] if j < n else ""
            if nxt in [",", "}", "]", ":"] or j >= n:
                out.append(ch)
                in_string = False
            else:
                out.append('\\"')
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)


# JSON 合法的单字符转义序列集合
_VALID_ESCAPES = set('"\\/ b f n r t')


def _escape_invalid_backslashes(text: str) -> str:
    """
    修复 JSON 字符串值内的非法反斜杠序列。
    适用场景：LLM 在 JSON 字符串中嵌入 LaTeX 公式，
    如 \\sum、\\alpha、\\frac 等，这些在 JSON 规范中均为非法转义。
    合法的单字符 JSON 转义：\\" \\\\ \\/ \\b \\f \\n \\r \\t \\uXXXX。
    """
    out: List[str] = []
    in_string = False
    escaped = False
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]
        if not in_string:
            out.append(ch)
            if ch == '"':
                in_string = True
            i += 1
            continue

        if escaped:
            # 检查该转义序列是否合法
            if ch in _VALID_ESCAPES:
                # 合法转义，保持不变
                out.append(ch)
            elif ch == 'u' and i + 4 < n and text[i + 1:i + 5].isalnum():
                # \uXXXX 形式，保持不变
                out.append(ch)
            else:
                # 非法转义：补一个反斜杠将其变为 \\x
                out.append('\\')
                out.append(ch)
            escaped = False
            i += 1
            continue

        if ch == '\\':
            out.append(ch)
            escaped = True
            i += 1
            continue

        if ch == '"':
            in_string = False
        out.append(ch)
        i += 1

    return "".join(out)


def _loads_with_repair(text: str) -> Union[Dict[str, Any], List[Any], None]:
    """Parse JSON with a conservative one-pass repair fallback."""
    candidate = text.strip()
    if not candidate:
        return None

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    candidate = _strip_outer_single_quotes(candidate)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    repaired = _escape_unescaped_double_quotes(candidate)
    if repaired != candidate:
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

    # 修复非法反斜杠（如 LaTeX 公式中的 \sum、\alpha 等）
    repaired2 = _escape_invalid_backslashes(candidate)
    if repaired2 != candidate:
        try:
            return json.loads(repaired2)
        except json.JSONDecodeError:
            pass

    # 组合修复：先修双引号，再修反斜杠
    repaired3 = _escape_invalid_backslashes(repaired)
    if repaired3 != repaired and repaired3 != repaired2:
        try:
            return json.loads(repaired3)
        except json.JSONDecodeError:
            pass

    return None


def extract_json_from_text(text: str) -> Union[Dict[str, Any], List[Any], None]:
    """
    Extract JSON object or array from text.
    Allows the following formats:
    1) Pure JSON text
    2) Code blocks wrapped in ```json ...``` or ``` ...```
    3) First JSON fragment {...} or [...] contained in text
    """
    if not text:
        return None

    # 1) Code block
    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if code_block:
        snippet = code_block.group(1).strip()
        parsed = _loads_with_repair(snippet)
        if parsed is not None:
            return parsed

    # 2) Parse entire text
    parsed = _loads_with_repair(text)
    if parsed is not None:
        return parsed

    # 3) Fragment parsing
    obj_match = re.search(r"\{[\s\S]*\}", text)
    if obj_match:
        parsed = _loads_with_repair(obj_match.group(0))
        if parsed is not None:
            return parsed

    arr_match = re.search(r"\[[\s\S]*\]", text)
    if arr_match:
        parsed = _loads_with_repair(arr_match.group(0))
        if parsed is not None:
            return parsed

    return None


# --------- Strict Validation Utilities ---------


def ensure_json_dict(data: Any, err: str = "Expected JSON object") -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(err)
    return data


def ensure_json_list(data: Any, err: str = "Expected JSON array") -> List[Any]:
    if not isinstance(data, list):
        raise ValueError(err)
    return data


def ensure_keys(data: Dict[str, Any], keys: Iterable[str]) -> Dict[str, Any]:
    missing = [k for k in keys if k not in data]
    if missing:
        raise KeyError(f"Missing required keys: {', '.join(missing)}")
    return data


def safe_json_loads(text: str, default: Any = None) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default


def json_to_text(data: Any, indent: int = 2) -> str:
    return json.dumps(data, ensure_ascii=False, indent=indent)


__all__ = [
    "extract_json_from_text",
    "ensure_json_dict",
    "ensure_json_list",
    "ensure_keys",
    "safe_json_loads",
    "json_to_text",
]

