#!/usr/bin/env python3
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

import os

import json
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import socket
import traceback
import concurrent.futures
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fusiondesk.core import ExecutionEngine, MissionRuntime, SeatAssignmentEngine
from fusiondesk.core.execution import model_registry_for_api, model_status

STATIC = ROOT / "dashboard" / "static"
LOG_DIR = ROOT / "dashboard" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
RUNTIME_DIR = ROOT / "dashboard" / "runtime"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
TRACE_LOG = LOG_DIR / "fusiondesk-debug.log"
SESSION_STORE_PATH = RUNTIME_DIR / "sessions.json"
CAPABILITY_MATRIX_PATH = ROOT / "fusiondesk" / "capabilities" / "matrix.json"
TRADEMASTER_STATS = ROOT / "flint" / "memory" / "trading" / "stats.md"
TRADEMASTER_LESSONS = ROOT / "flint" / "memory" / "trading" / "lessons" / "premium_reload_lessons.md"
TRADEMASTER_REVIEWS = ROOT / "flint" / "memory" / "trading" / "reviews"

HOST = os.environ.get("CLAUDE_DASHBOARD_HOST", "127.0.0.1")
PORT = int(os.environ.get("CLAUDE_DASHBOARD_PORT", "4899"))
FLINT_URL = "https://github.com/Chintanpatel24/flint"
FLINT_INSTALL_COMMAND = "curl -fsSL https://raw.githubusercontent.com/Chintanpatel24/flint/main/install.sh | bash"
MLX_PORT = int(os.environ.get("MLX_PORT", "4000"))
MLX_URL = f"http://127.0.0.1:{MLX_PORT}"
MODEL = os.environ.get("MLX_MODEL", "mlx-community/Qwen3.5-4B-4bit")
MLX_PYTHON = Path.home() / ".local" / "mlx-server" / "bin" / "python3"
MLX_SERVER = Path.home() / ".local" / "mlx-native-server" / "server.py"
CLAUDE_BIN = "/opt/homebrew/bin/claude"
DESKTOP_COMMAND = Path.home() / "Desktop" / "Claude Local.command"
PHONE_CONFIG = Path.home() / ".claude" / "screen-to-phone-config.sh"
PHONE_SEND = Path.home() / ".claude" / "imessage-send.sh"
MODEL_CACHE = Path.home() / ".cache" / "huggingface" / "hub" / "models--mlx-community--Qwen3.5-4B-4bit"
MLX_LOG = Path("/tmp/mlx-server.log")
CODEX_BIN = os.environ.get("CODEX_BIN", "codex")
STAGE_TIMEOUT_SECONDS = 30
LOCAL_CHAT_ENABLED = os.environ.get("LOCAL_CHAT_ENABLED", "false").strip().casefold() in {"1", "true", "yes", "on"}
DEFAULT_CHAT_ROUTE = os.environ.get("DEFAULT_CHAT_ROUTE", "fusiondesk").strip().casefold()
FUSIONDESK_AGENT_CLI_ENABLED = os.environ.get("FUSIONDESK_AGENT_CLI_ENABLED", "false").strip().casefold() in {"1", "true", "yes", "on"}
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_ALLOWED_CHAT_ID = os.environ.get("TELEGRAM_ALLOWED_CHAT_ID", "").strip()
TELEGRAM_BOT_ENABLED = os.environ.get("TELEGRAM_BOT_ENABLED", "false").strip().casefold() in {"1", "true", "yes", "on"}
FUSIONDESK_INTENT_PHRASES = (
    "use fusiondesk",
    "assign seats",
    "trademaster",
    "marketing campaign",
    "fusiondesk",
)
LOCAL_CHAT_DISABLED_MESSAGE = "Local chat is disabled. Use FusionDesk commands or enable local model."
QWEN_TIMEOUT_FALLBACK_MESSAGE = "Local Qwen is taking too long. Use FusionDesk commands or try again after restarting the local model."
MAX_SESSION_MESSAGES = 200


class SessionStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()

    def _read_unlocked(self) -> dict:
        if not self.path.exists():
            return {"sessions": {}}
        try:
            return json.loads(self.path.read_text())
        except Exception:
            return {"sessions": {}}

    def _write_unlocked(self, data: dict) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
        tmp.replace(self.path)

    def get(self, session_id: str) -> dict:
        with self.lock:
            data = self._read_unlocked()
            sessions = data.setdefault("sessions", {})
            session = sessions.setdefault(
                session_id,
                {"id": session_id, "created_at": time.time(), "updated_at": time.time(), "messages": []},
            )
            self._write_unlocked(data)
            return json.loads(json.dumps(session))

    def messages(self, session_id: str) -> list[dict]:
        return self.get(session_id).get("messages", [])

    def append_message(self, session_id: str, role: str, content: str, status: str = "done", metadata: dict | None = None) -> dict:
        with self.lock:
            data = self._read_unlocked()
            sessions = data.setdefault("sessions", {})
            session = sessions.setdefault(
                session_id,
                {"id": session_id, "created_at": time.time(), "updated_at": time.time(), "messages": []},
            )
            message = {
                "id": str(uuid.uuid4()),
                "role": role,
                "content": content,
                "status": status,
                "created_at": time.time(),
                "updated_at": time.time(),
                "metadata": metadata or {},
            }
            session.setdefault("messages", []).append(message)
            session["messages"] = session["messages"][-MAX_SESSION_MESSAGES:]
            session["updated_at"] = time.time()
            self._write_unlocked(data)
            return json.loads(json.dumps(message))

    def update_message(
        self,
        session_id: str,
        message_id: str,
        *,
        content: str | None = None,
        status: str | None = None,
        metadata: dict | None = None,
    ) -> dict | None:
        with self.lock:
            data = self._read_unlocked()
            session = data.setdefault("sessions", {}).get(session_id)
            if not session:
                return None
            for message in session.get("messages", []):
                if message.get("id") == message_id:
                    if content is not None:
                        message["content"] = content
                    if status is not None:
                        message["status"] = status
                    if metadata:
                        existing = message.setdefault("metadata", {})
                        existing.update(metadata)
                    message["updated_at"] = time.time()
                    session["updated_at"] = time.time()
                    self._write_unlocked(data)
                    return json.loads(json.dumps(message))
        return None

    def clear(self, session_id: str) -> None:
        with self.lock:
            data = self._read_unlocked()
            data.setdefault("sessions", {})[session_id] = {
                "id": session_id,
                "created_at": time.time(),
                "updated_at": time.time(),
                "messages": [],
            }
            self._write_unlocked(data)


