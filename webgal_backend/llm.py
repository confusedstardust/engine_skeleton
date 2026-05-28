from __future__ import annotations

import json
import copy
import re
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings
from .storage import read_json


class LLMError(RuntimeError):
    pass


class OpenAIFunctionClient:
    def __init__(self, trace_dir: Path | None = None) -> None:
        if not settings.llm_api_key:
            raise LLMError("DEEPSEEK_API_KEY is not set")
        self.trace_dir = trace_dir
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

    def call_text(
        self,
        trace_name: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        if settings.llm_api_mode == "chat":
            return self._call_chat_text(trace_name, system_prompt, user_prompt)
        return self._call_responses_text(trace_name, system_prompt, user_prompt)

    def parse_json_text(self, text: str, trace_name: str) -> dict[str, Any]:
        parsed = self._parse_function_arguments(self._strip_markdown_json_fence(text), trace_name)
        if hasattr(self, "trace_dir"):
            self._write_parsed_trace(trace_name, parsed)
        return parsed

    def _find_tool(self, function_name: str) -> dict[str, Any]:
        for tool in self.tools:
            fn = tool.get("function", {})
            if fn.get("name") == function_name:
                return tool
        raise LLMError(f"unknown function tool: {function_name}")

    def _request(self, path: str, payload: dict[str, Any], function_name: str) -> dict[str, Any]:
        base_url = settings.llm_base_url
        if "api.deepseek.com" in base_url and not base_url.endswith("/beta"):
            base_url = f"{base_url}/beta"
        url = f"{base_url}{path}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        trace: dict[str, Any] = {
            "at": datetime.now(timezone.utc).isoformat(),
            "function_name": function_name,
            "api_mode": settings.llm_api_mode,
            "url": url,
            "request": payload,
        }
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
                result = json.loads(response.read().decode("utf-8"))
                trace["response"] = result
                self._write_trace(function_name, trace)
                return result
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            trace["error"] = {"type": "HTTPError", "status": exc.code, "body": body}
            self._write_trace(function_name, trace)
            raise LLMError(f"LLM API error {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            trace["error"] = {"type": "URLError", "reason": str(exc)}
            self._write_trace(function_name, trace)
            raise LLMError(f"LLM API network error: {exc}") from exc

    def _write_trace(self, function_name: str, trace: dict[str, Any]) -> None:
        if not self.trace_dir:
            return
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        index = len(list(self.trace_dir.glob("*.json"))) + 1
        safe_name = re.sub(r"[^a-zA-Z0-9_]+", "_", function_name).strip("_") or "llm"
        path = self.trace_dir / f"{index:04d}_{safe_name}.json"
        path.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _responses_tool(self, chat_tool: dict[str, Any]) -> dict[str, Any]:
        fn = chat_tool["function"]
        return {
            "type": "function",
            "name": fn["name"],
            "description": fn.get("description", ""),
            "parameters": self._provider_schema(fn["parameters"]),
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
        }
        self._apply_max_tokens(payload, "max_output_tokens")
        self._apply_deepseek_thinking(payload)
        data = self._request("/responses", payload, function_name)
        for item in data.get("output", []):
            if item.get("type") == "function_call" and item.get("name") == function_name:
                if item.get("status") == "incomplete":
                    raise LLMError(
                        f"{function_name} output was truncated; increase WEBGAL_MAX_TOKENS"
                    )
                parsed = self._parse_function_arguments(item.get("arguments"), function_name)
                self._write_parsed_trace(function_name, parsed)
                return parsed
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
        }
        self._apply_max_tokens(payload, "max_tokens")
        self._apply_deepseek_thinking(payload)
        data = self._request("/chat/completions", payload, function_name)
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
                parsed = self._parse_function_arguments(fn.get("arguments"), function_name)
                self._write_parsed_trace(function_name, parsed)
                return parsed
        raise LLMError(f"model did not call required function: {function_name}")

    def _call_chat_text(self, trace_name: str, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        self._apply_max_tokens(payload, "max_tokens")
        self._apply_deepseek_thinking(payload)
        data = self._request("/chat/completions", payload, trace_name)
        choice = data["choices"][0]
        if choice.get("finish_reason") == "length":
            raise LLMError(
                f"{trace_name} output was truncated (finish_reason=length); increase WEBGAL_MAX_TOKENS"
            )
        content = choice["message"].get("content") or ""
        if not content.strip():
            raise LLMError(f"{trace_name} returned empty text")
        self._write_text_trace(trace_name, content)
        return content

    def _call_responses_text(self, trace_name: str, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": settings.llm_model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        self._apply_max_tokens(payload, "max_output_tokens")
        self._apply_deepseek_thinking(payload)
        data = self._request("/responses", payload, trace_name)
        chunks: list[str] = []
        for item in data.get("output", []):
            if item.get("status") == "incomplete":
                raise LLMError(f"{trace_name} output was truncated; increase WEBGAL_MAX_TOKENS")
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"}:
                    chunks.append(content.get("text", ""))
        text = "\n".join(chunk for chunk in chunks if chunk).strip()
        if not text:
            raise LLMError(f"{trace_name} returned empty text")
        self._write_text_trace(trace_name, text)
        return text

    def _write_parsed_trace(self, function_name: str, parsed_arguments: dict[str, Any]) -> None:
        if not self.trace_dir:
            return
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        traces = sorted(self.trace_dir.glob("*.json"))
        if not traces:
            return
        path = traces[-1]
        trace = json.loads(path.read_text(encoding="utf-8"))
        trace["parsed_arguments"] = parsed_arguments
        path.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _write_text_trace(self, trace_name: str, text: str) -> None:
        if not self.trace_dir:
            return
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        traces = sorted(self.trace_dir.glob("*.json"))
        if not traces:
            return
        path = traces[-1]
        trace = json.loads(path.read_text(encoding="utf-8"))
        if trace.get("function_name") != trace_name:
            return
        trace["text_output"] = text
        path.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _strip_markdown_json_fence(self, text: str) -> str:
        stripped = text.strip()
        if not stripped.startswith("```"):
            return stripped
        lines = stripped.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()

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

        repaired_text = self._escape_unescaped_quotes_in_json_strings(text)
        if repaired_text != text:
            try:
                parsed = json.loads(repaired_text)
                if isinstance(parsed, dict):
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
            repaired_object_text = self._escape_unescaped_quotes_in_json_strings(object_text)
            if repaired_object_text != object_text:
                try:
                    parsed = json.loads(repaired_object_text)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass

        preview = re.sub(r"\s+", " ", text[:500])
        raise LLMError(f"{function_name} returned invalid JSON arguments: {preview}")

    def _escape_unescaped_quotes_in_json_strings(self, text: str) -> str:
        result: list[str] = []
        in_string = False
        escaped = False

        for index, char in enumerate(text):
            if not in_string:
                result.append(char)
                if char == '"':
                    in_string = True
                    escaped = False
                continue

            if escaped:
                result.append(char)
                escaped = False
                continue
            if char == "\\":
                result.append(char)
                escaped = True
                continue
            if char == '"':
                next_non_space = self._next_non_space(text, index + 1)
                if next_non_space in {":", ",", "}", "]", ""}:
                    result.append(char)
                    in_string = False
                else:
                    result.append('\\"')
                continue
            result.append(char)

        return "".join(result)

    def _next_non_space(self, text: str, start: int) -> str:
        for char in text[start:]:
            if not char.isspace():
                return char
        return ""

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
        function = dict(tool["function"])
        function["parameters"] = self._provider_schema(function["parameters"])
        return {"type": "function", "function": function}

    def _provider_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        if "deepseek.com" not in settings.llm_base_url:
            return schema
        return _deepseek_compatible_schema(schema)

    def _apply_deepseek_thinking(self, payload: dict[str, Any]) -> None:
        if "deepseek.com" not in settings.llm_base_url:
            return
        if settings.llm_thinking not in {"enabled", "disabled"}:
            return
        payload["thinking"] = {"type": settings.llm_thinking}
        if settings.llm_thinking == "enabled" and settings.llm_reasoning_effort in {"high", "max", "low", "medium", "xhigh"}:
            payload["reasoning_effort"] = settings.llm_reasoning_effort

    def _apply_max_tokens(self, payload: dict[str, Any], field_name: str) -> None:
        if settings.llm_max_tokens is not None:
            payload[field_name] = settings.llm_max_tokens


def false_json() -> bool:
    return False


def _deepseek_compatible_schema(value: Any) -> Any:
    unsupported = {"minLength", "maxLength", "minItems", "maxItems", "$schema", "$id", "title"}
    if isinstance(value, list):
        return [_deepseek_compatible_schema(item) for item in value]
    if not isinstance(value, dict):
        return value

    result = {}
    for key, item in value.items():
        if key in unsupported:
            continue
        if key == "type" and isinstance(item, list):
            non_null = [schema_type for schema_type in item if schema_type != "null"]
            if non_null:
                result[key] = non_null[0]
            continue
        if key == "$defs":
            result["$def"] = _deepseek_compatible_schema(item)
            continue
        if key == "$ref" and isinstance(item, str):
            result[key] = item.replace("#/$defs/", "#/$def/")
            continue
        result[key] = _deepseek_compatible_schema(item)
    if result.get("type") == "object":
        properties = result.get("properties")
        if isinstance(properties, dict):
            result["required"] = list(properties)
            result["additionalProperties"] = False
    return copy.deepcopy(result)
