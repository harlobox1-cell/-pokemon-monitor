from src.buy_rules import evaluate_buy_rule
from src.models import ProductSnapshot


def make_snapshot(price=59.99, sku="26000001", in_stock=True, first_party=True):
    return ProductSnapshot(
        retailer="toymate-au",
        url="https://toymate.com.au/example/",
        title="Pokemon TCG Test",
        price=price,
        currency="AUD",
        in_stock=in_stock,
        sku=sku,
        source="test",
        first_party=first_party,
    )


def rule():
    return {"expected_sku": "26000001", "currency": "AUD", "max_price": 59.99, "quantity": 1}


def test_exact_match_is_eligible():
    assert evaluate_buy_rule(make_snapshot(), rule()).eligible is True


def test_over_price_is_blocked():
    assert evaluate_buy_rule(make_snapshot(price=60.00), rule()).eligible is False


def test_wrong_sku_is_blocked():
    assert evaluate_buy_rule(make_snapshot(sku="999"), rule()).eligible is False


def test_unknown_stock_is_blocked():
    assert evaluate_buy_rule(make_snapshot(in_stock=None), rule()).eligible is False


def test_non_first_party_is_blocked():
    assert evaluate_buy_rule(make_snapshot(first_party=False), rule()).eligible is False