SESSION_STORE = SessionStore(SESSION_STORE_PATH)
MISSION_RUNTIME = MissionRuntime.load()
TELEGRAM_SERVICE = None


def normalize_session_id(value: object | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return str(uuid.uuid4())
    cleaned = re.sub(r"[^a-zA-Z0-9_.:-]", "", raw)
    return cleaned[:96] or str(uuid.uuid4())


def clean_fact_value(value: str) -> str:
    value = str(value).strip(" .,!?\n\t")
    for splitter in (" and my ", " but ", " also ", " because ", " when "):
        if splitter in value.casefold():
            index = value.casefold().index(splitter)
            value = value[:index].strip(" .,!?\n\t")
    return value


def extract_user_facts(messages: list[dict]) -> dict[str, str]:
    facts: dict[str, str] = {}
    user_text = "\n".join(
        str(message.get("content", ""))
        for message in messages
        if message.get("role") == "user" and str(message.get("content", "")).strip()
    )
    patterns = {
        "name": [
            r"\bmy name is\s+([A-Z][A-Za-z0-9_' -]{1,40})",
            r"\bi am\s+([A-Z][A-Za-z0-9_' -]{1,40})",
            r"\bi'm\s+([A-Z][A-Za-z0-9_' -]{1,40})",
            r"\bcall me\s+([A-Z][A-Za-z0-9_' -]{1,40})",
        ],
        "birthday": [
            r"\bmy birthday is\s+([A-Za-z0-9, /\-]{3,40})",
            r"\bmy bday is\s+([A-Za-z0-9, /\-]{3,40})",
            r"\bbirthday:\s*([A-Za-z0-9, /\-]{3,40})",
            r"\bborn on\s+([A-Za-z0-9, /\-]{3,40})",
        ],
    }
    for fact, fact_patterns in patterns.items():
        for pattern in fact_patterns:
            matches = re.findall(pattern, user_text, flags=re.IGNORECASE)
            if matches:
                value = clean_fact_value(str(matches[-1]))
                if value:
                    facts[fact] = value
    return facts


def session_memory_recap(messages: list[dict], limit: int = 8) -> str:
    facts = extract_user_facts(messages)
    lines = []
    if facts:
        lines.append("Known facts: " + ", ".join(f"{key}={value}" for key, value in facts.items()))
    recent = [
        message
        for message in messages
        if message.get("role") in {"user", "assistant"}
        and message.get("status", "done") != "running"
        and str(message.get("content", "")).strip()
    ][-limit:]
    if recent:
        lines.append("Recent conversation:")
        for message in recent:
            role = "User" if message.get("role") == "user" else "FusionDesk"
            content = re.sub(r"\s+", " ", str(message.get("content", ""))).strip()
            if len(content) > 220:
                content = content[:220] + "..."
            lines.append(f"- {role}: {content}")
    return "\n".join(lines) if lines else "No prior session memory available."


def tool_state_for_plan(plan: dict) -> dict[str, str]:
    selected = set(plan.get("connectors", []))
    openrouter_key = bool(os.environ.get("OPENROUTER_API_KEY"))
    agent_reach_active = os.environ.get("AGENT_REACH_ENABLED", "false").strip().casefold() in {"1", "true", "yes", "on"}
    polygon_active = bool(os.environ.get("POLYGON_API_KEY"))
    runpod_active = bool(os.environ.get("RUNPOD_API_KEY"))
    github_active = bool(os.environ.get("GITHUB_TOKEN"))
    browser_active = os.environ.get("BROWSER_AUTOMATION_ENABLED", "false").strip().casefold() in {"1", "true", "yes", "on"}
    local = health().get("status", "offline")
    state = {
        "openrouter": "active" if openrouter_key else "inactive: OPENROUTER_API_KEY missing",
        "local_qwen": f"{local}; plain local chat enabled={LOCAL_CHAT_ENABLED}",
        "internet_access": "active through agent_reach" if agent_reach_active and "agent_reach" in selected else "inactive for this response",
        "agent_reach": "active" if agent_reach_active else "registered only; not active",
        "polygon_io": "active" if polygon_active else "registered only; live market data unavailable",
        "github": "active" if github_active else "registered only; GitHub API unavailable",
        "browser_automation": "active" if browser_active else "registered only; browser automation unavailable",
        "local_filesystem": "active for configured dashboard files only" if "local_filesystem" in selected else "not selected",
        "runpod": "active" if runpod_active else "registered only; GPU jobs unavailable",
    }
    for connector in sorted(selected - set(state)):
        state[connector] = "selected; no runtime status checker configured"
    return state


def build_fusiondesk_memory_context(messages: list[dict], plan: dict) -> dict:
    facts = extract_user_facts(messages)
    return {
        "facts": facts,
        "recap": session_memory_recap(messages),
        "tool_state": tool_state_for_plan(plan),
    }


class StageTimeout(RuntimeError):
    def __init__(self, stage: str):
        super().__init__(f"Timed out at stage: {stage}")
        self.stage = stage


def run_stage(stage: str, func):
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(func)
    try:
        return future.result(timeout=STAGE_TIMEOUT_SECONDS)
    except concurrent.futures.TimeoutError as exc:
        raise StageTimeout(stage) from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def trace(stage: str, **fields) -> None:
    safe_fields = {}
    for key, value in fields.items():
        if isinstance(value, str) and len(value) > 500:
            value = value[:500] + "...[truncated]"
        safe_fields[key] = value
    line = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stage": stage,
        **safe_fields,
    }
    try:
        TRACE_LOG.open("a").write(json.dumps(line, default=str) + "\n")
    except Exception:
        pass
    print(f"[FusionDeskTrace] {stage} {safe_fields}", flush=True)


