"""Команды над сайтом: деплой и `hostme <domain> <subcommand>`.

Регистрируются на root-app в cli.py; реальный порядок аргументов (домен/путь
первым) обеспечивает cli._translate_argv, поэтому первая строка каждого
docstring показывает именно его, а не Click-овский `hostme teardown DOMAIN`.
"""

from __future__ import annotations

import webbrowser
from typing import Annotated

import typer

from hostme import config, output
from hostme.core import services

ConfirmOption = Annotated[
    bool,
    typer.Option(
        "--confirm",
        "--yes",
        "-y",
        help="Подтвердить деструктивное действие без вопроса (обязателен вместе с --non-interactive/--json).",
    ),
]

DomainArg = Annotated[str, typer.Argument(help="Домен сайта из `hostme list`.")]


@output.guard
def deploy(
    ctx: typer.Context,
    path: Annotated[str, typer.Argument(help="Локальная папка с готовым сайтом (dist/build/public).")],
    domain: Annotated[str | None, typer.Argument(help="Домен; без него — <slug-папки>.<default-домен>.")] = None,
    server_name: Annotated[str | None, typer.Option("--server", help="Сервер из `hostme server list`.")] = None,
    target_name: Annotated[
        str | None, typer.Option("--target", help="Сторонний хостинг из `hostme target list` (домен обязателен).")
    ] = None,
    confirm: ConfirmOption = False,
    rebind: Annotated[
        bool,
        typer.Option("--rebind", help="Это тот же сайт из другой папки: перепривязать домен к ней (для CI)."),
    ] = False,
) -> None:
    """hostme <path> [domain] [--server NAME | --target NAME] [--rebind] — задеплоить папку (без слова "deploy").

    На свой сервер: создаёт сайт в Webinoly при первом деплое (html или php —
    по наличию *.php), включает SSL, заливает rsync --delete в новый релиз и
    переключает symlink — предыдущие релизы остаются для `rollback`.
    На --target: только заливка файлов (rsync или lftp mirror) с локальным
    бэкапом перед ней; сторонний хостинг — требует --confirm на каждый вызов.
    Webroot становится точным зеркалом папки: лишние файлы на сервере удаляются.
    Домен привязан к папке первого деплоя: из другой папки — отказ, пока не
    передан --rebind (CI собирает в новом checkout'е каждый раз).

    Example: hostme ./dist landing.example.com
    """
    result = services.deploy(ctx, path, domain, server_name, target_name, confirm, rebind)
    output.success(ctx, result.pop("message"), **result)


@output.guard
def list_(ctx: typer.Context) -> None:
    """hostme list — все сайты из реестра (+ служебные домены без деплоя, помечены отдельно).

    Example: hostme list --json
    """

    def render(d: dict) -> None:
        if not d["sites"]:
            output.console.print("Сайтов пока нет.")
            return
        for s in d["sites"]:
            if s["base_domain"]:
                output.console.print(
                    f"https://{s['domain']}  [служебный домен, без деплоя через hostme]  {s['server']}"
                )
            else:
                kind = "php" if s["php"] else "html"
                output.console.print(f"https://{s['domain']}  [{kind}]  {s['server']}  {s['deployed_at'] or ''}")

    sites, bare_base_domains = services.list_sites()
    output.emit_success(
        ctx,
        {
            "sites": [
                {
                    "domain": s.domain,
                    "server": s.server,
                    "php": s.php,
                    "deployed_at": s.deployed_at,
                    "base_domain": False,
                }
                for s in sites
            ]
            + [
                {"domain": name, "server": server_name, "php": None, "deployed_at": None, "base_domain": True}
                for name, server_name in bare_base_domains
            ]
        },
        render_human=render,
    )


@output.guard
def open_(ctx: typer.Context, domain: DomainArg) -> None:
    """hostme open <domain> — открыть https://<domain> в браузере по умолчанию.

    Example: hostme open landing.example.com
    """
    webbrowser.open(f"https://{domain}")
    output.success(ctx, f"Открываю https://{domain}", domain=domain)


@output.guard
def revs(ctx: typer.Context, domain: DomainArg) -> None:
    """hostme <domain> revs — список релизов сайта на сервере (для rollback/rollfore).

    Example: hostme landing.example.com revs
    """

    def render(d: dict) -> None:
        if not d["releases"]:
            output.console.print("Релизов пока нет.")
            return
        for r in d["releases"]:
            output.console.print(f"{r}{' (current)' if r == d['current'] else ''}")

    domain = config.normalize_domain(domain)
    output.emit_success(ctx, services.get_revisions(domain), render_human=render)


@output.guard
def rollback(ctx: typer.Context, domain: DomainArg, confirm: ConfirmOption = False) -> None:
    """hostme <domain> rollback [--confirm] — откатить на предыдущий релиз (сервер) или последний локальный бэкап (target).

    Обратимо: на сервере это переключение symlink (`rollfore` вернёт обратно),
    на target — восстановление снепшота, снятого перед последним деплоем.
    --dry-run показывает, на какой релиз откатился бы.

    Example: hostme landing.example.com rollback --confirm
    """
    domain = config.normalize_domain(domain)
    result = services.rollback(ctx, domain, confirm)
    output.success(ctx, result.pop("message"), **result)


@output.guard
def rollfore(ctx: typer.Context, domain: DomainArg) -> None:
    """hostme <domain> rollfore — вернуть сайт на следующий (после rollback) релиз. Только для своих серверов.

    Example: hostme landing.example.com rollfore
    """
    domain = config.normalize_domain(domain)
    result = services.rollfore(domain)
    output.success(ctx, result.pop("message"), **result)


