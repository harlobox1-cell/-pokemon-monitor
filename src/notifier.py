from __future__ import annotations
import aiohttp
import asyncio


class DiscordDeliveryError(RuntimeError):
    """Safe to log: never includes the webhook URL or response body."""
    def __init__(self, status=None):
        self.status = status
        message = f"Discord delivery failed: HTTP {status}" if status else "Discord delivery failed: connection error or timeout"
        super().__init__(message)

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
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(webhook_url, json=payload, allow_redirects=False) as resp:
                    if not 200 <= resp.status < 300:
                        raise DiscordDeliveryError(resp.status)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            raise DiscordDeliveryError() from None
