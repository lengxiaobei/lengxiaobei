"""Browser automation boundary.

参考来源：OpenClaw browser toolkit。这里提供 Playwright 可选实现；未安装浏览器依赖时，
返回明确错误而不是静默占位。
"""

from __future__ import annotations

from typing import Any


def fetch_text(url: str, selector: str | None = None, timeout_ms: int = 15000) -> dict[str, Any]:
    """用 Playwright 打开页面并提取文本，局部参考 OpenClaw browser tool。"""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return {"ok": False, "error": f"playwright is not installed: {exc}"}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            text = page.locator(selector).inner_text(timeout=timeout_ms) if selector else page.locator("body").inner_text(timeout=timeout_ms)
            title = page.title()
            browser.close()
            return {"ok": True, "url": url, "title": title, "text": text[:20000]}
    except Exception as exc:
        return {"ok": False, "url": url, "error": str(exc)}


def screenshot(url: str, path: str, timeout_ms: int = 15000) -> dict[str, Any]:
    """用 Playwright 截图。"""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return {"ok": False, "error": f"playwright is not installed: {exc}"}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.screenshot(path=path, full_page=True)
            browser.close()
            return {"ok": True, "url": url, "path": path}
    except Exception as exc:
        return {"ok": False, "url": url, "error": str(exc)}


def unavailable() -> str:
    return "browser tool is available via browser_fetch_text/browser_screenshot when playwright is installed"
