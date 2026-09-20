# Playwright

Browser tests cover the Chinese admin UI and API docs.

Recommended flow:

```powershell
$env:RUN_E2E="1"
$env:BASE_URL="http://127.0.0.1:8000"
pytest e2e
```
