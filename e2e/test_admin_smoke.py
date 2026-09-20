import os

import pytest
from playwright.sync_api import sync_playwright


@pytest.mark.e2e
@pytest.mark.skipif(os.getenv("RUN_E2E") != "1", reason="set RUN_E2E=1 to run browser tests")
def test_chinese_admin_smoke() -> None:
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:8000")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(f"{base_url}/admin/login")
        page.get_by_label("邮箱").fill("admin@example.com")
        page.get_by_label("密码").fill("Admin@123456")
        page.get_by_role("button", name="登录后台").click()
        page.get_by_text("运营概览与系统状态").wait_for()
        page.get_by_role("link", name="报表中心").click()
        page.get_by_text("运营、交易、售后和接口访问汇总").wait_for()
        page.get_by_role("link", name="API Key").click()
        page.get_by_text("控制外部系统访问 /api/v1 接口").wait_for()
        page.get_by_role("link", name="账号安全").click()
        page.get_by_text("修改当前登录账号的密码").wait_for()
        page.goto(f"{base_url}/admin/products/UNKNOWN-SKU/edit")
        page.get_by_text("页面未找到").wait_for()
        page.get_by_role("link", name="返回后台首页").click()
        page.get_by_text("运营概览与系统状态").wait_for()
        browser.close()
