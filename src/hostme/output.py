from __future__ import annotations

import json
import sys

from rich.console import Console

console = Console()
err_console = Console(stderr=True)

_json_mode = False


def set_json_mode(enabled: bool) -> None:
    global _json_mode
    _json_mode = enabled


def is_json_mode() -> bool:
    return _json_mode


def success(message: str, **fields: object) -> None:
    if _json_mode:
        console.print_json(data={"ok": True, "message": message, **fields})
    else:
        console.print(f"[green]✔[/green] {message}")


def info(message: str, **fields: object) -> None:
    if _json_mode:
        console.print_json(data={"ok": True, "message": message, **fields})
    else:
        console.print(message)


def error(message: str, **fields: object) -> None:
    if _json_mode:
        err_console.print(json.dumps({"ok": False, "error": message, **fields}, ensure_ascii=False))
    else:
        err_console.print(f"[red]✖[/red] {message}")
    sys.exit(1)
