# Webinoly на серверах hostme

Webinoly — установщик серверного стека и набор команд `site`, `httpauth`, `webinoly`, на которые опирается `hostme`. Источник формы команд — https://webinoly.com/ (страницы Install и Documentation). Код, который их вызывает, — `src/hostme/providers/webinoly.py`; перед работой с Webinoly сверяться с этим файлом, а не угадывать флаги.

## Установка стека

`hostme server init` ставит Webinoly сам:

```
wget -qO weby qrok.es/wy && sudo bash weby -php
```

Режим `-php` (nginx + php-fpm, без базы) ставится полностью неинтерактивно: вопросов про email и БД на этом шаге нет. Версию можно закрепить: `sudo bash weby -php -ver=1.17.9`. Режимы `-nginx`, `-lemp`, `-clean` hostme не использует: `-lemp` тянет MySQL/MariaDB, а база вне скоупа.

Требования: Ubuntu Server 24.04/26.04 LTS (arm64 или x86_64), минимум 512 MB RAM. Перед установкой руками: `sudo apt update && sudo apt -y upgrade`, желательно `reboot`.

## Проверка после установки

Код возврата `bash weby -php` ничего не доказывает: установщик идёт без `set -e`. Когда `webinoly.tar` скачался не целиком, `tar` пишет `Unexpected EOF`, в каталоге установки остаются два файла, а `weby` всё равно печатает `installed successfully` и падает позже на `app_purge: command not found` (случай 2026-11-12, `docs/research/2026-09-08-webinoly-behaviour.md`).

Поэтому после установки проверяется постусловие — три команды на сервере:

| Команда | Что доказывает |
|---|---|
| `command -v webinoly` | сам Webinoly |
| `command -v nginx` | веб-сервер |
| `command -v php` | PHP-FPM |

```
hostme server init / scripts/provision-server.sh
   |
   +-- bash weby -php            код 0 ничего не значит
   |
   +-- command -v webinoly nginx php   все три есть?
         |                    |
        да                  нет
         |                    |
     готово          неполная установка, ошибка
```

Нет хотя бы одной — установка неполная. `hostme` поднимает `WebinolyError` (exit-код `PROVIDER_ERROR`, 5) с текстом «установка Webinoly неполная: нет <имена>, вероятно обрезан архив webinoly.tar» и с результатом `webinoly -version`; `scripts/provision-server.sh` печатает те же факты и выходит с кодом 1. Повтор установки без исправления сети даёт ту же ошибку.

Порты:

| Порт | Направление | Назначение |
|---|---|---|
| 22/TCP | in/out | SSH |
| 25/TCP | out | почта |
| 80/TCP | in/out | HTTP |
| 443/TCP, 443/UDP | in/out | HTTPS, HTTP/3 |
| 587/TCP | out | SMTP (опционально) |
| 11371/TCP | out | ключи GPG |
| 22222/TCP | in | панель Webinoly |

## Раскладка сайта и releases

```
/var/www/<domain>/htdocs      симлинк -> releases/<таймстамп>
/var/www/<domain>/releases/   релизы, владелец www-data:www-data
/var/www/<domain>/*-nginx.conf   сниппеты сайта, Webinoly подключает сам
```

nginx-конфиг Webinoly жёстко ждёт `root /var/www/<domain>/htdocs`; сам конфиг не редактируется. Поэтому `htdocs` — симлинк на релиз, а `hostme` перекладывает его при деплое, rollback и rollfore (`switch_release`).

Два обязательных шага:

1. `mkdir -p releases` идёт под root и создаёт каталог `root:root` — сразу за ним нужен `chown www-data:www-data releases`, иначе nginx (он работает от `www-data`) не заходит внутрь и весь сайт отдаёт 404.
2. После смены симлинка нужен `nginx -t && systemctl reload nginx`: в `nginx.conf` включён `open_file_cache` (`valid=30s`), и без reload сайт отдаёт старый контент ещё до ~30 с.

Пустой `htdocs` без `autoindex` отдаёт `403`, не `404`. Поэтому `create_site` сразу кладёт заглушку `index.html`/`index.php` («Сайт в разработке»).

## Команды, которые вызывает hostme

