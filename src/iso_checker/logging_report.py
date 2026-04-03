from __future__ import annotations

import json
import logging
import sys
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

import structlog


def configure_logging(level: str, json_stdout: bool) -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    lvl = getattr(logging, level.upper(), logging.INFO)
    common: list[Any] = [
        structlog.contextvars.merge_contextvars,
        timestamper,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
    ]
    if json_stdout:
        common += [structlog.processors.dict_tracebacks, structlog.processors.JSONRenderer()]
        structlog.configure(processors=common, wrapper_class=structlog.make_filtering_bound_logger(lvl))
    else:
        common += [structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())]
        structlog.configure(processors=common, wrapper_class=structlog.make_filtering_bound_logger(lvl))


def mask_pan(pan: str | None) -> str | None:
    if not pan:
        return None
    p = str(pan).strip()
    if len(p) < 10:
        return "***"
    return f"{p[:6]}****{p[-4:]}"


class RunReport:
    """JSONL report + correlation for one TCP session."""

    def __init__(self, session_id: str | None, report_path: Path | None, human_stream: TextIO = sys.stderr) -> None:
        self.session_id = session_id or str(uuid.uuid4())
        self.report_path = report_path
        self.human_stream = human_stream
        self._fp: TextIO | None = None
        if report_path:
            self._fp = report_path.open("a", encoding="utf-8")

    def close(self) -> None:
        if self._fp:
            self._fp.close()
            self._fp = None

    def _write_jsonl(self, event: dict[str, Any]) -> None:
        event = {**event, "session_id": self.session_id, "ts": datetime.now(timezone.utc).isoformat()}
        line = json.dumps(event, ensure_ascii=False) + "\n"
        if self._fp:
            self._fp.write(line)
            self._fp.flush()

    def emit(self, event_type: str, **kwargs: Any) -> None:
        self._write_jsonl({"event": event_type, **kwargs})

    def human(self, msg: str) -> None:
        self.human_stream.write(msg.rstrip() + "\n")
        self.human_stream.flush()


def get_logger(**ctx: Any):
    return structlog.get_logger(**ctx)
