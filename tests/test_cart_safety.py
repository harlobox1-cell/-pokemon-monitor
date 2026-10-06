import asyncio
import json
from types import SimpleNamespace

import pytest

from src.cart_adapter import add_verified_toymate_item
from src.buyer import toymate_cart_once

URL = 'https://toymate.com.au/test/'
ITEM = dict(url=URL, retailer='toymate-au', expected_sku='ABC-123', currency='AUD',
            max_price=10, quantity=1, max_quantity=1)


def markup(price=10, product_id='FORM-42', extra=''):
    product = {'@type': 'Product', 'name': 'Test', 'sku': 'ABC-123', 'url': URL,
               'productID': product_id,
               'offers': {'price': price, 'priceCurrency': 'AUD', 'availability': 'https://schema.org/InStock'}}
    return '<script type="application/ld+json">' + json.dumps(product) + '</script><p>SKU: ABC-123 Online: Available</p>' + extra


class Control:
    def __init__(self, page, kind):
        self.page, self.kind = page, kind

    @property
    def first(self):
        return self

    async def count(self):
        return self.page.forms if self.kind == 'form' else 1

    def locator(self, selector):
        if 'button' in selector:
            return Control(self.page, 'button')
        return Control(self.page, 'quantity' if 'quantity' in selector else 'id')

    async def input_value(self):
        return self.page.quantity if self.kind == 'quantity' else self.page.product_id

    async def fill(self, value):
        if self.page.quantity_error:
            raise RuntimeError('quantity control unavailable')
        self.page.quantity = value

    async def is_disabled(self):
        return self.page.disabled

    async def get_attribute(self, name):
        return 'true' if self.page.aria_disabled else None

    async def is_visible(self):
        return True

    async def inner_text(self):
        return self.page.button_label

    async def click(self):
        self.page.clicks += 1
        if self.page.click_error:
            raise TimeoutError('submission outcome unknown')
        if self.page.checkout:
            self.page.url = 'https://toymate.com.au/checkout'


class Page:
    def __init__(self, **changes):
        self.url = URL
        self.status = 200
        self.forms = 1
        self.quantity = '6'
        self.product_id = 'FORM-42'
        self.quantity_error = False
        self.disabled = False
        self.aria_disabled = False
        self.button_label = 'Add to cart'
        self.click_error = False
        self.checkout = False
        self.clicks = 0
        self.navigations = 0
        self.html = [markup()]
        self.__dict__.update(changes)

    async def goto(self, *args, **kwargs):
        self.navigations += 1
        return SimpleNamespace(status=self.status) if self.status is not None else None

    async def wait_for_timeout(self, *args):
        pass

    async def content(self):
        return self.html.pop(0) if len(self.html) > 1 else self.html[0]

    def locator(self, selector):
        return Control(self, 'form')


@pytest.mark.parametrize('changes', [
    {'quantity_error': True}, {'forms': 2}, {'forms': 0}, {'disabled': True},
    {'aria_disabled': True}, {'product_id': 'wrong'}, {'button_label': 'Buy now'},
    {'html': [markup(product_id=None)]}, {'html': [markup(extra='Verify you are human')]},
    {'url': 'https://evil.example/test/'}, {'status': 429}, {'status': 403}, {'status': None},
    {'html': [markup(), markup(price=11)]},
    {'html': [markup(), markup(extra='<div class="cf-turnstile"></div>')]},
])
def test_uncertain_evidence_never_clicks(changes):
    page = Page(**changes)
    result = asyncio.run(add_verified_toymate_item(page, ITEM))
    assert not result.ok and page.clicks == 0
    assert result.status == 'blocked'


def test_successful_click_does_not_claim_verified_cart():
    page = Page()
    result = asyncio.run(add_verified_toymate_item(page, ITEM))
    assert page.clicks == 1 and page.quantity == '1'
    assert result.status == 'unconfirmed' and not result.ok


def test_click_timeout_never_retries():
    page = Page(click_error=True)
    result = asyncio.run(add_verified_toymate_item(page, ITEM))
    assert page.clicks == 1 and result.status == 'unconfirmed'
    assert 'no retry' in result.message


def test_unexpected_checkout_stops():
    page = Page(checkout=True)
    result = asyncio.run(add_verified_toymate_item(page, ITEM))
    assert page.clicks == 1 and result.status == 'safety_stop'


def test_bad_url_never_opens_a_browser_or_navigates():
    page = Page()
    result = asyncio.run(add_verified_toymate_item(page, {**ITEM, 'url': 'https://evil.example/'}))
    assert page.navigations == 0 and not result.ok
    result = asyncio.run(toymate_cart_once({'url': ''}))
    assert result.status == 'blocked'
