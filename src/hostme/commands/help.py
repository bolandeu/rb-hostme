"""`hostme help` — полный справочник с реальной surge-грамматикой вызова.

Click-овский список Commands показывает `teardown`/`config`/`auth` так, будто их
зовут первыми — это не так (домен первым). Этот справочник (и его --json-вид) —
то, на что ссылается bundled SKILL.md как на источник правды. Держать в синхроне
с реально реализованными командами.
"""

from __future__ import annotations

from hostme import output

GRAMMAR_NOTE = """
ВАЖНО про форму команд (не как в обычном Typer/Click-CLI, а как у surge.sh):

  hostme <path> [domain] [--server NAME]     — деплой (БЕЗ слова "deploy")
  hostme <domain> <subcommand> [...]         — управление сайтом (ДОМЕН ПЕРВЫМ)

Первая строка описания каждой команды показывает её реальную форму вызова:
`hostme mydomain.com teardown`, а не `hostme teardown mydomain.com` (Click в
Usage нарисует второе — не верить). Полный справочник с примерами — `hostme help`
(`hostme help --json` для агентов).
"""

# Полный справочник — источник и для `hostme help` (человеку/агенту без доступа к
# репозиторию), и для README/Claude Code skill'а поверх hostme (PRD раздел 2).
# Если команда здесь есть, она должна работать; чего нет в MVP, помечено явно.
_COMMAND_REFERENCE: list[tuple[str, str]] = [
    ("hostme <path> [domain] [--server NAME]", "деплой/обновление сайта (без слова deploy)"),
    ("hostme <domain> teardown [--confirm]", "снести сайт на сервере и убрать из реестра"),
    ("hostme <domain> config", "показать настройки сайта"),
    ("hostme <domain> config --redirect FROM=TO", "добавить/обновить redirect"),
    ("hostme <domain> config --remove-redirect FROM", "убрать redirect"),
    ("hostme <domain> config --cors ORIGIN [--cors ORIGIN ...]", "задать список разрешённых CORS-origin'ов"),
    ("hostme <domain> config --no-cors", "убрать CORS"),
    (
        "hostme <domain> config --nginx-snippet PATH",
        "залить произвольный локальный .conf как кастомный nginx-сниппет сайта",
    ),
    ("hostme <domain> config --no-nginx-snippet", "убрать кастомный nginx-сниппет"),
    ("hostme <domain> auth --user U --pass P", "включить password protection (HTTP Basic Auth)"),
    ("hostme <domain> auth --off", "выключить password protection"),
    ("hostme <domain> debug [--error] [--lines N]", "HTTP-статус + хвост access/error-лога"),
    ("hostme <domain> revs", "список релизов сайта (для rollback/rollfore)"),
    ("hostme <domain> rollback [--confirm]", "откатить сайт на предыдущий релиз"),
    ("hostme <domain> rollfore", "вернуть сайт на следующий (после rollback) релиз"),
    (
        "hostme <domain> maintenance [--confirm]",
        "очистить сайт, оставив встроенный плейсхолдер «в разработке»; старое содержимое не теряется — откат через rollback",
    ),
    ("hostme list", "таблица сайтов из реестра + служебные домены без деплоя через hostme (помечены отдельно)"),
    ("hostme open <domain>", "открыть сайт в браузере"),
    ("hostme doctor", "проверка окружения/конфига (бинари, права, ключи) без обращения к серверам"),
    (
        "hostme auth status [--check] [--provider server:N|target:N]",
        "откуда берутся доступы к серверам/target'ам и работают ли (exit 3 — проблема); значения не печатаются",
    ),
    ("hostme server add --name N --host H --user U [--key PATH] [--default]", "зарегистрировать сервер"),
    ("hostme server init <name>", "поставить/проверить Webinoly на сервере"),
    ("hostme server update <name>", "обновить сам Webinoly на сервере (не пакеты)"),
    ("hostme server list", "таблица серверов"),
    ("hostme server remove <name> [--force]", "убрать сервер из реестра"),
    ("hostme domain add <server> <domain> [--default]", "зарегистрировать служебный (base) домен"),
    ("hostme domain default <domain>", "сделать домен дефолтным (для авто-генерации поддоменов)"),
    ("hostme domain list", "таблица служебных доменов"),
    ("hostme domain remove <domain>", "убрать служебный домен из реестра"),
    (
        "hostme target add --name N --connection ssh|ftp|sftp --host H --user U [--password P] [--ssh-key PATH] [--path REMOTE]",
        "зарегистрировать сторонний хостинг (не Webinoly — просто заливка файлов)",
    ),
    ("hostme target list", "таблица target'ов"),
    ("hostme target remove <name> [--force]", "убрать target из реестра"),
    (
        "hostme skill install [--path PATH]",
        "записать bundled SKILL.md туда, откуда его читает AI-агент (по умолчанию ~/.claude/skills/hostme/SKILL.md)",
    ),
    ("hostme --ai", "напечатать bundled SKILL.md в stdout (для агента без доступа к файлам на диске) и выйти"),
    (
        "hostme <path> <domain> --target NAME [--confirm]",
        (
            "деплой на target вместо Webinoly-сервера (домен обязателен явно, нет base-доменов у target'ов); "
            "требует --confirm или интерактивного подтверждения — сторонний хостинг, --json НЕ пропускает молча"
        ),
    ),
    (
        "hostme <domain> teardown --confirm / rollback --confirm / maintenance --confirm",
        "деструктивные команды (свой сервер и target одинаково) требуют --confirm (алиас --yes/-y) в неинтерактивном режиме (--json/--non-interactive) — не пропускают молча",
    ),
    ("--json (в любой позиции — до и после команды)", "чистый JSON вместо rich-вывода, без цвета — для агентов"),
    (
        "--non-interactive (в любой позиции)",
        "никогда не спрашивать подтверждение — упасть понятной ошибкой вместо этого, если оно нужно",
    ),
    ("--dry-run (в любой позиции)", "показать, что сделала бы деструктивная команда, ничего не меняя"),
]

