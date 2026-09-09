# Реальные конфиги Webinoly (снято вживую с sites-first-beget, 2026-09-09)

Не редактировать — это копии того, что уже лежит на сервере (сам Webinoly
помечает их `DO NOT MODIFY`), сохранены сюда только для справки при написании
своих сниппетов в `docs/nginx-snippets/*.conf`, чтобы не дёргать сервер по
SSH каждый раз и не дублировать то, что уже есть.

- `gzip.conf` — `nginx.conf`, глобальные gzip-настройки (уже включено для всех сайтов)
- `headers-http.conf`, `headers-https.conf`, `headers-html.conf`, `headers.conf` — security-заголовки, HSTS, кэш статики по расширению
- `php.conf` — `location /` и `location ~* \.php$` для PHP-типа сайтов
- `locations.conf` — security-правила (dot-файлы, path traversal, заблокированные расширения)
- `auth.conf` — определение `.htpasswd`-файла для `hostme <domain> auth`
- `site-html.conf`, `site-php.conf` — примеры целиком сгенерированного server-блока для обоих типов сайта (реальные домены `bolandau.ru`/`test.bolandau.ru`, оставлены как есть для контекста)

Версии: Webinoly 1.21.2, стек 1.13. Если у Webinoly выйдет апдейт (`hostme
server update`) — эти файлы могут разойтись с реальностью, сверять при
странном поведении, не считать вечной истиной.
