from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from .secure_store import SecretBox

DEFAULT_SETTINGS = {
    "monitor_enabled": True,
    "purchases_enabled": False,
    "poll_seconds": 60,
    "jitter_seconds": 8,
    "request_timeout_seconds": 20,
    "notify_on_first_in_stock": True,
    "notify_new_products": True,
    "require_price_for_alert": False,
}

class ConfigStore:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "monitor.db"
        self.secret_box = SecretBox(str(self.data_dir))
        self._init_db()

    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self.connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS watches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enabled INTEGER NOT NULL DEFAULT 1,
                name TEXT NOT NULL DEFAULT '',
                retailer TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL UNIQUE,
                max_price REAL,
                browser INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS discovers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enabled INTEGER NOT NULL DEFAULT 1,
                retailer TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL UNIQUE,
                include_keywords TEXT NOT NULL DEFAULT '[]',
                exclude_keywords TEXT NOT NULL DEFAULT '[]',
                max_price REAL,
                browser INTEGER NOT NULL DEFAULT 0,
                product_browser INTEGER NOT NULL DEFAULT 0
            );
            """)
            columns = {r["name"] for r in c.execute("PRAGMA table_info(watches)")}
            for name, definition in {
                "expected_sku": "TEXT NOT NULL DEFAULT ''",
                "currency": "TEXT NOT NULL DEFAULT 'AUD'",
                "max_quantity": "INTEGER NOT NULL DEFAULT 1",
                "quantity": "INTEGER NOT NULL DEFAULT 1",
                "auto_buy": "INTEGER NOT NULL DEFAULT 0",
            }.items():
                if name not in columns:
                    c.execute(f"ALTER TABLE watches ADD COLUMN {name} {definition}")
            for k, v in DEFAULT_SETTINGS.items():
                c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, json.dumps(v)))

    def get_settings(self):
        out = DEFAULT_SETTINGS.copy()
        with self.connect() as c:
            for row in c.execute("SELECT key,value FROM settings"):
                try:
                    out[row["key"]] = json.loads(row["value"])
                except Exception:
                    out[row["key"]] = row["value"]
        return out

    def set_setting(self, key: str, value):
        with self.connect() as c:
            c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))

    def set_webhook(self, url: str):
        encrypted = self.secret_box.encrypt(url.strip())
        self.set_setting("discord_webhook_encrypted", encrypted)

    def get_webhook(self) -> str:
        settings = self.get_settings()
        return self.secret_box.decrypt(settings.get("discord_webhook_encrypted", ""))

    def webhook_configured(self) -> bool:
        return bool(self.get_webhook())

    def list_watches(self):
        with self.connect() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM watches ORDER BY id DESC")]
            for row in rows:
                row["auto_buy"] = row["auto_buy"] == 1
            return rows

    def add_watch(self, name, retailer, url, max_price, browser=False):
        with self.connect() as c:
            c.execute("""INSERT INTO watches(enabled,name,retailer,url,max_price,browser)
                         VALUES(1,?,?,?,?,?)
                         ON CONFLICT(url) DO UPDATE SET name=excluded.name, retailer=excluded.retailer,
                         max_price=excluded.max_price, browser=excluded.browser""",
                      (name or "", retailer or "", url.strip(), max_price, int(bool(browser))))

    def set_purchase_rule(self, watch_id, *, expected_sku, max_price,
                          max_quantity=1, quantity=1, currency="AUD", auto_buy=False):
        from .buy_rules import positive_money, positive_quantity
        if (not isinstance(expected_sku, str) or not expected_sku.strip()
                or expected_sku != expected_sku.strip() or currency != "AUD"
                or positive_money(max_price) is None
                or positive_quantity(max_quantity) is None
                or positive_quantity(quantity) is None or quantity > max_quantity
                or type(auto_buy) is not bool):
            raise ValueError("Exact SKU, positive price, integer quantities and AUD required")
        with self.connect() as c:
            c.execute("""UPDATE watches SET expected_sku=?, max_price=?, max_quantity=?,
                         quantity=?, currency=?, auto_buy=? WHERE id=?""",
                      (expected_sku, float(max_price), max_quantity, quantity, currency,
                       int(auto_buy), watch_id))

    def delete_watch(self, watch_id: int):
        with self.connect() as c:
            c.execute("DELETE FROM watches WHERE id=?", (watch_id,))

    def toggle_watch(self, watch_id: int):
        with self.connect() as c:
            c.execute("UPDATE watches SET enabled=CASE enabled WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (watch_id,))

    def list_discovers(self):
        rows = []
        with self.connect() as c:
            for r in c.execute("SELECT * FROM discovers ORDER BY id DESC"):
                d = dict(r)
                d["include_keywords"] = json.loads(d["include_keywords"] or "[]")
                d["exclude_keywords"] = json.loads(d["exclude_keywords"] or "[]")
                rows.append(d)
        return rows

    def add_discover(self, retailer, url, includes, excludes, max_price, browser=False, product_browser=False):
        with self.connect() as c:
            c.execute("""INSERT INTO discovers(enabled,retailer,url,include_keywords,exclude_keywords,max_price,browser,product_browser)
                         VALUES(1,?,?,?,?,?,?,?)
                         ON CONFLICT(url) DO UPDATE SET retailer=excluded.retailer,
                         include_keywords=excluded.include_keywords,exclude_keywords=excluded.exclude_keywords,
                         max_price=excluded.max_price,browser=excluded.browser,product_browser=excluded.product_browser""",
                      (retailer or "", url.strip(), json.dumps(includes), json.dumps(excludes), max_price, int(bool(browser)), int(bool(product_browser))))

    def delete_discover(self, discover_id: int):
        with self.connect() as c:
            c.execute("DELETE FROM discovers WHERE id=?", (discover_id,))

    def toggle_discover(self, discover_id: int):
        with self.connect() as c:
            c.execute("UPDATE discovers SET enabled=CASE enabled WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (discover_id,))

