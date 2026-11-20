# AGENTS.md

- The package Standard: https://github.com/bolandeu/python-package-gate/blob/main/skills/cli-builder/reference/standard.md (sections by name, for example «Install»).
- The gate before a commit: `gate check`, on this machine (Standard, CI). It is the only gate: no workflow runs it.

Инструкции для AI-агентов (Claude Code и т.п.), работающих в этом репозитории.

## Что это за проект

`hostme` — личный аналог surge.sh: CLI на Python/uv, который деплоит статические сайты и простые PHP-скрипты на собственные VPS (через [Webinoly](https://webinoly.com/)) одной командой, с поддержкой нескольких серверов и доменов. Что это за продукт и чего он не делает — **[docs/usage/product.md](docs/usage/product.md)**, читать первым для любой содержательной работы над проектом.

Дальше по важности:
- **[docs/usage/](docs/usage/)** — живая документация по темам: серверы и домены, настройки и реестр, контракт для агента, безопасность, команды Webinoly и процедура wildcard SSL.
- **[docs/research/](docs/research/)** — что и когда выяснилось на живой инфраструктуре (баги Webinoly, DNS Beget, форма команд surge.sh, SSH rate-limit).
- **[docs/adr/](docs/adr/)** — решения и их причины (тех-стек, хранение вне репозитория, секреты, форма команд, wildcard и SSH).
- План и прогресс — не файл в репозитории, а Antagor: идеи (`antagor idea list`), задачи и эпики (`.agents/antagor/`), доска (`antagor board`). Файл-бэклог в репозитории не заводить: он расходится с кодом.

## Skill для агентов (`~/.claude/skills/hostme/`)

Существует **глобальный** (не в этом репозитории) Claude Code skill `hostme` — `~/.claude/skills/hostme/SKILL.md`. Он не про разработку самого `hostme`, а про его *использование* другими агентами в других проектах, которым нужно задеплоить артефакт (см. [docs/usage/product.md](docs/usage/product.md)). Источник правды — **`src/rb_hostme/data/SKILL.md`** в этом репозитории (bundled в пакет; `hostme --ai` печатает его, `hostme skill install` копирует в `~/.claude/skills/hostme/`). Если меняется CLI-грамматика (`_translate_argv` в `cli.py`), `hostme help --json`, или общее поведение `--json`/`--confirm`/exit-кодов — править bundled-копию и после установки перезапускать `hostme skill install`; глобальную копию руками не редактировать. Skill намеренно тонкий: не дублирует список команд (его даёт голый `hostme` из docstring'ов команд), только конвенции и неочевидную грамматику.

## Проверенные на практике факты о Webinoly (не гадать, не перепроверять с нуля)

Что не про Webinoly, а про сам `hostme`/процесс работы над ним:

- Текущее состояние (какие серверы/домены/сайты реально зарегистрированы и задеплоены) — **не хранить статикой в этом файле, оно меняется**: смотреть `hostme server list` / `hostme domain list` / `hostme list` (агент сам восстановит картину через сам инструмент, когда понадобится).

## Тестирование (не обязательно — приоритет на скорость)

- Уже существующие тесты (`tests/unit/`, `tests/e2e/`) не удалять — они рабочие и уже ловили реальные баги (права `www-data`, формат `sudo site -list`), просто не наращивать этот объём без явного запроса. Порог покрытия — `fail_under` в `pyproject.toml`; цифру в тексте не держать, она менялась.
- Если всё же пишешь e2e — команда запуска не изменилась: `HOSTME_E2E_HOST=... HOSTME_E2E_USER=root HOSTME_E2E_BASE_DOMAIN=antagorapp.ru uv run pytest -m e2e` (по умолчанию скипается, см. `tests/conftest.py`).

## Безопасность / что нельзя коммитить

- `~/.config/hostme/*.yaml` (реестр серверов/сайтов, будущее состояние инструмента) — вне репозитория по дизайну ([ADR 0003](docs/adr/0003-settings-and-state-outside-the-repository.md)), туда не заглядывать при коммитах.
- Реестр в `~/.config/hostme` и `user_data_dir("hostme")` — живые данные владельца, а не песочница. Тесты и прогоны их не трогают: работа с реестром из кода — только read-modify-write (`load_sites` → изменить → `save_sites`), никогда запись файла целиком собранным в тесте списком. Так уже терялись реальные записи `sites.yaml`.
- Итоги секьюрити-ревью (права на конфиг, хранение `ssh_key`/пароля, принятые риски) — **[docs/usage/security.md](docs/usage/security.md)**, не дублировать здесь.

## Архитектура (cli-builder) и проверка

Пакет следует архитектуре cli-builder (Standard — ссылка выше) — см. README «Разработка». Коротко, что где:
- `commands/` — только разбор аргументов → один вызов сервиса → `output.success`/`output.emit_success`. Docstring команды = её `--help`; первая строка показывает реальную surge-форму вызова (`hostme <domain> teardown [--confirm]`).
- `core/services.py` — бизнес-логика; `core/errors.py` — подклассы `CliError` и таблица exit-кодов (`INVALID_ARGUMENTS` 2, `CREDENTIALS_UNHEALTHY` 3, `PROVIDER_ERROR` 5, `ERROR`/`ABORTED`/`UNEXPECTED` 1); `core/version.py`.
- `providers/` — ssh/rsync/lftp/Webinoly/HTTP-проба: единственное место с `subprocess`/`urllib`; ошибки наружу только как `ProviderError`.
- `output/` — human/json-вывод, `guard` (на каждой команде, команда получает `ctx` первым), `group`, `require_confirmation` (гейт `--confirm`, `--yes`/`-y` — алиасы). Режимы `--json/--quiet/--verbose/--non-interactive/--dry-run` — в `ctx.obj`; сервисам, которым они нужны, команда передаёт `ctx`.
- `credentials/manager.py` — пароли target'ов: сначала env `HOSTME_DEPLOY_<NAME>_PASSWORD`, потом OS keychain `hostme:<name>` (keychain необязателен — на headless-сервере его нет, это не ошибка); в `servers.yaml` секретов нет. `credentials/health.py` — `hostme auth status` (стандарт §8): запись `server:<имя>` (ssh-ключ, файл) и `target:<имя>` на каждый объект реестра; проверки `--check` — в `providers/ssh.py`/`ftp.py` (`check_*`, 10 с).
- Настройки — `~/.config/hostme` (путь одинаков на macOS и Linux); состояние (`sites.yaml`, `sites.d/`, `target-backups/`) — `platformdirs.user_data_dir("hostme")` (стандарт §13, [docs/usage/config-and-state.md](docs/usage/config-and-state.md)). Перенос со старого места — `config.migrate_legacy_data()` в root-callback.
- `hostme <domain> auth` (HTTP Basic Auth сайта) внутри называется `http-auth` — имя `auth` занято группой `auth status`; перевод — `_DOMAIN_SUBCOMMAND_TARGETS` в `cli.py`.

## Проверка и релиз

- Перед коммитом — gate: `gate check` на этой машине (команда — `[publish] gate_command` в `.agents/antagor/antagor.toml`; другого гейта нет, workflow его не гоняет) (lock, ruff, ty, pytest с порогом покрытия и снапшотами `--help`, `[[tool.rb.external]]`, сборка колеса, секреты, osv-scanner, правила Standard).
- Версия — только из git-тега `vX.Y.Z` (uv-dynamic-versioning); `version =` в pyproject не добавлять. Дистрибутив `rb-hostme`, команда `hostme`.
- `CHANGELOG.md` пишет `antagor publish`; руками не править.
- Docstring команды = её `--help`: меняешь поведение — меняй docstring в том же коммите, строка `Example: hostme …` обязательна (проверяется по реальному переводу argv). Потом `uv run pytest --snapshot-update` и прочитать diff `tests/snapshots/help/`.
- Новая внешняя программа (`subprocess`/`shutil.which` литералом) — запись в `[[tool.rb.external]]` в pyproject.
- **Каждое видимое изменение выходит релизом** через `antagor publish`: серверы и Mac ставят только из тегов.

## Внутри системы tools

Корневой агент `~/Work/tools/` деплоит hostme на серверы, держит доступы (секрет-менеджер) и бэкапит данные; правила — стандарт §13.

- **Сообщать корневому агенту** (в отчёте, рядом с тегом): новые/переименованные env-переменные и доступы, новые файлы данных или смена путей, зависимость от других tools, breaking-релиз.
- **Headless Linux**: env первым, keychain необязателен; без TTY никаких вопросов (`require_confirmation` падает с подсказкой про `--confirm`); никаких Mac-only путей.
- Настройки: `~/.config/hostme/` (servers.yaml, settings.yaml). Данные: `user_data_dir("hostme")` (macOS `~/Library/Application Support/hostme`, Linux `~/.local/share/hostme`: sites.yaml, sites.d/, target-backups/) и `~/.cache/hostme/ssh-control/` — вне репозитория; сам hostme ничего никуда не синхронизирует.

## Стиль работы над кодом

- Технологии зафиксированы: Python + uv (`uv python pin`), Typer, `ruamel.yaml`, `rich`, SSH/rsync через `subprocess` (не через paramiko/fabric — уважать `~/.ssh/config`). Причина — [ADR 0002](docs/adr/0002-stack-python-uv-typer-and-system-ssh.md).
- Перед началом работы и после неё состояние смотрит Antagor (`antagor board`), а не файл в репозитории. Одна задача — одна ветка и один результат; задачи, идеи и их связь ведёт Antagor.
- Меняешь `[project.scripts]` в `pyproject.toml` — сразу `uv tool install --editable . --force`: editable-режим не перегенерирует launcher, и `hostme` из PATH продолжит звать старый entry point (так однажды день ушёл на «сломанную» surge-грамматику).

## Architect only

A worker does not need this section: Antagor cuts it from the worker's brief.
