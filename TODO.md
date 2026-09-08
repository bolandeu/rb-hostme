# TODO: реализация Hostme

Детальный план работ по PRD.md. Структура — по фазам (см. PRD, раздел 11), внутри фазы — по подсистемам. Ссылки на разделы PRD/докы — в скобках.

---

## Phase 0 — подготовка репозитория

- [ ] `git init` в корне проекта (сейчас репозиторий не инициализирован), `.gitignore` (как минимум `.venv/`, `__pycache__/`, `*.pyc`, `.DS_Store`)
- [ ] `uv init` — `pyproject.toml`, layout `src/hostme/`
- [ ] `uv python pin <версия>` → `.python-version` (раздел 8 PRD)
- [ ] Зависимости: `uv add typer rich ruamel.yaml`; dev: `uv add --dev pytest pytest-cov ruff`
- [ ] Entry point в `pyproject.toml`: `[project.scripts] hostme = "hostme.cli:app"`
- [ ] Проверка глобальной установки: `uv tool install --editable .` → `hostme --help` работает из любой директории
- [ ] Базовый `README.md` (что это, как поставить, ссылка на PRD.md)

---

## Phase 1 — MVP (1 сервер, 1 base-домен, статика + PHP)

### 1.1 Модели данных и конфиг (раздел 7 PRD)

- [ ] Модели `Server` (`name, host, user, ssh_key, default, base_domains`) и `Site` (`domain, server, local_path, php, ssl, force_https, cors, redirects, password_protect, deployed_at`) — dataclass или pydantic
- [ ] Загрузка/сохранение `~/.config/hostme/servers.yaml` через `ruamel.yaml` (сохраняя форматирование при перезаписи)
- [ ] Загрузка/сохранение `~/.config/hostme/sites.yaml`, включая обработку `include:` (относительные пути от `~/.config/hostme/`) — **можно сразу**, даже если реально используется в Phase 2, т.к. схема нужна с первого дня
- [ ] Создание `~/.config/hostme/` при первом запуске, если не существует (без интерактивных вопросов)
- [ ] Функция резолва `domain → server`: точное совпадение в `sites.yaml`, иначе — по `base_domains` серверов (суффикс-мэтч), иначе — требуется `--server`
- [ ] Функция определения дефолтного домена: `<slug(имя-папки)>.<base_domain дефолтного сервера>` (раздел 2 PRD) — учесть сервер по умолчанию (`default: true` в `servers.yaml`)
- [ ] Валидация коллизий: домен занят другим `local_path` → ошибка; тот же `local_path` → апдейт (раздел 4 PRD)
- [ ] Unit-тесты на резолвинг домена/сервера и коллизии (без сети)

### 1.2 SSH/rsync-слой (раздел 8 PRD)

- [ ] `run_remote(server, command: str) -> RemoteResult(stdout, stderr, returncode)` — обёртка над `subprocess` + системный `ssh` (используя `-i ssh_key`, уважая `~/.ssh/config`)
- [ ] `rsync_to(local_path, server, remote_path)` — обёртка над системным `rsync -az --delete` (уточнить, нужен ли `--delete`, см. 1.6)
- [ ] Обработка ошибок соединения (недоступен хост, неверный ключ, permission denied) — понятные сообщения, ненулевой exit code
- [ ] Таймауты на SSH-команды (install/site create могут быть долгими — установить разумный, например 300с для `server init`, короче для остальных)

### 1.3 Webinoly-адаптер (docs/webinoly.md)