def default_chat_route() -> str:
    return DEFAULT_CHAT_ROUTE if DEFAULT_CHAT_ROUTE in {"qwen", "fusiondesk", "disabled"} else "fusiondesk"


def local_chat_disabled_response() -> dict:
    return {
        "ok": False,
        "message": LOCAL_CHAT_DISABLED_MESSAGE,
        "route": "disabled",
        "router_status": "Disabled",
        "seat_engine_status": "Bypassed",
        "local_model_status": "Disabled",
        "local_chat_enabled": LOCAL_CHAT_ENABLED,
        "default_chat_route": default_chat_route(),
    }


def qwen_timeout_response(stage: str, detail: str) -> dict:
    return {
        "ok": False,
        "message": QWEN_TIMEOUT_FALLBACK_MESSAGE,
        "detail": detail,
        "error_stage": stage,
        "stage_timeout_seconds": STAGE_TIMEOUT_SECONDS,
        "route": "local_model",
        "router_status": "Local Model",
        "seat_engine_status": "Bypassed",
        "local_model_status": "Online but slow",
        "friendly_fallback": True,
    }


def run(cmd: list[str], timeout: int = 8) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)


def health() -> dict:
    try:
        with urllib.request.urlopen(f"{MLX_URL}/health", timeout=1.5) as res:
            return json.loads(res.read().decode("utf-8"))
    except Exception:
        return {"status": "offline", "model": MODEL}


def lsof_port_pid(port: int) -> str | None:
    try:
        out = run(["/usr/sbin/lsof", "-ti", f"tcp:{port}"], timeout=3).stdout.strip()
        return out.splitlines()[0] if out else None
    except Exception:
        return None


def phone_target() -> str:
    if not PHONE_CONFIG.exists():
        return "not configured"
    for line in PHONE_CONFIG.read_text(errors="ignore").splitlines():
        if line.startswith("BUDDY="):
            return line.split("=", 1)[1].strip().strip('"')
    return "not configured"


def claude_version() -> str:
    if not Path(CLAUDE_BIN).exists():
        return "not installed"
    try:
        return run([CLAUDE_BIN, "--version"], timeout=6).stdout.strip() or "installed"
    except Exception:
        return "installed"


def lan_url() -> str:
    ip = "127.0.0.1"
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            pass
    return f"http://{ip}:{PORT}"


def backend_health() -> dict:
    local = health()
    telegram = telegram_status()
    return {
        "ok": True,
        "status": "ok",
        "service": "fusiondesk-dashboard",
        "host": HOST,
        "port": PORT,
        "lanUrl": lan_url(),
        "sessionStore": str(SESSION_STORE_PATH),
        "sessionStoreReady": SESSION_STORE_PATH.parent.exists(),
        "fusiondesk": "ready",
        "localQwen": local.get("status", "offline"),
        "agentCliEnabled": FUSIONDESK_AGENT_CLI_ENABLED,
        "routes": ["fusiondesk", "trademaster", "claude_code", "codex", "local_qwen"],
        "telegram": telegram,
    }


def flint_status() -> dict:
    candidates = [
        Path.home() / ".flint",
        Path("/Applications/Flint.app"),
        Path.home() / "Applications" / "Flint.app",
    ]
    found = [str(path) for path in candidates if path.exists()]
    return {
        "installed": bool(found),
        "paths": found,
        "url": FLINT_URL,
        "installCommand": FLINT_INSTALL_COMMAND,
        "summary": "Local-first markdown notes, graph, infinite canvas, and optional AI memory.",
    }


def read_tail(path: Path, limit: int = 10000) -> str:
    if not path.exists():
        return ""
    data = path.read_bytes()
    return data[-limit:].decode("utf-8", errors="replace")


def read_text_file(path: Path, fallback: str = "") -> str:
    try:
        return path.read_text(errors="replace")
    except Exception:
        return fallback


def capability_matrix() -> dict:
    if not CAPABILITY_MATRIX_PATH.exists():
        return {"ok": False, "message": "Capability matrix not found.", "capabilities": []}
    try:
        data = json.loads(CAPABILITY_MATRIX_PATH.read_text())
    except Exception as exc:
        return {"ok": False, "message": f"Capability matrix could not be read: {exc}", "capabilities": []}
    return {"ok": True, **data}


def trademaster_status() -> dict:
    reviews = sorted(TRADEMASTER_REVIEWS.glob("*.md")) if TRADEMASTER_REVIEWS.exists() else []
    recent_reviews = [
        {"name": path.name, "path": str(path), "preview": read_text_file(path)[:1000]}
        for path in reviews[-5:]
    ]
    return {
        "ok": True,
        "stats": read_text_file(TRADEMASTER_STATS, "# TradeMaster Stats\n\nNo stats generated yet."),
        "lessons": read_text_file(TRADEMASTER_LESSONS, "# TradeMaster Lessons\n\nNo lessons generated yet."),
        "reviewCount": len(reviews),
        "recentReviews": recent_reviews,
        "runner": "fusiondesk.memory.trade_review_executor.review_trade",
    }


def run_trademaster_review(payload: dict) -> dict:
    memory_dir = ROOT / "fusiondesk" / "memory"
    if str(memory_dir) not in sys.path:
        sys.path.insert(0, str(memory_dir))
    try:
        from trade_review_executor import review_trade

        saved = review_trade(
            ticker=str(payload.get("ticker") or "IWM").strip(),
            direction=str(payload.get("direction") or "Bullish").strip(),
            entry=str(payload.get("entry") or "").strip(),
            exit=str(payload.get("exit") or "").strip(),
            thesis=str(payload.get("thesis") or "").strip(),
            notes=str(payload.get("notes") or "").strip(),
        )
    except Exception as exc:
        trace("trademaster.review.error", error=str(exc), traceback=traceback.format_exc())
        return {"ok": False, "message": f"Trade review failed: {exc}"}
    return {"ok": True, "message": f"Trade review saved: {saved}", "saved": str(saved), "trademaster": trademaster_status()}


