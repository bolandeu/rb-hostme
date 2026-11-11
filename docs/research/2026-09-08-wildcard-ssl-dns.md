# DNS-01 для wildcard: шесть NS Beget и провал первой попытки

Дата: 2026-09-08 (первый прогон, провал), 2026-09-09 (`bolandau.ru`, успех). Где: `sites-first-beget`, домены `antagorapp.ru` и `bolandau.ru`, DNS у Beget. Как: `sudo site <домен> -ssl=on -wildcard` вручную по SSH, `dig TXT ... @<ns>` по каждому неймсерверу.

Сама процедура, как её выполнять сейчас, — `docs/usage/wildcard-ssl.md`. Здесь — что выяснилось.

## Первый прогон упал на рассинхроне NS

`antagorapp.ru`: TXT-запись `_acme-challenge` добавили в панели Beget и сразу нажали `Enter`. certbot ответил:

```text
Certbot failed to authenticate some domains (authenticator: manual):
  Detail: Incorrect TXT record "ixIXmtIs..." found at _acme-challenge.antagorapp.ru
  Detail: During secondary validation: Incorrect TXT record "kmoVBG2A..." found at _acme-challenge.antagorapp.ru
```text

Причина: домен обслуживают шесть NS тремя кластерами — `ns1/ns2.beget.ru`, `ns1/ns2.beget.pro`, `ns1/ns2.beget.com`. Они синхронизируются не мгновенно: в момент проверки часть отдавала старое значение, часть новое. Let's Encrypt проверяет из двух сетевых точек (primary и secondary, защита от BGP-хайджека) и увидел два разных значения. Обе точки получили `unauthorized`.

Проверка через публичные резолверы (8.8.8.8, 1.1.1.1) в тот момент не помогла: они тоже кэшируют один конкретный ответ и разнобой между NS не показывают.

## Второй прогон и `bolandau.ru`

После проверки **каждого** NS напрямую (`dig TXT _acme-challenge.<домен> @ns1.beget.ru` и так все шесть) прогон на `antagorapp.ru` прошёл с первого раза. Решение из этой находки — ADR 0008.

`bolandau.ru` (2026-09-09) прошёл тем же путём, с одним отличием: TXT-запись расходилась по шести NS неравномерно и не за один раз, между проверками «не хватает» NS менялся — несколько минут ожидания, пока все шесть не показали одно значение подряд. Сертификат подтверждён: SAN `DNS:*.bolandau.ru, DNS:bolandau.ru`, `sudo site bolandau.ru -info` → `SSL: Let's Encrypt`.

## Попытка API Beget

`https://api.beget.com/api/domain/getList` с логином и паролем из панели вернул `AUTH_ERROR: Username/password incorrect` и на GET, и на POST. Значит, для автоматизации нужны рабочие креды и, вероятно, отдельный метод управления DNS-записями, а не `domain/getList`. Креды в репозиторий не класть. Сама автоматизация отложена — идея HOSTME-IDEA-006.
