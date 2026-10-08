"""Reproducible Standard-API-equivalent token costs, not Codex invoices."""
from collections import defaultdict
from pathlib import Path
from statistics import mean
import json

from analyze_current import OFFICE, MODEL_ORDER, PRIMARY_MODELS, write_csv
from extract import read_records

PRICE_DATE = '2026-10-08'
PRICE_SOURCE = 'https://developers.openai.com/api/docs/pricing'
CACHE_SOURCE = 'https://developers.openai.com/api/docs/guides/prompt-caching'
# USD per million tokens. Cache writes replace ordinary input charges.
RATES = {
    'gpt-5.5': (5, .5, 5, 30),
    'gpt-5.6-luna': (.2, .02, .25, 1.2),
    'gpt-5.6-sol': (4, .4, 5, 20),
    'gpt-6-luna': (.1, .01, .125, .5),
    'gpt-6-sol': (2, .2, 2.5, 10),
    'gpt-6.1-sol': (2, .1, 2.5, 10),
}
PARTS = ['ordinary_input_usd', 'cached_read_usd', 'cache_write_usd', 'output_usd']
PRIMARY = ['gpt-5.5', *PRIMARY_MODELS]


def context_audit(path, end_line):
    """Inspect request sizes within the measured task; cumulative size is irrelevant."""
    records, errors = read_records(path)
    if errors:
        raise ValueError(f'Malformed token source: {path}')
    samples = []
    tiers = set()
    for line, event in records:
        if line > end_line:
            break
        payload = event.get('payload', {})
        if payload.get('type') == 'token_count':
            usage = (payload.get('info') or {}).get('last_token_usage')
            if usage:
                samples.append((usage['input_tokens'], line))
        if event.get('type') == 'turn_context':
            for key in ('service_tier', 'speed', 'tier'):
                if payload.get(key) is not None:
                    tiers.add(f'{key}={payload[key]}')
    if not samples:
        raise ValueError(f'No per-request usage for context-price audit: {path}')
    maximum, line = max(samples)
    return {'max_request_input_tokens': maximum, 'max_request_line': line,
            'request_usage_samples': len(samples), 'recorded_service_tiers': sorted(tiers)}


def price_run(run, audit):
    """Price the last cumulative counters exactly once, including failed sessions."""
    if audit['max_request_input_tokens'] > 272000:
        # GPT-5.5 uses a session surcharge; later models use request surcharges.
        # Do not silently apply short-context prices to a future long-context run.
        raise ValueError(f'{run["id"]}: long-context pricing requires a separate allocation')
    usage = run['usage']
    reads = run['cached_input_tokens']
    writes = usage.get('cache_write_input_tokens', 0)
    ordinary = run['input_tokens'] - reads - writes
    output = run['output_tokens']  # Includes reasoning output; never add it again.
    if min(ordinary, reads, writes, output) < 0:
        raise ValueError(f'{run["id"]}: invalid token partition')
    if run['input_tokens'] + output != run['total_tokens']:
        raise ValueError(f'{run["id"]}: inconsistent token total')
    costs = dict(zip(PARTS, [n * rate / 1e6 for n, rate in
                            zip((ordinary, reads, writes, output), RATES[run['model']])]))
    return {'run_id': run['id'], 'model': run['model'], 'setup': run['setup'],
            'application': run['app'], 'success': run['success'], 'minutes': run['minutes'],
            'input_tokens': run['input_tokens'], 'ordinary_input_tokens': ordinary,
            'cached_read_tokens': reads, 'cache_write_tokens': writes,
            'cache_write_field_recorded': 'cache_write_input_tokens' in usage,
            'output_tokens': output, 'reasoning_output_tokens_included': run['reasoning_output_tokens'],
            'total_tokens': run['total_tokens'], **costs, 'total_usd': sum(costs.values()),
            'no_cache_usd': run['input_tokens'] * RATES[run['model']][0] / 1e6 + costs['output_usd'],
            'price_date': PRICE_DATE, 'tier_assumption': 'Standard', 'context_band': 'short',
            'source_file': run['file'], 'source_sha256': run['sha256'],
            'usage_line': usage['line'], **audit}


