#!/usr/bin/env python
"""Tests for request-model resolution priority in BaseAgent and factory."""

import asyncio

from src.services.llm.config import LLMConfig
from src.services.llm.model_context import ModelContext, use_model_context
from src.agents.base_agent import BaseAgent
import src.services.llm.factory as llm_factory


class _DummyAgent(BaseAgent):
    def __init__(self):
        super().__init__(module_name="test", agent_name="dummy")

    async def process(self, *args, **kwargs):  # pragma: no cover - not used in tests
        return "ok"


def test_base_agent_prefers_request_model(monkeypatch):
    """Request context model should override config-level model selection."""

    monkeypatch.setattr(
        "src.agents.base_agent.get_llm_config",
        lambda: LLMConfig(model="global-model", api_key="k", base_url="http://x", binding="openai"),
    )

    agent = _DummyAgent()

    # Without request context, agent should use normal resolved model
    assert agent.get_model() == "global-model"

    # With request context, context model should win
    with use_model_context(ModelContext(request_id="req-1", request_model="request-model", source="test")):
        assert agent.get_model() == "request-model"


def test_factory_prefers_request_model_when_model_arg_missing(monkeypatch):
    """Factory complete should read request model from context when model arg is None."""

    captured = {}

    async def _fake_complete(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(llm_factory.cloud_provider, "complete", _fake_complete)
    monkeypatch.setattr(llm_factory, "_should_use_local", lambda base_url: False)
    monkeypatch.setattr(
        llm_factory,
        "get_llm_config",
        lambda: LLMConfig(model="global-model", api_key="k", base_url="http://x", binding="openai"),
    )

    async def _run():
        with use_model_context(
            ModelContext(request_id="req-2", request_model="request-model", source="test")
        ):
            return await llm_factory.complete(prompt="hi", system_prompt="sys")

    result = asyncio.run(_run())

    assert result == "ok"
    assert captured.get("model") == "request-model"