_NOT_IMPLEMENTED_NOTE = (
    "Не реализовано в MVP: `hostme <domain> ssl` (подстановка своего сертификата), "
    "`hostme <domain> discard` (нет аналога — у нас нет preview-концепции), wildcard SSL "
    "изнутри hostme (делается вручную по WILDCARD-SSL.md — DNS-01 требует ручного шага "
    "с DNS-провайдером), git push-to-deploy, -proxy= сайты (вне скоупа — только html/php/статика). "
    "Для сайтов на target (сторонний хостинг): `auth`/`config`/`ssl`/`debug`/`revs`/`rollfore` "
    "не поддерживаются вовсе (Webinoly-специфичны) — только deploy/list/open/teardown/rollback. "
    "ВАЖНО для агентов: deploy/teardown/rollback на target — это чужая/стороннняя инфраструктура, "
    "не собственный VPS пользователя. Такое действие требует явного --confirm (или интерактивного "
    "подтверждения) НА КАЖДЫЙ конкретный вызов; --json НЕ пропускает это подтверждение молча "
    "(в отличие от teardown на своём сервере) — агент не должен передавать --confirm сам по себе, "
    "не получив явного «да» от человека на именно это действие прямо сейчас."
)


@output.guard
def help_cmd() -> None:
    """hostme help — полный справочник команд с реальным порядком аргументов (--json для агентов).

    Example: hostme help --json
    """

    def render(d: dict) -> None:
        # markup=False обязателен: в usage-строках полно "[domain]"/"[--server NAME]" —
        # без этого Rich принимает квадратные скобки за markup-теги и съедает текст внутри.
        output.console.print("hostme — деплой сайтов на свои VPS (аналог surge.sh).\n", markup=False)
        output.console.print(GRAMMAR_NOTE.strip(), markup=False)
        output.console.print()
        width = max(len(c["usage"]) for c in d["commands"])
        for c in d["commands"]:
            output.console.print(f"  {c['usage'].ljust(width)}  {c['description']}", markup=False)
        output.console.print(f"\n{d['not_implemented']}", markup=False)

    output.emit_success(
        {
            "commands": [{"usage": usage, "description": desc} for usage, desc in _COMMAND_REFERENCE],
            "not_implemented": _NOT_IMPLEMENTED_NOTE,
        },
        render_human=render,
    )
