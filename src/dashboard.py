from __future__ import annotations
import hashlib
import hmac
import html
import os
from urllib.parse import quote
from aiohttp import web
from .retailers import infer_retailer

CSS = """
:root{color-scheme:dark;--bg:#0d0f12;--card:#181b20;--line:#2a2f38;--text:#f4f5f7;--muted:#aeb5c0;--accent:#6fa8ff;--good:#51d16a;--warn:#ffca57;--bad:#ff6b6b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}main{max-width:900px;margin:auto;padding:18px 14px 60px}h1{font-size:28px;margin:8px 0 4px}h2{font-size:20px;margin:24px 0 10px}.muted{color:var(--muted)}.grid{display:grid;gap:12px}.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px}.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.spread{display:flex;justify-content:space-between;gap:10px;align-items:center}.pill{background:#242933;border-radius:999px;padding:4px 9px;font-size:12px}.good{color:var(--good)}.warn{color:var(--warn)}.bad{color:var(--bad)}a{color:var(--accent)}input,select{width:100%;padding:12px;border:1px solid #343a45;border-radius:10px;background:#0f1217;color:white;font-size:16px}label{display:block;margin:9px 0 5px;color:var(--muted);font-size:14px}button,.btn{display:inline-block;border:0;border-radius:10px;padding:10px 13px;background:#2f6fed;color:white;font-weight:700;text-decoration:none;font-size:14px}.btn.secondary,button.secondary{background:#2a2f38}.btn.danger,button.danger{background:#7e2d34}.topnav{display:flex;gap:8px;overflow:auto;padding:8px 0 4px}.topnav a{white-space:nowrap;background:#171a1f;border:1px solid var(--line);border-radius:999px;padding:8px 11px;text-decoration:none;color:white}.statusdot{width:10px;height:10px;border-radius:50%;display:inline-block;background:var(--good)}.statusdot.off{background:var(--bad)}form.inline{display:inline}.flash{border:1px solid #39547c;background:#162135;padding:10px;border-radius:10px;margin:10px 0}.small{font-size:13px}.product-title{font-weight:700;line-height:1.3}code{word-break:break-all}.switchline{display:flex;align-items:center;gap:8px}.switchline input{width:auto}.login{max-width:420px;margin:12vh auto;padding:20px}.warning{border-color:#6b5429;background:#241e13}.footer{margin-top:28px;color:var(--muted);font-size:12px}@media(min-width:700px){.two{grid-template-columns:1fr 1fr}}
"""

def page(title, body, logged_in=True, flash=""):
    nav = "" if not logged_in else """<div class='topnav'><a href='/'>Dashboard</a><a href='/watches'>Products</a><a href='/discover'>Discovery</a><a href='/settings'>Settings</a><a href='/logout'>Log out</a></div>"""
    flash_html = f"<div class='flash'>{html.escape(flash)}</div>" if flash else ""
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'><title>{html.escape(title)}</title><style>{CSS}</style></head><body><main>{nav}{flash_html}{body}<div class='footer'>Pokémon Monitor v0.3 · monitor/alerts only · no payment details stored</div></main></body></html>"""


