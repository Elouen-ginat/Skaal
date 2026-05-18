from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from skaal.settings import LogFormat, LoggingSettings, get_settings, reset_settings_cache

_LEVEL_NAMES = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}
_RESERVED_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__)


class TextLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.name == "skaal.cli":
            if record.levelno <= logging.INFO:
                return message
            return f"{record.levelname:<7} {message}"

        timestamp = datetime.fromtimestamp(record.created, tz=UTC).strftime("%H:%M:%S")
        if record.levelno == logging.INFO and record.name.startswith("skaal.deploy"):
            message = f"==> {message}"
        return f"{timestamp} {record.levelname:<7} {record.name:<22} {message}"


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_FIELDS or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _parse_level(value: str | None) -> int | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return _LEVEL_NAMES.get(normalized)


def _resolve_format(override: LogFormat | None, logging_cfg: LoggingSettings) -> LogFormat:
    if override is not None:
        return override
    return logging_cfg.format


def _resolve_root_level(verbose: int, quiet: bool, logging_cfg: LoggingSettings) -> int:
    if quiet:
        return logging.ERROR
    if verbose >= 2:
        return logging.DEBUG
    if verbose == 1:
        return logging.INFO
    config_level = _parse_level(logging_cfg.level)
    if config_level is not None:
        return config_level
    return logging.WARNING


def _default_child_level(root_level: int) -> int:
    if root_level >= logging.ERROR:
        return root_level
    if root_level <= logging.INFO:
        return root_level
    return logging.INFO


def _build_handler(fmt: LogFormat) -> logging.Handler:
    handler = logging.StreamHandler()
    handler.setLevel(logging.NOTSET)
    if fmt == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(TextLogFormatter())
    return handler


def configure_cli_logging(*, verbose: int, quiet: bool, fmt: LogFormat | None) -> None:
    # Re-read settings on every CLI entry so env-var changes between
    # invocations (notably in tests) take effect.
    reset_settings_cache()
    logging_cfg = get_settings().resolved_logging

    resolved_format = _resolve_format(fmt, logging_cfg)
    root_level = _resolve_root_level(verbose, quiet, logging_cfg)
    child_level = _default_child_level(root_level)

    skaal_logger = logging.getLogger("skaal")
    skaal_logger.handlers = [
        handler for handler in skaal_logger.handlers if isinstance(handler, logging.NullHandler)
    ]
    skaal_logger.addHandler(_build_handler(resolved_format))
    skaal_logger.setLevel(root_level)
    skaal_logger.propagate = False

    logging.getLogger("skaal.cli").setLevel(child_level)
    logging.getLogger("skaal.deploy").setLevel(child_level)

    for logger_name, level_name in logging_cfg.loggers.items():
        level = _parse_level(level_name)
        if level is not None:
            logging.getLogger(logger_name).setLevel(level)


__all__ = [
    "JsonLogFormatter",
    "LogFormat",
    "TextLogFormatter",
    "configure_cli_logging",
]
