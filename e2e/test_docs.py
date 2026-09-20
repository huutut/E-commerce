import os

import pytest
from playwright.sync_api import sync_playwright


@pytest.mark.e2e
@pytest.mark.skipif(os.getenv("RUN_E2E") != "1", reason="set RUN_E2E=1 to run browser tests")
def test_openapi_docs_load() -> None:
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:8000")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(f"{base_url}/docs")
        page.get_by_text("Commerce Platform").wait_for()
        browser.close()
