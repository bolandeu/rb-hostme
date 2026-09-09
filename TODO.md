# TODO: реализация Hostme

Детальный план работ по PRD.md. Структура — по фазам (см. PRD, раздел 11), внутри фазы — по подсистемам. Ссылки на разделы PRD/докы — в скобках.

---

## Phase 0 — подготовка репозитория

- [x] `git init` в корне проекта, `.gitignore`
- [x] `uv init` — `pyproject.toml`, layout `src/hostme/`
- [x] `uv python pin` → `.python-version` (3.14, раздел 8 PRD)
- [x] Зависимости: `uv add typer rich ruamel.yaml`; dev: `uv add --dev pytest pytest-cov ruff`
- [x] Entry point в `pyproject.toml`: `[project.scripts] hostme = "hostme.cli:app"`
- [x] Проверка глобальной установки: `uv tool install --editable .` → `hostme --help` работает из любой директории (проверено из `/tmp`)
- [x] **2026-09-09, реальный найденный баг**: `[project.scripts]` в `pyproject.toml` поменяли с `hostme.cli:app` на `hostme.cli:main` (Phase 1.4, единый обработчик ошибок), но глобально установленный `~/.local/bin/hostme` — это сгенерированный при установке скрипт-обёртка, который **не перегенерируется сам** при простом изменении `pyproject.toml` (editable-режим подхватывает изменения кода модуля, но не меняет уже сгенерированный launcher). Из-за этого весь день глобальный `hostme` вызывал `app()` напрямую в обход `_translate_argv` — surge-грамматика (`hostme <domain> teardown` и т.п.) молча не работала при вызове голым `hostme` (работало только через `uv run hostme` из репозитория, где entry point резолвится заново). Обнаружено при попытке `hostme roksdigital.ru auth ...` → `No such command 'roksdigital.ru'`. Фикс: `uv tool install --editable . --force` после **любого** изменения `[project.scripts]`. Стоит запомнить/автоматизировать (хук на изменение `pyproject.toml`?) — иначе Skill для агентов будет выглядеть сломанным без явной причины
- [x] Базовый `README.md` (что это, как поставить, ссылка на PRD.md)

---

## Phase 1 — MVP (1 сервер, 1 base-домен, статика + PHP)

### 1.1 Модели данных и конфиг (раздел 7 PRD)

- [x] Модели `Server` (`name, host, user, ssh_key, default, base_domains`), `BaseDomain` (`name, default`) и `Site` (`domain, server, local_path, php, ssl, force_https, cors, redirects, password_protect, deployed_at`) — dataclass (`src/hostme/config.py`)
- [x] Загрузка/сохранение `~/.config/hostme/servers.yaml` через `ruamel.yaml`
- [x] Загрузка/сохранение `~/.config/hostme/sites.yaml`, включая обработку `include:` (относительные пути от `~/.config/hostme/`)
- [x] Создание `~/.config/hostme/` при первом запуске (`_ensure_config_dir`, права `700`, вызывается автоматически из `save_servers`/`save_sites`, без вопросов)
- [x] `resolve_server()`: `--server` явно > уже известный домен в `sites.yaml` > `base_domains` серверов (суффикс-мэтч) > `None`
- [x] `default_domain()`: `<slug(имя-папки)>.<первый зарегистрированный служебный домен>` (раздел 2 и 4 PRD — не "дефолтный сервер", а именно первый зарегистрированный base-домен, см. `default_base_domain`)
- [x] `check_collision()`: домен занят другим `local_path` → `ConfigError`; тот же `local_path` → не ошибка (апдейт)
- [x] Unit-тесты (`tests/unit/test_config.py`, 27 тестов, 95% покрытие `config.py`) — резолвинг домена/сервера, коллизии, roundtrip YAML, права доступа на файлы, `include`
- [x] **2026-09-09**: `slugify()` кодирует не-ASCII буквы (кириллица и т.п.) в punycode (`под-проект` → `xn----...`) через встроенный кодек `str.encode("punycode")` — валидный ACE DNS-лейбл, раскодируется обратно любым IDNA-резолвером (проверено через `idna.decode()`). Тест `test_slugify` обновлён под новое поведение

### 1.2 SSH/rsync-слой (раздел 8 PRD)