def build_app(store, monitor, admin_password: str):
    secret = store.secret_box.encrypt("session-signing-key")
    cookie_value = hmac.new(secret.encode(), admin_password.encode(), hashlib.sha256).hexdigest()

    def authed(request):
        return hmac.compare_digest(request.cookies.get("pm_session", ""), cookie_value)

    @web.middleware
    async def auth_middleware(request, handler):
        if request.path in ("/login", "/health") or request.path.startswith("/static/"):
            return await handler(request)
        if not authed(request):
            raise web.HTTPFound("/login")
        return await handler(request)

    app = web.Application(middlewares=[auth_middleware], client_max_size=1024 * 1024)

    async def health(request):
        return web.json_response({"ok": True, "running": monitor.running})

    async def login_get(request):
        body = """<div class='login card'><h1>Pokémon Monitor</h1><p class='muted'>Sign in to your private monitor dashboard.</p><form method='post'><label>Password</label><input type='password' name='password' autocomplete='current-password' required><p><button type='submit'>Sign in</button></p></form></div>"""
        return web.Response(text=page("Login", body, False), content_type="text/html")

    async def login_post(request):
        form = await request.post()
        if not hmac.compare_digest(str(form.get("password", "")), admin_password):
            body = """<div class='login card'><h1>Pokémon Monitor</h1><div class='flash'>Incorrect password.</div><form method='post'><label>Password</label><input type='password' name='password' required><p><button type='submit'>Sign in</button></p></form></div>"""
            return web.Response(text=page("Login", body, False), status=401, content_type="text/html")
        resp = web.HTTPFound("/")
        secure = request.headers.get("X-Forwarded-Proto", request.scheme) == "https"
        resp.set_cookie("pm_session", cookie_value, httponly=True, secure=secure, samesite="Strict", max_age=60*60*24*30)
        return resp

    async def logout(request):
        resp = web.HTTPFound("/login")
        resp.del_cookie("pm_session")
        return resp

    async def home(request):
        settings = store.get_settings()
        products = monitor.state.data.get("products", {})
        good = sum(1 for p in products.values() if p.get("in_stock") is True)
        webhook = store.webhook_configured()
        body = f"""
        <h1>Pokémon Monitor</h1><p class='muted'>Cloud dashboard — manage it from Safari on your phone.</p>
        <div class='grid two'>
          <div class='card'><div class='spread'><strong>Monitor</strong><span class='{'good' if settings.get('monitor_enabled') else 'bad'}'>{'ON' if settings.get('monitor_enabled') else 'OFF'}</span></div><p class='muted small'>Polling about every {int(settings.get('poll_seconds',60))} seconds.</p></div>
          <div class='card'><div class='spread'><strong>Discord</strong><span class='{'good' if webhook else 'warn'}'>{'CONNECTED' if webhook else 'NOT SET'}</span></div><p class='muted small'>{good} currently in-stock result(s).</p></div>
        </div>
        <h2>Latest product checks</h2>
        """
        if not products:
            body += "<div class='card'><p>No product checks yet. Add a product or discovery rule first.</p></div>"
        else:
            for url, data in list(products.items())[-30:][::-1]:
                val = data.get("in_stock")
                cls = "good" if val is True else "bad" if val is False else "warn"
                stock = "IN STOCK" if val is True else "OUT" if val is False else "UNKNOWN"
                price = "Unknown" if data.get("price") is None else f"{data.get('price')} {html.escape(str(data.get('currency','AUD')))}"
                body += f"<div class='card'><div class='product-title'>{html.escape(data.get('title') or url)}</div><p><span class='{cls}'>{stock}</span> · {html.escape(price)}</p><div class='row'><span class='pill'>{html.escape(data.get('retailer','unknown'))}</span><a class='btn secondary' href='{html.escape(url)}' target='_blank' rel='noopener'>Open</a></div></div>"
        return web.Response(text=page("Dashboard", body, True, request.query.get("msg", "")), content_type="text/html")

    async def settings_get(request):
        s = store.get_settings()
        webhook_label = "Configured ✅" if store.webhook_configured() else "Not configured"
        body = f"""
        <h1>Settings</h1>
        <div class='card'><form method='post'>
        <div class='switchline'><input type='checkbox' name='monitor_enabled' {'checked' if s.get('monitor_enabled') else ''}><label style='margin:0'>Monitor enabled</label></div>
        <label>Poll interval (seconds, minimum 30)</label><input type='number' min='30' max='3600' name='poll_seconds' value='{int(s.get('poll_seconds',60))}'>
        <label>Discord webhook</label><input type='password' name='webhook' placeholder='{webhook_label}' autocomplete='off'>
        <p class='muted small'>Webhook is encrypted before it is stored. Leaving this blank keeps the current webhook.</p>
        <div class='switchline'><input type='checkbox' name='notify_first' {'checked' if s.get('notify_on_first_in_stock') else ''}><label style='margin:0'>Notify when first seen in stock</label></div>
        <div class='switchline'><input type='checkbox' name='notify_new' {'checked' if s.get('notify_new_products') else ''}><label style='margin:0'>Notify on newly discovered matching products</label></div>
        <div class='switchline'><input type='checkbox' name='require_price' {'checked' if s.get('require_price_for_alert') else ''}><label style='margin:0'>Require a readable price before alerting</label></div>
        <p><button type='submit'>Save settings</button></p></form>
        <form method='post' action='/test-discord'><button class='secondary' type='submit'>Send test Discord alert</button></form></div>
        <div class='card warning'><strong>Security</strong><p class='small'>Do not paste card numbers, CVVs, bank passwords or your personal Discord token here. This version only monitors stock and sends alerts.</p></div>
        """
        return web.Response(text=page("Settings", body), content_type="text/html")

    async def settings_post(request):
        f = await request.post()
        store.set_setting("monitor_enabled", f.get("monitor_enabled") == "on")
        try:
            poll = max(30, min(3600, int(f.get("poll_seconds", 60))))
        except ValueError:
            poll = 60
        store.set_setting("poll_seconds", poll)
        store.set_setting("notify_on_first_in_stock", f.get("notify_first") == "on")
        store.set_setting("notify_new_products", f.get("notify_new") == "on")
        store.set_setting("require_price_for_alert", f.get("require_price") == "on")
        webhook = str(f.get("webhook", "")).strip()
        if webhook:
            if not webhook.startswith("https://discord.com/api/webhooks/") and not webhook.startswith("https://discordapp.com/api/webhooks/"):
                raise web.HTTPBadRequest(text="That does not look like a Discord webhook URL.")
            store.set_webhook(webhook)
        monitor.wake()
        raise web.HTTPFound("/settings?msg=" + quote("Settings saved"))

    async def test_discord(request):
        webhook = store.get_webhook()
        if not webhook:
            raise web.HTTPFound("/settings?msg=" + quote("Add your Discord webhook first"))
        try:
            await monitor.notifier.send(webhook, "✅ Pokémon Monitor connected", ["Your phone alerts are working.", "Cloud monitor v0.3 is ready."], None)
        except Exception as e:
            raise web.HTTPFound("/settings?msg=" + quote(f"Discord test failed: {str(e)[:120]}"))

        raise web.HTTPFound("/settings?msg=" + quote("Test alert sent"))

    async def watches_get(request):
        rows = store.list_watches()
        body = """<h1>Products</h1><div class='card'><form method='post'><label>Product URL</label><input type='url' name='url' placeholder='https://…' required><label>Name (optional)</label><input name='name' placeholder='30th Anniversary ETB'><label>Maximum price (optional)</label><input type='number' step='0.01' min='0' name='max_price' placeholder='110'><div class='switchline'><input type='checkbox' name='browser'><label style='margin:0'>Use browser rendering for this page</label></div><p><button type='submit'>Add product</button></p></form></div><h2>Watchlist</h2>"""
        if not rows:
            body += "<div class='card'>No products added yet.</div>"
        for r in rows:
            body += f"""<div class='card'><div class='spread'><div><strong>{html.escape(r.get('name') or r['url'])}</strong><div class='muted small'>{html.escape(r.get('retailer') or 'unknown')}</div></div><span class='{'good' if r['enabled'] else 'bad'}'>{'ON' if r['enabled'] else 'OFF'}</span></div><p class='small'><code>{html.escape(r['url'])}</code></p><div class='row'><form class='inline' method='post' action='/watches/{r['id']}/toggle'><button class='secondary'>Toggle</button></form><form class='inline' method='post' action='/watches/{r['id']}/delete'><button class='danger'>Delete</button></form></div></div>"""
        return web.Response(text=page("Products", body, True, request.query.get("msg", "")), content_type="text/html")

    async def watches_post(request):
        f = await request.post()
        url = str(f.get("url", "")).strip()
        retailer = infer_retailer(url)
        try:
            max_price = float(f.get("max_price")) if str(f.get("max_price", "")).strip() else None
        except ValueError:
            max_price = None
        store.add_watch(str(f.get("name", "")).strip(), retailer, url, max_price, f.get("browser") == "on")
        monitor.wake()
        raise web.HTTPFound("/watches?msg=" + quote("Product added"))

    async def watches_toggle(request):
        store.toggle_watch(int(request.match_info["id"]))
        monitor.wake()
        raise web.HTTPFound("/watches")

    async def watches_delete(request):
        store.delete_watch(int(request.match_info["id"]))
        monitor.wake()
        raise web.HTTPFound("/watches")

    async def discover_get(request):
        rows = store.list_discovers()
        retailer_options = ["target-au","big-w-au","kmart-au","eb-games-au","jb-hifi-au","toymate-au","pokemon-centre-au","pokemon-center-us","costco-au"]
        options = "".join(f"<option value='{x}'>{x}</option>" for x in retailer_options)
        body = f"""<h1>Discovery</h1><p class='muted'>Watch a Pokémon category/search page and alert when a new matching product appears.</p><div class='card'><form method='post'><label>Retailer</label><select name='retailer'>{options}</select><label>Category/search URL</label><input type='url' name='url' required placeholder='https://…'><label>Must contain keywords</label><input name='include_keywords' value='pokemon, tcg'><label>Exclude keywords</label><input name='exclude_keywords' value='plush, clothing'><label>Maximum price (optional)</label><input type='number' step='0.01' min='0' name='max_price'><div class='switchline'><input type='checkbox' name='browser'><label style='margin:0'>Use browser rendering for discovery page</label></div><div class='switchline'><input type='checkbox' name='product_browser'><label style='margin:0'>Use browser rendering for discovered product pages</label></div><p><button type='submit'>Add discovery rule</button></p></form></div><h2>Rules</h2>"""
        if not rows:
            body += "<div class='card'>No discovery rules yet.</div>"
        for r in rows:
            inc = ", ".join(r.get("include_keywords", []))
            body += f"""<div class='card'><div class='spread'><strong>{html.escape(r['retailer'])}</strong><span class='{'good' if r['enabled'] else 'bad'}'>{'ON' if r['enabled'] else 'OFF'}</span></div><p class='small'>{html.escape(r['url'])}</p><p class='muted small'>Keywords: {html.escape(inc)}</p><div class='row'><form class='inline' method='post' action='/discover/{r['id']}/toggle'><button class='secondary'>Toggle</button></form><form class='inline' method='post' action='/discover/{r['id']}/delete'><button class='danger'>Delete</button></form></div></div>"""
        return web.Response(text=page("Discovery", body, True, request.query.get("msg", "")), content_type="text/html")

    async def discover_post(request):
        f = await request.post()
        includes = [x.strip() for x in str(f.get("include_keywords", "")).split(",") if x.strip()]
        excludes = [x.strip() for x in str(f.get("exclude_keywords", "")).split(",") if x.strip()]
        try:
            max_price = float(f.get("max_price")) if str(f.get("max_price", "")).strip() else None
        except ValueError:
            max_price = None
        store.add_discover(str(f.get("retailer", "")), str(f.get("url", "")), includes, excludes, max_price, f.get("browser") == "on", f.get("product_browser") == "on")
        monitor.wake()
        raise web.HTTPFound("/discover?msg=" + quote("Discovery rule added"))

    async def discover_toggle(request):
        store.toggle_discover(int(request.match_info["id"]))
        monitor.wake()
        raise web.HTTPFound("/discover")

    async def discover_delete(request):
        store.delete_discover(int(request.match_info["id"]))
        monitor.wake()
        raise web.HTTPFound("/discover")

    app.router.add_get("/health", health)
    app.router.add_get("/login", login_get)
    app.router.add_post("/login", login_post)
    app.router.add_get("/logout", logout)
    app.router.add_get("/", home)
    app.router.add_get("/settings", settings_get)
    app.router.add_post("/settings", settings_post)
    app.router.add_post("/test-discord", test_discord)
    app.router.add_get("/watches", watches_get)
    app.router.add_post("/watches", watches_post)
    app.router.add_post("/watches/{id}/toggle", watches_toggle)
    app.router.add_post("/watches/{id}/delete", watches_delete)
    app.router.add_get("/discover", discover_get)
    app.router.add_post("/discover", discover_post)
    app.router.add_post("/discover/{id}/toggle", discover_toggle)
    app.router.add_post("/discover/{id}/delete", discover_delete)
    return app