def summarize_cost(rows, scope, equal_apps=False):
    apps = sorted({r['application'] for r in rows})
    def avg(key):
        return mean(mean(r[key] for r in rows if r['application'] == app) for app in apps) if equal_apps else mean(r[key] for r in rows)
    successes = sum(r['success'] for r in rows)
    successful = [r for r in rows if r['success']]
    total = sum(r['total_usd'] for r in rows)
    return {'scope': scope, 'model': rows[0]['model'], 'setup': rows[0]['setup'],
            'n': len(rows), 'successes': successes, 'applications': apps,
            'application_counts': {app: sum(r['application'] == app for r in rows) for app in apps},
            'weighting': 'equal application means' if equal_apps else 'session mean',
            'mean_minutes': avg('minutes'), 'mean_total_tokens': avg('total_tokens'),
            **{f'mean_{part}': avg(part) for part in PARTS}, 'mean_total_usd': avg('total_usd'),
            'mean_no_cache_usd': avg('no_cache_usd'), 'total_observed_usd': total,
            'successful_session_mean_usd': mean(r['total_usd'] for r in successful) if successful else None,
            'spent_usd_per_observed_success': total / successes if successes else None,
            'run_ids': [r['run_id'] for r in rows]}


def cost_summaries(ledger):
    groups = defaultdict(list)
    for row in ledger:
        groups[(row['model'], row['setup'])].append(row)
    cohort = [summarize_cost(rows, 'all included sessions') for rows in groups.values()]
    balanced = []
    for (model, setup), rows in groups.items():
        if model == 'gpt-5.5' and setup in ['mcp', 'native']:
            balanced.append(summarize_cost(rows, 'ten applications', True))
        office = [r for r in rows if r['application'] in OFFICE]
        if set(r['application'] for r in office) == set(OFFICE):
            balanced.append(summarize_cost(office, 'three Office applications', True))
    application = [summarize_cost([r for r in rows if r['application'] == app], app)
                   for rows in groups.values() for app in sorted({r['application'] for r in rows})]
    order = lambda row: (MODEL_ORDER.index(row['model']), ['mcp', 'native', 'aionly'].index(row['setup']))
    return sorted(cohort, key=order), sorted(balanced, key=order), sorted(application, key=order)


def add_cost_analysis(data, out):
    runs = [r for r in data['runs'] if r['included']]
    ledger = [price_run(r, context_audit(Path(data['source_root']) / r['file'], r['end_line'])) for r in runs]
    cohort, balanced, application = cost_summaries(ledger)
    snapshot = {'date': PRICE_DATE, 'currency': 'USD', 'tier': 'Standard',
                'unit': 'per million tokens', 'source': PRICE_SOURCE, 'cache_source': CACHE_SOURCE,
                'models': [{'model': mod, 'ordinary_input': RATES[mod][0], 'cached_read': RATES[mod][1],
                            'cache_write': RATES[mod][2] if mod != 'gpt-5.5' else None,
                            'output': RATES[mod][3],
                            'source': f'https://developers.openai.com/api/docs/models/{mod}'} for mod in MODEL_ORDER],
                'notes': ['GPT-5.5 has no separate cache-write premium.',
                          'GPT-5.6 Sol prices are promotional, available at least through 2026-11-21.',
                          'All measured requests are at most 272,000 input tokens; long-context surcharges are not applied.',
                          'Standard is a reference assumption; no service tier is recorded in these turn contexts.',
                          'These are token-cost equivalents, not ChatGPT/Codex subscription charges or invoices.',
                          'Hosted-tool fees, regional premiums, taxes, infrastructure and framework/tool construction are excluded.']}
    data['cost_analysis'] = {'pricing': snapshot, 'ledger': ledger, 'cohorts': cohort,
                             'equal_application': balanced, 'by_application': application,
                             'cache_write_tokens': sum(r['cache_write_tokens'] for r in ledger),
                             'max_request_input_tokens': max(r['max_request_input_tokens'] for r in ledger)}
    (out / 'data' / 'pricing_snapshot.json').write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
    write_csv(out / 'data' / 'cost_sessions.csv', ledger)
    write_csv(out / 'data' / 'cost_comparisons.csv', cohort + balanced)
    write_csv(out / 'data' / 'cost_by_application.csv', application)
