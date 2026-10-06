import asyncio
from types import SimpleNamespace
import subprocess
import sys

import aiohttp
import pytest

from src.notifier import DiscordNotifier, DiscordDeliveryError
from src.run_report import summarize_run, report_markdown
from discord_test import send_test, TITLE


class Response:
    def __init__(self, status):
        self.status = status
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass
    async def text(self):
        raise AssertionError('Response bodies must not be logged')


class Session:
    def __init__(self, response):
        self.response = response
        self.calls = []
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass
    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if isinstance(self.response, Exception):
            raise self.response
        return Response(self.response)


@pytest.mark.parametrize('status', [301, 400, 401, 404, 429, 500])
def test_discord_failures_are_safe_and_not_retried(monkeypatch, status):
    session = Session(status)
    monkeypatch.setattr(aiohttp, 'ClientSession', lambda **kwargs: session)
    with pytest.raises(DiscordDeliveryError) as error:
        asyncio.run(DiscordNotifier().send('https://discord.com/api/webhooks/id/private-token', 'Test', ['test']))
    assert str(status) in str(error.value)
    assert 'private-token' not in str(error.value)
    assert len(session.calls) == 1 and session.calls[0][1]['allow_redirects'] is False


@pytest.mark.parametrize('error', [aiohttp.ClientConnectionError('secret-url'), asyncio.TimeoutError('secret-url')])
def test_transport_errors_do_not_expose_webhook(monkeypatch, error):
    session = Session(error)
    monkeypatch.setattr(aiohttp, 'ClientSession', lambda **kwargs: session)
    with pytest.raises(DiscordDeliveryError) as caught:
        asyncio.run(DiscordNotifier().send('private-url', 'Test', []))
    assert 'secret-url' not in str(caught.value) and 'private-url' not in str(caught.value)


def test_manual_test_posts_one_labelled_message(monkeypatch):
    session = Session(204)
    monkeypatch.setattr(aiohttp, 'ClientSession', lambda **kwargs: session)
    asyncio.run(send_test('https://discord.com/api/webhooks/id/token'))
    assert len(session.calls) == 1
    assert session.calls[0][1]['json']['embeds'][0]['title'] == TITLE


def test_test_command_does_not_send_by_default():
    result = subprocess.run([sys.executable, 'discord_test.py'], capture_output=True, text=True)
    assert result.returncode == 0 and 'No message sent' in result.stdout


def test_invalid_webhook_never_posts(monkeypatch):
    def forbidden(**kwargs):
        raise AssertionError('Must not create a network session')
    monkeypatch.setattr(aiohttp, 'ClientSession', forbidden)
    with pytest.raises(ValueError):
        asyncio.run(send_test('https://example.com/api/webhooks/id/token'))


def test_run_report_separates_no_alerts_from_delivery_proof():
    monitor = SimpleNamespace(stock_alert_attempts=0, stock_alerts_sent=0, run_observations={
        'a': {'last_error': 'a private error string'},
        'b': {'in_stock': True, 'alert_eligible': True},
        'c': {'in_stock': False},
        'd': {'in_stock': None},
        'e': {'in_stock': True, 'alert_eligible': False},
    })
    report = summarize_run(monitor, [{'url': k, 'retailer': 'kmart-au'} for k in 'abcdef'])
    assert report['products'] == 6
    assert all(report[k] == 1 for k in ('not_checked', 'fetch_errors', 'qualifying_stock',
                                      'out_of_stock', 'unknown_stock', 'excluded_by_rules'))
    assert report['stock_alerts_attempted'] == 0 and report['stock_alerts_sent'] == 0
    assert 'private' not in str(report)
    assert 'does not test the webhook' in report_markdown(report)


def test_monitor_counts_deliveries_but_not_unchanged_stock(tmp_path):
    import json
    from src.monitor import PokemonMonitor
    class Config:
        def get_settings(self): return {}
        def get_webhook(self): return 'fake-test-webhook'
    async def run():
        monitor = PokemonMonitor(Config(), str(tmp_path))
        markup = '<script type="application/ld+json">' + json.dumps({
            '@type': 'Product', 'name': 'Test', 'sku': '123',
            'offers': {'price': 10, 'priceCurrency': 'AUD', 'availability': 'https://schema.org/InStock'}
        }) + '</script>'
        async def html(*args, **kwargs): return markup
        async def notify(*args): pass
        monitor.fetcher.html = html
        monitor.notifier.send = notify
        item = {'url': 'https://toymate.com.au/test/'}
        await monitor.check_item(item, {})
        assert monitor.stock_alert_attempts == monitor.stock_alerts_sent == 1
        await monitor.check_item(item, {})
        assert monitor.stock_alert_attempts == monitor.stock_alerts_sent == 1
        assert monitor.run_observations[item['url']]['alert_eligible'] is True
    asyncio.run(run())
