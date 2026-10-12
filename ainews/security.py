"""Redact credentials before storing diagnostic text or writing task logs."""
from __future__ import annotations

import re

_CREDENTIALS = re.compile(
    r"(?:(?<![0-9])\d{7,12}:[A-Za-z0-9_-]{30,50}|(?<![\w-])(?:"
    r"gh[pousr]_[A-Za-z0-9]{30,255}|github_pat_[A-Za-z0-9_]{40,255}|"
    r"sk-(?:proj-|ant-)?[A-Za-z0-9_-]{24,255}|hf_[A-Za-z0-9]{25,255}|"
    r"AIza[A-Za-z0-9_-]{30,50}))(?![\w-])"
)
_URL_AUTH = re.compile(r"(https?://)[^\s/@]+@", re.I)
_QUERY_SECRET = re.compile(
    r"([?&](?:token|key|api[_-]?key|api[_-]?hash|access[_-]?token|secret|password)=)[^&#\s]+", re.I
)
_AUTH_HEADER = re.compile(r"(\b(?:Bearer|Basic)\s+)[A-Za-z0-9_+/=.-]+", re.I)


def redact(value: object, *, secrets: tuple[str, ...] = ()) -> str:
    text = str(value)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = _CREDENTIALS.sub("[REDACTED]", text)
    text = _URL_AUTH.sub(r"\1[REDACTED]@", text)
    text = _QUERY_SECRET.sub(r"\1[REDACTED]", text)
    return _AUTH_HEADER.sub(r"\1[REDACTED]", text)


def safe_error(exc: Exception) -> str:
    return redact(f"{type(exc).__name__}: {exc}")
