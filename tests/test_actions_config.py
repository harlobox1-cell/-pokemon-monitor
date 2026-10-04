import pytest
from run_once import ActionsConfig


def test_only_enabled_products_are_checked():
    config = ActionsConfig({'products': [
        {'url': 'https://www.bigw.com.au/product/test/p/123'},
        {'url': 'https://example.com/', 'enabled': False},
    ]}, 'private-test-value')
    assert len(config.list_watches()) == 1
    assert config.list_watches()[0]['enabled'] is True
    assert config.get_webhook() == 'private-test-value'
    assert config.list_discovers() == []


def test_unknown_product_host_rejected():
    with pytest.raises(ValueError):
        ActionsConfig({'products': [{'url': 'https://example.com/'}]}, '')
