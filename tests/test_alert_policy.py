import asyncio
import json
from types import SimpleNamespace

import pytest
from src.alert_policy import refine_snapshot
from src.models import ProductSnapshot
from src.monitor import PokemonMonitor
from src.retailers import parse_product


def page(seller=None, price=79, sku='123', currency='AUD'):
    offers={'price':price,'priceCurrency':currency,'availability':'https://schema.org/InStock'}
    if seller: offers['seller']={'name':seller}
    return '<script type="application/ld+json">'+json.dumps({'@type':'Product','name':'Prismatic Evolutions ETB','sku':sku,'offers':offers})+'</script><button data-testid="add-to-cart-button">Add to cart</button>'


@pytest.mark.parametrize('seller,allowed', [('Kmart',True),('Gameology',False),(None,False),('Kmart Bargain Reseller',False)])
def test_marketplace_and_unknown_sellers_blocked(seller,allowed):
    h=page(seller)
    snap=refine_snapshot(parse_product('https://www.kmart.com.au/product/example/',h),h,{})
    assert snap.first_party is allowed
    if not allowed: assert snap.in_stock is None


def test_recommendation_stock_does_not_override_primary_sold_out():
    h=page()+'''<form><input name="id" value="42"><input name="quantity" value="1"><button type="submit" disabled>Out of stock</button></form><form><input name="productId" value="99"><button type="submit">Add to cart</button></form>'''
    snap=refine_snapshot(parse_product('https://toymate.com.au/example/',h),h,{})
    assert snap.in_stock is False


def test_missing_primary_control_is_unknown():
    h=page()
    snap=refine_snapshot(parse_product('https://toymate.com.au/example/',h),h,{})
    assert snap.in_stock is None


def test_wrong_sku_is_suppressed():
    h=page('Target Australia')
    snap=refine_snapshot(parse_product('https://www.target.com.au/p/example/123',h),h,{'expected_sku':'456'})
    assert snap.in_stock is None


@pytest.mark.parametrize('price,currency,allowed', [(79,'AUD',True),(80,'AUD',False),(None,'AUD',False),(50,'USD',False),(float('nan'),'AUD',False)])
def test_price_cap_currency_and_unknown_price(price,currency,allowed):
    snap=ProductSnapshot('target-au','https://www.target.com.au/p/test','Test',price,currency,True,'123','json-ld',first_party=True)
    assert PokemonMonitor._eligible(None,snap,{'max_price':79,'currency':'AUD'},{'first_party_only':True}) is allowed


def test_failed_notification_does_not_consume_restock(tmp_path):
    class Config:
        def get_settings(self):return {}
        def get_webhook(self):return 'test'
    monitor=PokemonMonitor(Config(),str(tmp_path))
    async def html(*args,**kwargs):return page('Target Australia')
    async def fail(*args,**kwargs):raise RuntimeError('delivery failed')
    monitor.fetcher.html=html
    monitor.notifier.send=fail
    item={'url':'https://www.target.com.au/p/test','max_price':79,'currency':'AUD'}
    with pytest.raises(RuntimeError):asyncio.run(monitor.check_item(item,{'strict_product_checks':True,'first_party_only':True}))
    assert item['url'] not in monitor.state.data['products']


def test_target_disabled_purchase_button_overrides_schema():
    h=page('Target Australia').replace('data-testid="add-to-cart-button"', 'data-testid="add-to-cart-button" aria-disabled="true"')
    snap=refine_snapshot(parse_product('https://www.target.com.au/p/test',h),h,{})
    assert snap.in_stock is False
