"""The data files this package ships (the agent skill, the nginx defaults), read through importlib.resources."""

from __future__ import annotations

from importlib.resources import files


def load_nginx_defaults() -> str:
    return (files("hostme.data") / "nginx-defaults.conf").read_text(encoding="utf-8")
