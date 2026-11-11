# Стек: Python, uv, Typer, системные ssh и rsync

Язык — Python, версия закреплена `uv python pin`. CLI — Typer, YAML —
`ruamel.yaml` (сохраняет форматирование и комментарии: файл правят руками),
вывод — `rich`. SSH и rsync hostme вызывает как системные программы через
`subprocess`, не через Python-библиотеку.

Почему системные `ssh`/`rsync`: они уже настроены на машине человека — читают
`~/.ssh/config`, алиасы, `ProxyJump` и ssh-агент. Paramiko/Fabric дали бы второй
набор настроек и сломали бы существующий конфиг. Остальное (Typer,
`ruamel.yaml`, `rich`) — по стандарту пакета cli-builder.

Следствия:

- Требования к машине: `ssh` и `rsync` в PATH (плюс `lftp` для ftp/sftp-target).
- Ошибки ssh/rsync/Webinoly наружу выходят только как `PROVIDER_ERROR` (код 5).
- Соединение переиспользуется через `ControlMaster`/`ControlPersist`: частые
  короткие подключения ловили rate-limit и fail2ban на сервере.
