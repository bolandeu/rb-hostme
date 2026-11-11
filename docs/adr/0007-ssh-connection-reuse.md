# Переиспользовать одно SSH-соединение

Один деплой делает пять-семь коротких SSH-подключений подряд (`site_exists` → `create_site` → `enable_ssl` → `rsync` → `chown` → reload). Реальный сервер ответил rate-limit и fail2ban на такую серию, поэтому `hostme` держит одно мультиплексирующее соединение: `ControlMaster`/`ControlPersist 60s`, сокет в `~/.cache/hostme/ssh-control/`, по нему же идёт `rsync -e`. Выбрали это, а не паузы между командами: паузы удлиняют деплой и не снимают причину.

Находка — `docs/research/2026-09-09-ssh-rate-limit.md`, код — `src/hostme/providers/ssh.py`, комментарий у `_CONTROL_DIR`.