- [x] `run_remote(server, command: str) -> RemoteResult(stdout, stderr, returncode)` — `src/hostme/ssh.py`, обёртка над `subprocess` + системный `ssh` (`-i ssh_key`, `BatchMode=yes`)
- [x] `rsync_to(local_path, server, remote_path, delete=True)` — обёртка над системным `rsync -az [--delete]`
- [x] Обработка ошибок соединения: код `255` → `SshError` с понятным сообщением (недоступен хост/неверный ключ/permission denied — SSH сам возвращает 255 на все эти случаи); прочие ненулевые коды возврата команды — не ошибка, а обычный `RemoteResult(ok=False)` (агент/CLI сам решает, что с этим делать)
- [x] Таймауты: `DEFAULT_TIMEOUT=30`с на обычные команды, `LONG_TIMEOUT=300`с для `rsync_to`/долгих операций типа `server init`
- [x] Юнит-тесты (`tests/unit/test_ssh.py`, subprocess замокан) + e2e (`tests/e2e/test_ssh_layer.py`, реальный SSH/rsync на `sites-first-beget`) — 96% покрытие `ssh.py`
- [x] **2026-09-09**: реализовано переиспользование соединения через `ControlMaster=auto`/`ControlPersist=60s` (`src/hostme/ssh.py`, `_ssh_options`/`_control_path`) — общий `ControlPath` (короткий hash от `user@host`, чтобы не упереться в лимит длины unix-сокета) используется и в `run_remote`, и в `-e` для `rsync_to`, так что вся цепочка команд одного `deploy` реально делит один TCP+auth хендшейк. Проверено вживую на `sites-first-beget`: второй `run_remote` — 0.14с против 0.77с у первого (полный хендшейк), `ssh -O check` подтвердил один и тот же `pid` мастера для `run_remote` и последующего `rsync_to`.

### 1.3 Webinoly-адаптер (docs/webinoly.md)

Реализовано в `src/hostme/webinoly.py`, юнит-тесты в `tests/unit/test_webinoly.py` (100% покрытие модуля) + e2e в `tests/e2e/test_webinoly_adapter.py` (прогнан на `sites-first-beget`, полный цикл create→ssl→upload→curl→delete зелёный).

