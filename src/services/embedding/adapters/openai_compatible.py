# -*- coding: utf-8 -*-
"""OpenAI-compatible embedding adapter for OpenAI, Azure, HuggingFace, LM Studio, etc."""

import logging
from typing import Any, Dict

import httpx

from .base import BaseEmbeddingAdapter, EmbeddingRequest, EmbeddingResponse

logger = logging.getLogger(__name__)


class OpenAICompatibleEmbeddingAdapter(BaseEmbeddingAdapter):
    MODELS_INFO = {
        "text-embedding-3-large": {"default": 3072, "dimensions": [256, 512, 1024, 3072]},
        "text-embedding-3-small": {"default": 1536, "dimensions": [512, 1536]},
        "text-embedding-ada-002": 1536,
    }

    # 缓存不支持自定义维度的模型名称，避免重复尝试
    _models_without_custom_dims: set = set()

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_version:
            headers["api-key"] = self.api_key
        else:
            headers["Authorization"] = f"Bearer {self.api_key}"

        model_name = request.model or self.model
        payload = {
            "input": request.texts,
            "model": model_name,
            "encoding_format": request.encoding_format or "float",
        }

        # 如果模型已知不支持自定义维度，则不发送 dimensions 参数
        dims_value = request.dimensions or self.dimensions
        should_send_dims = dims_value and model_name not in self._models_without_custom_dims

        if should_send_dims:
            payload["dimensions"] = dims_value

        url = f"{self.base_url.rstrip('/')}/embeddings"
        if self.api_version:
            if "?" not in url:
                url += f"?api-version={self.api_version}"
            else:
                url += f"&api-version={self.api_version}"

        logger.debug(f"Sending embedding request to {url} with {len(request.texts)} texts")

        # 由于外网代理导致无法访问局域网代理，因此需要禁用代理
        async with httpx.AsyncClient(timeout=self.request_timeout, proxy=None) as client:
            response = await client.post(url, json=payload, headers=headers)

            # 如果返回 400 且是因为不支持自定义维度，则去掉 dimensions 参数重试
            if response.status_code == 400 and should_send_dims:
                error_text = response.text.lower()
                if "matryoshka" in error_text or "dimensions" in error_text:
                    logger.warning(
                        f"模型 '{model_name}' 不支持自定义维度，将去掉 dimensions 参数重试"
                    )
                    # 记住该模型不支持自定义维度，后续请求直接跳过
                    self._models_without_custom_dims.add(model_name)
                    payload.pop("dimensions", None)
                    response = await client.post(url, json=payload, headers=headers)

            if response.status_code >= 400:
                logger.error(f"HTTP {response.status_code} response body: {response.text}")

            response.raise_for_status()
            data = response.json()

        embeddings = [item["embedding"] for item in data["data"]]

        actual_dims = len(embeddings[0]) if embeddings else 0
        expected_dims = request.dimensions or self.dimensions

        if expected_dims and actual_dims != expected_dims:
            logger.warning(
                f"Dimension mismatch: expected {expected_dims}, got {actual_dims}. "
                f"Model '{data['model']}' may not support custom dimensions."
            )

        logger.info(
            f"Successfully generated {len(embeddings)} embeddings "
            f"(model: {data['model']}, dimensions: {actual_dims})"
        )

        return EmbeddingResponse(
            embeddings=embeddings,
            model=data["model"],
            dimensions=actual_dims,
            usage=data.get("usage", {}),
        )

    def get_model_info(self) -> Dict[str, Any]:
        model_info = self.MODELS_INFO.get(self.model, self.dimensions)

        if isinstance(model_info, dict):
            return {
                "model": self.model,
                "dimensions": model_info.get("default", self.dimensions),
                "supported_dimensions": model_info.get("dimensions", []),
                "supports_variable_dimensions": len(model_info.get("dimensions", [])) > 1,
                "provider": "openai_compatible",
            }
        else:
            return {
                "model": self.model,
                "dimensions": model_info or self.dimensions,
                "supports_variable_dimensions": False,
                "provider": "openai_compatible",
            }
