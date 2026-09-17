# hostme

Личный аналог [surge.sh](https://surge.sh/): CLI на Python/uv, который одной командой деплоит статические сайты и простые PHP-скрипты на собственные VPS (через [Webinoly](https://webinoly.com/)), с поддержкой нескольких серверов и доменов.

Полная спецификация — **[PRD.md](PRD.md)**. План реализации — **[TODO.md](TODO.md)**. Для AI-агентов, работающих в этом репозитории — **[AGENTS.md](AGENTS.md)**.

## Установка

На любой другой машине (репозиторий приватный — нужен `gh auth login`,
который настраивает git credential helper; на машине без интерактивного
логина — `gh auth setup-git`, или SSH-форма ниже):

```
uv tool install "git+https://github.com/bolandeu/hostme.git"
```

Обновление после новых коммитов: `uv tool upgrade hostme`. Через SSH (если
HTTPS отказывает в авторизации):

```
uv tool install "git+ssh://git@github.com/bolandeu/hostme.git"
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

## Разработка

```
uv run hostme --help
uv run pytest
uv run ruff check .
```
