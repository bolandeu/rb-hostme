from __future__ import annotations

from rich.console import Console

# Данные — в stdout, ошибки и диагностика — в stderr, чтобы
# `hostme list > out.txt` никогда не поймал строку «✖ …» как данные.
console = Console()
err_console = Console(stderr=True)
