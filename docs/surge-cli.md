# surge.sh CLI — референс

Источник: http://surge.sh/docs/cli/

CLI Hostme намеренно копирует форму команд surge (`<path> <domain>` для деплоя, `<domain> <subcommand>` для управления) — см. PRD.md, разделы 2 и 6. Ниже — то, что реально есть у surge, для сверки при реализации.

## Публикация

- `surge <path> <domain>` — задеплоить проект на домен
- `surge <path> publish` — задеплоить, используя `CNAME`-файл проекта
- `surge ... --preview` — деплой-превью без влияния на продакшн

## Управление проектом

- `surge <domain> revs` — история версий
- `surge <domain> rollback` / `rollfore` / `cutover` / `discard` — переключение между версиями
- `surge <domain> config` — просмотр/изменение настроек проекта
- `surge <domain> teardown` — снести опубликованный проект
- `surge <domain> invite <emails>` / `revoke <emails>` — совместный доступ (**не переносим** — single user, см. PRD раздел 10)

## Инфраструктура и мониторинг

- `surge <domain> dns` / `zone` — управление DNS-записями
- `surge <domain> stats` — трафик/аналитика (**не переносим**)
- `surge <domain> debug` — статус, файлы, аудит-логи, кэш, сертификаты
- `surge <domain> ssl` — установка кастомного SSL-сертификата

## Аккаунт (не переносим — своя инфраструктура, не SaaS)

`login` / `logout` / `whoami` / `verify` / `mfa` / `list` / `plan` / `card` / `tokens` / `nuke`

Из этой группы в Hostme остаётся только смысловой аналог `list` (список сайтов), без всего остального — нет аккаунта/биллинга, которым можно было бы управлять.

## [TBD/уточнить]

Полный список флагов есть в Command Reference surge (не был включён в выжимку выше) — сверить при реализации конкретных подкоманд (`config`, `debug`, `ssl`).
