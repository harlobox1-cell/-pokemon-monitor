from src.buyer import validate_for_cart
from src.models import ProductSnapshot


def snap(**kw):
    base = dict(
        retailer="toymate-au",
        url="https://toymate.com.au/test/",
        title="Pokemon TCG Test",
        price=59.99,
        currency="AUD",
        in_stock=True,
        sku="26000001",
        source="json-ld",
        first_party=True,
    )
    base.update(kw)
    return ProductSnapshot(**base)


def rule(**kw):
    base = dict(
        retailer="toymate-au",
        expected_sku="26000001",
        currency="AUD",
        max_price=59.99,
        quantity=1,
    )
    base.update(kw)
    return base


def test_cart_rule_allows_exact_safe_match():
    assert validate_for_cart(snap(), rule())[0] is True


def test_cart_rule_blocks_over_price():
    ok, _ = validate_for_cart(snap(price=60.00), rule())
    assert ok is False


def test_cart_rule_blocks_wrong_sku():
    ok, _ = validate_for_cart(snap(sku="999"), rule())
    assert ok is False


def test_cart_rule_blocks_unknown_stock():
    ok, _ = validate_for_cart(snap(in_stock=None), rule())
    assert ok is False


def test_cart_rule_blocks_quantity_over_one():
    ok, _ = validate_for_cart(snap(), rule(quantity=2))
    assert ok is False
