# hostme

Личный аналог [surge.sh](https://surge.sh/): CLI на Python/uv, который одной командой деплоит статические сайты и простые PHP-скрипты на собственные VPS (через [Webinoly](https://webinoly.com/)), с поддержкой нескольких серверов и доменов.

Полная спецификация — **[PRD.md](PRD.md)**. План реализации — **[TODO.md](TODO.md)**. Для AI-агентов, работающих в этом репозитории — **[AGENTS.md](AGENTS.md)**.

## Установка

На любой другой машине (репозиторий приватный — нужен `gh auth login`,
который настраивает git credential helper; на машине без интерактивного
логина — `gh auth setup-git`, или SSH-форма ниже):

```
uv tool install "rb-hostme @ git+https://github.com/bolandeu/hostme.git@vX.Y.Z"
```

`vX.Y.Z` — последний тег релиза (только из тега, не из ветки). Дистрибутив
называется `rb-hostme`, команда — `hostme`. Копию, поставленную под старым
именем `hostme`, сначала удалить: `uv tool uninstall hostme`, иначе два
пакета дерутся за одну команду. Через SSH (если HTTPS отказывает в авторизации):

```
uv tool install "rb-hostme @ git+ssh://git@github.com/bolandeu/hostme.git@vX.Y.Z"
```

При разработке самого `hostme` (в этом репозитории) — editable-режим, чтобы
изменения в коде подхватывались без переустановки:

```
uv tool install --editable .
```

**После изменения `[project.scripts]` в `pyproject.toml`** editable-режим
не перегенерирует уже установленный launcher-скрипт сам — обязательно
`uv tool install --editable . --force`, иначе `hostme` из PATH продолжит
звать старый entry point (см. AGENTS.md).

После любого из вариантов `hostme` доступен как обычная команда в PATH из
любой директории.

## Требования к серверу перед `server add`/`server init`

- Чистый Ubuntu Server 24.04/26.04 LTS (arm64 или x86_64), минимум 512MB RAM — `hostme server init` сам ставит Webinoly (nginx+php-fpm), но ОС должна быть готова заранее
- Открытые порты (входящие как минимум): `22/TCP` (SSH), `80/TCP` и `443/TCP+UDP` (HTTP/HTTPS/HTTP3). Подробный список (включая исходящие для почты/GPG) — [docs/webinoly.md](docs/webinoly.md), раздел «Установка»
- SSH-пользователь (обычно `root`) должен пускать по ключу (`ssh_key` в `hostme server add`) и иметь **passwordless sudo** — `hostme`/Webinoly не умеют отвечать на запрос пароля sudo
- Перед первым `server init`: `sudo apt update && sudo apt -y upgrade` (и по-хорошему `reboot`) — руками, `hostme` этого не делает

## Деплой

```
hostme <path> [domain] [--server NAME]
```

Заливка файлов идёт через `rsync --delete`: webroot на сервере становится точным зеркалом локальной папки на момент деплоя. Если файл убрать из `path` и задеплоить снова — на сервере он тоже исчезнет. Это сделано намеренно, чтобы повторный деплой был идемпотентным и не копил старые файлы — но по той же причине деплой не той (пустой/неверной) папки снесёт существующий контент сайта на сервере.

## Для агентов

`hostme --ai` печатает встроенный SKILL.md (конвенции: `--json`, exit-коды,
`--dry-run`/`--confirm`, правила для `--target`); `hostme skill install`
кладёт его в `~/.claude/skills/hostme/`. Список команд — голый `hostme`,
полный справочник с примерами — `hostme help` (`--json` для агентов).

## Разработка

Архитектура — по [cli-builder](https://github.com/bolandeu/cli-generator):
`commands/` (только разбор аргументов) → `core/` (сервисы, ошибки) →
`providers/` (ssh/rsync/lftp/Webinoly — всё, что выходит за пределы процесса),
`output/` (human/json, guard), `credentials/` (пароли target'ов: env
`HOSTME_<TARGET>_PASSWORD`, иначе OS keychain `hostme:<target>`; `auth status`).

Проверка — один гейт (`~/Work/tools/docs/standard-release.md` §3):

```
uv run scripts/release.py --check
```

(lock, ruff, ty, pytest с порогом покрытия и снапшотами `--help`, сверка
`[[tool.rb.external]]` с кодом, changelog-фрагмент, сборка+установка колеса,
osv-scanner). После клонирования один раз `scripts/install_hooks.sh`
(`core.hooksPath=.githooks`: pre-commit блокирует команду, чей код поменялся
без docstring = `--help`; pre-push сообщает корневому агенту о тегах).

Изменение с видимым эффектом — фрагмент `changelog.d/+<slug>.<type>.md`
(`uv run towncrier create +<slug>.<type>.md -c "…"`). Релиз:
`uv run scripts/release.py patch|minor|major` на чистом `main` — собирает
changelog, коммитит, ставит тег; push — `git push --follow-tags`. Версия
только из git-тега, `version =` в pyproject нет.