def mission_response(payload: dict, runtime: MissionRuntime | None = None) -> dict:
    user_goal = str(payload.get("user_goal") or payload.get("goal") or payload.get("task") or "").strip()
    if not user_goal:
        return {"ok": False, "message": "user_goal is required."}
    mission = (runtime or MISSION_RUNTIME).run_mission(user_goal)
    return {"ok": True, "mission": mission}


def clean_chat_text(text: str) -> str:
    text = text.strip()
    for start, end in (("<think>", "</think>"), ("<|channel>thought", "<channel|>")):
        while start in text and end in text:
            before, rest = text.split(start, 1)
            _, after = rest.split(end, 1)
            text = (before + after).strip()
    if text.startswith("Thinking Process:"):
        chunks = [chunk.strip() for chunk in text.split("\n\n") if chunk.strip()]
        if chunks:
            text = chunks[-1]
    if text.startswith("Action: Output"):
        text = text.splitlines()[-1].strip()
    return text.strip().strip('"')


def _strip_command_prefix(prompt: str, prefixes: tuple[str, ...]) -> str:
    lowered = prompt.strip().casefold()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return prompt.strip()[len(prefix):].strip(" :-\n\t")
    return prompt.strip()


def _run_cli_command(command_template: str | None, default_command: list[str], prompt: str, route: str) -> dict:
    if not FUSIONDESK_AGENT_CLI_ENABLED:
        return {
            "ok": False,
            "message": f"{route} routing is configured but CLI execution is disabled. Set FUSIONDESK_AGENT_CLI_ENABLED=true to enable it.",
            "route": route,
            "router_status": route,
            "seat_engine_status": "Bypassed",
            "local_model_status": "Bypassed",
        }

    if command_template:
        rendered = command_template.replace("{prompt}", prompt)
        cmd = shlex.split(rendered)
        if "{prompt}" not in command_template:
            cmd.append(prompt)
    else:
        cmd = default_command

    try:
        proc = run(cmd, timeout=180)
    except Exception as exc:
        return {
            "ok": False,
            "message": f"{route} command failed to start: {exc}",
            "route": route,
            "router_status": route,
            "seat_engine_status": "Bypassed",
            "local_model_status": "Bypassed",
        }
    output = (proc.stdout or proc.stderr or "").strip()
    return {
        "ok": proc.returncode == 0,
        "message": output or f"{route} returned no output.",
        "route": route,
        "router_status": route,
        "seat_engine_status": "Bypassed",
        "local_model_status": "Bypassed",
        "returncode": proc.returncode,
    }


def run_claude_code_command(prompt: str) -> dict:
    command_template = os.environ.get("CLAUDE_CODE_COMMAND")
    return _run_cli_command(
        command_template,
        [CLAUDE_BIN, "-p", prompt],
        prompt,
        "claude_code",
    )


def run_codex_command(prompt: str) -> dict:
    command_template = os.environ.get("CODEX_COMMAND")
    return _run_cli_command(
        command_template,
        [CODEX_BIN, "exec", "--skip-git-repo-check", prompt],
        prompt,
        "codex",
    )


def route_remote_command(prompt: str, history: list[dict] | None = None) -> dict:
    text = prompt.strip()
    lowered = text.casefold()
    if not text:
        return {"ok": False, "message": "Type a command first.", "route": "empty"}
    if lowered in {"/health", "health", "status"}:
        return {"ok": True, "message": json.dumps(backend_health(), indent=2), "route": "health", "health": backend_health()}
    if lowered.startswith("/claude ") or lowered.startswith("claude code ") or lowered.startswith("claude:"):
        task = _strip_command_prefix(text, ("/claude", "claude code", "claude:"))
        return run_claude_code_command(task)
    if lowered.startswith("/codex ") or lowered.startswith("codex:") or lowered.startswith("codex "):
        task = _strip_command_prefix(text, ("/codex", "codex:", "codex"))
        return run_codex_command(task)
    if lowered.startswith("/trademaster ") or "trademaster" in lowered:
        task = _strip_command_prefix(text, ("/trademaster",))
        return fusiondesk_chat(f"Use FusionDesk {task}", history=history or [])
    return route_chat(text, history or [])


def start_model() -> dict:
    current = health()
    if current.get("status") == "ok":
        return {"ok": True, "message": "Model server is already running.", "health": current}

    if not MLX_PYTHON.exists() or not MLX_SERVER.exists():
        return {"ok": False, "message": "MLX Python/server is not installed."}

    log = MLX_LOG.open("ab", buffering=0)
    env = os.environ.copy()
    env["MLX_MODEL"] = MODEL
    env["MLX_PORT"] = str(MLX_PORT)
    subprocess.Popen(
        [str(MLX_PYTHON), str(MLX_SERVER)],
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
    )

    deadline = time.time() + 35
    while time.time() < deadline:
        current = health()
        if current.get("status") == "ok":
            return {"ok": True, "message": "Model server is online.", "health": current}
        time.sleep(1)
    return {"ok": False, "message": "Model server did not answer yet. Check logs.", "log": read_tail(MLX_LOG)}


def stop_model() -> dict:
    pid = lsof_port_pid(MLX_PORT)
    if not pid:
        return {"ok": True, "message": "Model server is already stopped."}
    try:
        os.kill(int(pid), signal.SIGTERM)
        return {"ok": True, "message": f"Stopped model server PID {pid}."}
    except Exception as exc:
        return {"ok": False, "message": f"Could not stop PID {pid}: {exc}"}


def open_claude() -> dict:
    if not DESKTOP_COMMAND.exists():
        return {"ok": False, "message": "Desktop Claude Local.command was not found."}
    proc = run(["/usr/bin/open", str(DESKTOP_COMMAND)], timeout=5)
    return {"ok": proc.returncode == 0, "message": "Opening Claude Local." if proc.returncode == 0 else proc.stderr}


