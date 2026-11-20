"""Внешние интеграции hostme — всё, что говорит с чем-то за пределами процесса.

Не HTTP-API, а локальные бинари (`ssh`/`rsync`/`lftp`) и Webinoly поверх SSH
(architecture.md §2, «Non-HTTP integrations»). Контракт тот же, что у
HttpProvider из шаблона: любая ошибка вендора наружу выходит как
`ProviderError` (exit 5) с понятным `action`, никогда как голый трейсбек
или CalledProcessError. Выше этого слоя (core/, commands/) никто не видит
subprocess.
"""
