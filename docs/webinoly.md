# Webinoly — полный референс команд

Источник: https://webinoly.com/ (страницы Install + Documentation: Site, Stack, HttpAuth, Log, Webinoly). Извлечено из локально сохранённых HTML-страниц документации (`docs/ webinoly/`, дамп от 2024-08-04) — после консолидации в этот файл дамп можно удалить, здесь есть всё необходимое.

Использование в проекте Hostme: см. `PRD.md`. Ниже — полная выжимка команд Webinoly как таковых, без привязки к Hostme; разделы, которые Hostme **не использует** (WordPress, MySQL/MariaDB и всё, что от них зависит), помечены явно, но оставлены для справки на будущее.

---

## Установка

Требования: Ubuntu Server 24.04/26.04 LTS (arm64 или x86_64), bash, минимум 512MB RAM.

Открытые порты:

| Порт | Направление | Назначение |
|---|---|---|
| 22/TCP | in/out | SSH |
| 25/TCP | out | почта |
| 80/TCP | in/out | HTTP |
| 443/TCP, 443/UDP | in/out | HTTPS |
| 587/TCP | out | SMTP (опционально) |
| 11371/TCP | out | GPG-ключи |
| 22222/TCP | in | админ-панель Webinoly |

Перед установкой: `sudo apt update && sudo apt -y upgrade` (и по-хорошему `reboot`).

Команда установки:

```
wget -qO weby qrok.es/wy && sudo bash weby <режим> <версия>
```

Режимы:

| Режим | Пакеты | Для чего |
|---|---|---|
| `-nginx` | только Nginx | статические HTML-сайты |
| `-php` | Nginx + PHP | **используется в Hostme** — статика + PHP, без БД |
| `-lemp` (по умолчанию) | Nginx + PHP + MySQL/MariaDB | WordPress / full-stack — **не используется в Hostme** |
| `-clean` | ничего | ручная кастомная сборка через `stack` |

Конкретную версию Webinoly можно закрепить: `sudo bash weby -lemp -ver=1.17.9` (актуально с версии 1.17.9+).

