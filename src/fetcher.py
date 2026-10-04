from __future__ import annotations
import os
import aiohttp

class Fetcher:
    def __init__(self, timeout_seconds: int = 20, user_agent: str = "PokemonStockMonitor/0.3 (+personal-use)"):
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self._browser = None
        self._playwright = None

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _browser_html(self, url: str) -> str:
        if os.getenv("PLAYWRIGHT_ENABLED", "true").lower() not in ("1", "true", "yes", "on"):
            raise RuntimeError("Playwright disabled")
        if not self._browser:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
        page = await self._browser.new_page(user_agent=self.user_agent)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_seconds * 1000)
            await page.wait_for_timeout(1200)
            return await page.content()
        finally:
            await page.close()

    async def html(self, url: str, browser: bool = False) -> str:
        if browser:
            return await self._browser_html(url)
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-AU,en;q=0.9",
        }
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url, allow_redirects=True) as resp:
                resp.raise_for_status()
                return await resp.text()