@output.guard
def maintenance(ctx: typer.Context, domain: DomainArg, confirm: ConfirmOption = False) -> None:
    """hostme <domain> maintenance [--confirm] — очистить сайт, оставив встроенный плейсхолдер «в разработке».

    Содержимое не теряется: на сервере это новый релиз (откат — `rollback`),
    на target — снимается бэкап перед заливкой. --dry-run показывает план.

    Example: hostme landing.example.com maintenance --confirm
    """
    domain = config.normalize_domain(domain)
    result = services.set_maintenance(ctx, domain, confirm)
    output.success(ctx, result.pop("message"), **result)


@output.guard
def teardown(ctx: typer.Context, domain: DomainArg, confirm: ConfirmOption = False) -> None:
    """hostme <domain> teardown [--confirm] — снести сайт (файлы + SSL) и убрать из реестра. Необратимо.

    На сервере удаляет сайт из Webinoly со всеми релизами; на target — файлы
    в remote_path. --dry-run показывает, что было бы удалено.

    Example: hostme landing.example.com teardown --confirm
    """
    domain = config.normalize_domain(domain)
    result = services.teardown(ctx, domain, confirm)
    output.success(ctx, result.pop("message"), **result)


@output.guard
def auth(
    ctx: typer.Context,
    domain: DomainArg,
    user: Annotated[str | None, typer.Option("--user", help="Логин для HTTP Basic Auth.")] = None,
    password: Annotated[str | None, typer.Option("--pass", help="Пароль (локально не хранится).")] = None,
    off: Annotated[bool, typer.Option("--off", help="Снять защиту паролем.")] = False,
) -> None:
    """hostme <domain> auth --user U --pass P | --off — password protection (HTTP Basic Auth). Только свои серверы.

    Example: hostme landing.example.com auth --user admin --pass s3cret
    """
    domain = config.normalize_domain(domain)
    result = services.set_http_auth(domain, user, password, off)
    output.success(ctx, result.pop("message"), **result)


def _render_site_config(d: dict) -> None:
    output.console.print(f"domain: {d['domain']}")
    output.console.print(f"server: {d['server']}")
    output.console.print(f"php: {d['php']}")
    output.console.print(f"ssl: {d['ssl']}  (force-https: всегда включён вместе с SSL, см. docs/webinoly.md)")
    output.console.print(f"cors: {', '.join(d['cors']) or '(нет)'}")
    if d["redirects"]:
        for r in d["redirects"]:
            output.console.print(f"redirect: {r['from']} -> {r['to']}")
    else:
        output.console.print("redirects: (нет)")
    output.console.print(f"password_protect: {d['password_protect'] or '(выкл)'}")


@output.guard
def site_config(
    ctx: typer.Context,
    domain: DomainArg,
    cors: Annotated[list[str], typer.Option("--cors", help="Разрешённый CORS-origin (повторяемый).")] = [],  # noqa: B006
    no_cors: Annotated[bool, typer.Option("--no-cors", help="Убрать CORS.")] = False,
    redirect: Annotated[list[str], typer.Option("--redirect", help="Редирект FROM=TO (повторяемый).")] = [],  # noqa: B006
    remove_redirect: Annotated[list[str], typer.Option("--remove-redirect", help="Убрать редирект FROM.")] = [],  # noqa: B006
    force_https: Annotated[
        bool, typer.Option("--force-https", help="Принудительный HTTPS — у Webinoly и так всегда включён с SSL.")
    ] = False,
    no_force_https: Annotated[
        bool, typer.Option("--no-force-https", help="Не поддерживается: Webinoly не отключает редирект на HTTPS.")
    ] = False,
    nginx_snippet: Annotated[
        str | None, typer.Option("--nginx-snippet", help="Локальный .conf → кастомный nginx-сниппет сайта.")
    ] = None,
    no_nginx_snippet: Annotated[bool, typer.Option("--no-nginx-snippet", help="Убрать кастомный сниппет.")] = False,
) -> None:
    """hostme <domain> config [--cors ORIGIN ...] [--redirect FROM=TO] [--nginx-snippet PATH] ... — настройки сайта; без флагов печатает текущие.

    Только свои серверы (Webinoly). Все изменения обратимы соответствующим
    --no-*/--remove-* флагом.

    Example: hostme landing.example.com config --redirect /old=/new
    """
    domain = config.normalize_domain(domain)
    result = services.update_site_config(
        domain, cors, no_cors, redirect, remove_redirect, force_https, no_force_https, nginx_snippet, no_nginx_snippet
    )
    if result["message"] is None:
        site: config.Site = result["site"]
        output.emit_success(
            ctx,
            {
                "domain": site.domain,
                "server": site.server,
                "php": site.php,
                "ssl": site.ssl,
                "force_https": site.force_https,
                "cors": site.cors,
                "redirects": site.redirects,
                "password_protect": site.password_protect,
            },
            render_human=_render_site_config,
        )
        return
    output.success(ctx, result["message"], domain=domain)


@output.guard
def debug(
    ctx: typer.Context,
    domain: DomainArg,
    error: Annotated[bool, typer.Option("--error", help="Хвост error-лога вместо access-лога.")] = False,
    lines: Annotated[int, typer.Option("--lines", help="Сколько строк лога.")] = 10,
) -> None:
    """hostme <domain> debug [--error] [--lines N] — HTTP-статус сайта + хвост nginx-лога с сервера.

    Example: hostme landing.example.com debug --error --lines 50
    """

    def render(d: dict) -> None:
        output.console.print(f"https://{d['domain']} -> {d['http_status']}")
        output.console.print(f"--- {'error' if error else 'access'} log (последние {lines}) ---")
        output.console.print(d["log"] or "(пусто)")

    domain = config.normalize_domain(domain)
    output.emit_success(ctx, services.get_debug_info(domain, error, lines), render_human=render)
