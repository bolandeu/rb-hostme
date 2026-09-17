from __future__ import annotations

import urllib.error
import urllib.request


def head_status(domain: str, timeout: float = 8.0) -> str:
    """HTTP-статус `https://<domain>` одним HEAD-запросом — для `hostme <domain> debug`.

    Единственный HTTP-вызов в hostme; полноценный HttpProvider из шаблона тут
    не нужен: нет авторизации, а 4xx/5xx — не ошибка провайдера, а сам ответ,
    который и хотел увидеть пользователь. Сетевую недоступность тоже отдаём
    строкой, а не исключением — `debug` должен дойти до хвоста лога на
    сервере даже когда сайт не отвечает (там как раз и будет причина).
    """
    req = urllib.request.Request(f"https://{domain}", method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return str(resp.status)
    except urllib.error.HTTPError as exc:
        return str(exc.code)
    except Exception as exc:  # noqa: BLE001
        return f"ошибка: {exc}"
