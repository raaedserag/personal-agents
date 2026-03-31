"""
LLM Client — Routes requests to Ollama (local) or Claude API (cloud).

Each agent declares its model config in agent.yaml. This client reads that
config and routes accordingly. Supports both streaming and non-streaming.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Generator

import requests


@dataclass
class ModelConfig:
    """Model configuration for a specific tier."""
    provider: str          # "ollama" or "anthropic"
    name: str              # e.g., "llama3.2" or "claude-sonnet-4-20250514"
    base_url: str = ""     # For Ollama
    api_key: str = ""      # For Anthropic


@dataclass
class LLMClientConfig:
    """Full LLM config with default and heavy tiers."""
    default: ModelConfig = field(default_factory=lambda: ModelConfig(
        provider="ollama",
        name="llama3.2",
        base_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"),
    ))
    heavy: ModelConfig = field(default_factory=lambda: ModelConfig(
        provider="anthropic",
        name="claude-sonnet-4-20250514",
        api_key=os.getenv("ANTHROPIC_API_KEY", ""),
    ))

    @classmethod
    def from_yaml(cls, model_config: dict) -> LLMClientConfig:
        """Build from the 'model' section of agent.yaml."""
        config = cls()
        if "default" in model_config:
            d = model_config["default"]
            config.default = ModelConfig(
                provider=d.get("provider", "ollama"),
                name=d.get("name", "llama3.2"),
                base_url=d.get("base_url", os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")),
            )
        if "heavy" in model_config:
            h = model_config["heavy"]
            config.heavy = ModelConfig(
                provider=h.get("provider", "anthropic"),
                name=h.get("name", "claude-sonnet-4-20250514"),
                api_key=h.get("api_key", os.getenv("ANTHROPIC_API_KEY", "")),
            )
        return config


class LLMClient:
    """
    Unified LLM client that routes to the right provider.

    Usage:
        client = LLMClient(config)
        response = client.complete(messages, task_type="default")
        # or for streaming:
        for token in client.stream(messages, task_type="default"):
            print(token, end="")
    """

    def __init__(self, config: LLMClientConfig | None = None):
        self.config = config or LLMClientConfig()

    def _get_model(self, task_type: str) -> ModelConfig:
        if task_type == "heavy":
            return self.config.heavy
        return self.config.default

    def complete(
        self,
        messages: list[dict],
        task_type: str = "default",
        system_prompt: str = "",
        max_tokens: int = 4096,
        timeout: int = 120,
    ) -> str:
        """Non-streaming completion. Returns the full response text."""
        model = self._get_model(task_type)

        if model.provider == "ollama":
            return self._ollama_complete(model, messages, system_prompt, timeout)
        elif model.provider == "anthropic":
            return self._anthropic_complete(model, messages, system_prompt, max_tokens, timeout)
        else:
            raise ValueError(f"Unknown provider: {model.provider}")

    def stream(
        self,
        messages: list[dict],
        task_type: str = "default",
        system_prompt: str = "",
        max_tokens: int = 4096,
        timeout: int = 120,
    ) -> Generator[str, None, None]:
        """Streaming completion. Yields tokens as they arrive."""
        model = self._get_model(task_type)

        if model.provider == "ollama":
            yield from self._ollama_stream(model, messages, system_prompt, timeout)
        elif model.provider == "anthropic":
            yield from self._anthropic_stream(model, messages, system_prompt, max_tokens, timeout)
        else:
            raise ValueError(f"Unknown provider: {model.provider}")

    # ── Ollama ───────────────────────────────────────────────────

    def _ollama_complete(
        self, model: ModelConfig, messages: list[dict], system_prompt: str, timeout: int,
    ) -> str:
        all_messages = messages.copy()
        if system_prompt:
            all_messages = [{"role": "system", "content": system_prompt}] + all_messages

        try:
            resp = requests.post(
                f"{model.base_url}/api/chat",
                json={"model": model.name, "messages": all_messages, "stream": False},
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "")
        except requests.exceptions.ConnectionError:
            return f"[LLM Error] Cannot connect to Ollama at {model.base_url}"
        except requests.exceptions.Timeout:
            return f"[LLM Error] Ollama timed out after {timeout}s"
        except Exception as e:
            return f"[LLM Error] Ollama: {e}"

    def _ollama_stream(
        self, model: ModelConfig, messages: list[dict], system_prompt: str, timeout: int,
    ) -> Generator[str, None, None]:
        all_messages = messages.copy()
        if system_prompt:
            all_messages = [{"role": "system", "content": system_prompt}] + all_messages

        try:
            resp = requests.post(
                f"{model.base_url}/api/chat",
                json={"model": model.name, "messages": all_messages, "stream": True},
                timeout=timeout,
                stream=True,
            )
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line:
                    chunk = json.loads(line)
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if chunk.get("done"):
                        break
        except Exception as e:
            yield f"[LLM Error] Ollama streaming: {e}"

    # ── Anthropic (Claude) ───────────────────────────────────────

    def _anthropic_complete(
        self, model: ModelConfig, messages: list[dict], system_prompt: str,
        max_tokens: int, timeout: int,
    ) -> str:
        api_key = model.api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            return "[LLM Error] ANTHROPIC_API_KEY not configured"

        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }

        # Convert messages: filter out system messages (handled separately)
        api_messages = [m for m in messages if m["role"] != "system"]

        body: dict = {
            "model": model.name,
            "max_tokens": max_tokens,
            "messages": api_messages,
        }
        if system_prompt:
            body["system"] = system_prompt

        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=body,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            # Extract text from content blocks
            return "".join(
                block.get("text", "") for block in data.get("content", [])
                if block.get("type") == "text"
            )
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "unknown"
            detail = ""
            if e.response is not None:
                try:
                    detail = e.response.json().get("error", {}).get("message", "")
                except Exception:
                    detail = e.response.text[:300]
            return f"[LLM Error] Claude API HTTP {status}: {detail}"
        except Exception as e:
            return f"[LLM Error] Claude API: {e}"

    def _anthropic_stream(
        self, model: ModelConfig, messages: list[dict], system_prompt: str,
        max_tokens: int, timeout: int,
    ) -> Generator[str, None, None]:
        api_key = model.api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            yield "[LLM Error] ANTHROPIC_API_KEY not configured"
            return

        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }

        api_messages = [m for m in messages if m["role"] != "system"]

        body: dict = {
            "model": model.name,
            "max_tokens": max_tokens,
            "messages": api_messages,
            "stream": True,
        }
        if system_prompt:
            body["system"] = system_prompt

        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=body,
                timeout=timeout,
                stream=True,
            )
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                line_str = line.decode("utf-8")
                if not line_str.startswith("data: "):
                    continue
                data_str = line_str[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    event = json.loads(data_str)
                    if event.get("type") == "content_block_delta":
                        text = event.get("delta", {}).get("text", "")
                        if text:
                            yield text
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            yield f"[LLM Error] Claude streaming: {e}"


# ── Convenience function ─────────────────────────────────────────

_default_client: LLMClient | None = None


def get_llm_client(config: LLMClientConfig | None = None) -> LLMClient:
    """Get or create a singleton LLM client."""
    global _default_client
    if config is not None:
        _default_client = LLMClient(config)
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
