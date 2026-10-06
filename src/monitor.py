from __future__ import annotations
import asyncio
import random
from datetime import datetime, timezone

from .fetcher import Fetcher
from .buy_rules import evaluate_purchase
from .alert_policy import refine_snapshot
import math
from .notifier import DiscordNotifier
from .retailers import discover_product_links, infer_retailer, parse_product
from .state import StateStore

class PokemonMonitor:
    def __init__(self, config_store, data_dir: str):
        self.config_store = config_store
        settings = config_store.get_settings()
        self.fetcher = Fetcher(int(settings.get("request_timeout_seconds", 20)))
        self.notifier = DiscordNotifier()
        self.state = StateStore(data_dir)
        self.runtime_watch = {}
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        self.running = False

    def stop(self):
        self._stop.set()
        self._wake.set()

    def wake(self):
        self._wake.set()

    async def close(self):
        await self.fetcher.close()

    def _eligible(self, snap, item, settings):
        if settings.get("first_party_only") and not snap.first_party:
            return False
        if item.get("currency") and snap.currency != item["currency"]:
            return False
        if snap.price is not None and (not math.isfinite(snap.price) or snap.price <= 0):
            return False
        if snap.in_stock is not True:
            return False
        max_price = item.get("max_price")
        if settings.get("require_price_for_alert") and snap.price is None:
            return False
        if max_price is not None and (snap.price is None or snap.price > float(max_price)):
            return False
        return True

    async def _notify(self, title, lines, url=None):
        webhook = self.config_store.get_webhook()
        if webhook:
            await self.notifier.send(webhook, title, lines, url)

    async def _notify_stock(self, snap, item, kind="RESTOCK"):
        price = "Unknown" if snap.price is None else f"{snap.price:.2f} {snap.currency}"
        lines = [f"Retailer: **{snap.retailer}**", f"Price: **{price}**", "Stock: **IN STOCK**"]
        if snap.sku:
            lines.append(f"SKU/PID: `{snap.sku}`")
        if item.get("max_price") is not None:
            lines.append(f"Your max: {float(item['max_price']):.2f}")
        await self._notify(f"🚨 {kind}: {snap.title}", lines, snap.url)

    async def check_item(self, item, settings):
        url = item["url"]
        key = url
        retailer = item.get("retailer") or infer_retailer(url)
        try:
            html = await self.fetcher.html(url, browser=bool(item.get("browser", False)))
            snap = parse_product(url, html, retailer)
            if settings.get("strict_product_checks"):
                snap = refine_snapshot(snap, html, item)
        except Exception as e:
            self.state.data["products"].setdefault(key, {})["last_error"] = str(e)[:500]
            self.state.save()
            return

        prev = self.state.data["products"].get(key)
        current = snap.to_dict()
        current["last_error"] = ""
        current["checked_at"] = datetime.now(timezone.utc).isoformat()
        eligible = self._eligible(snap, item, settings)
        was_eligible = bool(prev and prev.get("alert_eligible"))
        if eligible:
            if prev is None and settings.get("notify_on_first_in_stock", True):
                await self._notify_stock(snap, item, "FIRST SEEN")
            elif prev is not None and not was_eligible:
                await self._notify_stock(snap, item, "RESTOCK / PRICE QUALIFIED")
            elif prev is not None and prev.get("price") != snap.price:
                await self._notify_stock(snap, item, "PRICE CHANGE")
        try:
            purchase_snap = refine_snapshot(parse_product(url, html, retailer), html, item)
            decision = evaluate_purchase(purchase_snap, item, settings)
            current["purchase_eligible"] = decision.eligible
            current["purchase_reason"] = decision.reason
        except Exception:
            current["purchase_eligible"] = False
            current["purchase_reason"] = "Purchase evidence could not be verified"
        current["alert_eligible"] = eligible
        self.state.data["products"][key] = current
        self.state.save()

    async def discover(self, entry, settings):
        if not entry.get("enabled"):
            return
        try:
            html = await self.fetcher.html(entry["url"], browser=bool(entry.get("browser", False)))
            links = discover_product_links(entry["url"], html, entry.get("include_keywords", []), entry.get("exclude_keywords", []))
        except Exception:
            return
        discovered_state = self.state.data.setdefault("discovered", {})
        for url, label in links:
            if url in discovered_state:
                continue
            discovered_state[url] = {"label": label, "retailer": entry.get("retailer") or infer_retailer(url)}
            item = {
                "enabled": True,
                "name": label,
                "retailer": entry.get("retailer") or infer_retailer(url),
                "url": url,
                "max_price": entry.get("max_price"),
                "browser": entry.get("product_browser", entry.get("browser", False)),
                "discovered": True,
            }
            self.runtime_watch[url] = item
            if settings.get("notify_new_products", True):
                await self._notify(
                    f"🆕 NEW MATCH: {label[:180]}",
                    [f"Retailer: **{item['retailer']}**", "Matched your discovery keywords."],
                    url,
                )
        self.state.save()

    async def cycle(self):
        settings = self.config_store.get_settings()
        if not settings.get("monitor_enabled", True):
            return
        watches = [w for w in self.config_store.list_watches() if w.get("enabled")]
        discovers = [d for d in self.config_store.list_discovers() if d.get("enabled")]
        self.runtime_watch = {item["url"]: item for item in watches if item.get("url")}

        discovery_rules = {e.get("retailer"): e for e in discovers}
        for url, data in self.state.data.get("discovered", {}).items():
            retailer = data.get("retailer") or infer_retailer(url)
            rule = discovery_rules.get(retailer, {})
            self.runtime_watch.setdefault(url, {
                "enabled": True,
                "name": data.get("label", url),
                "retailer": retailer,
                "url": url,
                "max_price": rule.get("max_price"),
                "browser": rule.get("product_browser", rule.get("browser", False)),
                "discovered": True,
            })

        for entry in discovers:
            await self.discover(entry, settings)

        for item in list(self.runtime_watch.values()):
            await self.check_item(item, settings)
            await asyncio.sleep(1.0)

        self.state.data["last_cycle"] = datetime.now(timezone.utc).isoformat()
        self.state.save()

    async def run_forever(self):
        self.running = True
        if self.config_store.webhook_configured():
            try:
                await self._notify("🟢 Pokémon Monitor online", ["Cloud monitor started.", "Monitoring only; no checkout/payment actions are performed by v0.3."])
            except Exception:
                pass
        try:
            while not self._stop.is_set():
                try:
                    await self.cycle()
                    self.state.data["last_error"] = ""
                except Exception as e:
                    self.state.data["last_error"] = str(e)[:1000]
                    self.state.save()
                settings = self.config_store.get_settings()
                delay = max(30, int(settings.get("poll_seconds", 60))) + random.uniform(0, max(0, int(settings.get("jitter_seconds", 8))))
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
        finally:
            self.running = False
            await self.close()

