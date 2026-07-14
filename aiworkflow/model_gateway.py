from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from .config import ModelConfig
from .errors import ModelGatewayError


@dataclass(slots=True)
class ModelResponse:
    content: str
    model: str


class ModelClient:
    def complete(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        raise NotImplementedError


class MockModelClient(ModelClient):
    def __init__(self, model_name: str = "mock"):
        self.model_name = model_name

    def complete(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        content = (
            "# Mock AI Diff\n\n"
            "```diff\n"
            "--- a/README.md\n"
            "+++ b/README.md\n"
            "@@\n"
            "+ AI workflow mock change placeholder.\n"
            "```\n\n"
            "## 说明\n"
            "这是 mock 模型输出，用于验证工作流、图谱检索、上下文组装和校验闭环。\n"
        )
        return ModelResponse(content=content, model=self.model_name)


class OpenAICompatibleModelClient(ModelClient):
    def __init__(self, config: ModelConfig):
        self.config = config
        if not config.base_url:
            raise ModelGatewayError("MODEL_BASE_URL 未配置。")
        if not config.api_key:
            raise ModelGatewayError("MODEL_API_KEY 未配置。")

    def complete(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        endpoint = self.config.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise ModelGatewayError(f"模型网关 HTTP {exc.code}: {body}") from exc
        except Exception as exc:  # noqa: BLE001
            raise ModelGatewayError(f"模型网关调用失败: {exc}") from exc
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelGatewayError(f"模型网关返回格式不符合 OpenAI-compatible 协议: {data}") from exc
        return ModelResponse(content=str(content), model=self.config.model)


def make_model_client(config: ModelConfig, force_mock: bool = False) -> ModelClient:
    if force_mock or config.model.lower().startswith("mock"):
        return MockModelClient(config.model)
    return OpenAICompatibleModelClient(config)
