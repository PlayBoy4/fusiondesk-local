"""Execute FusionDesk plans through connector adapters."""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


OPENROUTER_URL = os.environ.get("OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")
MODEL_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "registry" / "models.json"


DEFAULT_MODEL_PRIORITY = [
    "anthropic/claude-sonnet-4",
    "openai/gpt-4o",
    "google/gemini-2.5-flash",
    "openai/gpt-4o-mini",
]


def load_model_registry() -> dict[str, Any]:
    try:
        return json.loads(MODEL_REGISTRY_PATH.read_text())
    except Exception:
        return {
            "version": "fallback",
            "policy": "Fallback registry used because fusiondesk/registry/models.json could not be loaded.",
            "fallback_chain": list(DEFAULT_MODEL_PRIORITY),
            "models": [
                {
                    "label": model,
                    "seat": model,
                    "provider_model": model,
                    "status": "active",
                    "connector": "openrouter",
                    "aliases": [model],
                }
                for model in DEFAULT_MODEL_PRIORITY
            ],
        }


def model_registry_entries() -> list[dict[str, Any]]:
    return list(load_model_registry().get("models", []))


def model_registry_for_api() -> dict[str, Any]:
    registry = load_model_registry()
    return {
        "version": registry.get("version"),
        "policy": registry.get("policy"),
        "fallback_chain": active_fallback_chain(),
        "models": [
            {
                "label": item.get("label"),
                "seat": item.get("seat"),
                "provider_model": item.get("provider_model"),
                "status": item.get("status"),
                "connector": item.get("connector"),
            }
            for item in registry.get("models", [])
        ],
    }


def _model_lookup() -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for item in model_registry_entries():
        keys = [
            item.get("label"),
            item.get("seat"),
            item.get("provider_model"),
            *(item.get("aliases") or []),
        ]
        for key in keys:
            if key:
                lookup[str(key).casefold()] = item
    return lookup


def _is_executable_model(item: dict[str, Any]) -> bool:
    return item.get("status") == "active" and item.get("connector") == "openrouter" and bool(item.get("provider_model"))


def active_fallback_chain() -> list[str]:
    active = {
        item.get("provider_model")
        for item in model_registry_entries()
        if _is_executable_model(item)
    }
    chain = [
        model
        for model in load_model_registry().get("fallback_chain", DEFAULT_MODEL_PRIORITY)
        if model in active
    ]
    return chain or list(DEFAULT_MODEL_PRIORITY)


def resolve_executable_model(model: str) -> str | None:
    item = _model_lookup().get(str(model).casefold())
    if not item:
        return None
    if not _is_executable_model(item):
        return None
    return str(item["provider_model"])


MODEL_PRIORITY = active_fallback_chain()
MODEL_STATUS = {
    "available_models": list(MODEL_PRIORITY),
    "active_model": None,
    "failed_models": [],
    "fallback_chain": [],
    "skipped_models": [],
}


class ModelInvocationError(RuntimeError):
    def __init__(self, message: str, code: int | str | None = None):
        super().__init__(message)
        self.code = code


def model_status() -> dict[str, Any]:
    return {
        "available_models": list(active_fallback_chain()),
        "active_model": MODEL_STATUS["active_model"],
        "failed_models": list(MODEL_STATUS["failed_models"]),
        "fallback_chain": list(MODEL_STATUS["fallback_chain"]),
        "skipped_models": list(MODEL_STATUS["skipped_models"]),
    }


def reset_model_status() -> None:
    MODEL_STATUS["active_model"] = None
    MODEL_STATUS["failed_models"] = []
    MODEL_STATUS["fallback_chain"] = []
    MODEL_STATUS["skipped_models"] = []


def mark_model_attempt(model: str) -> None:
    print(f"[ModelAttempt] {model}", flush=True)
    MODEL_STATUS["fallback_chain"].append(model)


def mark_model_fail(model: str, error: Exception) -> None:
    code = getattr(error, "code", None) or _classify_error_code(str(error))
    print(f"[ModelFail] {code}", flush=True)
    if model not in MODEL_STATUS["failed_models"]:
        MODEL_STATUS["failed_models"].append(model)


def mark_model_fallback(model: str) -> None:
    print(f"[ModelFallback] {model}", flush=True)


def mark_model_success(model: str) -> None:
    print(f"[ModelSuccess] {model}", flush=True)
    MODEL_STATUS["active_model"] = model


def mark_model_skip(model: str) -> None:
    print(f"[ModelSkip] {model}", flush=True)
    if model not in MODEL_STATUS["skipped_models"]:
        MODEL_STATUS["skipped_models"].append(model)


def resolve_openrouter_model(model: str) -> str:
    resolved = resolve_executable_model(model)
    if not resolved:
        raise ModelInvocationError(f"Model is not active in registry: {model}", code="inactive_model")
    return resolved


