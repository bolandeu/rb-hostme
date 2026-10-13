from __future__ import annotations

from importlib.resources import files


def load_skill_doc() -> str:
    return (files("hostme.data") / "SKILL.md").read_text(encoding="utf-8")


def load_nginx_defaults() -> str:
    return (files("hostme.data") / "nginx-defaults.conf").read_text(encoding="utf-8")
