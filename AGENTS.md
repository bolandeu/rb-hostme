# AGENTS.md

Инструкции для AI-агентов (Claude Code и т.п.), работающих в этом репозитории.

## Что это за проект

`hostme` — личный аналог surge.sh: CLI на Python/uv, который деплоит статические сайты и простые PHP-скрипты на собственные VPS (через [Webinoly](https://webinoly.com/)) одной командой, с поддержкой нескольких серверов и доменов. Полная спецификация — **[PRD.md](PRD.md)**, читай его первым для любой содержательной работы над проектом.

Дальше по важности:
- **[TODO.md](TODO.md)** — детальный план реализации по фазам. Перед тем как писать код, свериться, на какой фазе/пункте мы находимся, и отмечать пункты по мере выполнения.
- **[docs/webinoly.md](docs/webinoly.md)** — полный референс команд Webinoly (устанавливается на серверах). Обращаться сюда, а не гадать/угадывать флаги.
- **[docs/surge-cli.md](docs/surge-cli.md)** — референс команд surge.sh, на форму которых ориентируется CLI `hostme`.
- **[WILDCARD-SSL.md](WILDCARD-SSL.md)** — пошаговая (проверенная вживую) инструкция по выпуску wildcard SSL, плюс раздел с реальными граблями и заметка про будущую автоматизацию через API регистратора/хостинга.

## Skill для агентов (`~/.claude/skills/hostme/`)

Существует **глобальный** (не в этом репозитории) Claude Code skill `hostme` — `~/.claude/skills/hostme/SKILL.md`. Он не про разработку самого `hostme`, а про его *использование* другими агентами в других проектах, которым нужно задеплоить артефакт (раздел 2 PRD). Источник правды — **`src/hostme/data/SKILL.md`** в этом репозитории (bundled в пакет; `hostme --ai` печатает его, `hostme skill install` копирует в `~/.claude/skills/hostme/`). Если меняется CLI-грамматика (`_translate_argv` в `cli.py`), `hostme help --json`, или общее поведение `--json`/`--confirm`/exit-кодов — править bundled-копию и после установки перезапускать `hostme skill install`; глобальную копию руками не редактировать. Skill намеренно тонкий: не дублирует список команд (его даёт голый `hostme` из docstring'ов команд), только конвенции и неочевидную грамматику.

## Проверенные на практике факты о Webinoly (не гадать, не перепроверять с нуля)

Все подтверждённые вживую факты о поведении Webinoly (команды, форматы вывода, найденные баги вроде `open_file_cache`/прав на `releases/`, реальный MVP-путь для SSL) — **в `docs/webinoly.md`, раздел «Итог для Hostme»**. Не дублировать их здесь: этот файл про инструкции агенту, `docs/webinoly.md` — источник истины по самому Webinoly. Wildcard SSL и DNS-пропагация (Beget, шесть NS, диагностика) — отдельно в `WILDCARD-SSL.md`, включая раздел «История: что пошло не так».

Что не про Webinoly, а про сам `hostme`/процесс работы над ним:

- SSH-соединения переиспользуются через `ControlMaster`/`ControlPersist` (`src/hostme/providers/ssh.py`, см. комментарий у `_CONTROL_DIR`) — было поймано на реальном rate-limit/fail2ban от слишком частых коротких подключений подряд.
- Текущее состояние (какие серверы/домены/сайты реально зарегистрированы и задеплоены) — **не хранить статикой в этом файле, оно меняется**: смотреть `hostme server list` / `hostme domain list` / `hostme list` (агент сам восстановит картину через сам инструмент, когда понадобится).

## Тестирование (не обязательно — приоритет на скорость)


- Уже существующие тесты (`tests/unit/`, `tests/e2e/`) не удалять — они рабочие и уже ловили реальные баги (права `www-data`, формат `sudo site -list`), просто не наращивать этот объём без явного запроса.
- Если всё же пишешь e2e — команда запуска не изменилась: `HOSTME_E2E_HOST=... HOSTME_E2E_USER=root HOSTME_E2E_BASE_DOMAIN=antagorapp.ru uv run pytest -m e2e` (по умолчанию скипается, см. `tests/conftest.py`).

## Безопасность / что нельзя коммитить

- `~/.config/hostme/*.yaml` (реестр серверов/сайтов, будущее состояние инструмента) — вне репозитория по дизайну (PRD §8), туда не заглядывать при коммитах.
- API-ключи (например, попытка авторизации в Beget API) — если появятся рабочие креды, хранить вне репозитория, не в `docs/`.
- Итоги секьюрити-ревью (права на конфиг, хранение `ssh_key`/пароля, принятые риски) — **PRD.md §9**, не дублировать здесь.

## Архитектура (cli-builder) и проверка

Пакет следует архитектуре [cli-builder](https://github.com/bolandeu/cli-generator) — см. README «Разработка». Коротко, что где:
- `commands/` — только разбор аргументов → один вызов сервиса → `output.success`/`output.emit_success`. Docstring команды = её `--help`; первая строка показывает реальную surge-форму вызова (`hostme <domain> teardown [--confirm]`).
- `core/services.py` — бизнес-логика; `core/errors.py` — фиксированная таблица кодов (`INVALID_ARGUMENTS` 2, `PROVIDER_ERROR` 5, `ERROR`/`ABORTED`/`UNEXPECTED` 1); `core/version.py`.
- `providers/` — ssh/rsync/lftp/Webinoly/HTTP-проба: единственное место с `subprocess`/`urllib`; ошибки наружу только как `ProviderError`.
- `output/` — human/json-вывод, `guard` (на каждой команде), `group`, `require_confirmation` (гейт `--confirm`, `--yes`/`-y` — алиасы), состояние `--json/--quiet/--verbose/--non-interactive/--dry-run`.
- `credentials/manager.py` — пароли target'ов: сначала env `HOSTME_<NAME>_PASSWORD`, потом OS keychain `hostme:<name>` (keychain необязателен — на headless-сервере его нет, это не ошибка); в `servers.yaml` секретов нет. `credentials/health.py` — `hostme auth status` (стандарт §8): запись `server:<имя>` (ssh-ключ, файл) и `target:<имя>` на каждый объект реестра; проверки `--check` — в `providers/ssh.py`/`ftp.py` (`check_*`, 10 с).
- `~/.config/hostme` оставлен намеренно (PRD §8), без `platformdirs` — осознанное отклонение от шаблона (путь одинаков на macOS и Linux).
- `hostme <domain> auth` (HTTP Basic Auth сайта) внутри называется `http-auth` — имя `auth` занято группой `auth status`; перевод — `_DOMAIN_SUBCOMMAND_TARGETS` в `cli.py`.

## Проверка и релиз (`~/Work/tools/docs/standard-release.md`)

- Перед коммитом — `uv run scripts/release.py --check` (единственный гейт: lock, ruff, ty, pytest с порогом покрытия и снапшотами `--help`, `[[tool.rb.external]]`, фрагмент, сборка колеса, osv-scanner).
- Версия — только из git-тега `vX.Y.Z` (uv-dynamic-versioning); `version =` в pyproject не добавлять. Дистрибутив `rb-hostme`, команда `hostme`.
- Изменение с видимым эффектом — фрагмент `changelog.d/+<slug>.<type>.md` (`uv run towncrier create …`), `CHANGELOG.md` руками не править.
- Docstring команды = её `--help`: меняешь поведение — меняй docstring в том же коммите (pre-commit блокирует), строка `Example: hostme …` обязательна (проверяется по реальному переводу argv). Потом `uv run pytest --snapshot-update` и прочитать diff `tests/snapshots/help/`.
- Новая внешняя программа (`subprocess`/`shutil.which` литералом) — запись в `[[tool.rb.external]]` в pyproject.
- **Каждое видимое изменение выходит релизом**: серверы и Mac ставят только из тегов. Merge в `main` → `uv run scripts/release.py patch|minor|major` → push с `--follow-tags` (с подтверждения) → тег в отчёте.

## Внутри системы tools

Корневой агент `~/Work/tools/` деплоит hostme на серверы, держит доступы (Doppler) и бэкапит данные; правила — стандарт §13.

- **Сообщать корневому агенту** (в отчёте, рядом с тегом): новые/переименованные env-переменные и доступы, новые файлы данных или смена путей, зависимость от других tools, breaking-релиз.
- **Headless Linux**: env первым, keychain необязателен; без TTY никаких вопросов (`require_confirmation` падает с подсказкой про `--confirm`); никаких Mac-only путей.
- Данные: `~/.config/hostme/` (servers.yaml, sites.yaml, sites.d/, target-backups/) и `~/.cache/hostme/ssh-control/` — вне репозитория; сам hostme ничего никуда не синхронизирует.

## Стиль работы над кодом

- Технологии зафиксированы в PRD §8: Python + uv (`uv python pin`), Typer, `ruamel.yaml`, `rich`, SSH/rsync через `subprocess` (не через paramiko/fabric — уважать `~/.ssh/config`).
- Форма CLI-команд копирует surge.sh (`hostme <path> <domain>`, `hostme <domain> teardown` и т.п.) — не изобретать свой стиль команд, сверяться с `docs/surge-cli.md`.
- Перед реализацией любого шага, завязанного на поведение Webinoly, сверяться с `docs/webinoly.md`; если там что-то не сходится с реальностью — перепроверять на `sites-first-beget` и обновлять и `docs/webinoly.md`, и этот файл (секция выше).
- TODO.md — источник истины по прогрессу; отмечать выполненные пункты по ходу работы, а не только в конце.
- **Всегда следовать TODO.md**: перед началом работы — свериться, какой пункт делаем; после завершения пункта — отметить его выполненным в TODO.md и сделать отдельный git-коммит на этот пункт (не накапливать несколько пунктов в один коммит). Если по ходу реализации выясняется, что PRD.md/TODO.md устарели или ошибались в деталях (как уже было с флагами Webinoly) — поправить их в том же коммите, а не оставлять расхождение.
