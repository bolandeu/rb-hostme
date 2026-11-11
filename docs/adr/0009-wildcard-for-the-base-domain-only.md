# Wildcard — только для base-домена, поддомены идут через `-add-to-wildcard`

Wildcard-сертификат требует DNS-01 и ручного шага, а обычный `-ssl=on` на каждый поддомен бьёт по лимиту запросов Let's Encrypt при многих сайтах. Поэтому MVP-путь такой: base-домен получает wildcard один раз вручную (`sudo site <домен> -ssl=on -wildcard`), а каждый новый поддомен цепляется к нему без DNS-шага — `sudo site <sub>.<домен> -ssl=on -add-to-wildcard=<домен>`, подтверждено вживую на `test1`/`test2.antagorapp.ru`. Обычный per-domain `-ssl=on` остаётся запасным путём: он продлевается автоматически, wildcard — нет.

Компромисс: пропущенное продление wildcard снимает HTTPS со всех поддоменов сразу. Этот риск принят ради отсутствия ручной работы на каждый поддомен.

Код — `webinoly.enable_ssl(..., add_to_wildcard=...)`; процедура base-домена — `docs/usage/wildcard-ssl.md`.