- [ ] `webinoly_install(server, mode="-php")` — `wget -qO weby qrok.es/wy && sudo bash weby -php`; идемпотентность — проверить, установлен ли уже Webinoly, прежде чем повторно ставить (`sudo webinoly -version` или `-info`, ловим код возврата)
- [ ] **[Нужна проверка на реальном сервере]** Неинтерактивность install-скрипта `weby` — задаёт ли он вопросы в процессе; если да — найти unattended-флаги или заскриптовать ответы (см. открытый вопрос в `docs/webinoly.md`)
- [ ] `site_create(server, domain, type: "html"|"php")` → `sudo site <domain> -html` / `-php`
- [ ] `site_exists(server, domain)` — через `sudo site -list` (парсинг вывода) или `sudo site <domain> -info` (код возврата/наличие в выводе)
- [ ] `site_delete(server, domain, force=True, revoke_ssl=True)` → `sudo site <domain> -delete=force -revoke=on`
- [ ] `site_ssl_on(server, domain, wildcard=False)` → `sudo site <domain> -ssl=on [-wildcard]`; учесть, что для wildcard нужна ручная DNS TXT-валидация (см. docs/webinoly.md) — для MVP: включаем SSL для конкретных поддоменов не через wildcard, а через обычный `-ssl=on` на каждый домен отдельно (Let's Encrypt лимиты позволяют); wildcard — Phase 2, когда понадобится сразу закрыть весь base-домен
- [ ] Парсер вывода `sudo site -list` → структура (тип сайта, ssl вкл/выкл и т.д.) для сверки с локальным реестром
- [ ] Общий helper для выполнения команд Webinoly с `sudo` без интерактивного пароля (условие: пользователь на сервере имеет passwordless sudo, либо `sudo -n`) — задокументировать требование к серверу в README/`server add`

### 1.4 CLI-каркас (Typer)

- [ ] `hostme/cli.py` — корневое Typer-приложение, глобальный флаг `--json` (raise на уровне контекста, доступен во всех командах)
- [ ] Единый обработчик ошибок: любое исключение → человекочитаемое сообщение в stderr (или JSON-объект `{"error": ...}` при `--json`) + ненулевой exit code; успех → exit 0
- [ ] Соглашение о выводе: обычный режим — `rich` (таблицы/чек-марки), `--json` — чистый JSON без цветного форматирования и лишних print'ов
- [ ] Проверить, что ни одна MVP-команда не блокируется на `input()` без явного флага (раздел 9 PRD)

### 1.5 Команды: серверы и домены

- [ ] `hostme server add --name --host --user [--key] [--default]` — запись в `servers.yaml`, проверка дубликата имени
- [ ] `hostme server init <name>` — вызывает `webinoly_install` (1.3), выводит статус по шагам
- [ ] `hostme server list` — таблица серверов
- [ ] `hostme server remove <name>` — с проверкой, что на сервере не осталось сайтов в реестре (или явное предупреждение/`--force`)
- [ ] `hostme domain add <server> <domain>` — регистрирует base-домен в `servers.yaml`; MVP: без wildcard SSL сразу (см. 1.3), просто резервирует домен для авто-генерации поддоменов

### 1.6 Команда деплоя

- [ ] `hostme <path> [domain] [--server NAME]`:
  1. резолв домена (дефолт из имени папки) и сервера (по домену/`--server`/дефолтному серверу)
  2. проверка коллизии (1.1)
  3. автоопределение типа сайта: рекурсивный поиск `*.php` в `path` → `php`/`html`
  4. если сайта с этим доменом ещё нет на сервере (1.3 `site_exists`) → `site_create` + `site_ssl_on`
  5. `rsync_to` — залить файлы в webroot Webinoly-сайта (`/var/www/<domain>/htdocs`, уточнить точный путь по факту первого теста)
  6. обновить/добавить запись в `sites.yaml` (`deployed_at` = текущее время)
  7. вывести URL (`https://<domain>`)
- [ ] Решить и задокументировать поведение `rsync --delete` (удалять на сервере файлы, которых нет локально) — вероятно, да для идемпотентности деплоя, но явно прописать в PRD/README
- [ ] Обработка ошибки на середине деплоя (например, rsync упал после создания сайта на Webinoly) — сайт на сервере уже создан, но в реестре не появится, пока весь процесс не завершится успешно, либо использовать двухфазную запись (сначала "pending", потом "deployed")

### 1.7 Остальные MVP-команды

- [ ] `hostme list` — таблица всех сайтов из `sites.yaml` (домен, сервер, php, ssl, deployed_at); `--json` — сырой список объектов
- [ ] `hostme open <domain>` — `webbrowser.open(f"https://{domain}")`
- [ ] `hostme <domain> teardown` — `site_delete` на сервере + удаление записи из `sites.yaml`, подтверждение (если не `--json`/не указан `--yes`)

### 1.8 Тестирование Phase 1

- [ ] Unit-тесты: конфиг (1.1), парсинг вывода Webinoly-команд (моки), резолвинг домена/сервера
- [ ] Интеграционный чек-лист на реальном тестовом VPS (Ubuntu, чистый):
  - [ ] `server add` + `server init` — Webinoly встал, `sudo webinoly -version` отвечает
  - [ ] `domain add` с реальным доменом (A-запись заранее направлена на сервер)
  - [ ] `hostme ./test-site` (статика) → сайт открывается по HTTPS
  - [ ] `hostme ./test-php-site` (с `.php`-файлом) → PHP реально выполняется, не отдаётся как текст
  - [ ] повторный `hostme ./test-site` (тот же путь) → обновление без ошибок
  - [ ] `hostme list`, `hostme open`, `hostme <domain> teardown` — весь цикл
- [ ] Ручная проверка агентского сценария: вызов `hostme` из Claude Code (или скрипта) без интерактивного шелла — убедиться, что не виснет и возвращает вменяемый JSON/exit code

---

## Phase 2 — мульти-сервер, мульти-домен, доп. фичи

### 2.1 Несколько серверов и base-доменов

- [ ] Убедиться, что резолвинг домена/сервера (1.1) корректно работает при нескольких серверах и нескольких base-доменах (юнит-тесты на неоднозначные случаи)
- [ ] `hostme domain add <server> <domain>` — включение wildcard SSL для base-домена (`-ssl=on -wildcard`, с DNS TXT-валидацией — здесь уже придётся быть интерактивным или заранее подготовить DNS-провайдера; решить вручную/через флаг `--manual-dns-ack`)

### 2.2 Кастомные домены 2-го уровня

- [ ] Деплой в ещё не зарегистрированный домен без `--server` → понятная ошибка с подсказкой указать `--server`
- [ ] После первого деплоя кастомного домена — привязка домен→сервер сохраняется в `sites.yaml` (уже так по дизайну, зафиксировать тестом)

### 2.3 `hostme <domain> auth` — password protection

- [ ] `hostme <domain> auth --user U --pass P` → `sudo httpauth <domain> -add=[user,pass]` + `sudo httpauth <domain> -path=/`
- [ ] `hostme <domain> auth --off` → `sudo httpauth <domain> -path=all -purge`
- [ ] Обновление `password_protect` в `sites.yaml` (хранить только факт вкл/выкл + логин, **не** хранить пароль в открытом виде локально — решить: не сохранять пароль вовсе, раз он уже ушёл на сервер)
- [ ] Закрыть открытый вопрос PRD §13.2: `--pass` в аргументе командной строки — ок для MVP или нужен `--password-file`/чтение из stdin

### 2.4 `hostme <domain> config` — CORS, redirects, force-https

- [ ] **Force HTTPS**: проверить, не включено ли это уже по умолчанию через `-ssl=on` в Webinoly (в доке сказано «Nginx настроен на редирект HTTP→HTTPS» после включения SSL) — если да, флаг `--force-https` в Hostme может быть no-op/всегда true, обновить PRD по факту
- [ ] **Custom redirects**: маппинг на нативный `sudo site <domain> -redirection -from=... -to=... -http-code=...` (docs/webinoly.md) — реализовать `hostme <domain> redirect add/remove` поверх него, синхронизировать список в `sites.yaml`
- [ ] **CORS**: у Webinoly нет нативного per-site CORS-флага → нужен собственный custom-nginx сниппет per site (`/var/www/<domain>/*-nginx.conf`, см. docs/webinoly.md, раздел «Кастомный Nginx-конфиг»). Спроектировать:
  - [ ] шаблон сниппета с `add_header Access-Control-Allow-Origin ...` на основе списка `cors` в `sites.yaml`
  - [ ] механизм заливки файла по SSH + `nginx reload`
  - [ ] обновление сниппета при каждом изменении `cors` списка (idempotent overwrite)
- [ ] `hostme <domain> config` без флагов — просто печатает текущие настройки сайта из `sites.yaml` (+ сверка с реальным состоянием на сервере, если удастся дёшево получить)

### 2.5 `include` в sites.yaml

- [ ] Реализовать (если не сделано в 1.1) чтение нескольких файлов из `sites.d/*.yaml`, объединение в один список сайтов в памяти
- [ ] Команда или просто документация: как вручную завести `sites.d/personal.yaml`, `sites.d/clients.yaml` и добавить их в `include:`
- [ ] Убедиться, что запись (создание/обновление сайта) идёт в тот файл, откуда сайт был изначально прочитан, а не всегда в главный `sites.yaml`

---

## Phase 3 — доработки

### 3.1 `hostme <domain> debug`

- [ ] Статус: HTTP HEAD/GET запрос на `https://<domain>`, таймаут, код ответа
- [ ] Логи: `sudo log <domain> [-error] -lines=N` через SSH, вывод хвоста в терминал

### 3.2 Rollback (`revs`/`rollback`/`rollfore`/`cutover`/`discard`)

- [ ] Спроектировать схему releases на сервере: Webinoly ожидает фиксированный webroot (`/var/www/<domain>/htdocs`) — для releases-подхода понадобится держать `releases/<timestamp>/` рядом и симлинк `htdocs → releases/<current>` (или `current` симлинк внутри `htdocs`, уточнить, что позволяет структура Webinoly без конфликта с его собственными файлами типа `wp-config.php`/кэша)
- [ ] `deploy` должен класть файлы в новую `releases/<ts>` папку, а не поверх текущей (меняет 1.6 rsync-шаг)
- [ ] `hostme <domain> revs` — список releases (по датам папок)
- [ ] `hostme <domain> rollback` / `rollfore` — переключение симлинка на предыдущий/следующий release + возможно `nginx reload`, если нужно
- [ ] `hostme <domain> discard` — удаление незакоммиченного/незадеплоенного изменения (уточнить точную семантику относительно surge — как это выглядит при отсутствии "preview" концепции)
- [ ] Политика хранения старых releases (сколько хранить, когда чистить)

### 3.3 Git push-to-deploy (опционально)

- [ ] Оценить целесообразность (bare-репозиторий на сервере + `post-receive` hook, вызывающий тот же деплой-путь) — отдельное мини-исследование перед реализацией

### 3.4 `-proxy=` сайты (Node/Java/etc. за Nginx)

- [ ] `hostme <path> <domain> --proxy PORT` (или автоопределение по наличию `package.json`/отсутствию статики+php) → `sudo site <domain> -proxy=[localhost:PORT]`
- [ ] Вопрос управления самим процессом приложения (systemd unit?) — вне зоны ответственности Webinoly/Hostme, задокументировать как ограничение

---

## Сквозные задачи (не привязаны к одной фазе)

- [ ] Пройтись по `docs/webinoly.md` разделу «[TBD/уточнить]» после первого реального `server init` и обновить и PRD.md §13, и docs/webinoly.md по факту
- [ ] Требования к серверу перед `server add`/`server init`: чистый Ubuntu 24.04/26.04, открытые порты (см. docs/webinoly.md «Установка»), passwordless sudo для SSH-пользователя — оформить как явный чек-лист/секцию в README
- [ ] Секьюрити-ревью: как хранится `ssh_key` путь (не сам ключ) в `servers.yaml`, права доступа на `~/.config/hostme/` (600/700), не логируется ли пароль `httpauth` в `--json`/стектрейсах
- [ ] Решить вопрос из PRD §13.2 (формат передачи пароля) окончательно и закрыть открытый вопрос в PRD.md
- [ ] Skill/обёртка для агентов Claude Code, которая знает про `hostme` (как вызывать, какие есть команды) — чтобы агенты могли публиковать артефакты без ре-объяснения синтаксиса каждый раз (по духу раздела 2 PRD)
