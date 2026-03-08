#!/usr/bin/env python
"""Unit tests for request-level model context."""

from src.services.llm.model_context import (
    ModelContext,
    get_model_context,
    reset_model_context,
    set_model_context,
    use_model_context,
)


def test_set_and_reset_model_context():
    """set_model_context and reset_model_context should work as a pair."""
    # Ensure clean state
    assert get_model_context() is None

    token = set_model_context(ModelContext(request_id="req-1", request_model="gpt-x", source="test"))
    try:
        ctx = get_model_context()
        assert ctx is not None
        assert ctx.request_id == "req-1"
        assert ctx.request_model == "gpt-x"
        assert ctx.source == "test"
    finally:
        reset_model_context(token)

    assert get_model_context() is None


def test_use_model_context_manager():
    """use_model_context should auto-reset after context exits."""
    assert get_model_context() is None

    with use_model_context(ModelContext(request_id="req-2", request_model="claude-3", source="ctx_mgr")):
        ctx = get_model_context()
        assert ctx is not None
        assert ctx.request_id == "req-2"
        assert ctx.request_model == "claude-3"
        assert ctx.source == "ctx_mgr"

    assert get_model_context() is None