def send_phone_test() -> dict:
    if not PHONE_SEND.exists():
        return {"ok": False, "message": "Phone bridge is not installed."}
    msg = "Claude Stack Dashboard test message."
    proc = run([str(PHONE_SEND), msg], timeout=30)
    return {"ok": proc.returncode == 0, "message": "Sent phone test message." if proc.returncode == 0 else proc.stderr}


def telegram_status() -> dict:
    service = TELEGRAM_SERVICE
    return {
        "enabled": TELEGRAM_BOT_ENABLED,
        "configured": bool(TELEGRAM_BOT_TOKEN),
        "allowedChatId": bool(TELEGRAM_ALLOWED_CHAT_ID),
        "running": bool(service and service.is_alive()),
        "lastError": getattr(service, "last_error", "") if service else "",
        "lastUpdateId": getattr(service, "last_update_id", None) if service else None,
    }


class TelegramBotService(threading.Thread):
    def __init__(self, token: str):
        super().__init__(daemon=True)
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.stop_event = threading.Event()
        self.last_error = ""
        self.last_update_id = None

    def api(self, method: str, payload: dict | None = None, timeout: int = 35) -> dict:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["content-type"] = "application/json"
        req = urllib.request.Request(f"{self.base_url}/{method}", data=data, headers=headers, method="POST" if payload else "GET")
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8"))

    def send_message(self, chat_id: int | str, text: str) -> None:
        chunks = [text[i:i + 3900] for i in range(0, len(text), 3900)] or [""]
        for chunk in chunks:
            self.api("sendMessage", {"chat_id": chat_id, "text": chunk})

    def chat_allowed(self, chat_id: int | str) -> bool:
        return not TELEGRAM_ALLOWED_CHAT_ID or str(chat_id) == TELEGRAM_ALLOWED_CHAT_ID

    def handle_message(self, message: dict) -> None:
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        text = str(message.get("text") or "").strip()
        if not chat_id or not text:
            return
        if not self.chat_allowed(chat_id):
            self.send_message(chat_id, "FusionDesk rejected this chat. Set TELEGRAM_ALLOWED_CHAT_ID to this chat id if it is yours.")
            return

        trace("telegram.command.received", chat_id=chat_id, text=text)
        session_id = f"telegram:{chat_id}"
        SESSION_STORE.append_message(session_id, "user", text, metadata={"source": "telegram"})
        result = route_remote_command(text, SESSION_STORE.messages(session_id))
        response = result.get("message") or json.dumps(result, indent=2)
        SESSION_STORE.append_message(
            session_id,
            "assistant",
            response,
            metadata={"source": "telegram", "route": result.get("route")},
        )
        self.send_message(chat_id, response)
        trace("telegram.command.returned", chat_id=chat_id, ok=result.get("ok"), route=result.get("route"))

    def run(self) -> None:
        offset = None
        trace("telegram.start")
        while not self.stop_event.is_set():
            try:
                query = {"timeout": 25}
                if offset is not None:
                    query["offset"] = offset
                url = f"{self.base_url}/getUpdates?{urlencode(query)}"
                with urllib.request.urlopen(url, timeout=35) as res:
                    data = json.loads(res.read().decode("utf-8"))
                for update in data.get("result", []):
                    update_id = update.get("update_id")
                    if update_id is not None:
                        offset = update_id + 1
                        self.last_update_id = update_id
                    message = update.get("message") or update.get("edited_message")
                    if message:
                        self.handle_message(message)
                self.last_error = ""
            except Exception as exc:
                self.last_error = str(exc)
                trace("telegram.error", error=str(exc))
                time.sleep(5)


def start_telegram_service() -> None:
    global TELEGRAM_SERVICE
    if not TELEGRAM_BOT_ENABLED:
        return
    if not TELEGRAM_BOT_TOKEN:
        trace("telegram.disabled", reason="missing_token")
        return
    if TELEGRAM_SERVICE and TELEGRAM_SERVICE.is_alive():
        return
    TELEGRAM_SERVICE = TelegramBotService(TELEGRAM_BOT_TOKEN)
    TELEGRAM_SERVICE.start()


def open_flint_github() -> dict:
    proc = run(["/usr/bin/open", FLINT_URL], timeout=5)
    return {"ok": proc.returncode == 0, "message": "Opening Flint GitHub." if proc.returncode == 0 else proc.stderr}


def chat(prompt: str, history: list[dict]) -> dict:
    trace("chat.enter", prompt=prompt)
    stage = "local_model_health"
    if health().get("status") != "ok":
        trace("chat.health.offline_return_unavailable")
        return {
            "ok": False,
            "message": "Local model unavailable at stage: local_model_health",
            "error_stage": "local_model_health",
            "stage_timeout_seconds": STAGE_TIMEOUT_SECONDS,
            "route": "local_model",
            "router_status": "Local Model",
            "seat_engine_status": "Bypassed",
            "local_model_status": "Unavailable: local_model_health",
        }

    messages = []
    for item in history[-12:]:
        role = item.get("role")
        content = item.get("content", "")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 768,
        "messages": messages,
    }
    req = urllib.request.Request(
        f"{MLX_URL}/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json", "x-api-key": "sk-local"},
        method="POST",
    )
    try:
        stage = "local_model_generation"
        trace("chat.mlx.request.start", url=f"{MLX_URL}/v1/messages")
        with urllib.request.urlopen(req, timeout=STAGE_TIMEOUT_SECONDS) as res:
            data = json.loads(res.read().decode("utf-8"))
        trace("chat.mlx.request.returned", usage=data.get("usage", {}))
        stage = "local_model_response_parse"
        text = "\n".join(part.get("text", "") for part in data.get("content", []) if part.get("type") == "text")
        message = clean_chat_text(text)
        if not message or message == "(No output)":
            trace("chat.empty_response", error_stage=stage)
            return {
                "ok": False,
                "message": "Local model returned no text at stage: local_model_response_parse",
                "error_stage": "local_model_response_parse",
                "stage_timeout_seconds": STAGE_TIMEOUT_SECONDS,
                "route": "local_model",
                "router_status": "Local Model",
                "seat_engine_status": "Bypassed",
                "local_model_status": "No text: local_model_response_parse",
            }
        result = {
            "ok": True,
            "message": message,
            "usage": data.get("usage", {}),
            "route": "local_model",
            "router_status": "Local Model",
            "seat_engine_status": "Bypassed",
            "local_model_status": "Online",
        }
        trace("chat.return", ok=True)
        return result
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        trace("chat.mlx.http_error", status=exc.code, message=message, error_stage=stage)
        return {
            "ok": False,
            "message": f"Local model HTTP error at stage: {stage}",
            "detail": message,
            "error_stage": stage,
            "stage_timeout_seconds": STAGE_TIMEOUT_SECONDS,
            "route": "local_model",
            "router_status": "Local Model",
            "seat_engine_status": "Bypassed",
            "local_model_status": f"HTTP error: {stage}",
        }
    except TimeoutError as exc:
        trace("chat.timeout", error=str(exc), error_stage=stage, traceback=traceback.format_exc())
        return qwen_timeout_response(stage, str(exc))
    except Exception as exc:
        is_timeout = "timed out" in str(exc).casefold()
        trace("chat.exception", error=str(exc), error_stage=stage, timeout=is_timeout, traceback=traceback.format_exc())
        if is_timeout:
            return qwen_timeout_response(stage, str(exc))
        status = f"Timed out: {stage}" if is_timeout else f"Unavailable: {stage}"
        return {
            "ok": False,
            "message": f"Local model unavailable at stage: {stage}",
            "detail": str(exc),
            "error_stage": stage,
            "stage_timeout_seconds": STAGE_TIMEOUT_SECONDS,
            "route": "local_model",
            "router_status": "Local Model",
            "seat_engine_status": "Bypassed",
            "local_model_status": status,
        }


