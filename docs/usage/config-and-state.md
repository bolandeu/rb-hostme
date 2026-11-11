# Настройки, состояние и реестр

Что hostme читает и где что лежит. Ничего из этого не живёт в git-репозитории —
почему, ADR [0003](../adr/0003-settings-and-state-outside-the-repository.md).

## Две папки

| Что | Путь | Кто пишет |
| --- | --- | --- |
| Настройки | `~/.config/hostme/` — `servers.yaml`, `settings.yaml` | человек |
| Состояние | `platformdirs.user_data_dir("hostme")` — `sites.yaml`, `sites.d/`, `target-backups/` | сам hostme |

`user_data_dir("hostme")` — macOS `~/Library/Application Support/hostme`, Linux
`~/.local/share/hostme`. До v0.4.0 всё лежало в `~/.config/hostme`; старое место
переносится само при первом запуске.

Права: обе папки `700`, `servers.yaml`/`sites.yaml` — `600`.

## `servers.yaml` — серверы и служебные домены

```yaml
servers:
  - name: vps1
    host: 45.12.34.56
    user: root
    ssh_key: ~/.ssh/id_ed25519      # путь к ключу, не сам ключ
    default: true
    base_domains:
      - name: example.dev
        default: true               # домен по умолчанию для авто-имени
  - name: vps2
    host: 88.99.11.22
    user: deploy
    ssh_key: ~/.ssh/id_ed25519
    base_domains:
      - name: side-projects.io
```

`ssh_key` хранит только путь: файл ключа остаётся у ssh. Паролей в файле нет.

## `sites.yaml` — реестр сайтов

```yaml
include:
  - sites.d/personal.yaml
  - sites.d/clients.yaml

sites:
  - domain: blog.example.dev
    server: vps1
    local_path: /Users/me/dev/blog/dist
    php: false
    ssl: true
    force_https: true
    cors: []
    redirects: []
    password_protect: null         # факт защиты и логин, без пароля
    deployed_at: "2026-09-08T12:00:00"
```

`include` разносит сайты по файлам (по проектам, по клиентам) и не трогает
основной. Пути в `include` — относительные от папки `sites.yaml`. Обновление
сайта пишется обратно в тот файл, откуда он прочитан.

Поля сайта меняются командой `hostme <domain> config` (CORS, редиректы,
nginx-сниппет), `hostme <domain> auth` (Basic Auth) и деплоем (`php`, `ssl`,
`deployed_at`). Руками файл править можно: `ruamel.yaml` сохраняет
форматирование и комментарии.

## `settings.yaml` — политики

```yaml
target_backups:
  keep: 5            # последние N снепшотов на target
  max_age_days: 30   # и/или старше X дней
```

Снепшот удаляется, если он не среди последних `keep` **или** старше
`max_age_days`. Самый свежий не удаляется никогда: он нужен `rollback`.
`hostme doctor` показывает путь, размер и политику бэкапов.

## Пароли target'ов

Пароль стороннего хостинга hostme не держит в `servers.yaml`: он приходит из
переменной окружения `HOSTME_DEPLOY_<NAME>_PASSWORD`, иначе из OS keychain
(`hostme:<name>`). Keychain необязателен: на headless-сервере его нет — это не
ошибка. `hostme auth status` показывает, откуда взят доступ и работает ли он,
не печатая значений.
