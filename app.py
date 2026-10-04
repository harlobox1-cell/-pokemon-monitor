from __future__ import annotations
import asyncio
import os
import signal
from aiohttp import web
from src.config_store import ConfigStore
from src.monitor import PokemonMonitor
from src.dashboard import build_app

async def main():
    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
    if not admin_password:
        raise RuntimeError("ADMIN_PASSWORD environment variable is required. Set a strong private password in your cloud host settings.")

    data_dir = os.getenv("DATA_DIR", "data")
    port = int(os.getenv("PORT", "8080"))
    store = ConfigStore(data_dir)
    monitor = PokemonMonitor(store, data_dir)
    app = build_app(store, monitor, admin_password)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, monitor.stop)
        except NotImplementedError:
            pass

    try:
        await monitor.run_forever()
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
