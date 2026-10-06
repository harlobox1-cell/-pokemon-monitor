import copy
import json
import subprocess
import sys

from purchase_preflight import audit_config


def config():
    return {'products': [{'name': 'Test', 'url': 'https://toymate.com.au/test/',
            'retailer': 'toymate-au', 'expected_sku': 'ABC-123', 'currency': 'AUD',
            'max_price': 10, 'max_quantity': 1, 'quantity': 1}]}


def test_configuration_preflight_never_enables_permissions():
    source = config()
    original = copy.deepcopy(source)
    result = audit_config(source)
    assert result['configuration_valid'] is True
    assert result['master_purchase_permission'] is False
    assert result['products'][0]['auto_buy'] is False
    assert source == original
    assert 'no live stock verification' in result['mode']


def test_unsupported_retailers_and_missing_rules_are_explained():
    result = audit_config({'products': [{'name': 'Kmart', 'retailer': 'kmart-au',
                                        'url': 'https://www.kmart.com.au/product/test/'}]})
    assert not result['configuration_valid']
    assert 'Purchase adapter unavailable for this retailer' in result['products'][0]['problems']


def test_duplicate_product_configuration_is_flagged():
    source = config()
    source['products'] *= 2
    result = audit_config(source)
    assert not result['configuration_valid']
    assert all(any('Duplicate' in p for p in row['problems']) for row in result['products'])


def test_cli_reports_invalid_json_without_exposing_content(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('sensitive-invalid-content')
    result = subprocess.run([sys.executable, 'purchase_preflight.py', '--config', str(path)],
                            capture_output=True, text=True)
    assert result.returncode == 1
    assert 'sensitive-invalid-content' not in result.stdout + result.stderr
    assert json.loads(result.stdout)['configuration_valid'] is False


def test_repository_watchlist_keeps_spending_off():
    from pathlib import Path
    source = json.loads(Path('watchlist.json').read_text())
    assert source['settings']['purchases_enabled'] is False
    assert all(p['auto_buy'] is False and p['quantity'] == 1 and p['max_quantity'] == 1
               for p in source['products'])
