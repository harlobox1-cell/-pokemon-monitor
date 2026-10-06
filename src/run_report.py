"""Safe run diagnostics: counts only, no webhook URLs or response bodies."""
from collections import Counter


def summarize_run(monitor, watches):
    counts = Counter()
    failures = Counter()
    for item in watches:
        state = monitor.run_observations.get(item['url'])
        if state is None:
            counts['not_checked'] += 1
        elif state.get('last_error'):
            counts['fetch_errors'] += 1
            failures[item.get('retailer', 'unknown')] += 1
        elif state.get('alert_eligible') is True:
            counts['qualifying_stock'] += 1
        elif state.get('in_stock') is False:
            counts['out_of_stock'] += 1
        elif state.get('in_stock') is None:
            counts['unknown_stock'] += 1
        else:
            counts['excluded_by_rules'] += 1
    return {
        'products': len(watches),
        **{key: counts[key] for key in ('not_checked', 'fetch_errors', 'qualifying_stock', 'out_of_stock',
                                       'unknown_stock', 'excluded_by_rules')},
        'stock_alerts_attempted': monitor.stock_alert_attempts,
        'stock_alerts_sent': monitor.stock_alerts_sent,
        'fetch_errors_by_retailer': dict(failures),
    }


def report_markdown(report):
    labels = {
        'products': 'Products configured', 'not_checked': 'Not checked in this run',
        'fetch_errors': 'Fetch or parsing failures',
        'qualifying_stock': 'Qualifying stock observations', 'out_of_stock': 'Out of stock',
        'unknown_stock': 'Stock unknown', 'excluded_by_rules': 'Excluded by price/currency/seller rules',
        'stock_alerts_attempted': 'Stock alerts attempted', 'stock_alerts_sent': 'Stock alerts accepted by Discord',
    }
    rows = '\n'.join(f'| {label} | {report[key]} |' for key, label in labels.items())
    return ('## Monitor run summary\n\n| Check | Count |\n| --- | ---: |\n' + rows
            + '\n\nZero attempted alerts means no new alert event was sent. It does not test the webhook. '
              'Unchanged qualifying stock is intentionally not re-alerted. Auto-buy permissions do not disable stock alerts.\n')