- [x] `install(server, mode="-php")` — подтверждено вживую: `wget -qO weby qrok.es/wy && bash weby -php` полностью неинтерактивен (никаких вопросов). Идемпотентность через `is_installed()` (`command -v webinoly`) перед установкой
- [x] `create_site(server, domain, site_type)` → `sudo site <domain> -html` / `-php`
- [x] `site_exists(server, domain)` / `list_sites(server)` — через `sudo site -list` + `parse_site_list()`
- [x] `delete_site(server, domain, revoke_ssl=True)` → `sudo site <domain> -delete=force -revoke=on|off`
- [x] `enable_ssl(server, domain, wildcard=False, add_to_wildcard=None)` — три режима: обычный `-ssl=on`, новый wildcard-сертификат (`-wildcard`, ручной DNS-01, см. WILDCARD-SSL.md), и **`-add-to-wildcard=<base>`** — привязка к уже существующему wildcard-сертификату **без единого DNS-шага** (подтверждено вживую на test1/test2.antagorapp.ru). Это и есть реальный путь для MVP: base-домен получает wildcard один раз вручную (WILDCARD-SSL.md), а каждый новый поддомен цепляется через `add_to_wildcard` — быстрее и надёжнее, чем per-domain `-ssl=on` (не бьёт по Let's Encrypt rate limit на много сайтов)
- [x] `fix_ownership(server, domain)` — обязательный `chown -R www-data:www-data` после заливки (см. 1.2/AGENTS.md)
- [x] `parse_site_list()` — **найден и исправлен реальный баг**: формат тегов у Webinoly — несколько отдельных скобочных групп подряд без разделителя, `(HTML)(NoSSL)`, а не `(HTML, NoSSL)`, как можно было бы предположить по документации. Юнит-тест `test_parse_site_list_multiple_adjacent_parens_no_ssl` фиксирует это явно
- [x] `sudo` без пароля — подтверждено, работает из коробки на `sites-first-beget` (пользователь `root`, `sudo` не спрашивает пароль сам у себя)

### 1.4 CLI-каркас (Typer)

- [x] `hostme/cli.py` — корневое Typer-приложение, глобальный флаг `--json` (raise на уровне контекста, доступен во всех командах)
- [x] Единый обработчик ошибок: любое исключение → человекочитаемое сообщение в stderr (или JSON-объект `{"error": ...}` при `--json`) + ненулевой exit code; успех → exit 0 — все свои ошибки (`ConfigError`/`SshError`/`WebinolyError`) наследуются от общего `HostmeError` (`src/hostme/errors.py`) и ловятся в `main()`; плюс catch-all на непредвиденный `Exception`, чтобы агенту не прилетал голый трейсбек
- [x] Соглашение о выводе: обычный режим — `rich` (таблицы/чек-марки), `--json` — чистый JSON без цветного форматирования и лишних print'ов (`src/hostme/output.py`)
- [x] Проверить, что ни одна MVP-команда не блокируется на `input()` без явного флага (раздел 9 PRD) — `input()` нигде не используется
- [x] **2026-09-09**: форма команд приведена к surge-стилю (AGENTS.md/docs/surge-cli.md) — `hostme <path> [domain]` и `hostme <domain> teardown` без промежуточных слов вроде `deploy`. Typer/Click умеет только статическое дерево подкоманд, поэтому реальный argv переписывается в explicit-подкоманды (`_translate_argv` в `cli.py`) до того, как его увидит Typer: если первый токен не совпадает с `server`/`domain`/`list`/`open`, а второй — с `teardown`/`config`/`auth`/`ssl`/`debug`, это домен-менеджмент (`<domain> <subcmd>` → `<subcmd> <domain>`); иначе — деплой (`<path> ...` → `_deploy <path> ...`, команда скрыта из `--help`). Известное ограничение: локальная папка не может называться буквально `server`/`domain`/`list`/`open` без явного пути вроде `./server` — как и у самого surge с его зарезервированными словами

### 1.5 Команды: серверы и домены

- [x] `hostme server add --name --host --user [--key] [--default]` — запись в `servers.yaml`, проверка дубликата имени
- [x] `hostme server init <name>` — вызывает `webinoly_install` (1.3) + `enable_sftp`, выводит статус по шагам
- [x] **2026-09-09**: `hostme server update <name>` → `sudo webinoly -update` — обновляет сам Webinoly (не пакеты сервера). Флаг подтверждён в `Options:` `/usr/bin/webinoly` и неинтерактивен. **Прогнан вживую** на `sites-first-beget` (по явному согласию пользователя) — версия осталась `1.21.2` (уже была актуальной, идемпотентный no-op), все 4 живых сайта (`bolandau.ru`, `antagorapp.ru`, `roksdigital.ru`, кириллический) после этого по-прежнему `200`
- [x] `hostme server list` — таблица серверов
- [x] `hostme server remove <name>` — с проверкой, что на сервере не осталось сайтов в реестре (или явное предупреждение/`--force`)
- [x] `hostme domain add <server> <domain>` — регистрирует base-домен в `servers.yaml`; MVP: без wildcard SSL сразу (см. 1.3), просто резервирует домен для авто-генерации поддоменов

### 1.6 Команда деплоя

- [x] `hostme <path> [domain] [--server NAME]`:
  1. резолв домена (дефолт из имени папки) и сервера (по домену/`--server`/дефолтному серверу)
  2. проверка коллизии (1.1)
  3. автоопределение типа сайта: рекурсивный поиск `*.php` в `path` → `php`/`html`
  4. если сайта с этим доменом ещё нет на сервере (1.3 `site_exists`) → `site_create` + `site_ssl_on` (через `add-to-wildcard`, если домен — поддомен зарегистрированного base-домена)
  5. `rsync_to` — залить файлы в webroot Webinoly-сайта (**подтверждено**: `/var/www/<domain>/htdocs`, см. AGENTS.md) **и сразу `chown -R www-data:www-data`** на этот путь — подтверждено на практике (2026-09-08, `tests/e2e/test_webinoly_smoke.py`): SSH-пользователь `root`, поэтому rsync/tee пишет файлы от root, а `htdocs` после `webinoly -sftp=on` создаётся с правами `750` без доступа «остальным» — без chown nginx (работает от `www-data`) отдаёт **403** на реально загруженный контент. Либо `rsync --chown=www-data:www-data`, либо отдельный `chown -R` после заливки — обязательный шаг, не опция
  6. обновить/добавить запись в `sites.yaml` (`deployed_at` = текущее время)
  7. вывести URL (`https://<domain>`)
- [x] Решить и задокументировать поведение `rsync --delete` — **решено: да, всегда включено** (идемпотентность деплоя важнее риска снести контент неверной папкой); задокументировано в PRD.md (раздел 6) и README.md (раздел «Деплой»)
- [x] Обработка ошибки на середине деплоя — **решено простой двухфазной записью, без отдельного поля статуса**: запись в `sites.yaml` пишется сразу после успешного создания сайта на сервере (`deployed_at=None`), затем обновляется `deployed_at` после успешной заливки. Если rsync/chown упадёт — сайт всё равно виден в `list`/доступен для `teardown`, а не осиротеет (не создастся на сервере невидимо для реестра)

### 1.7 Остальные MVP-команды

- [x] `hostme list` — таблица всех сайтов из `sites.yaml` (домен, сервер, php, ssl, deployed_at); `--json` — сырой список объектов
- [x] **2026-09-09**: `hostme list` дополнительно показывает служебные (base) домены, у которых нет записи в `sites.yaml` (никогда не деплоились через `hostme <path> <domain>`, только заглушка/wildcard-настройка вручную) — помечены отдельно (`[служебный домен, без деплоя через hostme]`, `base_domain: true` в `--json`), а не молча пропадают из списка. Нашёл по реальному вопросу пользователя «почему bolandau.ru/antagorapp.ru не в list»
- [x] `hostme open <domain>` — `webbrowser.open(f"https://{domain}")`
- [x] `hostme <domain> teardown` — `site_delete` на сервере + удаление записи из `sites.yaml`, с подтверждением (`typer.confirm`), которое пропускается при `--yes`/`-y` или `--json` (не блокирует агентов)

### 1.8 Тестирование Phase 1

Политика тестирования (обязательная, не опциональная) описана в `AGENTS.md`: юнит-покрытие ≥80% (порог зафиксирован в `pyproject.toml`, проверяется автоматически) + e2e-тесты на реальном сервере для всего, что трогает SSH/Webinoly.

- [x] Каркас тестов: `tests/unit/`, `tests/e2e/`, `tests/conftest.py` (skip e2e без `HOSTME_E2E_HOST`), `pytest-cov` с `fail_under=80` в `pyproject.toml`
- [x] `tests/e2e/test_webinoly_smoke.py` — e2e полного цикла статического сайта (create → ssl → upload → curl → delete) напрямую через SSH; прогнан на `sites-first-beget`, поймал реальный баг с правами `www-data` (см. AGENTS.md)
- [ ] Unit-тесты: конфиг (1.1), парсинг вывода Webinoly-команд (моки), резолвинг домена/сервера
- [ ] Переписать `tests/e2e/test_webinoly_smoke.py` на вызов самого `hostme` CLI (subprocess), когда появятся `deploy`/`teardown` — сырой SSH был временной мерой
- [ ] E2E на PHP-сайт (`hostme ./test-php-site` с `.php`-файлом) → PHP реально выполняется, не отдаётся как текст — по образцу `test_webinoly_smoke.py`
- [ ] E2E на `server add` + `server init` с нуля (на ещё одном чистом сервере, если/когда он появится) — текущий e2e предполагает Webinoly уже установлен
- [ ] Ручная проверка агентского сценария: вызов `hostme` из Claude Code (или скрипта) без интерактивного шелла — убедиться, что не виснет и возвращает вменяемый JSON/exit code

---

## Сквозное улучшение (вне исходного плана)

- [x] **2026-09-09**: `create_site()` всегда кладёт заглушку `index.html`/`index.php` («Сайт в разработке») сразу после создания сайта на Webinoly — иначе между созданием сайта и заливкой реального контента (или для сайтов-заглушек под base-домен, см. WILDCARD-SSL.md) nginx отдаёт голый `403` (пустой `htdocs`, `try_files` без `autoindex`). Best-effort — не роняет `create_site`, если вдруг не получилось. Накачено и на уже существующие `bolandau.ru`/`antagorapp.ru` (были 403 → стали 200)

## Phase 2 — мульти-сервер, мульти-домен, доп. фичи

### 2.1 Несколько серверов и base-доменов

- [x] **2026-09-09**: реальная регистрация двух base-доменов на `sites-first-beget` — `bolandau.ru` (дефолтный) и `antagorapp.ru` (не дефолтный, но уже с настоящим wildcard DNS+SSL, см. WILDCARD-SSL.md). Заодно добавлены недостающие команды: `hostme domain add ... --default` (смена дефолта при регистрации) и `hostme domain default <domain>` (смена дефолта без пере-регистрации) — `hostme domain list` для просмотра. Резолвинг (1.1) уже был написан универсально под N серверов/доменов, отдельных правок не потребовалось
- [ ] Убедиться, что резолвинг домена/сервера (1.1) корректно работает при нескольких серверах и нескольких base-доменах (юнит-тесты на неоднозначные случаи)
- [ ] `hostme domain add <server> <domain>` — автоматическое включение wildcard SSL для base-домена. **Отложено (2026-09-09) до появления DNS-провайдера с API** — без API-доступа к DNS (сейчас DNS у Beget, панель без API-ключа) единственный вариант — TXT-запись руками через панель + строго последовательные `Enter` в certbot (см. WILDCARD-SSL.md), и это не автоматизировать без ручного шага. Как только появится провайдер/API — реализовать `-ssl=on -wildcard` с автопубликацией TXT-записи через API вместо ручного шага. Пока — делать по WILDCARD-SSL.md (уже дважды пройдено вживую, работает)

### 2.2 Кастомные домены 2-го уровня

- [x] **2026-09-09**: реальный кастомный домен `roksdigital.ru` (не поддомен base-домена, DNS уже указывал на `sites-first-beget`) задеплоен через `hostme <path> roksdigital.ru --server sites-first-beget` — обычный per-domain SSL (не wildcard), `www.` редиректит на apex, `200` и валидный сертификат подтверждены curl'ом
- [x] **2026-09-09**: кастомные домены 2-го уровня с кириллицей — `config.normalize_domain()` приводит домен целиком к punycode через встроенный `str.encode("idna")` (в отличие от `slugify()`, который кодирует один лейбл — `idna` сам бьёт по точкам и кодирует TLD тоже: `.рф` → `.xn--p1ai`). Применяется в `deploy`/`teardown`/`auth`/`config`/`domain add`/`domain default` — везде, где домен приходит от пользователя напрямую как аргумент CLI. Проверено вживую: `hostme <path> растаможка-авто.рф --server ...` → сайт создан как `xn----7sbaabmy6aqugnooj.xn--p1ai`, реальный браузер (`agent-browser`) открывает и кириллический, и punycode-адрес, оба показывают задеплоенную страницу с валидным SSL (`curl` в тестовом окружении не смог — не кодирует SNI в punycode для не-ASCII хоста, это баг локального curl, не сайта)

- [x] Деплой в ещё не зарегистрированный домен без `--server` → понятная ошибка с подсказкой указать `--server` (уже было реализовано в `cli.py` deploy: «Не удалось определить сервер для домена {domain}. Укажи --server явно.»)
- [x] После первого деплоя кастомного домена — привязка домен→сервер сохраняется в `sites.yaml` (по дизайну `Site.server`, `resolve_server` проверяет реестр раньше суффикс-мэтча по base_domains — проверено вручную: `resolve_server(..., 'foo.antagorapp.ru')` находит сервер по суффиксу даже когда antagorapp.ru не дефолтный base-домен)

### 2.3 `hostme <domain> auth` — password protection

- [x] `hostme <domain> auth --user U --pass P` → `sudo httpauth <domain> -add=[user,pass]` + `sudo httpauth <domain> -path=/` (`webinoly.set_http_auth`, `-add=` значение экранируется через `shlex.quote` — без этого пароль от пользователя шёл бы прямой command injection в root-сессию по SSH)
- [x] `hostme <domain> auth --off` → `sudo httpauth <domain> -path=all -delete` (`webinoly.disable_http_auth`). **Реальный баг публичной доки Webinoly (найден 2026-09-09 на живом `roksdigital.ru`)**: флага `-purge` у `httpauth` не существует вовсе (шапка `/usr/bin/httpauth`: `Options: -add, -delete, -list, -wp-admin, -whitelist, -path`), `-path=all -purge` падал с `[ERROR] Please, enter a valid URL path!`. Заодно выяснилось: Webinoly пишет `[ERROR]`-сообщения в **stdout**, не stderr — из-за этого исключение показывало пустой текст ошибки; исправлено везде в `webinoly.py` через новый хелпер `_error_text()` (stderr с фолбэком на stdout, 17 мест). Оба фикса — код + `docs/webinoly.md` + regression-тест
- [x] Обновление `password_protect` в `sites.yaml` — **решено: не хранить пароль вовсе**, только `{"enabled": true, "user": ...}`, раз он уже ушёл на сервер
- [x] Закрыт открытый вопрос PRD §13.2: `--pass` в аргументе командной строки — **ок для MVP** (single user, локальная машина), без `--password-file`; решение зафиксировано в PRD.md §13. Проверено вживую на `sites-first-beget` (`auth --off` на несуществующем домене корректно упал с понятной ошибкой, реестр не тронут при ошибке)

### 2.4 `hostme <domain> config` — CORS, redirects, force-https

- [x] **Force HTTPS**: подтверждено по докам и вживую — `-ssl=on` у Webinoly всегда сам ставит редирект HTTP→HTTPS, отключить нельзя. `hostme <domain> config --force-https` — no-op с понятным сообщением, `--no-force-https` — явная ошибка (не поддерживается)
- [x] **Custom redirects**: `hostme <domain> config --redirect FROM=TO` / `--remove-redirect FROM` поверх нативного `sudo site <domain> -redirection -from=... -to=... -http-code=...` (`webinoly.add_redirect`/`remove_redirect`), синхронизация списка в `sites.yaml`. Проверено вживую на `test2.antagorapp.ru`: `302 /old-path → /new-path`, затем удалено
- [x] **CORS**: свой custom-nginx сниппет (`webinoly.set_cors`, `/var/www/<domain>/hostme-cors-nginx.conf`) — на уровне `server{}`, **без своего `location /`** (уже объявлен самим Webinoly в основном конфиге сайта — второй `location /` в том же server-блоке уронил бы `nginx -t`, разбирался в реальном сгенерённом конфиге сайта перед реализацией). Origin сверяется через nginx `if`+regex, при несовпадении/отсутствии `Origin` заголовок вообще не шлётся (не просто пустой). `nginx -t` перед `reload`, при провале — откат файла, nginx не трогается. Проверено вживую на `test2.antagorapp.ru`: разрешённый origin получает эхо в `Access-Control-Allow-Origin`, неразрешённый/отсутствующий — без заголовка; остальные сайты на сервере не пострадали
- [x] `hostme <domain> config` без флагов — печатает текущие настройки сайта из `sites.yaml` (сверка с реальным состоянием на сервере не реализована — решено, что не нужно для MVP, локальный реестр и так пишется синхронно с каждой операцией)
- [x] **2026-09-09: общий механизм произвольных nginx-настроек** — `hostme <domain> config --nginx-snippet PATH` / `--no-nginx-snippet` (`webinoly.set_custom_nginx_snippet`, тот же безопасный паттерн, что и у CORS — `nginx -t` + reload + откат при поломке, вынесено в общий `_write_snippet_or_remove`). Заготовки — `docs/nginx-snippets/` (не в реестре, отдельная папка с шаблонами под разные генераторы статики). Реализован и **несколько часов отлаживался вживую** на `test.bolandau.ru` (реальный PHP+HTML сайт с формами `form.php`/`subscribe.php` и коллизиями `catalog.html`+`catalog/`, `blog.html`+`blog/`) — четыре реальных найденных грабля nginx, подробно задокументированы в `docs/nginx-snippets/README.md`: (1) на PHP-сайтах `$uri` внутри error_page-обработчика — это уже `/index.php`, не исходный путь, нужен `$request_uri`; (2) `if` вместе с `try_files` в одном location не работает («if is evil»); (3) при коллизии `page.html`+`page/` Webinoly матчит директорию раньше файла — решено проактивной проверкой `-f` на rewrite-фазе, ДО того как Webinoly вообще пробует директорию; (4) `error_page` не перезапускается для ошибки внутри уже активной обработки другого `error_page` — решено разводом на два невложенных шага (проактивный `-f` для "файл есть", отдельный необременённый `error_page 404 /404.html` для "файла точно нет"), в итоге **и статус 404, и кастомный контент корректны одновременно** (SEO-требование пользователя выполнено). Итоговый `clean-urls.conf` — чистые URL + `/page/`→`/page` + кастомный 404 (верный статус) + PHP-скрипты/статика не тронуты, все сценарии проверены вживую и в реальном браузере

### 2.5 `include` в sites.yaml

**2026-09-09: не приоритет, но чтение+запись уже реализованы и работают** — не обязательно для single-user с некрупным реестром, смысл появится только если сайтов станет много и захочется разложить их по смыслу (`sites.d/personal.yaml`, `sites.d/clients.yaml`) или гитить/шарить только часть. Оставлено как есть, не выкидываем (бесплатно для тех, кто не использует).

- [x] Чтение нескольких файлов из `sites.d/*.yaml`, объединение в один список сайтов в памяти (было в 1.1)
- [ ] ~~Команда или документация: как вручную завести `sites.d/*.yaml`~~ — решено не делать, пока реально не понадобится
- [x] Запись (создание/обновление сайта) идёт в тот файл, откуда сайт был изначально прочитан (`Site.source_file`), а не всегда в главный `sites.yaml`

---

## Phase 3 — доработки

### 3.1 `hostme <domain> debug`

- [x] Статус: HTTP HEAD-запрос на `https://<domain>` (`urllib`, без новой зависимости), таймаут 8с, код ответа или текст ошибки
- [x] Логи: `sudo log <domain> [-error] -lines=N` через SSH — **важный нюанс**: у Webinoly `log <domain>` без обёртки стримит в реальном времени и никогда сам не завершается (`tail -f`), поэтому обёрнуто в `sudo timeout <N>s log ...; true` на самом сервере — иначе `run_remote` провис бы до собственного таймаута на каждый вызов `debug`. Проверено вживую на `roksdigital.ru`: access-лог (по умолчанию выключен у Webinoly для новых сайтов — корректно репортится как есть, не баг) и error-лог (реальные записи об попытках сканирования `.env`/`.git` ботами, заблокированные правилами Webinoly)

### 3.2 Rollback (`revs`/`rollback`/`rollfore`/`cutover`/`discard`)

**2026-09-09: реализовано и проверено вживую на `test2.antagorapp.ru`** (полный цикл: deploy A → deploy B → deploy C → revs → rollback → rollback → rollfore → rollfore, контент на каждом шаге сверен `curl`).

- [x] Схема releases: `htdocs` — симлинк на `releases/<таймстамп>` (`webinoly.ensure_releases_layout`, `switch_release`, `release_path`, `releases_dir`). Идемпотентная миграция: если `htdocs` уже директория с контентом (свежесозданный сайт или уже задеплоенный до этой фичи) — переносится в `releases/<ts>-migrated` как первый релиз, ничего не теряется. Конфликт с файлами Webinoly (`wp-config.php` и т.п.) не актуален — WordPress не используется (раздел 10 PRD)
- [x] `deploy` льёт в новую `releases/<ts>` директорию, атомарно переключает симлинк (`ln -sfn ... && mv -Tf`) — не поверх текущей (1.6 rsync-шаг переписан)
- [x] `hostme <domain> revs` — список релизов + пометка текущего
- [x] `hostme <domain> rollback` / `rollfore` — переключение на предыдущий/следующий по списку, ошибка с понятным текстом на границах (`нет более старого/нового релиза`)
- [x] Политика хранения — `prune_releases`, оставляет последние 5, никогда не удаляет текущий даже если он старше
- [ ] `hostme <domain> discard` — **решено не реализовывать**: у surge это про откат ещё не подтверждённого preview-деплоя, а у Hostme нет концепции preview (каждый `deploy` сразу и есть прод) — прямого аналога нет, реализация под этим именем была бы вводящей в заблуждение
- **Найдено и исправлено вживую (2 реальных бага, не ловятся юнит-тестами с моками):**
  1. `mkdir -p releases` создаёт директорию от `root:root` с правами `750` (умаск сервера) — `www-data` (от которого работает nginx) не может даже зайти внутрь → **весь сайт отдавал голый 404**, несмотря на то что права на файлы глубже были верными. Фикс: `ensure_releases_layout` сразу делает `chown www-data:www-data releases`
  2. У Webinoly в `nginx.conf` включён `open_file_cache` (`valid=30s`) — после переключения симлинка nginx **до ~30 секунд продолжал отдавать старый релиз** по закэшированному файловому дескриптору, несмотря на то что симлинк на сервере уже указывал на новый. Фикс: `switch_release()` всегда делает `nginx -t && systemctl reload nginx` после переключения (переиспользует существующий `_reload_nginx` из CORS-фичи)
- **Важно**: во время этого прогона по неосторожности дважды перезаписал реальный `~/.config/hostme/sites.yaml` тестовыми данными вместо read-modify-write, потеряв записи `roksdigital.ru`/`растаможка-авто.рф` — восстановлено вручную по факту состояния на сервере. Запомнено в памяти агента (`testing_real_config_care`), чтобы не повторять

### 3.3 Git push-to-deploy (опционально)

- [ ] Оценить целесообразность (bare-репозиторий на сервере + `post-receive` hook, вызывающий тот же деплой-путь) — отдельное мини-исследование перед реализацией

### 3.4 `-proxy=` сайты (Node/Java/etc. за Nginx)

**Решено (2026-09-09): не нужно** — вне скоупа проекта по явному запросу, не реализуем.

---

## Сквозные задачи (не привязаны к одной фазе)

- [x] **2026-09-09**: `docs/webinoly.md` актуализирован по факту — раздел «Итог для Hostme» переписан с реальными пойманными багами (chown на releases/, open_file_cache, заглушка вместо 403, add-to-wildcard как реальный MVP-путь), снят устаревший `[TBD/уточнить]` про флаг удаления (решён, `-delete=force`, подтверждён e2e)
- [x] **2026-09-09, полный аудит флагов**: после того как `-purge` у `httpauth` оказался несуществующим (см. 2.3), сверил вообще все флаги, которые `hostme` реально шлёт в `site`/`log`/`webinoly`/`httpauth`, с шапками `Options:`/`Arguments:` в самих скриптах на сервере (`/usr/bin/site` и т.д.) — единственный найденный баг был в `httpauth -purge`, всё остальное (`site -html/-php/-ssl=on/-delete=force/-redirection/...`, `log -error/-lines=`, `webinoly -sftp=on/-version`) соответствует реальным Options/Arguments дословно
- [x] **2026-09-09**: чек-лист требований к серверу — README.md, раздел «Требования к серверу перед server add/server init» (Ubuntu 24.04/26.04, порты, passwordless sudo, apt update+upgrade заранее)
- [x] **2026-09-09**: секьюрити-ревью пройден — подробности в PRD.md §9 (Нефункциональные требования). Коротко: права `700`/`600` на конфиг верные, `ssh_key` — только путь, пароль `httpauth` не хранится локально и не эхается в ошибках (проверено вживую), нет сырых стектрейсов наружу. Заодно добавил `vps.txt`/`*.env`/`.env*` в `.gitignore` (было только на дисциплине агента, не enforced)
- [x] **2026-09-09**: `hostme help` (+ `hostme -h`/`--help`, теперь тоже работает как алиас) — полный справочник команд с реальным синтаксисом вызова (домен/путь первым, не как в обычном Click-дереве), с `--json`-вариантом для агентов. Root `--help`/epilog явно предупреждает, что список Commands от Click вводит в заблуждение (показывает `teardown`/`config`/`auth` как будто их вызывают первыми) и отсылает к `hostme help`. Попутно найден и исправлен баг: Rich интерпретировал `[domain]`/`[--server NAME]` в тексте как markup-теги и съедал их — исправлено `markup=False` для `help_cmd` и `rich.markup.escape()` для epilog
- [x] **2026-09-09**: `~/.claude/skills/hostme/SKILL.md` — глобальный (не в этом репозитории, чтобы был доступен агентам в любом проекте, раздел 2 PRD: агенты публикуют артефакты из чужих репозиториев) Claude Code skill. Тонкая обёртка: не дублирует список команд (чтобы не расходился с реальностью), а прямо говорит агенту сначала вызвать `hostme help --json`; отдельно предупреждает про главный источник ошибок — домен/путь первым, не подкоманда (`hostme mysite.com teardown`, не `hostme teardown mysite.com`), и про `--json`/`--yes` для неинтерактивного вызова
