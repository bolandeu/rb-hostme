---
id: HOSTME-IDEA-015
title: 'Ручной прогон критерия 3 (путь с нуля) отложен: тестовый файл tests/e2e/test_fro'
created: '2026-11-12T08:22:02+00:00'
source_project: hostme
source_path: /Users/bolandau/Work/tools/hostme
status: new
found_in_epic: E-003
---

Ручной прогон критерия 3 (путь с нуля) отложен: тестовый файл tests/e2e/test_from_zero.py написан, но ни разу не запускался. Условия для прогона: переустановленная чистая машина (p2g-1, 177.3.221.61) и wildcard-запись *.p2g-1.bolandau.ru на её IP — без неё сгенерированные домены уходят на net-angel-vps. Прогон: HOSTME_E2E_HOST=177.3.221.61 HOSTME_E2E_USER=root HOSTME_E2E_BASE_DOMAIN=p2g-1.bolandau.ru HOSTME_E2E_SSH_KEY=~/.ssh/id_play2go uv run pytest -m e2e tests/e2e/test_from_zero.py
