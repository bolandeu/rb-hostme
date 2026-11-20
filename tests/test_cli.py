"""Helpers to run the CLI in-process, shared by the template's tests (test_skills.py).

hostme's own tests of the CLI as a whole live in tests/unit/test_cli.py.
"""

from __future__ import annotations

import json
import re

from typer.testing import CliRunner

from rb_hostme.cli import app

runner = CliRunner()


def invoke(*args: str, **kwargs):
    return runner.invoke(app, list(args), **kwargs)


def plain(text: str) -> str:
    """The text without ANSI colour codes: CI forces Rich colours the Mac does not."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def invoke_json(*args: str, **kwargs) -> tuple[int, dict]:
    """Run a command with --json and parse stdout — the contract agents rely on."""
    result = invoke(*args, "--json", **kwargs)
    assert result.stdout.strip(), f"no stdout for {args!r}; stderr: {result.stderr}"
    return result.exit_code, json.loads(result.stdout)
