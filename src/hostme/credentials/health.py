"""Отчёт `hostme auth status [--check] --json` (tools/docs/standard-release.md §8).

Форма — межинструментальный контракт (`tools-watch` читает её у всех CLI, ничего
не зная о провайдерах), закреплена tests/unit/test_auth.py; её изменение — breaking.

Доступы у hostme — per-target (одна запись на каждый зарегистрированный объект):
- `server:<name>` — свой VPS, доступ по ssh-ключу (файл из servers.yaml);
- `target:<name>` — сторонний хостинг: пароль (env HOSTME_DEPLOY_<TARGET>_PASSWORD, иначе
  keychain `hostme:<target>`) или ssh-ключ (файл).
Значения секретов отсюда не выходят — только для вычистки из сообщений.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from rich.markup import escape

from hostme import config, output
from hostme.core.errors import CredentialsUnhealthyError, InvalidArgumentsError
from hostme.credentials import manager
from hostme.providers import ftp, ssh

CHECK_TIMEOUT = 10.0  # секунд на одну проверку (стандарт §8), без повторов
ALWAYS_PROBLEMS = frozenset({"invalid", "expired"})
HEALTHY = frozenset({"ok", "unchecked"})

Probe = Callable[[], tuple[str, str | None]]


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _scrub(message: str | None, secrets: list[str]) -> str | None:
    if message is None:
        return None
    for secret in secrets:
        if secret:
            message = message.replace(secret, "***")
    return message


def _entry(provider: str, fields: list[str]) -> dict:
    return {
        "provider": provider,
        "required": True,
        "fields": fields,
        "source": "missing",
        "source_ref": "",
        "status": "missing",
        "expires_at": None,
        "quota": None,
        "message": None,
    }


def _key_entry(provider: str, key: str) -> tuple[dict, bool]:
    """Запись для доступа по ssh-ключу (source=file). Второе — найден ли ключ."""
    entry = _entry(provider, ["ssh_key"])
    path = Path(key).expanduser()
    entry["source_ref"] = str(path)
    if not path.is_file():
        entry["message"] = f"ключ {path} не найден"
        return entry, False
    entry.update(source="file", status="unchecked")
    return entry, True


def _server_entry(server: config.Server) -> tuple[dict, Probe | None, list[str]]:
    entry, found = _key_entry(f"server:{server.name}", server.ssh_key)
    return entry, (lambda: ssh.check_server(server, CHECK_TIMEOUT)) if found else None, []


def _target_entry(target: config.Target) -> tuple[dict, Probe | None, list[str]]:
    provider = f"target:{target.name}"
    if target.ssh_key:
        entry, found = _key_entry(provider, target.ssh_key)
        return entry, (lambda: ssh.check_target(target, CHECK_TIMEOUT)) if found else None, []

    entry = _entry(provider, ["password"])
    env_name, service = manager.env_var_name(target.name), manager.service_name(target.name)
    located = manager.locate(target.name)
    if located is None:
        entry.update(source_ref=f"{env_name} or keychain service {service}", message="not set: password")
        return entry, None, []
    value, source, where = located
    entry.update(
        source=source,
        source_ref=where if source == "env" else f"keychain service {where}",
        status="unchecked",
    )
    if target.connection == "ssh":
        return entry, lambda: ssh.check_target(target, CHECK_TIMEOUT), [value]
    return entry, lambda: ftp.check_target(target, CHECK_TIMEOUT), [value]


def _is_problem(entry: dict) -> bool:
    if entry["status"] in ALWAYS_PROBLEMS:
        return True
    return entry["required"] and entry["status"] not in HEALTHY


def status(tool: str, version: str, *, check: bool, only: str | None) -> tuple[dict, CredentialsUnhealthyError | None]:
    """То, что печатает `auth status`: отчёт и проблема (exit 3), если есть."""
    candidates = [_server_entry(s) for s in config.load_servers()]
    candidates += [_target_entry(t) for t in config.load_targets()]
    if only is not None:
        candidates = [c for c in candidates if c[0]["provider"] == only]
        if not candidates:
            raise InvalidArgumentsError(
                f"Неизвестный провайдер {only!r}",
                action="Формат: server:<имя> или target:<имя> — см. `hostme auth status`.",
            )

    credentials = []
    for entry, probe, secrets in candidates:
        if check and probe is not None:
            probe_status, message = probe()
            entry.update(status=probe_status, message=_scrub(message, secrets))
        credentials.append(entry)

    payload = {"tool": tool, "version": version, "checked_at": _now_iso(), "credentials": credentials}
    problems = {e["provider"]: e["status"] for e in credentials if _is_problem(e)}
    return payload, CredentialsUnhealthyError(problems) if problems else None


def render(payload: dict) -> None:
    """Человеку: строка на запись."""
    if not payload["credentials"]:
        output.console.print("Серверов и target'ов пока нет — проверять нечего.")
    for entry in payload["credentials"]:
        mark = {"ok": "[green]✔[/green]", "unchecked": "[dim]·[/dim]"}.get(entry["status"], "[red]✖[/red]")
        detail = f" — {entry['message']}" if entry["message"] else ""
        line = f"{entry['provider']}: {entry['status']} ({entry['source']}: {entry['source_ref']}){detail}"
        output.console.print(f"{mark} {escape(line)}")
