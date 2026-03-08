# -*- coding: utf-8 -*-
"""
Request-level model context for LLM calls.

This module provides coroutine-safe request context storage (ContextVar)
for per-request model selection without parameter threading.
"""

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass
class ModelContext:
    """Request-scoped model context."""

    request_id: str | None = None
    request_model: str | None = None
    source: str = "request"


_model_context_var: ContextVar[ModelContext | None] = ContextVar("model_context", default=None)


def get_model_context() -> ModelContext | None:
    """Get current request model context."""
    return _model_context_var.get()


def set_model_context(context: ModelContext) -> Token:
    """Set request model context and return token for reset."""
    return _model_context_var.set(context)


def reset_model_context(token: Token) -> None:
    """Reset request model context by token."""
    _model_context_var.reset(token)


@contextmanager
def use_model_context(context: ModelContext):
    """Context manager for temporary request model context."""
    token = set_model_context(context)
    try:
        yield context
    finally:
        reset_model_context(token)
