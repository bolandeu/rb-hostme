from __future__ import annotations

from typing import Annotated

import typer

from hostme import output
from hostme.core import services

app = output.group("Синхронизация bundled SKILL.md туда, откуда его читают AI-агенты.")


@app.command("install")
@output.guard
def install(
    path: Annotated[
        str | None,
        typer.Option("--path", help="Куда записать (по умолчанию — ~/.claude/skills/hostme/SKILL.md)."),
    ] = None,
) -> None:
    """hostme skill install [--path PATH] — записать встроенный SKILL.md туда, откуда его читает AI-агент.

    Источник правды — копия внутри установленного пакета (`hostme --ai` печатает
    её же); после обновления hostme перезапусти, чтобы установленный skill не
    расходился с реальным CLI.
    """
    result = services.install_skill(path)
    output.success(result.pop("message"), **result)