def is_fusiondesk_chat(prompt: str) -> bool:
    normalized = prompt.strip().casefold()
    return any(phrase in normalized for phrase in FUSIONDESK_INTENT_PHRASES)


def chat_route(prompt: str) -> str:
    if is_fusiondesk_chat(prompt):
        return "fusiondesk_assign"
    route = default_chat_route()
    if route == "fusiondesk":
        return "fusiondesk_default"
    if route == "disabled":
        return "disabled"
    return "qwen"


def route_chat(prompt: str, history: list[dict]) -> dict:
    route = chat_route(prompt)
    if route == "fusiondesk_assign":
        trace("router.route", route_selected="fusiondesk_assign", skipped_local_model=True)
        return fusiondesk_chat(prompt, history=history)
    if route == "fusiondesk_default":
        trace("router.route", route_selected="fusiondesk_default", skipped_local_model=True)
        return fusiondesk_chat(prompt, history=history)
    if route == "disabled":
        trace("router.route", route_selected="disabled", skipped_local_model=True)
        return local_chat_disabled_response()
    if not LOCAL_CHAT_ENABLED:
        trace("router.route", route_selected="disabled", skipped_local_model=True, reason="local_chat_disabled")
        return local_chat_disabled_response()
    trace("router.route", route_selected="qwen", skipped_local_model=False)
    return chat(prompt, history)


def fusiondesk_task_from_prompt(prompt: str) -> str:
    task = prompt.strip()
    lowered = task.casefold()
    if lowered.startswith("use fusiondesk"):
        task = task[len("use fusiondesk"):].strip(" :-\n\t") or prompt.strip()
    return task


def fusiondesk_chat(prompt: str, history: list[dict] | None = None) -> dict:
    trace("fusiondesk_chat.enter", prompt=prompt)
    task = fusiondesk_task_from_prompt(prompt)

    payload = {"task": task}
    trace("fusiondesk_chat.router", task=task)
    trace("fusiondesk_chat.seat_assignment.start")
    result = seat_assignment(payload)
    trace(
        "fusiondesk_chat.seat_assignment.returned",
        ok=result.get("ok"),
        selected_skill=result.get("selected_skill"),
        mode=result.get("mode"),
        connectors=result.get("connectors"),
    )
    if not result.get("ok"):
        trace("fusiondesk_chat.return", ok=False, message=result.get("message"))
        return result

    memory_context = build_fusiondesk_memory_context((history or []) + [{"role": "user", "content": prompt}], result)
    trace("fusiondesk_chat.skill_detection", selected_skill=result.get("selected_skill"))
    trace("fusiondesk_chat.execution.start", connector="openrouter")
    execution = ExecutionEngine.load().execute(task=task, plan=result, memory_context=memory_context)
    trace(
        "fusiondesk_chat.execution.returned",
        ok=execution.get("ok"),
        connector=(execution.get("execution") or {}).get("connector"),
        model=(execution.get("execution") or {}).get("model"),
        fallback_used=(execution.get("execution") or {}).get("fallback_used"),
    )
    response = {
        "ok": execution.get("ok", False),
        "message": execution.get("message", ""),
        "fusiondesk": result,
        "execution": execution.get("execution", {}),
        "memory_context": memory_context,
        "route": "fusiondesk",
        "router_status": "FusionDesk",
        "seat_engine_status": "Executed" if execution.get("ok") else "Execution Error",
        "local_model_status": "Bypassed",
    }
    trace("fusiondesk_chat.answer_returned", bytes=len(response["message"]))
    return response


