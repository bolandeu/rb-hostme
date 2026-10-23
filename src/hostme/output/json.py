"""Machine-readable output: the one function that prints a JSON document to stdout."""

from __future__ import annotations

import json

import typer


def emit(data: dict) -> None:
    # Одна строка на объект (JSONL-совместимо), ensure_ascii=False — сообщения
    # на русском должны читаться в логах агента как текст, а не как \uXXXX.
    # Не через Rich Console: тот переносит длинный текст по словам и ломает JSON.
    typer.echo(json.dumps(data, ensure_ascii=False))