Не используйте `-lemp` по умолчанию, если планируете кастомизировать сервер (версию PHP, движок БД и т.п.) — для этого лучше `-clean` + `stack` (см. Пример #5 ниже).

### Примеры быстрого старта (из офиц. Quick Setup)

**HTML:**
```
wget -qO weby qrok.es/wy && sudo bash weby -nginx
sudo site example.com -html
sudo site example.com -ssl=on
sudo webinoly -sftp=on
```

**PHP (сценарий Hostme):**
```
wget -qO weby qrok.es/wy && sudo bash weby -php
sudo site example.com -php
sudo site example.com -ssl=on
sudo webinoly -sftp=on
```

**Reverse proxy** (Node/Java/Django/Vue/Angular/... за Nginx):
```
wget -qO weby qrok.es/wy && sudo bash weby -nginx
sudo site example.com -proxy=[localhost:8082]
sudo site example.com -ssl=on -root-path=/opt/app/web
```

**Кастомная сборка:**
```
wget -qO weby qrok.es/wy && sudo bash weby -clean
sudo stack -php-ver=7.4
sudo webinoly -timezone
sudo nano /opt/webinoly/webinoly.conf
sudo stack -lemp -build=light
sudo site example.com -php
```

**WordPress** [не используется в Hostme]:
```
wget -qO weby qrok.es/wy && sudo bash weby
sudo site example.com -wp -cache=on
sudo site example.com -ssl=on
sudo httpauth -add
sudo webinoly -sftp=on
```

---

## `site` — создание и управление сайтами

```
sudo site <domain> <option> <option2>
```

Флаги: `-cache -clone-from -delete -delete-all -empty -force-redirect -forward -html -info -list -multisite-convert -mysql -on -off -parked -php -proxy -redirection -ssl -wp`

### Создание сайта

```
sudo site example.com -html          # статика
sudo site example.com -php           # PHP (используется в Hostme)
```

Главный домен (не поддомен) автоматически отвечает и на `example.com`, и на `www.example.com` (см. `-force-redirect` ниже).

Для PHP-сайтов Nginx настроен на `try_files $uri $uri/ /index.php$is_args$args;` — всё замыкается на index-файл, 404 нужно обрабатывать в самом PHP-коде.

PHP-сайт с базой данных [не используется в Hostme — см. PRD, MySQL вне скоупа]:
```
sudo site example.com -mysql
sudo site -mysql                                  # без домена — просто создать БД+юзера
sudo site example.com -mysql=custom               # с вопросами
sudo site -mysql=[host,dbname,dbuser,password]     # напрямую
```
`random` вместо пароля — автогенерация.

FastCGI Cache поддерживается для любого PHP-сайта.

### WordPress [не используется в Hostme]

```
sudo site example.com -wp
sudo site example.com -wp=custom -cache=on
sudo site example.com -wp=[<setup_db>,<setup_wp>,<host>,<dbname>,<dbuser>,<dbpass>,<wp_prefix>,<external_db_user>,<external_db_pass>]
sudo site example.com -wp -db-role=extra
sudo site example.com -multisite-convert
sudo site example.com -replace-content=[search-this,replace-with]
sudo site example.com -env=<production|staging|development|local>
```
Конфиг `wp-config.php` создаётся Webinoly в `/var/www/example.com/wp-config.php` (на уровень выше `htdocs`). Поддержка внешних БД (Amazon RDS и т.п.) через `-external-db=[user,pass]`.

### Подпапки (subfolder) — независимая конфигурация каждой директории домена

```
sudo site example.com -html -subfolder=/one
sudo site example.com -php -subfolder=/two
sudo site example.com -wp -subfolder=/three
sudo site example.com -proxy -subfolder=/four
sudo site example.com -delete -subfolder=/xxx
```
Можно вообще не иметь сайта в корне домена, только в подпапках, в любой комбинации типов. Большинство команд (`-cache`, `-multisite-convert`, `-clone-from`, `-info`, `httpauth ... -path`, `log ... -wp`, `webinoly -backup`/`-clear-cache`) принимают `-subfolder=/xxx` для адресации конкретной подпапки. Удаление домена с `-subfolder` удаляет **все** подпапки внутри.

### Parked-домен (алиас)

```
sudo site example.com -parked
sudo site example.com -parked=mainsite.com
```
Доп. для WP Multisite: `sudo site example.com -parked=mainsite.com -domain-mapping-wp-id=3`.

### Domain forwarding

```
sudo site example.com -forward=example.org
sudo site example.com -forward=https://example.org -root=on   # без сохранения путей
```

### Reverse Proxy — потенциально полезно в Phase 3 Hostme для не-PHP приложений

```
sudo site example.com -proxy=[localhost:8080]
sudo site example.com -proxy=[127.0.0.1:8080]
sudo site example.com -proxy=[https://example.com]
sudo site example.com -proxy=[http://example.com:8080]
sudo site example.com -proxy=[http://unix:/home/<user>/<project>/<project>.sock]
```
URI в апстриме не поддерживается (`http://localhost:8000/uri/` — нельзя). Для случаев, где нужен URI в бэкенд-пути (например S3-репозитории), есть **Dedicated Reverse Proxy** — конфиг полностью прозрачный, без стандартных защитных заголовков/блокировок:
```
sudo site example.com -proxy=[https://repo.example.org] -dedicated-reverse-proxy
sudo site example.com -proxy=[https://s3.bucket1.aws.com] -dedicated-reverse-proxy=simple   # поддержка URI в пути бэкенда
```
⚠️ Dedicated reverse-proxy — только для файловых репозиториев (S3-подобных), не для сайтов: убирает часть HTTP-заголовков и защит.

### Fully custom (`-empty`)

```
sudo site example.com -empty              # пустой сайт, свой nginx-конфиг с нуля
sudo site example.com -empty=blank        # без дефолтных location-блоков/заголовков вообще
```
Свой конфиг кладётся в `/var/www/example.com/custom-nginx.conf` (нужен минимум один `location /`).

### Управление сайтом

```
sudo site example.com -on / -off          # временно вкл/выкл без удаления
sudo site example.com -clone-from=dev.example.com [-overwrite=on] [-env=staging]
sudo site example.com -delete             # с подтверждением
sudo site example.com -delete=force       # без вопросов (unattended)
sudo site example.com -delete=keep-db     # не удалять БД
sudo site example.com -delete=force -revoke=on   # + отозвать SSL
sudo site -delete-all[=force|=keep-db]    # снести все сайты на сервере
sudo site example.com -info [-subfolder=/x]
sudo site -list [=<фильтр>]
```
Фильтры `-list`: `disabled, main, html, php, wordpress, parked, proxy, forward, tools, default, ssl, nossl, sslstaging, accesslog, noaccesslog, cache, nocache, adminauth, noadminauth, debug, nodebug, wpenv`.

Сайт, помеченный как `default-site` или `tools-site`, нельзя удалить обычным способом (только через `force`/`-delete-all`).

Флаг удаления сайта, который использует Hostme, — `-delete=force` (см. выше), подтверждён вживую (`tests/e2e/test_webinoly_smoke.py`, `webinoly.delete_site`). Вопрос из PRD закрыт.

### www / non-www

```
sudo site example.com -force-redirect=<www|root|off>
sudo site example.com -force-redirect=root -ignore-ssl   # если SSL-сертификат покрывает только один вариант
```

### FastCGI Cache

```
sudo site example.com -cache=on                 # для WP (pre-configured)
sudo site example.com -wp -cache=on -wp-cache-plugins=on
sudo site example.com -cache=custom              # для PHP / WordPress / Reverse-Proxy — своя конфигурация
sudo site example.com -cache=custom -cache-valid
sudo site example.com -cache=custom -query-string-cache=one
sudo site example.com -cache=custom -query-string-never-cache=two
sudo site example.com -cache=custom -query-string-cache-default=never
sudo site example.com -cache=custom -skip-cache=/page
sudo site example.com -cache=custom -skip-cookie-cache=app_logged_in
sudo site example.com -cache=off [-reset]
```

### SSL (Let's Encrypt)

```
sudo site example.com -ssl=on              # всегда доступно, авто-редирект HTTP→HTTPS
sudo site example.com -ssl=off [-revoke=<on|off|force>]
sudo site example.com -ssl=on -root=mainsite.com          # для parked-сайтов
sudo site example.com -ssl=on -root-path=/opt/myapp/web   # для reverse-proxy (локальный апстрим)
sudo site example.com -ssl=on -manual=<http|dns>           # если сайт не доступен напрямую снаружи; НЕ продлевается автоматически
sudo site example.com -ssl=on -wildcard                    # *.example.com, нужна DNS TXT-запись для валидации
sudo site sub.example.com -ssl=on -add-to-wildcard=example.com   # добавить сайт к существующему wildcard-серту (только 1 уровень поддоменов)
sudo site -ssl=renew                        # форс проверки продления (<30 дней до истечения)
sudo site -ssl=force-renewal-all
sudo site example.com -ssl=force-renewal [-root=... | -root-path=... | -wildcard | -manual=...]
sudo site example.com -ssl=on -test-cert [-wildcard | -root-path=...]   # staging-окружение Let's Encrypt для тестов
sudo site example.com -ssl=on -ssl-key=/path/cert.key -ssl-crt=/path/cert.crt [-ssl-ocsp=/path/cert.pem]   # свой сертификат
```
Сертификаты Let's Encrypt валидны 90 дней, продление — автоматическое (ежедневный таймер + еженедельная сверка Webinoly), кроме `-manual` и (уточнить) части кастомных случаев. Email для регистрации — `sudo webinoly -email=user@example.com`. Свои сертификаты лучше класть в `/etc/nginx/certs` (входит в бэкапы/экспорт Webinoly).

### Редиректы

```
sudo site example.com -redirection                                   # интерактивно
sudo site example.com -redirection -from=/path -to=/test -http-code=308
sudo site example.com -redirection -from=/path -to=http://example.com
sudo site example.com -redirection -from=/path -http-code=410        # без "to" для статус-кодов типа ошибок
sudo site example.com -redirection -delete -from=/path
sudo site example.com -redirection -from='^\.(gif|jpg|jpeg)$' -to=/test -regex=insensitive
sudo site example.com -redirection -list
```
`-http-code`: 301/302/303/307/308 (редиректы), плюс 403/410/444/451 (без `to`). По умолчанию 302. `-exact` — точное совпадение пути (без вложенных). `-regex`: `sensitive|insensitive|longest`.

### Кастомный Nginx-конфиг

Файл `/var/www/example.com/*-nginx.conf` (любое имя, оканчивающееся на `-nginx.conf`) — поддерживается для сайтов любого типа. Для parked-сайтов: `/var/www/{maindomain}/*-{parkeddomain_com}_parked.conf`. Стандартные файлы Webinoly трогать нельзя (перезапишутся при апдейте), но `/etc/nginx/apps.d/*` (reverse-proxy и custom-cache конфиги) — можно. Общий `http`-контекст — `/etc/nginx/conf.d/*.conf`; применяется ко всем сайтам сразу — `/etc/nginx/conf.d/*.conf.srv`. `sudo webinoly -server-reset` — сброс к дефолту, если что-то сломалось.

Webinoly сам определяет домен vs поддомен (домен = `example.com` + `www.example.com`, поддомен = только `sub.example.com`); форсировать явно — `-subdomain=<true|false>`.

---

## `stack` — установка/удаление пакетов (Nginx/PHP/MySQL) и версии

```
sudo stack <option> <option2>
```

Флаги: `-html -lemp -mysql -mysql-ver -php -php-ver -pma -purge -purge-server-all`

```
sudo stack -nginx                       # стабильная ветка
sudo stack -nginx=mainline               # mainline-ветка
sudo stack -php [=force]                 # force — не спрашивать про установку nginx заодно
sudo stack -mysql                        # MariaDB по умолчанию [не используется в Hostme]
sudo stack -lemp                         # nginx+php+mysql [не используется в Hostme]
sudo stack -php-ver=7.4                  # смена версии PHP (переустановка, если уже стоит другая)
sudo stack -mysql-ver=11.4               # смена версии MariaDB (даунгрейд не поддержан) [не используется]
sudo stack -nginx -purge [=force]        # удаление пакета
sudo stack -php -purge
sudo stack -mysql -purge [-mysql=keep-data]   # phpMyAdmin удалится автоматически
sudo stack -purge-server-all[=force]     # снести вообще все пакеты Webinoly
```
Перед удалением nginx рекомендуется отозвать все SSL: `sudo site -delete-all=force -revoke=on`.

Доп. инструменты (устанавливаются по умолчанию вместе со стеком, можно ставить/удалять по отдельности): Let's Encrypt, Duply&Duplicity (бэкапы), Postfix, Redis, Memcached, phpMyAdmin.

```
sudo stack -lemp -build=light    # без доп. инструментов
sudo stack -lemp -build=basic    # только Let's Encrypt + Backups + Postfix
sudo stack -nginx -build=light   # профили работают и для отдельных пакетов
sudo stack -letsencrypt [-purge]
sudo stack -backups [-purge]
sudo stack -postfix [-purge]
sudo stack -redis [-purge]
sudo stack -memcached [-purge]
sudo stack -pma [-purge]         # нужен nginx+php
```

---

## `httpauth` — HTTP Basic Auth (используется в Hostme для password protection)

```
sudo httpauth <option>
```

Флаги: `-add -delete -list -path -whitelist -wp-admin`

```
sudo httpauth -add                          # создать юзера (интерактивно)
sudo httpauth -add=[user,password]          # для unattended-скриптов — то, что нужно Hostme для `<domain> auth`
sudo httpauth example.com -add              # юзер с доступом только к одному домену
```
Если у домена есть свои юзеры — глобальные юзеры на этом домене перестают работать (доступ только "своим").

```
sudo httpauth -delete
sudo httpauth -delete=user
sudo httpauth example.com -delete
sudo httpauth -list
sudo httpauth example.com -list
sudo httpauth example.com -list=protected     # список защищённых путей
sudo httpauth -whitelist -list
```

```
sudo httpauth example.com -path=/folder                 # защитить папку
sudo httpauth example.com -path=/                        # защитить весь сайт — то, что нужно Hostme
sudo httpauth example.com -path=/folder/file.php -exact  # защитить конкретный файл
sudo httpauth example.com -path=/one/folder/ -subfolder=/one
sudo httpauth example.com -path=/folder -delete           # снять защиту с папки
sudo httpauth example.com -path=all -delete                # снять защиту полностью — то, что нужно Hostme для `auth --off`
```

**Важно, реальный баг публичной доки (найден 2026-09-09):** флага `-purge` у `httpauth` **не существует** — шапка самого `/usr/bin/httpauth` перечисляет: `Options: -add, -delete, -list, -wp-admin, -whitelist, -path`. `-path=... -purge` падает с `[ERROR] Please, enter a valid URL path!` (returncode 1, текст в stdout, не в stderr — ещё один нюанс, см. «Итог для Hostme»). Правильный флаг — **`-delete`**. Проверено вживую на `roksdigital.ru`: `-path=/ -delete` реально снимает защиту, `-path=all -delete` (внутри скрипта разворачивается в `-path -delete-all`) — снимает со всех путей сразу.

```
sudo httpauth -whitelist                        # добавить свой IP в whitelist (интерактивно)
sudo httpauth -whitelist=10.126.196.2
sudo httpauth -whitelist=1.1.1.1,2.2.2.2          # несколько через запятую
sudo httpauth -whitelist -purge
```

WP-логин и панель Webinoly (`wp-admin`, `wp-login.php`) защищены Basic Auth по умолчанию [не актуально для Hostme без WP]:
```
sudo httpauth example.com -wp-admin=<on|off>
```

---

## `log` — логи

```
sudo log <domain> <option>
```

Флаги: `-auth -error -le -mail -mysql -only-error -php -purge -ssh -syslog -wp` (устаревший: `-only-error` в пользу access-log toggle, см. ниже; `-fpm` = алиас `-php`)

```
sudo log example.com              # access-лог сайта (в реальном времени)
sudo log                          # access-лог всех сайтов
sudo log -only-error=off          # включить access-лог для новых сайтов (по умолчанию выключен)
sudo log example.com -only-error=off
sudo log example.com -error       # error-лог сайта
sudo log -error                   # error-лог всех сайтов
sudo log example.com -lines=25    # число строк вывода (по умолчанию 10)
```
Access/error-логи — на уровне всего домена, `-subfolder` игнорируется (кроме WP debug-режима).

```
sudo log example.com -wp                    # WP debug.log в реальном времени [не используется в Hostme]
sudo log example.com -wp=on [-display=off] [-env=development]
sudo log -php    /  -ssh  /  -mail  /  -syslog  /  -auth  /  -le
```
```
sudo log -mysql=error                      # [не используется в Hostme]
sudo log -mysql=general [-enable|-disable]
sudo log -mysql=slow [-enable [-long-query-time=3] | -disable]
sudo log -mysql=binary [-enable|-disable]
```
```
sudo log -purge [=force]
sudo log -purge=<nginx|letsencrypt|mysql|redis|all|force>
```

---

## `webinoly` — глобальные настройки сервера

```
sudo webinoly <option>
```

Флаги: `-backup -blockip -cache-valid -clear-cache -custom-headers -datadog -db-import -dbpass -default-site -dynvar -email -external-sources-update -info -login-www-data -mysql-password -mysql-public-access -query-string-cache -query-string-never-cache -timezone -tools-port -tools-site -server-reset -skip-cache -skip-cookie-cache -smtp -uninstall -update -verify -version`

**Подтверждено на практике (Webinoly 1.21.2, 2026-09-08):** `-login-www-data=on` из дампа документации 2024 года больше не работает (`[ERROR] Please, enter a valid option!`) — актуальный флаг **`-sftp=on`**, он и используется везде ниже.

### Обновление Webinoly

```
sudo webinoly -update       # обновляет только сам Webinoly, не пакеты сервера
```
Систему (`apt update && apt -y upgrade`) обновлять отдельно, минимум раз в месяц. На VPS — раз в ~4 месяца сделать stop/start инстанса (не reboot), чтобы провайдер мог переехать на новый хост.

### FastCGI Cache — глобально

```
sudo webinoly -cache-valid                       # интерактивно (200 / 3xx-4xx / inactivity)
sudo webinoly -cache-valid=[10d,1w,5m]            # 200-код, простой, редиректы
sudo webinoly -clear-cache=<fastcgi|redis|memcached|opcache|all|<domain>>
sudo webinoly -skip-cache=/page [-list | -delete] [-regex=<sensitive|insensitive>]
sudo webinoly -skip-cookie-cache=<cookie> [-list | -delete] [-regex=...]
sudo webinoly -query-string-cache=<qs> [-delete | -list]
sudo webinoly -query-string-never-cache=<qs> [-delete | -list]
```

### Блокировка IP

```
sudo webinoly -blockip=123.231.12.31
sudo webinoly -blockip -list
sudo webinoly -blockip -purge / -blockip=123.231.12.31 -purge
sudo webinoly -blockip=1.1.1.1,2.2.2.2
```

### Дефолтный сайт сервера (ответ на запрос по голому IP)

```
sudo webinoly -default-site=<default|blackhole|domain>
```
`blackhole` — сервер вообще не отвечает (444) на запросы к неизвестным доменам; также включает `reuseport`/`backlog`/`deferred` в Nginx `listen`.

### HTTP-заголовки

Поддерживаются: Cache-Control, CSP, HSTS, Permissions-Policy, Referrer-Policy, X-Content-Type-Options, X-Frame-Options, X-Robots-Tag, X-XSS-Protection — включаются/настраиваются через `/opt/webinoly/webinoly.conf`.
Свои заголовки — через файлы `/opt/webinoly/templates/source/custom_header_{http|html|https}_webinoly.data` (строки `add_header ...;`), применить: `sudo webinoly -custom-headers=reload` (или `-remove`).

### MySQL-инструменты [не используются в Hostme]

```
sudo webinoly -dbpass
sudo webinoly -mysql-password [=[user,pass]]
sudo webinoly -db-import [-file=/folder/name.sql] [-external-db=[user,pass,host:port]]
sudo webinoly -mysql-public-access=on [-bind=<::|*|ip[,ip...]>] [-create-master-user=[user,pass]] [-replication-slave]
```
Права БД по умолчанию (меняется в конфиге): `basic|limited|extra|complete|full|grant|all`, за сайт — `sudo site example.com -wp -db-role=extra`.

### Панель инструментов (phpMyAdmin, PHP info/ping/status, Nginx status)

```
http://server-ip:22222              # защищено HTTP Auth
sudo webinoly -tools-port[=19816]
sudo webinoly -tools-site=example.com    # доступ только с этого домена (порт 19816 и т.п.)
sudo webinoly -tools-site=default        # сброс
sudo webinoly -tools-site=reset          # пересобрать сайт панели с нуля
```

### Сервер / SFTP / таймзона / почта

```
sudo webinoly -sftp=<on|off>    # SFTP-доступ для www-data (используется в примерах Hostme)
sudo webinoly -timezone[=America/Mexico_City]
sudo webinoly -smtp [=[smtp_host,user,password,mainhost.com]] [-purge]
```

### Бэкапы

```
sudo webinoly -backup=local -export[=<domain>|=[d1,d2,d3]] [-subfolder=/x] [-skip-db] [-filename=... -destination=...]
sudo webinoly -backup=local -import=<full|stack|sites> -file=/folder/name [-overwrite=on]
sudo webinoly -backup=local [-wp=<domain>|=[d1,d2,d3]] [-destination=/folder] [-max=5] [-bucket=bucketname/folder]
sudo webinoly -backup=local -dbname=<name|=[n1,n2,n3]|all> [-external-db=[user,pass,url:port]] [-filename=db.sql]
sudo webinoly -aws-s3-credentials [=[key,secret]] [=awsiamrole]
sudo webinoly -backup=s3 -profile=name -bucket=bucketname/folder -source=/folder [-max-age=2M]
sudo webinoly -backup=s3 -run / -delete / -list / -info / -restore [=<file|folder>] [-destination=...] [-date=...]
sudo webinoly -backup=s3 -add-db-pre=example.com [-max=5] [-bucket=...] [-list|-purge]
sudo webinoly -backup=s3 -send-to-s3=/file -bucket=bucketname/folder [-s3-compatible-endpoint=...]
```
`export=full` восстанавливает и конфигурацию, и сайты; можно возить только `/opt/webinoly/webinoly.conf`, чтобы раздать одинаковый конфиг всей команде. SSL-сертификаты сами по себе не экспортируются/импортируются отдельно от сайта (только вместе с полным экспортом сервера).

### Datadog [вероятно не нужно Hostme, но задокументировано]

```
sudo webinoly -datadog
sudo webinoly -datadog=<api_key> -integrations=off -logs=off
sudo webinoly -datadog -integrations=<nginx|fpm|mysql|redis> [-purge] [-logs=on]
sudo webinoly -datadog -purge
```

### Сброс / диагностика / удаление

```
sudo webinoly -server-reset[=<os|nginx|php|mysql|all|permissions>] [-recalculate=on]
sudo webinoly -dynvar=<variable> -value=<data>     # точечная правка /opt/webinoly/webinoly.conf
sudo webinoly -verify           # проверка целостности файлов/конфигурации
sudo webinoly -info             # полная информация об установке
sudo webinoly -version           # (-v / -V) — версия Webinoly + версия стека
sudo webinoly -uninstall [-no-recovery]   # сайты и пакеты НЕ удаляются, только сами команды Webinoly
```
После ручной правки `/opt/webinoly/webinoly.conf` всегда нужен `-server-reset`, иначе изменения не применятся.

Конфиг-файл `/opt/webinoly/webinoly.conf` покрывает: ОС/таймзону/kernel/swap, IAM Role, ветку Nginx, лимиты загрузки файлов, email, SFTP, access-логи и их формат, error log level, дефолтный сайт, порт/домен админ-панели, whitelist IP для HTTP Auth, blockip, блокируемые файлы/расширения, FastCGI Cache таймауты, WP-специфичные дефолты (кэш, basic auth, лимит запросов к wp-admin, xmlrpc), HTTP-заголовки, версию/тюнинг PHP (`pm`, `pm.max_children`, `memory_limit`, `max_execution_time`, `max_file_uploads`, `max_input_vars`, opcache-настройки, `disable_functions`, `allow_url_fopen`), Redis maxmemory, движок/версию БД, внешние DB credentials, дефолтные права БД, MySQL general/binary/slow log.

---

## Итог для Hostme (см. также PRD.md/AGENTS.md)

Всё ниже реализовано в `src/hostme/webinoly.py` и подтверждено вживую на `sites-first-beget` (Ubuntu 24.04.4, Webinoly 1.21.2, стек 1.13), не только по документации:

- Установка на новый сервер: `wget -qO weby qrok.es/wy && sudo bash weby -php` — подтверждено полностью неинтерактивным (никаких вопросов про email/DB на этом шаге).
- Создание сайта: `sudo site <domain> -html` или `-php` (автоопределение по наличию `*.php`), сразу с заглушкой `index.html`/`index.php` вместо голого 403 — пустой `htdocs` без `autoindex` отдаёт именно 403, не 404 (реальный пойманный баг, см. TODO.md, «Сквозное улучшение»).
- SSL всегда: `sudo site <domain> -ssl=on` (обычный per-domain, HTTP-01, авто-продление) или `-add-to-wildcard=<base>` (мгновенно, без DNS-шага, если у base-домена уже есть wildcard-сертификат) — это и есть реальный MVP-путь, а не `-wildcard` на каждый домен.
- Wildcard-сертификат на base-домен (`-ssl=on -wildcard`) — ручной DNS-01, два TXT-шага подряд, см. WILDCARD-SSL.md; прошли полностью дважды вживую (`antagorapp.ru`, `bolandau.ru`). Не автоматизировано — нужен DNS-провайдер с API (пока нет, DNS у Beget без API-доступа), отложено в TODO.md (2.1).
- Удаление: `sudo site <domain> -delete=force -revoke=on|off`.
- Password protection: `sudo httpauth <domain> -add=[user,pass]` / `-path=/` / `-path=all -delete` для снятия (**не `-purge`** — этого флага у `httpauth` не существует, ошибка в публичной доке Webinoly, см. раздел `httpauth` выше) — реализовано в `hostme <domain> auth`, значения экранируются `shlex.quote` (без этого была бы command injection через `--pass`). Заодно: сообщения об ошибках Webinoly пишет в **stdout**, не в stderr — `webinoly.py` строит текст исключений через `_error_text()` (stderr, с фолбэком на stdout), иначе ошибка показывалась бы пустой.
- Редиректы: `sudo site <domain> -redirection -from=... -to=... -http-code=...` — `hostme <domain> config --redirect/--remove-redirect`.
- CORS: своего флага у Webinoly нет — свой nginx-сниппет (`/var/www/<domain>/hostme-cors-nginx.conf`) на уровне `server{}`, без `location /` (уже занят самим Webinoly — второй `location /` в том же server-блоке роняет `nginx -t`). `hostme <domain> config --cors/--no-cors`.
- Логи (`sudo log <domain>`) стримят в реальном времени и сами никогда не завершаются — `hostme <domain> debug` оборачивает в `timeout <N>s` на сервере, иначе команда виснет до собственного таймаута.
- `nginx.conf` у Webinoly включает `open_file_cache` (`valid=30s`) — после любой смены symlink'а webroot (releases/rollback) обязателен `nginx -t && systemctl reload nginx`, иначе сайт до ~30с отдаёт старый контент несмотря на уже переключенный симлинк. Реальный пойманный баг, см. TODO.md 3.2.
- Releases/rollback: `htdocs` — симлинк на `releases/<таймстамп>`, а не сама директория (жёсткое требование — nginx-конфиг Webinoly ожидает фиксированный `root /var/www/<domain>/htdocs`, руками не редактируется). `mkdir -p releases` создаёт директорию `root:root` — обязателен `chown www-data:www-data releases` сразу же, иначе весь сайт отдаёт 404 (реальный пойманный баг).
- SFTP для загрузки файлов вручную (не только через Hostme): `sudo webinoly -sftp=on`.
- WordPress и MySQL/MariaDB — сознательно не используются (см. PRD, раздел 10); `-proxy=` (reverse proxy для Node/Java) — тоже вне скоупа по явному решению (только html/php/статика).