def seat_assignment(payload: dict) -> dict:
    trace("seat_assignment.enter", keys=sorted(payload.keys()))
    task = str(payload.get("task", "")).strip()
    if not task:
        trace("seat_assignment.reject", reason="missing_task")
        return {"ok": False, "message": "Task is required."}

    skill = str(payload.get("skill") or payload.get("selected_skill") or "").strip() or None
    mode = str(payload.get("mode") or "").strip() or None
    cost = str(payload.get("costPreference") or payload.get("cost_preference") or "balanced").strip()
    quality = str(payload.get("qualityPreference") or payload.get("quality_preference") or "balanced").strip()
    available_models = payload.get("available_models")
    if available_models is not None and not isinstance(available_models, list):
        available_models = None
    connector_requirements = payload.get("connector_requirements")
    if connector_requirements is not None and not isinstance(connector_requirements, list):
        connector_requirements = None

    try:
        trace(
            "seat_assignment.engine.start",
            task=task,
            skill=skill,
            mode=mode,
            cost=cost,
            quality=quality,
        )
        result = run_stage(
            "seat_assignment.engine",
            lambda: SeatAssignmentEngine.load().assign(
                task=task,
                selected_skill=skill,
                mode=mode,
                available_models=available_models,
                connector_requirements=connector_requirements,
                cost_preference=cost,
                quality_preference=quality,
            ),
        )
        trace(
            "seat_assignment.engine.returned",
            selected_skill=result.get("selected_skill"),
            mode=result.get("mode"),
            confidence=result.get("confidence"),
        )
        return {"ok": True, **result}
    except StageTimeout as exc:
        trace("seat_assignment.timeout", error_stage=exc.stage)
        return {
            "ok": False,
            "message": str(exc),
            "error_stage": exc.stage,
            "stage_timeout_seconds": STAGE_TIMEOUT_SECONDS,
        }
    except Exception as exc:
        trace("seat_assignment.exception", error=str(exc), traceback=traceback.format_exc())
        return {"ok": False, "message": str(exc)}


