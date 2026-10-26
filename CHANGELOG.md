# Changelog

All notable changes to this project are documented here. Versions follow
[SemVer](https://semver.org/) (while at `0.x`, a minor bump may break).

The changelog is written by `antagor publish`; don't edit it by hand.

## v0.6.1 — 2026-10-26

### Main

- Merge pull request #1: template v1.27.3 (Renovate)
- chore(template): Update dependency https://homeserver.tailee01ab.ts.net:3000/bolandeu/cli-generator.git to v1.27.3


## v0.6.0 — 2026-10-23

### Main

- antagor init: project hostme (HOSTME)
- antagor init: project hostme (HOSTME)
- Template v1.27.1: update from v1.2.10
- Шаблон: источник и repository_url — Gitea


## [0.5.3] - 2026-10-19

### Removed

- Убрано запасное чтение старого имени `HOSTME_<TARGET>_PASSWORD`: пароль target'а — только `HOSTME_DEPLOY_<TARGET>_PASSWORD` или keychain.


## [0.5.2] - 2026-10-19

### Changed

- Пароль target'а читается из `HOSTME_DEPLOY_<TARGET>_PASSWORD` (контракт ключей sysadmin, правило 6); старое имя `HOSTME_<TARGET>_PASSWORD` работает запасным с предупреждением, будет убрано в следующем релизе.


## [0.5.1] - 2026-10-13

### Added

- Флаг `--rebind` у деплоя: явное «это тот же сайт из другой папки» — домен перепривязывается к новой папке без отказа. Нужен CI (`sitegen ci`/`publish` собирают в новом checkout'е); без флага защита от чужой папки остаётся.


## [0.5.0] - 2026-10-13

### Added

- Сайты на своём сервере получают nginx-дефолты hostme (`/var/www/<domain>/hostme-defaults-nginx.conf`, Webinoly не перезаписывает его при обновлении): закрывающий слэш у всех страниц (`/a`, `/a.html`, `/a/index.html` → 301 `/a/` с сохранением query string, плоский `a.html` отдаётся по `/a/`) и `Cache-Control: public, max-age=31536000, immutable` для `/_astro/*`. Файл перезаливается при каждом деплое и в `hostme server update`, который теперь обновляет дефолты всем сайтам сервера. Сниппет `docs/nginx-snippets/static-site-generator.conf` больше не убирает слэш: теперь в нём только charset и кастомный 404.


## [0.4.1] - 2026-10-13

### Fixed

- `--json`: строки прогресса долгих команд (deploy, server init/update) больше не печатаются в stdout отдельными JSON-объектами — уходят в stderr; в stdout ровно один объект-итог.


## [0.4.0] - 2026-09-30

### Added

- Политика хранения бэкапов target'ов: `~/.config/hostme/settings.yaml` → `target_backups: {keep: N, max_age_days: X}` (по умолчанию последние 5 без срока; самый свежий снепшот не удаляется). `hostme doctor` показывает путь, размер, число снепшотов и политику (`--json`: `data_dir`, `target_backups`).

### Changed

- Состояние переехало в `platformdirs.user_data_dir("hostme")` (стандарт tools §13): `sites.yaml`, `sites.d/` и `target-backups/`. При первом запуске hostme сам переносит их из `~/.config/hostme` и сообщает об этом в stderr; `servers.yaml` остаётся в `~/.config/hostme`.


## [0.3.0] - 2026-09-30

### Added

- `hostme auth status [--check] [--provider server:N|target:N] --json` — отчёт о доступах по общему для tools контракту: запись на каждый сервер (ssh-ключ) и target (пароль), откуда он берётся и работает ли (`--check` — один read-only вход за 10 с); exit 3 при проблеме. `hostme <domain> auth` (HTTP Basic Auth) работает как раньше.

### Changed

- Дистрибутив переименован в `rb-hostme` (команда остаётся `hostme`): старую установку удалить `uv tool uninstall hostme`, ставить `uv tool install "rb-hostme @ git+https://github.com/bolandeu/hostme.git@vX.Y.Z"`. Версия берётся из git-тега, changelog собирается из фрагментов.
- Пароль target'а сначала берётся из `HOSTME_<TARGET>_PASSWORD`, OS keychain необязателен: без него (headless Linux) hostme работает на переменных окружения, `target add` без `--password` берёт пароль из env. Деструктивная команда без TTY и без `--confirm` падает с INVALID_ARGUMENTS, а не ждёт ответа.
- У каждой команды в `--help` есть строка `Example:`, квадратные скобки (`[domain]`, `[--confirm]`) больше не пропадают из справки; у `config --force-https/--no-force-https` появились описания.


## [0.2.0] - 2026-09-17

### Changed — рефакторинг на архитектуру cli-builder (breaking для агентов)

- **`--json`: конверт ошибки теперь в stdout**, как и успешный (раньше — в
  stderr). Один поток для парсинга; `ok: false` + ненулевой exit-код говорят об
  ошибке. JSON — одна строка, кириллица как есть (`ensure_ascii=False`).
- **Фиксированная таблица exit-кодов** (conventions.md cli-builder):
  `2` INVALID_ARGUMENTS (в т.ч. «не найден в реестре», «уже занято», деструктивная
  команда без `--confirm` в неинтерактивном режиме), `5` PROVIDER_ERROR
  (ssh/rsync/lftp/Webinoly упали или не найдены; в конверте поле `provider`),
  `1` ERROR/ABORTED/UNEXPECTED. Код `CONFIRMATION_REQUIRED` упразднён в пользу
  `INVALID_ARGUMENTS`.
- **`--confirm`** — флаг подтверждения деструктивных команд (`teardown`,
  `rollback`, `maintenance`, деплой на `--target`); `--yes`/`-y` остаются
  алиасами.
- **Голый `hostme` и `hostme <group>`** печатают справку и выходят с `0`
  (было `2`). Заголовок — `hostme <версия> — <описание>`, у каждой команды в
  списке — реальная форма вызова (домен/путь первым).
- **`doctor` всегда выходит с `0`**; результат проверок — поле `healthy`
  (было `ok`, конфликтовало с полем конверта).
- Отказ в интерактивном подтверждении — `ABORTED` (exit 1) вместо голого
  `typer.Exit(1)`.
- `hostme teardown --help` (и другие `<subcommand> --help`) показывает справку по
  этой команде, а не по деплою папки с именем «teardown».

### Added

- `--version`, `--quiet`, `--verbose` (DEBUG-лог в stderr: какие ssh/rsync/lftp
  команды реально запускаются; пароли туда не попадают).
- `@output.guard` на каждой команде: непойманное исключение → JSON-конверт
  `UNEXPECTED` (трейсбек — в stderr под `--verbose`), а не голый трейсбек.
- Docstring (= `--help`) у каждой команды и подсказки у всех опций.
- Quality gates: ruff с правилами `S` (security), `ty`, порог покрытия
  (`fail_under`) в `pyproject.toml`, CI (ubuntu/macos/windows + `uv tool install`
  + OSV-Scanner по `uv.lock`), dependabot, pre-commit хук на устаревшие
  docstring команд (`scripts/install_hooks.sh`), `scripts/release.py`.

### Internal

- Слои по architecture.md: `commands/` (разбор аргументов), `core/` (сервисы,
  ошибки, версия), `providers/` (ssh/ftp/webinoly/http — всё, что выходит за
  пределы процесса), `output/` (human/json, guard, group), `credentials/`.
