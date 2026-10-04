"""One stock-check cycle for GitHub Actions. Secrets stay in environment variables."""
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from src.config_store import DEFAULT_SETTINGS
from src.monitor import PokemonMonitor
from src.retailers import infer_retailer


class ActionsConfig:
    def __init__(self, config, webhook):
        self.webhook = webhook
        self.settings = {**DEFAULT_SETTINGS, **config.get('settings', {})}
        self.watches = []
        for item in config.get('products', []):
            if not item.get('enabled', True):
                continue
            url = item.get('url', '')
            if urlsplit(url).scheme != 'https' or infer_retailer(url) == 'unknown':
                raise ValueError('Each enabled product needs an HTTPS URL from a supported retailer.')
            self.watches.append({**item, 'enabled': True})

    def get_settings(self):
        return self.settings

    def get_webhook(self):
        return self.webhook

    def list_watches(self):
        return self.watches

    def list_discovers(self):
        return []


async def main():
    config = ActionsConfig(json.loads(Path('watchlist.json').read_text()), os.getenv('DISCORD_WEBHOOK_URL', '').strip())
    if not config.watches:
        raise SystemExit('Add product URLs to watchlist.json before enabling monitoring.')
    parts = urlsplit(config.webhook)
    if parts.scheme != 'https' or parts.hostname not in ('discord.com', 'discordapp.com') or not parts.path.startswith('/api/webhooks/'):
        raise SystemExit('Set the DISCORD_WEBHOOK_URL repository Actions secret before enabling monitoring.')
    monitor = PokemonMonitor(config, os.getenv('DATA_DIR', 'data'))
    # This mode only checks the explicitly configured products.
    monitor.state.data['discovered'] = {}
    try:
        if not monitor.state.data.get('connection_test_sent'):
            await monitor.notifier.send(config.webhook, '✅ Pokémon monitor connection test', [
                'Discord delivery is working. This is a setup test, not a stock alert.',
                f'{len(config.watches)} product URLs configured. First-party sellers only.',
                'Scheduled every 15 minutes; GitHub may delay runs. Only verified stock within fixed price caps will alert.',
                'Coverage gaps are recorded in watchlist.json; no auto-purchases.'
            ])
            monitor.state.data['connection_test_sent'] = True
            monitor.state.save()
        await monitor.cycle()
        failed = sum(bool(monitor.state.data['products'].get(p['url'], {}).get('last_error')) for p in config.watches)
        print(f'Checked {len(config.watches)} product(s); {failed} fetch error(s).')
        unknown = sum(monitor.state.data['products'].get(p['url'], {}).get('in_stock') is None for p in config.watches)
        if not monitor.state.data.get('first_cycle_report_sent'):
            await monitor.notifier.send(config.webhook, 'Pokémon monitor first check complete', [
                f'{len(config.watches)} configured; {failed} fetch errors; {unknown} unknown or excluded results.',
                'Unknown sellers, marketplace offers and unverified availability are suppressed.',
                'Stock alerts are separate. No qualifying stock does not mean the monitor is off.'
            ])
            monitor.state.data['first_cycle_report_sent'] = True
            monitor.state.save()
        if failed == len(config.watches):
            raise SystemExit('All product checks failed; monitoring cannot confirm stock.')
    finally:
        await monitor.close()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as exc:
        # Never put webhook URLs or response bodies in public Actions logs.
        print(f'Monitor failed ({type(exc).__name__}); inspect configuration and connectivity.')
        raise SystemExit(1) from None