def status() -> dict:
    h = health()
    pid = lsof_port_pid(MLX_PORT)
    server_status = h.get("status", "offline")
    if not LOCAL_CHAT_ENABLED:
        local_qwen_status = "Disabled"
    elif server_status == "ok":
        local_qwen_status = "Online but slow"
    else:
        local_qwen_status = "Error"
    return {
        "model": MODEL,
        "modelCached": MODEL_CACHE.exists(),
        "server": server_status,
        "serverModel": h.get("model", MODEL),
        "serverPid": pid,
        "fusiondeskStatus": "Ready",
        "localQwenStatus": local_qwen_status,
        "localChatEnabled": LOCAL_CHAT_ENABLED,
        "defaultChatRoute": default_chat_route(),
        "sessionStoreReady": SESSION_STORE_PATH.parent.exists(),
        "agentCliEnabled": FUSIONDESK_AGENT_CLI_ENABLED,
        "telegram": telegram_status(),
        "claude": claude_version(),
        "phoneTarget": phone_target(),
        "phoneReady": PHONE_SEND.exists() and PHONE_CONFIG.exists(),
        "desktopLauncher": DESKTOP_COMMAND.exists(),
        "lanUrl": lan_url(),
        "flint": flint_status(),
        "log": read_tail(MLX_LOG, 6000),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        (LOG_DIR / "dashboard.log").open("a").write(f"{time.strftime('%H:%M:%S')} {fmt % args}\n")

    def send_json(self, payload: dict, code: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        trace("http.response.start", path=getattr(self, "path", ""), code=code, bytes=len(body))
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("cache-control", "no-store, max-age=0")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        trace("http.response.sent", path=getattr(self, "path", ""), code=code)

    def send_stream_event(self, payload: dict) -> bool:
        try:
            self.wfile.write(json.dumps(payload).encode("utf-8") + b"\n")
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            trace("stream.client_disconnected", error=str(exc))
            return False

    def stream_fusiondesk_chat(self, prompt: str, session_id: str | None = None) -> None:
        task = fusiondesk_task_from_prompt(prompt)
        trace("stream.fusiondesk.start", task=task)
        self.send_response(200)
        self.send_header("content-type", "application/x-ndjson")
        self.send_header("cache-control", "no-store, max-age=0")
        self.end_headers()

        assistant_id = None
        if session_id:
            SESSION_STORE.append_message(session_id, "user", prompt, metadata={"source": "dashboard", "route": "fusiondesk"})
            assistant = SESSION_STORE.append_message(
                session_id,
                "assistant",
                "Thinking...",
                status="running",
                metadata={"source": "dashboard", "route": "fusiondesk"},
            )
            assistant_id = assistant["id"]

        result = seat_assignment({"task": task})
        if not result.get("ok"):
            message = result.get("message", "Seat assignment failed.")
            if session_id and assistant_id:
                SESSION_STORE.update_message(session_id, assistant_id, content=f"Error: {message}", status="error")
            self.send_stream_event({"type": "error", "message": message})
            return
        if session_id and assistant_id:
            SESSION_STORE.update_message(
                session_id,
                assistant_id,
                metadata={
                    "selected_skill": result.get("selected_skill"),
                    "mode": result.get("mode"),
                    "connectors": result.get("connectors"),
                    "confidence": result.get("confidence"),
                },
            )
        memory_context = build_fusiondesk_memory_context(
            SESSION_STORE.messages(session_id) if session_id else [{"role": "user", "content": prompt}],
            result,
        )
        if session_id and assistant_id:
            SESSION_STORE.update_message(
                session_id,
                assistant_id,
                metadata={
                    "memory_recap": memory_context.get("recap"),
                    "known_facts": memory_context.get("facts", {}),
                    "tool_state": memory_context.get("tool_state", {}),
                },
            )
        self.send_stream_event(
            {
                "type": "plan",
                "selected_skill": result.get("selected_skill"),
                "mode": result.get("mode"),
                "connectors": result.get("connectors"),
                "seat_assignments": result.get("seat_assignments"),
                "confidence": result.get("confidence"),
                "memory_recap": memory_context.get("recap"),
                "tool_state": memory_context.get("tool_state"),
            }
        )
        streamed = ""
        for event in ExecutionEngine.load().execute_stream(task=task, plan=result, memory_context=memory_context):
            if event.get("type") == "token":
                streamed += event.get("text") or ""
                if session_id and assistant_id:
                    SESSION_STORE.update_message(session_id, assistant_id, content=streamed or "Thinking...", status="running")
            elif event.get("type") == "done":
                streamed = event.get("message") or streamed
                if session_id and assistant_id:
                    SESSION_STORE.update_message(
                        session_id,
                        assistant_id,
                        content=streamed,
                        status="done",
                        metadata={"execution": event.get("execution", {})},
                    )
            elif event.get("type") == "error":
                message = event.get("message") or "FusionDesk execution failed."
                if session_id and assistant_id:
                    SESSION_STORE.update_message(
                        session_id,
                        assistant_id,
                        content=f"Error: {message}",
                        status="error",
                        metadata={"execution": event.get("execution", {})},
                    )
            self.send_stream_event(event)
        trace("stream.fusiondesk.sent", task=task)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/api/health":
            self.send_json(backend_health())
            return
        if path == "/api/status":
            self.send_json(status())
            return
        if path == "/api/models/status":
            self.send_json(model_status())
            return
        if path == "/api/models":
            self.send_json({"ok": True, **model_registry_for_api()})
            return
        if path == "/api/capabilities":
            self.send_json(capability_matrix())
            return
        if path == "/api/missions":
            self.send_json({"ok": True, "missions": MISSION_RUNTIME.list_missions()})
            return
        if path.startswith("/api/missions/"):
            mission_id = path.rsplit("/", 1)[-1]
            mission = MISSION_RUNTIME.get_mission(mission_id)
            if mission:
                self.send_json({"ok": True, "mission": mission})
            else:
                self.send_json({"ok": False, "message": "Mission not found."}, 404)
            return
        if path == "/api/trademaster/status":
            self.send_json(trademaster_status())
            return
        if path == "/api/session":
            session_id = normalize_session_id((query.get("session_id") or [""])[0])
            session = SESSION_STORE.get(session_id)
            messages = session.get("messages", [])
            self.send_json({
                "ok": True,
                "session_id": session_id,
                "messages": messages,
                "facts": extract_user_facts(messages),
                "memory_recap": session_memory_recap(messages),
            })
            return
        if path == "/assets/logo.png":
            self.serve_file(ROOT / "assets" / "icons" / "claude-local-thumbnail.png", "image/png")
            return
        target = STATIC / ("index.html" if path == "/" else path.lstrip("/"))
        if target.resolve().is_relative_to(STATIC.resolve()) and target.exists():
            ctype = "text/html" if target.suffix == ".html" else "text/css" if target.suffix == ".css" else "application/javascript"
            self.serve_file(target, ctype)
            return
        self.send_error(404)

    def serve_file(self, path: Path, ctype: str) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("content-type", ctype)
        self.send_header("cache-control", "no-store, max-age=0")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(body or "{}")
        except json.JSONDecodeError:
            payload = {}
        path = urlparse(self.path).path
        trace("ui.request", path=path, method="POST", bytes=length)
        trace("router.enter", path=path)
        actions = {
            "/api/model/start": start_model,
            "/api/model/stop": stop_model,
            "/api/claude/open": open_claude,
            "/api/phone/test": send_phone_test,
            "/api/flint/github": open_flint_github,
        }
        if path in actions:
            self.send_json(actions[path]())
            return
        if path == "/api/chat":
            prompt = str(payload.get("prompt", "")).strip()
            if not prompt:
                self.send_json({"ok": False, "message": "Type a message first."}, 400)
                return
            session_id = normalize_session_id(payload.get("session_id"))
            history = payload.get("history") or SESSION_STORE.messages(session_id)
            SESSION_STORE.append_message(session_id, "user", prompt, metadata={"source": "dashboard"})
            trace("router.chat", prompt=prompt)
            result = route_remote_command(prompt, history)
            SESSION_STORE.append_message(
                session_id,
                "assistant",
                result.get("message", ""),
                status="done" if result.get("ok") else "error",
                metadata={"source": "dashboard", "route": result.get("route")},
            )
            self.send_json(result)
            return
        if path == "/api/chat/stream":
            prompt = str(payload.get("prompt", "")).strip()
            if not prompt:
                self.send_json({"ok": False, "message": "Type a message first."}, 400)
                return
            session_id = normalize_session_id(payload.get("session_id"))
            route = chat_route(prompt)
            trace("router.chat.stream", prompt=prompt, route=route)
            if route in {"fusiondesk_assign", "fusiondesk_default"}:
                trace("router.route", route_selected=route, skipped_local_model=True)
                self.stream_fusiondesk_chat(prompt, session_id)
                return
            history = payload.get("history") or SESSION_STORE.messages(session_id)
            SESSION_STORE.append_message(session_id, "user", prompt, metadata={"source": "dashboard"})
            result = route_remote_command(prompt, history)
            SESSION_STORE.append_message(
                session_id,
                "assistant",
                result.get("message", ""),
                status="done" if result.get("ok") else "error",
                metadata={"source": "dashboard", "route": result.get("route")},
            )
            self.send_json(result)
            return
        if path == "/api/fusiondesk/assign":
            trace("router.fusiondesk.assign_endpoint", route_selected="fusiondesk_assign", skipped_local_model=True)
            result = seat_assignment(payload)
            self.send_json(result, 200 if result.get("ok") else 400)
            return
        if path == "/api/missions":
            trace("router.missions.create", route_selected="mission_runtime", skipped_local_model=True)
            result = mission_response(payload)
            self.send_json(result, 200 if result.get("ok") else 400)
            return
        if path == "/api/command":
            prompt = str(payload.get("prompt", "")).strip()
            session_id = normalize_session_id(payload.get("session_id"))
            if not prompt:
                self.send_json({"ok": False, "message": "Type a command first."}, 400)
                return
            SESSION_STORE.append_message(session_id, "user", prompt, metadata={"source": "dashboard-command"})
            result = route_remote_command(prompt, SESSION_STORE.messages(session_id))
            SESSION_STORE.append_message(
                session_id,
                "assistant",
                result.get("message", ""),
                status="done" if result.get("ok") else "error",
                metadata={"source": "dashboard-command", "route": result.get("route")},
            )
            self.send_json(result)
            return
        if path == "/api/session/clear":
            session_id = normalize_session_id(payload.get("session_id"))
            SESSION_STORE.clear(session_id)
            self.send_json({"ok": True, "message": "Session cleared.", "session_id": session_id})
            return
        if path == "/api/trademaster/review":
            self.send_json(run_trademaster_review(payload))
            return
        self.send_error(404)


def main() -> None:
    start_telegram_service()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Claude Stack Dashboard: http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