def _classify_error_code(message: str) -> str:
    lowered = message.casefold()
    for code in ("404", "429", "401", "500", "502", "503", "504"):
        if code in lowered:
            return code
    if "timed out" in lowered or "timeout" in lowered:
        return "timeout"
    if "unavailable" in lowered or "no endpoints" in lowered:
        return "unavailable"
    return "error"


class ModelConnector(Protocol):
    def generate(self, *, model: str, messages: list[dict[str, str]], timeout: int) -> str:
        ...

    def stream_generate(self, *, model: str, messages: list[dict[str, str]], timeout: int):
        ...


@dataclass
class OpenRouterConnector:
    api_key: str | None = None
    url: str = OPENROUTER_URL

    def generate(self, *, model: str, messages: list[dict[str, str]], timeout: int) -> str:
        api_key = (self.api_key or os.environ.get("OPENROUTER_API_KEY") or "").strip()
        if api_key.casefold().startswith("bearer "):
            api_key = api_key.split(" ", 1)[1].strip()
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")

        provider_model = resolve_openrouter_model(model)
        payload = {
            "model": provider_model,
            "messages": messages,
            "stream": False,
        }
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://127.0.0.1:4899",
                "X-Title": "FusionDesk AI",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                data = json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ModelInvocationError(f"OpenRouter HTTP {exc.code}: {detail}", code=exc.code) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise ModelInvocationError(f"OpenRouter timed out: {exc}", code="timeout") from exc
        except urllib.error.URLError as exc:
            raise ModelInvocationError(f"OpenRouter unavailable: {exc}", code="unavailable") from exc

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("OpenRouter returned no choices")
        message = choices[0].get("message", {})
        text = str(message.get("content") or "").strip()
        if not text:
            raise ModelInvocationError("OpenRouter returned an empty response", code="empty")
        return text

    def stream_generate(self, *, model: str, messages: list[dict[str, str]], timeout: int):
        api_key = (self.api_key or os.environ.get("OPENROUTER_API_KEY") or "").strip()
        if api_key.casefold().startswith("bearer "):
            api_key = api_key.split(" ", 1)[1].strip()
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")

        provider_model = resolve_openrouter_model(model)
        payload = {
            "model": provider_model,
            "messages": messages,
            "stream": True,
        }
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://127.0.0.1:4899",
                "X-Title": "FusionDesk AI",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                for raw_line in res:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    delta = (chunk.get("choices") or [{}])[0].get("delta", {})
                    text = delta.get("content")
                    if text:
                        yield text
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ModelInvocationError(f"OpenRouter HTTP {exc.code}: {detail}", code=exc.code) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise ModelInvocationError(f"OpenRouter timed out: {exc}", code="timeout") from exc
        except urllib.error.URLError as exc:
            raise ModelInvocationError(f"OpenRouter unavailable: {exc}", code="unavailable") from exc


