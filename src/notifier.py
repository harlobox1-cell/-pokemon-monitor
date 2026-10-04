from __future__ import annotations
import aiohttp

class DiscordNotifier:
    async def send(self, webhook_url: str, title: str, lines: list[str], url: str | None = None):
        webhook_url = (webhook_url or "").strip()
        if not webhook_url:
            return
        description = "\n".join(lines)
        embed = {"title": title[:256], "description": description[:4096]}
        if url:
            embed["url"] = url
        payload = {"username": "Pokemon Monitor", "embeds": [embed]}
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(webhook_url, json=payload) as resp:
                if resp.status >= 300:
                    body = await resp.text()
                    raise RuntimeError(f"Discord webhook failed: HTTP {resp.status}: {body[:200]}")
