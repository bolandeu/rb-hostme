# hostme

Личный аналог [surge.sh](https://surge.sh/): CLI на Python/uv, который одной командой деплоит статические сайты и простые PHP-скрипты на собственные VPS (через [Webinoly](https://webinoly.com/)), с поддержкой нескольких серверов и доменов.

Полная спецификация — **[PRD.md](PRD.md)**. План реализации — **[TODO.md](TODO.md)**. Для AI-агентов, работающих в этом репозитории — **[AGENTS.md](AGENTS.md)**.

## Установка

Из Gitea-реестра (пакет релизится туда):

```
uv tool install rb-hostme --index https://homeserver.tailee01ab.ts.net:3000/api/packages/bolandeu/pypi/simple
```

Или из git-тега, на любой машине:

```
uv tool install "rb-hostme @ git+https://homeserver.tailee01ab.ts.net:3000/bolandeu/hostme.git@vX.Y.Z"
```

`vX.Y.Z` — последний тег релиза (только из тега, не из ветки). Дистрибутив
называется `rb-hostme`, команда — `hostme`; обновление — `uv tool upgrade rb-hostme`.

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
- Открытые порты (входящие как минимум): `22/TCP` (SSH), `80/TCP` и `443/TCP+UDP` (HTTP/HTTPS/HTTP3). Подробный список (включая исходящие для почты/GPG) — [docs/usage/webinoly.md](docs/usage/webinoly.md), раздел «Установка»
- SSH-пользователь (обычно `root`) должен пускать по ключу (`ssh_key` в `hostme server add`) и иметь **passwordless sudo** — `hostme`/Webinoly не умеют отвечать на запрос пароля sudo
- Перед первым `server init`: `sudo apt update && sudo apt -y upgrade` (и по-хорошему `reboot`) — руками, `hostme` этого не делает

## Деплой

```
hostme <path> [domain] [--server NAME]
```

Заливка файлов идёт через `rsync --delete`: webroot на сервере становится точным зеркалом локальной папки на момент деплоя. Если файл убрать из `path` и задеплоить снова — на сервере он тоже исчезнет. Это сделано намеренно, чтобы повторный деплой был идемпотентным и не копил старые файлы — но по той же причине деплой не той (пустой/неверной) папки снесёт существующий контент сайта на сервере.

## Где лежат настройки и данные

- Настройки — `~/.config/hostme/`: `servers.yaml` (серверы и target'ы), `settings.yaml`.
- Данные (пишет сам hostme) — `platformdirs.user_data_dir("hostme")` (macOS
  `~/Library/Application Support/hostme`, Linux `~/.local/share/hostme`):
  `sites.yaml` + `sites.d/`, `target-backups/<target>/<ts>/` — снепшоты target-сайта перед деплоем.
  До v0.4.0 всё лежало в `~/.config/hostme` — переносится само при первом запуске.
- Хранение бэкапов (`settings.yaml`, по умолчанию `keep: 5` без срока; самый свежий не удаляется):

  ```yaml
  target_backups:
    keep: 5            # последние N на target
    max_age_days: 30   # и/или удалять старше X дней
  ```

- `hostme doctor` показывает путь, размер и политику бэкапов.

## Для агентов

`hostme --ai` печатает встроенный SKILL.md (конвенции: `--json`, exit-коды,
`--dry-run`/`--confirm`, правила для `--target`); `hostme skill install`
кладёт его в `~/.claude/skills/hostme/`. Список команд — голый `hostme`,
полный справочник с примерами — `hostme help` (`--json` для агентов).

## Разработка

Архитектура — по [cli-builder](https://homeserver.tailee01ab.ts.net:3000/bolandeu/cli-generator):
`commands/` (только разбор аргументов) → `core/` (сервисы, ошибки) →
`providers/` (ssh/rsync/lftp/Webinoly — всё, что выходит за пределы процесса),
`output/` (human/json, guard), `credentials/` (пароли target'ов: env
`HOSTME_DEPLOY_<TARGET>_PASSWORD`, иначе OS keychain `hostme:<target>`; `auth status`).

Проверка — один гейт: шаг `rb-release check` в `.gitea/workflows/ci.yml`
(та же команда в CI), из корня пакета:

```
uvx --from "git+https://homeserver.tailee01ab.ts.net:3000/bolandeu/cli-generator.git@v1.27.1#subdirectory=gate" rb-release check
```

(lock, ruff, ty, pytest с порогом покрытия и снапшотами `--help`, сверка
`[[tool.rb.external]]` с кодом, сборка+установка колеса, правила Standard,
gitleaks и osv-scanner, если установлены). Работа и релизы — через Antagor
(`antagor publish` пишет CHANGELOG.md и ставит тег). Версия только из
git-тега, `version =` в pyproject нет.
