# Webinoly 1.21.2: что ведёт себя не так, как в документации

Дата: 2026-09-08 и позже. Где: сервер `sites-first-beget` (Ubuntu 24.04.4, Webinoly 1.21.2, стек 1.13), живые прогоны. Как: установка, команды `site`/`httpauth`/`webinoly` вручную по SSH и из `hostme`, плюс `tests/e2e/test_webinoly_smoke.py`.

Что нужно постоянно (команды, форматы, раскладка) — `docs/usage/webinoly.md`. Здесь — только находки и их даты.

## 2026-09-08. Установка `-php` неинтерактивна

`wget -qO weby qrok.es/wy && sudo bash weby -php` прошёл без единого вопроса — ни про email, ни про БД. Вывод: `server init` может ставить стек без TTY.

## 2026-09-08. `-login-www-data` больше нет

Флаг `sudo webinoly -login-www-data=on` из дампа документации 2024 года падает с `[ERROR] Please, enter a valid option!`. Актуальный флаг — `-sftp=on`, он и используется.

## 2026-09-09. Пустой сайт отдаёт 403, не 404

Свежесозданный сайт с пустым `htdocs` отвечает `403`: в `try_files` нет `autoindex`. Пользователь видит «доступ запрещён» вместо заглушки. Фикс — сразу после `create_site` класть `index.html`/`index.php` («Сайт в разработке»); накачено и на `bolandau.ru`/`antagorapp.ru` (было 403, стало 200).

## 2026-09-09. `mkdir -p releases` под root ломает сайт

Каталог `releases/` создаётся SSH-сессией root и принадлежит `root:root`. nginx работает от `www-data`, не может даже зайти внутрь и отдаёт 404 на весь сайт, хотя права файлов глубже верные. Фикс — `chown www-data:www-data releases` сразу после создания.

## 2026-09-09. `open_file_cache` держит старый контент до ~30 с

В `nginx.conf` Webinoly включён `open_file_cache` с `valid=30s`. После перекладки симлинка `htdocs` сайт ещё до ~30 с отдаёт старый файл по закэшированному дескриптору. Фикс — `nginx -t && systemctl reload nginx` на каждое переключение релиза.

## 2026-09-09. У `httpauth` нет флага `-purge`, а ошибки идут в stdout

Публичная документация Webinoly предлагает `httpauth ... -path -purge`. Шапка самого `/usr/bin/httpauth` перечисляет только `-add, -delete, -list, -wp-admin, -whitelist, -path`; `-path=<...> -purge` падает с `[ERROR] Please, enter a valid URL path!`. Правильный флаг снятия защиты — `-delete`; `-path=all -delete` снимает со всех путей сразу. Проверено на `roksdigital.ru`.

Вторая находка того же прогона: Webinoly пишет `[ERROR] ...` в **stdout**, а stderr оставляет пустым, код возврата — 1. Без фолбэка на stdout текст исключения был бы пустым. Фикс — `_error_text()` в `src/hostme/providers/webinoly.py`.

## 2026-09-09. `sudo log` не завершается сам

`sudo log <domain>` стримит в реальном времени и не выходит, поэтому внутри `hostme <domain> debug` он обёрнут в `timeout <N>s` на сервере.

## 2026-09-09. Флаг удаления сайта — `-delete=force`

`sudo site <domain> -delete` спрашивает подтверждение, `-delete=force` — нет. Подтверждено живьём, вопрос из спеки закрыт; SSL отзывается `-revoke=on|off`.

## 2026-10-13. Сниппеты `*-nginx.conf` переживают `webinoly -update`

Проверено `hostme server update` на `sites-first-beget`: файлы `/var/www/<domain>/hostme-*-nginx.conf` на месте и работают после апдейта. Сам `webinoly.conf` апдейт может переписать.

## 2026-10-13. Brotli на этих серверах недоступен

nginx 1.30.4 из nginx.org собран без модуля Brotli, пакета `nginx-module-brotli` в репозитории нет. Сайты отдаются только с gzip. Идея HOSTME-IDEA-003.

## 2026-11-12. Обрезанное скачивание `webinoly.tar` даёт ложный успех

Где: свежий Ubuntu 26.04 у NetAngels (`net-angel-vps`), чистая машина, установка через `weby`. `wget` скачал `webinoly.tar` только до ~12 KB — полный архив 829440 B. `tar` сообщил `Unexpected EOF`, распаковка оставила два файла в каталоге установки, nginx и php не поставились.

`weby` идёт без `set -e`: он напечатал `installed successfully`, а затем упал на `app_purge: command not found`. Тот же URL с другой машины отдаёт полный архив (829440 B) — это сетевая неисправность одной машины, не геоблокировка и не блокировка URL.

`hostme` повторял эту ошибку: шаг установки верил коду возврата `bash weby`. Фикс — постусловие после установки (`verify_install()` в `src/hostme/providers/webinoly.py`, та же проверка в `scripts/provision-server.sh`): без any из `webinoly`, `nginx`, `php` установка считается неполной и даёт ошибку. Что именно проверяется — `docs/usage/webinoly.md`, «Проверка после установки». Причина обрыва на одной машине не искалась (out of scope), повторное скачивание — ручной workaround.
