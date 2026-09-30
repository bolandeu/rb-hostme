# Changelog

Формат — [Keep a Changelog](https://keepachangelog.com/), версии — [SemVer](https://semver.org/).
Руками не править: каждое изменение — фрагмент в `changelog.d/`
(`uv run towncrier create +<slug>.<type>.md -c "…"`), `scripts/release.py
patch|minor|major` собирает их в секцию версии. Версия — из git-тега.

<!-- towncrier release notes start -->
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
