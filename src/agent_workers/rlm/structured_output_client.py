"""Structured output client abstraction (Slice 5.1)."""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

from agent_control.model_router import ResolvedEndpoint
from agent_workers.rlm.completion import chat_completion

logger = logging.getLogger(__name__)

ProviderName = Literal["native_ollama_schema", "instructor_ollama"]


def structured_output_provider_name() -> str:
    return os.environ.get("STRUCTURED_OUTPUT_PROVIDER", "native_ollama_schema").strip()


class StructuredOutputClient:
  """Provider adapter for official-engine completions.

  Instructor may improve generation, but callers must still run Pydantic validation,
  premerge, and normalizers on the returned text.
  """

  def __init__(self, provider: str | None = None) -> None:
      requested = provider or structured_output_provider_name()
      self.provider: ProviderName
      if requested == "instructor_ollama":
          self.provider = "instructor_ollama" if self._instructor_available() else "native_ollama_schema"
          if self.provider != "instructor_ollama":
              logger.warning(
                  "STRUCTURED_OUTPUT_PROVIDER=instructor_ollama unavailable; "
                  "falling back to native_ollama_schema"
              )
      else:
          self.provider = "native_ollama_schema"

  @staticmethod
  def _instructor_available() -> bool:
      try:
          import instructor  # noqa: F401

          return True
      except ImportError:
          return False

  def complete(
      self,
      *,
      endpoint: ResolvedEndpoint,
      system_prompt: str,
      user_prompt: str,
      response_format: dict[str, Any] | str | None,
      timeout_seconds: float,
      max_tokens: int = 2048,
  ) -> dict[str, Any]:
      if self.provider == "instructor_ollama":
          return self._complete_instructor(
              endpoint=endpoint,
              system_prompt=system_prompt,
              user_prompt=user_prompt,
              response_format=response_format,
              timeout_seconds=timeout_seconds,
              max_tokens=max_tokens,
          )
      return self._complete_native(
          endpoint=endpoint,
          system_prompt=system_prompt,
          user_prompt=user_prompt,
          response_format=response_format,
          timeout_seconds=timeout_seconds,
          max_tokens=max_tokens,
      )

  def _complete_native(
      self,
      *,
      endpoint: ResolvedEndpoint,
      system_prompt: str,
      user_prompt: str,
      response_format: dict[str, Any] | str | None,
      timeout_seconds: float,
      max_tokens: int,
  ) -> dict[str, Any]:
      result = chat_completion(
          endpoint,
          system_prompt=system_prompt,
          user_prompt=user_prompt,
          max_tokens=max_tokens,
          timeout_seconds=timeout_seconds,
          response_format=response_format,
          stream=False,
      )
      result["structured_output_provider"] = "native_ollama_schema"
      return result

  def _complete_instructor(
      self,
      *,
      endpoint: ResolvedEndpoint,
      system_prompt: str,
      user_prompt: str,
      response_format: dict[str, Any] | str | None,
      timeout_seconds: float,
      max_tokens: int,
  ) -> dict[str, Any]:
      try:
          import instructor
          from openai import OpenAI
      except ImportError:
          return self._complete_native(
              endpoint=endpoint,
              system_prompt=system_prompt,
              user_prompt=user_prompt,
              response_format=response_format,
              timeout_seconds=timeout_seconds,
              max_tokens=max_tokens,
          )

      base = endpoint.base_url.rstrip("/")
      if base.endswith("/v1"):
          base = base[:-3]
      client = instructor.from_openai(
          OpenAI(base_url=f"{base}/v1", api_key=endpoint.api_key or "ollama"),
          mode=instructor.Mode.JSON,
      )
      messages = [
          {"role": "system", "content": system_prompt},
          {"role": "user", "content": user_prompt},
      ]
      response = client.chat.completions.create(
          model=endpoint.model or "llama3",
          messages=messages,
          max_tokens=max_tokens,
          timeout=timeout_seconds,
          response_model=None,
      )
      content = response.choices[0].message.content or ""
      return {
          "content": content,
          "model": endpoint.model,
          "provider": endpoint.provider,
          "base_url": endpoint.base_url,
          "usage": {},
          "structured_output_provider": "instructor_ollama",
          "response_format_mode": (
              "schema" if isinstance(response_format, dict) else response_format or "none"
          ),
      }