| `hostme` | Webinoly |
|---|---|
| `server init` | `wget -qO weby qrok.es/wy && sudo bash weby -php`, затем `sudo webinoly -sftp=on` |
| создать сайт | `sudo site <domain> -html` или `sudo site <domain> -php` (тип по наличию `*.php`) |
| включить SSL | `sudo site <domain> -ssl=on` / `-ssl=on -add-to-wildcard=<base>` / `-ssl=on -wildcard` |
| выключить SSL | `sudo site <domain> -ssl=off [-revoke=on/off/force]` |
| удалить сайт | `sudo site <domain> -delete=force -revoke=on/off` |
| список сайтов | `sudo site -list` |
| включить/выключить | `sudo site <domain> -on` / `-off` |
| www или без www | `sudo site <domain> -force-redirect=www/root/off` |
| `hostme <domain> auth` | `sudo httpauth <domain> -add=[user,pass]`, затем `sudo httpauth <domain> -path=/` |
| `hostme <domain> auth --off` | `sudo httpauth <domain> -path=all -delete` |
| `hostme <domain> config --redirect` | `sudo site <domain> -redirection -from=<path> -to=<url> -http-code=<код>` |
| `hostme <domain> config --remove-redirect` | `sudo site <domain> -redirection -delete -from=<path>` |
| `hostme <domain> debug` | `sudo log <domain>` и `sudo log <domain> -error` |
| `server update` | `sudo webinoly -update` |

`-ssl=on` всегда включает и редирект HTTP→HTTPS; отдельного флага, чтобы оставить HTTP, у Webinoly нет. Поэтому `hostme` отказывает на `--no-force-https`.

`-add-to-wildcard=<base>` привязывает сайт к уже выпущенному сертификату base-домена: ни DNS-шага, ни нового запроса в Let's Encrypt. Только один уровень поддоменов.

`sudo site -list` печатает строки вида:

```
 + e2edebug2.antagorapp.ru (HTML)(NoSSL)
```

Домен и отдельные скобочные группы подряд, без запятой между ними и без разделителя — `parse_site_list` разбирает именно эту форму.

Сообщения об ошибке Webinoly пишет в **stdout**, не в stderr (`[ERROR] ...`, код возврата 1). `_error_text()` берёт stderr и падает на stdout, иначе текст исключения был бы пустым.

`sudo log <domain>` стримит в реальном времени и сам не завершается. `hostme <domain> debug` оборачивает его в `timeout <N>s` на сервере, иначе команда висит до своего таймаута.

## Свои nginx-сниппеты

Файлы `*-nginx.conf` в `/var/www/<domain>/` Webinoly подключает сам, для сайта любого типа. Их не перезаписывает ни апдейт сайта, ни `webinoly -update`.

Ограничение: в одном `server{}` может быть только один `location /` — его уже занимает Webinoly, второй роняет `nginx -t`. Сниппет `hostme` (CORS, дефолты сайта) пишется на уровне `server{}` без `location /`. Стандартные файлы Webinoly трогать нельзя, их перезапишет апдейт; `/etc/nginx/conf.d/*.conf` — общий `http`-контекст для всех сайтов.

Сниппеты hostme:

- `/var/www/<domain>/hostme-cors-nginx.conf` — `hostme <domain> config --cors`.
- `/var/www/<domain>/hostme-defaults-nginx.conf` — из `src/hostme/data/nginx-defaults.conf` (закрывающий слэш, кэш `/_astro/`), перезаливается при деплое и `hostme server update`.

## Глобальные настройки, которые нужны

- `sudo webinoly -sftp=on` — SFTP для `www-data`, заливка файлов руками.
- `sudo webinoly -email=<адрес>` — email для Let's Encrypt, иначе certbot спрашивает его.
- `sudo webinoly -update` — обновляет только сам Webinoly, не пакеты (`apt`) и не конфиг сайта.
- `sudo webinoly -default-site=<default|blackhole|domain>` — ответ на запрос по голому IP.
- `sudo webinoly -server-reset` — сброс к дефолту после ручной правки `/opt/webinoly/webinoly.conf`.
- `sudo webinoly -version` — версия Webinoly и стека.
- `sudo site <domain> -info` — состояние сайта, строка `SSL: Let's Encrypt` показывает сертификат.

## Не используется

Вне скоупа `hostme` (только html/php/статика): WordPress (`-wp`), MySQL/MariaDB (`-mysql`, `stack -mysql`), `-proxy=` и `-empty`, parked-домены, subfolder-конфигурации, FastCGI cache, `stack` (`-php-ver`, `-purge`), бэкапы Webinoly (`-backup=`), Datadog, панель инструментов (`-tools-port`, `-tools-site`), блокировка IP (`-blockip`). Полный список флагов — документация на webinoly.com; возвращаться туда, когда такой пункт войдёт в скоуп.
