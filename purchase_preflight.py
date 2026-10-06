"""Read-only configuration audit. Makes no network, cart or payment requests."""
import argparse
from collections import Counter
import json
from pathlib import Path

from src.buy_rules import purchase_rule_problems


def audit_config(config):
    if not isinstance(config, dict):
        raise ValueError('Configuration must be an object')
    settings = config.get('settings', {})
    products = config.get('products', [])
    if not isinstance(settings, dict) or not isinstance(products, list):
        raise ValueError('Settings must be an object and products must be a list')
    master = settings.get('purchases_enabled', False)
    counts = Counter(p.get('url') for p in products
                     if isinstance(p, dict) and isinstance(p.get('url'), str))
    rows = []
    for index, item in enumerate(products):
        if not isinstance(item, dict):
            raise ValueError('Every product must be an object')
        problems = purchase_rule_problems(item)
        auto_buy = item.get('auto_buy', False)
        if type(auto_buy) is not bool:
            problems.append('Auto-buy must be a JSON boolean')
        if isinstance(item.get('url'), str) and counts[item['url']] > 1:
            problems.append('Duplicate product URL; consolidate into one rule')
        rows.append({
            'product': item.get('name') or f'Product {index + 1}',
            'auto_buy': auto_buy is True,
            'configuration_valid': not problems,
            'problems': problems,
        })
    return {
        'mode': 'configuration-only; no live stock verification or purchase execution',
        'master_purchase_permission': master is True,
        'configuration_valid': type(master) is bool and bool(rows)
                               and all(row['configuration_valid'] for row in rows),
        'settings_problems': [] if type(master) is bool else ['Master permission must be a JSON boolean'],
        'products': rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='watchlist.json', help='JSON configuration to inspect without modifying it')
    args = parser.parse_args()
    try:
        report = audit_config(json.loads(Path(args.config).read_text()))
    except (OSError, ValueError, TypeError):
        print(json.dumps({'configuration_valid': False, 'error': 'Configuration could not be read or has an invalid structure'}))
        return 1
    print(json.dumps(report, indent=2))
    return 0 if report['configuration_valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
