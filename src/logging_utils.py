"""Structured JSON-lines telemetry for tool calls."""

from __future__ import annotations

import json
import inspect
import threading
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, TypeVar

from src.config import LOG_PATH

F = TypeVar("F", bound=Callable[..., Any])
_write_lock = threading.Lock()


def log_tool_call(name: str, args: dict[str, Any], result: Any, latency_ms: float) -> None:
    """Append one structured tool event without writing sensitive prompt data."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(result, dict):
        summary: Any = result
    else:
        summary = str(result)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": name,
        "args": args,
        "result_summary": summary,
        "latency_ms": round(latency_ms, 2),
    }
    with _write_lock, LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def logged_tool(name: str) -> Callable[[F], F]:
    """Log successful and failed tool executions with elapsed time."""

    def decorate(function: F) -> F:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            try:
                bound = inspect.signature(function).bind_partial(*args, **kwargs)
                bound.apply_defaults()
                tool_args = bound.arguments
            except (TypeError, ValueError):
                tool_args = {"args": args, "kwargs": kwargs}
            try:
                result = function(*args, **kwargs)
            except Exception as exc:
                log_tool_call(
                    name,
                    tool_args,
                    {"error": str(exc)},
                    (time.perf_counter() - started) * 1000,
                )
                raise
            log_tool_call(
                name,
                tool_args,
                result,
                (time.perf_counter() - started) * 1000,
            )
            return result

        return wrapped  # type: ignore[return-value]

    return decorate
