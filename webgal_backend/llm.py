from __future__ import annotations

import json
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .config import settings
from .storage import read_json


class LLMError(RuntimeError):
    pass


class OpenAIFunctionClient:
    def __init__(self) -> None:
        if not settings.llm_api_key:
            raise LLMError("DEEPSEEK_API_KEY is not set")
        self.tools_path = settings.skill_dir / "references" / "openai-tools.built.json"
        self.source_tools_path = settings.skill_dir / "references" / "openai-tools.json"
        self.builder_path = settings.skill_dir / "scripts" / "build_openai_tools.py"
        self._ensure_built_tools()
        self.tools = read_json(self.tools_path)["tools"]

    def _ensure_built_tools(self) -> None:
        if not self.source_tools_path.exists():
            raise LLMError(f"missing tool source: {self.source_tools_path}")
        import sys
        subprocess.run(
            [sys.executable, str(self.builder_path), str(self.source_tools_path), str(self.tools_path)],
            check=True,
            cwd=str(settings.skill_dir.parent),
            capture_output=True,
            text=True,
        )

    def call_function(
        self,
        function_name: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        tool = self._find_tool(function_name)
        if settings.llm_api_mode == "chat":
            return self._call_chat(function_name, tool, system_prompt, user_prompt)
        return self._call_responses(function_name, tool, system_prompt, user_prompt)

    def _find_tool(self, function_name: str) -> dict[str, Any]:
        for tool in self.tools:
            fn = tool.get("function", {})
            if fn.get("name") == function_name:
                return tool
        raise LLMError(f"unknown function tool: {function_name}")

    def _request(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{settings.llm_base_url}{path}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"LLM API error {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"LLM API network error: {exc}") from exc

    def _responses_tool(self, chat_tool: dict[str, Any]) -> dict[str, Any]:
        fn = chat_tool["function"]
        return {
            "type": "function",
            "name": fn["name"],
            "description": fn.get("description", ""),
            "parameters": fn["parameters"],
            "strict": bool(fn.get("strict", True)),
        }

    def _call_responses(
        self,
        function_name: str,
        tool: dict[str, Any],
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        payload = {
            "model": settings.llm_model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "tools": [self._responses_tool(tool)],
            "tool_choice": {"type": "function", "name": function_name},
            "parallel_tool_calls": false_json(),
            "max_output_tokens": settings.llm_max_tokens,
        }
        data = self._request("/responses", payload)
        for item in data.get("output", []):
            if item.get("type") == "function_call" and item.get("name") == function_name:
                if item.get("status") == "incomplete":
                    raise LLMError(
                        f"{function_name} output was truncated; increase WEBGAL_MAX_TOKENS"
                    )
                return self._parse_function_arguments(item.get("arguments"), function_name)
        raise LLMError(f"model did not call required function: {function_name}")

    def _call_chat(
        self,
        function_name: str,
        tool: dict[str, Any],
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        payload = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "tools": [self._chat_tool(tool)],
            "tool_choice": {"type": "function", "function": {"name": function_name}},
            "max_tokens": settings.llm_max_tokens,
        }
        data = self._request("/chat/completions", payload)
        choice = data["choices"][0]
        if choice.get("finish_reason") == "length":
            raise LLMError(
                f"{function_name} output was truncated (finish_reason=length); "
                "keep text fields concise or increase WEBGAL_MAX_TOKENS"
            )
        message = choice["message"]
        for call in message.get("tool_calls", []):
            fn = call.get("function", {})
            if fn.get("name") == function_name:
                return self._parse_function_arguments(fn.get("arguments"), function_name)
        raise LLMError(f"model did not call required function: {function_name}")

    def _parse_function_arguments(self, raw_arguments: Any, function_name: str) -> dict[str, Any]:
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if raw_arguments is None:
            return {}

        text = str(raw_arguments).strip()
        if not text:
            return {}

        try:
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise LLMError(f"{function_name} arguments must be a JSON object")
            return parsed
        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()
        try:
            parsed, _end = decoder.raw_decode(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        object_text = self._first_balanced_json_object(text)
        if object_text:
            try:
                parsed = json.loads(object_text)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        preview = re.sub(r"\s+", " ", text[:500])
        raise LLMError(f"{function_name} returned invalid JSON arguments: {preview}")

    def _first_balanced_json_object(self, text: str) -> str | None:
        start = text.find("{")
        if start < 0:
            return None

        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        return None

    def _chat_tool(self, tool: dict[str, Any]) -> dict[str, Any]:
        """Return a Chat Completions tool compatible with OpenAI-style providers.

        DeepSeek's OpenAI-compatible endpoint accepts function tools, but some
        compatible providers reject OpenAI's `strict` extension. We keep the
        JSON Schema parameters and enforce strictness locally after the call.
        """
        if "deepseek.com" not in settings.llm_base_url:
            return tool
        function = dict(tool["function"])
        function.pop("strict", None)
        return {"type": "function", "function": function}


def false_json() -> bool:
    return False
