"""
大模型适配层。

目标：换厂商只改配置，节点代码一行不动。
新增一个厂商 = 写一个子类 + 注册，约 30 行。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    text: str
    usage: dict[str, Any] = field(default_factory=dict)
    raw: Any = None


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def complete(
        self,
        *,
        model: str,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """执行一次文本生成。"""


class MockLLMProvider(LLMProvider):
    """
    离线测试用：不发网络请求、不花钱。

    responses 可按 prompt 关键字定制，命中就返回对应文本，否则回显提示词，
    这样离线也能把分支、变量渲染、并发全部跑通。
    """

    name = "mock"

    def __init__(self, responses: dict[str, str] | None = None, default: str | None = None):
        self.responses = responses or {}
        self.default = default
        self.calls: list[dict[str, Any]] = []

    async def complete(self, *, model, prompt, temperature=0.7, max_tokens=1024) -> LLMResponse:
        self.calls.append({"model": model, "prompt": prompt, "temperature": temperature})
        for keyword, text in self.responses.items():
            if keyword in prompt:
                return LLMResponse(text=text, usage={"prompt_tokens": len(prompt),
                                                     "completion_tokens": len(text),
                                                     "model": model})
        reply = self.default if self.default is not None else f"[mock 回复] {prompt[:80]}"
        return LLMResponse(text=reply, usage={"prompt_tokens": len(prompt),
                                              "completion_tokens": len(reply),
                                              "model": model})


class OpenAIProvider(LLMProvider):
    """OpenAI 兼容接口。依赖延迟导入，没装 SDK 也不影响其它模块。"""

    name = "openai"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key
        self.base_url = base_url
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("使用 openai provider 前请先安装：pip install openai") from exc
            self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    async def complete(self, *, model, prompt, temperature=0.7, max_tokens=1024) -> LLMResponse:
        resp = await self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = resp.choices[0].message.content or ""
        usage = {
            "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
            "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
            "total_tokens": resp.usage.total_tokens if resp.usage else 0,
            "model": model,
        }
        return LLMResponse(text=text, usage=usage, raw=resp)


PROVIDER_REGISTRY: dict[str, type[LLMProvider]] = {
    MockLLMProvider.name: MockLLMProvider,
    OpenAIProvider.name: OpenAIProvider,
}


def get_provider(name: str = "mock", **kwargs) -> LLMProvider:
    if name not in PROVIDER_REGISTRY:
        raise ValueError(f"未注册的 provider: {name}，可选 {list(PROVIDER_REGISTRY)}")
    return PROVIDER_REGISTRY[name](**kwargs)
