#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Prompt Budget Manager for Research module.

Provides stage-aware + model-aware input budget calculation and token-based
single-text truncation for prompt safety.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from .token_tracker import count_tokens_with_tiktoken

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class PromptBudgetConfig:
    """Resolved prompt budget configuration for a single stage/model."""

    context_window_tokens: int = 0
    reserved_output_tokens: int = 2048
    safety_margin_tokens: int = 1024
    char_per_token_fallback: float = 4.0


class PromptBudgetManager:
    """Compute prompt budgets and truncate text to budget."""

    DEFAULTS = PromptBudgetConfig()
    MIN_INPUT_BUDGET_TOKENS = 128

    def __init__(self, config: dict[str, Any] | None = None):
        research_cfg = (config or {}).get("research", {})
        token_budget_cfg = research_cfg.get("token_budget", {})
        self._token_budget_cfg = token_budget_cfg if isinstance(token_budget_cfg, dict) else {}

    def get_budget(self, stage: str, model: str | None = None) -> int:
        """Return available input budget (tokens) after output/margin reservation."""
        cfg, source = self._resolve_config_with_source(stage=stage, model=model)
        budget = cfg.context_window_tokens - cfg.reserved_output_tokens - cfg.safety_margin_tokens
        final_budget = max(self.MIN_INPUT_BUDGET_TOKENS, budget)
        logger.debug(
            "prompt_budget model=%s stage=%s source=%s context_window=%d reserved_output=%d safety_margin=%d final_budget=%d",
            model or "",
            stage,
            source,
            cfg.context_window_tokens,
            cfg.reserved_output_tokens,
            cfg.safety_margin_tokens,
            final_budget,
        )
        return final_budget

    def truncate_text_to_budget(
        self,
        text: str,
        budget_tokens: int,
        model: str | None = None,
        suffix: str = "",
    ) -> str:
        """Truncate a single text to fit into `budget_tokens` (token-based)."""
        if not text:
            return text

        token_budget = max(1, int(budget_tokens))
        current_tokens = self._count_tokens(text, model=model)
        if current_tokens <= token_budget:
            return text

        tail = suffix or ""
        tail_tokens = self._count_tokens(tail, model=model) if tail else 0

        if tail_tokens >= token_budget:
            return self._truncate_core(tail, budget_tokens=token_budget, model=model)

        core_budget = token_budget - tail_tokens
        core_text = self._truncate_core(text, budget_tokens=core_budget, model=model)
        return f"{core_text}{tail}"

    def _resolve_config(self, stage: str, model: str | None = None) -> PromptBudgetConfig:
        """Resolve effective budget config."""
        resolved, _ = self._resolve_config_with_source(stage=stage, model=model)
        return resolved

    def _resolve_config_with_source(
        self, stage: str, model: str | None = None
    ) -> tuple[PromptBudgetConfig, str]:
        """Resolve effective budget config and indicate context-window source."""
        cfg = self._token_budget_cfg
        resolved = PromptBudgetConfig(
            context_window_tokens=self.DEFAULTS.context_window_tokens,
            reserved_output_tokens=self._safe_int(
                cfg.get("default_reserved_output_tokens"), self.DEFAULTS.reserved_output_tokens
            ),
            safety_margin_tokens=self._safe_int(
                cfg.get("default_safety_margin_tokens"), self.DEFAULTS.safety_margin_tokens
            ),
            char_per_token_fallback=self._safe_float(
                cfg.get("char_per_token_fallback"), self.DEFAULTS.char_per_token_fallback
            ),
        )

        stages = cfg.get("stages", {})
        if isinstance(stages, dict):
            stage_cfg = stages.get(stage)
            if isinstance(stage_cfg, dict):
                resolved = self._apply_override(resolved, stage_cfg)

        # LLM config (data/user/settings/llm_configs.json active config) can define
        # model-level context window and should take precedence when model matches.
        llm_context_window = self._get_active_llm_context_window(model)
        if not llm_context_window:
            raise ValueError(
                "Missing required LLM context_window_tokens in active LLM configuration. "
                "Please set it in Settings -> LLM."
            )

        resolved = PromptBudgetConfig(
            context_window_tokens=llm_context_window,
            reserved_output_tokens=resolved.reserved_output_tokens,
            safety_margin_tokens=resolved.safety_margin_tokens,
            char_per_token_fallback=resolved.char_per_token_fallback,
        )
        return resolved, "active_llm"

    @staticmethod
    def _get_active_llm_context_window(model: str | None = None) -> int | None:
        """
        Read context window from active LLM configuration.

        Applies only when:
        - active config has a valid positive context_window_tokens
        - model is not provided, or matches active config model (case-insensitive)
        """
        try:
            from src.services.config import get_active_llm_config

            active = get_active_llm_config() or {}
            configured_model = (active.get("model") or "").strip()
            if model and configured_model and configured_model.lower() != model.lower():
                return None

            value = active.get("context_window_tokens")
            if value is None:
                return None

            parsed = int(value)
            if parsed > 0:
                return parsed
        except Exception as e:
            logger.debug(f"Failed to read context window from active LLM config: {e}")

        return None

    def _count_tokens(self, text: str, model: str | None = None) -> int:
        """Count tokens with tiktoken first; fallback to chars/token estimation."""
        if not text:
            return 0

        if model:
            tiktoken_count = count_tokens_with_tiktoken(text, model)
            if tiktoken_count > 0:
                return tiktoken_count

        fallback_cfg = self._resolve_config(stage="default", model=model)
        chars_per_token = max(1.0, fallback_cfg.char_per_token_fallback)
        return max(1, int(len(text) / chars_per_token))

    def _truncate_core(self, text: str, budget_tokens: int, model: str | None = None) -> str:
        """Binary-search best character boundary that satisfies token budget."""
        if not text or budget_tokens <= 0:
            return ""

        if self._count_tokens(text, model=model) <= budget_tokens:
            return text

        low, high = 1, len(text)
        best = ""

        while low <= high:
            mid = (low + high) // 2
            candidate = text[:mid]
            candidate_tokens = self._count_tokens(candidate, model=model)

            if candidate_tokens <= budget_tokens:
                best = candidate
                low = mid + 1
            else:
                high = mid - 1

        return best.rstrip()

    @staticmethod
    def _apply_override(base: PromptBudgetConfig, override: dict[str, Any]) -> PromptBudgetConfig:
        """Apply partial override to a PromptBudgetConfig."""
        return PromptBudgetConfig(
            context_window_tokens=PromptBudgetManager._safe_int(
                override.get("context_window_tokens"), base.context_window_tokens
            ),
            reserved_output_tokens=PromptBudgetManager._safe_int(
                override.get("reserved_output_tokens"), base.reserved_output_tokens
            ),
            safety_margin_tokens=PromptBudgetManager._safe_int(
                override.get("safety_margin_tokens"), base.safety_margin_tokens
            ),
            char_per_token_fallback=PromptBudgetManager._safe_float(
                override.get("char_per_token_fallback"), base.char_per_token_fallback
            ),
        )

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default


__all__ = ["PromptBudgetConfig", "PromptBudgetManager"]
