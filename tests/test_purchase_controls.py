import sqlite3
import pytest
from src.buy_rules import evaluate_buy_rule, evaluate_purchase
from src.config_store import ConfigStore
from src.models import ProductSnapshot
from src.alert_policy import refine_snapshot
from src.retailers import parse_product

URL = 'https://toymate.com.au/test/'

def snap(**changes):
    fields = dict(retailer='toymate-au', url=URL, title='Test', price=10,
                  currency='AUD', in_stock=True, sku='ABC-123', source='test',
                  first_party=True, stock_verified=True)
    fields.update(changes)
    return ProductSnapshot(**fields)

def rule(**changes):
    fields = dict(url=URL, enabled=True, auto_buy=True, expected_sku='ABC-123',
                  currency='AUD', max_price=10, quantity=1, max_quantity=1)
    fields.update(changes)
    return fields

@pytest.mark.parametrize('settings', [None, {}, {'purchases_enabled': False},
                                      {'purchases_enabled': 'true'}, {'purchases_enabled': 1}])
def test_master_requires_literal_true(settings):
    assert not evaluate_purchase(snap(), rule(), settings).eligible

@pytest.mark.parametrize('changes', [dict(auto_buy=False), dict(auto_buy=1),
    dict(auto_buy='on'), dict(expected_sku=''), dict(expected_sku='ABC123'),
    dict(max_price='NaN'), dict(max_price='Infinity'), dict(max_price='bad'),
    dict(max_price=0), dict(max_price=True), dict(quantity=2), dict(quantity=1.5),
    dict(quantity=True), dict(max_quantity=0), dict(currency='USD'),
    dict(enabled=False), dict(discovered=True)])
def test_invalid_rules_block(changes):
    assert not evaluate_purchase(snap(), rule(**changes), {'purchases_enabled': True}).eligible

@pytest.mark.parametrize('changes', [dict(price=float('nan')), dict(price=float('inf')),
    dict(price=None), dict(price=10.01), dict(sku=None), dict(sku='ABC123'),
    dict(first_party=1), dict(first_party=False), dict(in_stock=None),
    dict(in_stock=1), dict(stock_verified=False), dict(currency='USD'),
    dict(url='https://evil.example/test/'), dict(url='http://toymate.com.au/test/')])
def test_invalid_evidence_blocks(changes):
    assert not evaluate_purchase(snap(**changes), rule(), {'purchases_enabled': True}).eligible

def test_explicit_eligible_boundary_and_switch_revocation():
    settings = {'purchases_enabled': True}
    assert evaluate_purchase(snap(), rule(), settings).eligible
    settings['purchases_enabled'] = False
    assert not evaluate_purchase(snap(), rule(), settings).eligible

@pytest.mark.parametrize('field', ['expected_sku', 'max_price', 'quantity', 'max_quantity', 'currency', 'url'])
def test_missing_purchase_fields_block(field):
    item = rule(); del item[field]
    assert not evaluate_purchase(snap(), item, {'purchases_enabled': True}).eligible

def test_cart_validator_requires_exact_sku():
    assert not evaluate_buy_rule(snap(), {'max_price': 10}).eligible

def test_existing_database_migration_and_persistence(tmp_path):
    with sqlite3.connect(tmp_path / 'monitor.db') as c:
        c.execute('CREATE TABLE watches (id INTEGER PRIMARY KEY, enabled INTEGER DEFAULT 1, name TEXT, retailer TEXT, url TEXT UNIQUE, max_price REAL, browser INTEGER DEFAULT 0)')
        c.execute("INSERT INTO watches VALUES(1,1,'Original','toymate-au',?,10,0)", (URL,))
    store = ConfigStore(str(tmp_path))
    assert store.get_settings()['purchases_enabled'] is False
    row = store.list_watches()[0]
    assert row['name'] == 'Original' and row['auto_buy'] is False and row['max_quantity'] == 1
    store.set_purchase_rule(1, expected_sku='ABC-123', max_price=10, auto_buy=True)
    store = ConfigStore(str(tmp_path))
    assert store.list_watches()[0]['auto_buy'] is True
    assert store.get_settings()['purchases_enabled'] is False
    store.add_watch('Renamed', 'toymate-au', URL, 10)
    assert store.list_watches()[0]['expected_sku'] == 'ABC-123'
    with pytest.raises(ValueError):
        store.set_purchase_rule(1, expected_sku='ABC-123', max_price='NaN', auto_buy=True)
    assert store.list_watches()[0]['max_price'] == 10

def test_unverified_page_wording_never_authorizes_purchase():
    markup = '<p>SKU: ABC-123 Add to cart</p>'
    result = refine_snapshot(parse_product(URL, markup), markup, rule())
    assert not result.stock_verified

def test_purchase_quantity_cap_is_distinct_from_cart_adapter():
    item = rule(quantity=2, max_quantity=2)
    assert evaluate_purchase(snap(), item, {'purchases_enabled': True}).eligible
    assert not evaluate_buy_rule(snap(), item).eligible

@pytest.mark.parametrize('extra,verified', [('', True), (' CAPTCHA verify you are human', False)])
def test_verified_evidence_and_security_stop(extra, verified):
    import json
    markup = '<script type="application/ld+json">' + json.dumps({
        '@type': 'Product', 'sku': 'ABC-123', 'url': URL,
        'offers': {'price': 10, 'priceCurrency': 'AUD', 'availability': 'https://schema.org/InStock'}
    }) + '</script><p>SKU: ABC-123 Online: Available</p>' + extra
    result = refine_snapshot(parse_product(URL, markup), markup, rule())
    assert result.stock_verified is verified
    assert evaluate_purchase(result, rule(), {'purchases_enabled': True}).eligible is verified


def test_dashboard_controls_and_authentication(tmp_path):
    import asyncio
    from types import SimpleNamespace
    from aiohttp.test_utils import TestClient, TestServer
    from src.dashboard import build_app
    store = ConfigStore(str(tmp_path))
    store.add_watch('Test', 'toymate-au', URL, 10)
    watch_id = store.list_watches()[0]['id']
    monitor = SimpleNamespace(running=False, wake=lambda: None)
    async def run():
        async with TestClient(TestServer(build_app(store, monitor, 'secret'))) as client:
            response = await client.post(f'/watches/{watch_id}/purchase-rule', data={}, allow_redirects=False)
            assert response.status == 302 and response.headers['Location'] == '/login'
            await client.post('/login', data={'password': 'secret'}, allow_redirects=False)
            response = await client.get('/watches')
            assert response.status == 200 and 'Auto-buy: OFF' in await response.text()
            response = await client.post(f'/watches/{watch_id}/purchase-rule', data={
                'expected_sku': 'ABC-123', 'max_price': '10', 'quantity': '1',
                'max_quantity': '2', 'auto_buy': 'on'}, allow_redirects=False)
            assert response.status == 302
            assert store.list_watches()[0]['auto_buy'] is True
            assert store.get_settings()['purchases_enabled'] is False
            response = await client.post(f'/watches/{watch_id}/purchase-rule', data={
                'expected_sku': 'ABC-123', 'max_price': 'NaN', 'quantity': '1',
                'max_quantity': '2'}, allow_redirects=False)
            assert response.status == 400
            await client.post('/settings', data={'purchases_enabled': 'on'}, allow_redirects=False)
            assert store.get_settings()['purchases_enabled'] is True
            await client.post('/settings', data={}, allow_redirects=False)
            assert store.get_settings()['purchases_enabled'] is False
    asyncio.run(run())