@dataclass
class ExecutionEngine:
    connectors: dict[str, ModelConnector]
    timeout_seconds: int = 60

    @classmethod
    def load(cls) -> "ExecutionEngine":
        return cls(connectors={"openrouter": OpenRouterConnector()})

    def execute(self, *, task: str, plan: dict[str, Any], memory_context: dict[str, Any] | None = None) -> dict[str, Any]:
        connectors = plan.get("connectors", [])
        if "openrouter" not in connectors:
            return {
                "ok": False,
                "message": "No executable model connector selected.",
                "answer": "",
                "plan": plan,
                "execution": {"attempts": [], "connector": None, "model": None},
            }

        messages = self._messages(task=task, plan=plan, memory_context=memory_context)
        reset_model_status()
        attempts = []
        last_error = ""
        for model in self._candidate_models(plan):
            attempt = {"connector": "openrouter", "model": model}
            try:
                mark_model_attempt(model)
                answer = self.connectors["openrouter"].generate(
                    model=model,
                    messages=messages,
                    timeout=self.timeout_seconds,
                )
                attempt["ok"] = True
                attempts.append(attempt)
                mark_model_success(model)
                return {
                    "ok": True,
                    "message": answer,
                    "answer": answer,
                    "plan": plan,
                    "execution": {
                        "connector": "openrouter",
                        "model": model,
                        "attempts": attempts,
                        "fallback_used": len(attempts) > 1,
                    },
                }
            except Exception as exc:
                last_error = str(exc)
                attempt["ok"] = False
                attempt["error"] = last_error
                attempts.append(attempt)
                mark_model_fail(model, exc)
                next_model = self._next_model(model, plan)
                if next_model:
                    mark_model_fallback(next_model)

        return {
            "ok": False,
            "message": f"FusionDesk execution failed: {last_error}",
            "answer": "",
            "plan": plan,
            "execution": {
                "connector": "openrouter",
                "model": None,
                "attempts": attempts,
                "fallback_used": len(attempts) > 1,
            },
        }

    def execute_stream(self, *, task: str, plan: dict[str, Any], memory_context: dict[str, Any] | None = None):
        connectors = plan.get("connectors", [])
        if "openrouter" not in connectors:
            yield {
                "type": "error",
                "message": "No executable model connector selected.",
                "execution": {"attempts": [], "connector": None, "model": None},
            }
            return

        messages = self._messages(task=task, plan=plan, memory_context=memory_context)
        reset_model_status()
        attempts = []
        last_error = ""
        for model in self._candidate_models(plan):
            attempt = {"connector": "openrouter", "model": model}
            answer_parts = []
            try:
                mark_model_attempt(model)
                yield {"type": "start", "connector": "openrouter", "model": model}
                for text in self.connectors["openrouter"].stream_generate(
                    model=model,
                    messages=messages,
                    timeout=self.timeout_seconds,
                ):
                    answer_parts.append(text)
                    yield {"type": "token", "text": text}
                answer = "".join(answer_parts).strip()
                if not answer:
                    raise RuntimeError("OpenRouter returned an empty response")
                attempt["ok"] = True
                attempts.append(attempt)
                mark_model_success(model)
                yield {
                    "type": "done",
                    "message": answer,
                    "execution": {
                        "connector": "openrouter",
                        "model": model,
                        "attempts": attempts,
                        "fallback_used": len(attempts) > 1,
                    },
                }
                return
            except Exception as exc:
                last_error = str(exc)
                attempt["ok"] = False
                attempt["error"] = last_error
                attempts.append(attempt)
                mark_model_fail(model, exc)
                next_model = self._next_model(model, plan)
                if next_model:
                    mark_model_fallback(next_model)
                yield {"type": "fallback", "model": model, "error": last_error}

        yield {
            "type": "error",
            "message": f"FusionDesk execution failed: {last_error}",
            "execution": {
                "connector": "openrouter",
                "model": None,
                "attempts": attempts,
                "fallback_used": len(attempts) > 1,
            },
        }

    def _candidate_models(self, plan: dict[str, Any]) -> list[str]:
        planned_models = []
        for assignment in plan.get("seat_assignments", []):
            model = assignment.get("model")
            if not model:
                continue
            resolved = resolve_executable_model(str(model))
            if resolved:
                planned_models.append(resolved)
            else:
                mark_model_skip(str(model))

        candidates = []
        for model in active_fallback_chain() + planned_models:
            if model not in candidates:
                candidates.append(model)
        return candidates

    def _next_model(self, current_model: str, plan: dict[str, Any]) -> str | None:
        candidates = self._candidate_models(plan)
        try:
            return candidates[candidates.index(current_model) + 1]
        except (ValueError, IndexError):
            return None

    def _messages(
        self,
        *,
        task: str,
        plan: dict[str, Any],
        memory_context: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        seats = ", ".join(
            f"{item.get('seat')}={item.get('model')}" for item in plan.get("seat_assignments", [])
        )
        system = (
            "You are FusionDesk AI. Execute the selected skill and answer the user directly. "
            "Do not print the seat assignment JSON unless the user asks for the plan. "
            "Be concise, useful, and explicit about assumptions. "
            "Use the session memory recap when answering identity, birthday, preference, or 'I already gave it' questions. "
            "Never claim live internet, market data, filesystem, browser, GitHub, RunPod, or other tool access unless Tool State says that connector is active. "
            "If a connector is registered but inactive, say it is registered but not available for this response."
        )
        context = (
            f"Selected skill: {plan.get('selected_skill')}\n"
            f"Mode: {plan.get('mode')}\n"
            f"Connectors: {', '.join(plan.get('connectors', []))}\n"
            f"Seats: {seats}\n"
            f"Confidence: {plan.get('confidence')}\n"
            f"Warnings: {', '.join(plan.get('warnings', []))}"
        )
        memory = memory_context or {}
        context_parts = [context]
        if memory.get("recap"):
            context_parts.append(f"Session memory recap:\n{memory['recap']}")
        if memory.get("facts"):
            facts = "\n".join(f"- {key}: {value}" for key, value in memory["facts"].items())
            context_parts.append(f"Known user facts from this session:\n{facts}")
        if memory.get("tool_state"):
            tool_lines = "\n".join(f"- {key}: {value}" for key, value in memory["tool_state"].items())
            context_parts.append(f"Tool State:\n{tool_lines}")
        context_text = "\n\n".join(context_parts)
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": f"{context_text}\n\nUser task:\n{task}"},
        ]
