"""Rebuild the supplemental numeric tables from the public, processed ledgers."""
from collections import Counter
from pathlib import Path
from statistics import fmean, median
import csv
import json
import re

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
OUT = ROOT / 'output/tables'

def read(name):
    with (DATA / name).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))

def hu(value):
    return f'{float(value):.2f}'.replace('.', ',')

def write_table(name, columns, header, rows):
    text = '\n'.join([r'\begin{tabular}{' + columns + '}', r'\toprule',
                      header + r' \\', r'\midrule',
                      *[' & '.join(row) + r' \\' for row in rows],
                      r'\bottomrule', r'\end{tabular}']) + '\n'
    (OUT / name).write_text(text, encoding='utf-8')

def numbers(text):
    return re.findall(r'(?<![A-Za-z])\d+,\d+', text)

def build():
    OUT.mkdir(parents=True, exist_ok=True)
    apps = read('application_summary.csv')
    sessions = [r for r in read('sessions.csv') if r['included'] == 'True']
    main = [r for r in sessions if r['model'] == 'gpt-5.5' and r['bucket'] in ['native', 'mcp']]
    assert len(sessions) == 110 and sum(r['success'] == 'True' for r in sessions) == 103
    summary = read('summary.csv')
    groups = [next(r for r in summary if r['model'] == 'gpt-5.5' and r['bucket'] == setup)
              for setup in ['native', 'mcp']]
    costs = read('cost_sessions.csv')
    rows = []
    for label, key, scale in [
        ('Szkriptindítások száma', 'script_launches_mean', 1),
        ('Teljes tokenszám (millió)', 'total_tokens_mean', 1e6),
        ('Nem gyorsítótárazott bemenet (ezer)', 'uncached_input_tokens_mean', 1e3),
        ('Kimeneti tokenek (ezer)', 'output_tokens_mean', 1e3)]:
        rows.append([label, *[hu(float(r[key])/scale) for r in groups]])
    rows.append(['Becsült tokenköltség (USD)', *[
        hu(fmean(float(r['total_usd']) for r in costs if r['model'] == 'gpt-5.5' and r['setup'] == setup))
        for setup in ['native', 'mcp']]])
    write_table('eroforrasok.tex', '@{}lrr@{}', r'Mérőszám & Referencia ($n=35$) & AGATA ($n=39$)', rows)

    rows = []
    for app in ['Excel', 'PowerPoint', 'Word']:
        record = next(r for r in apps if r['app'] == app and r['bucket'] == 'aionly')
        assert int(record['n']) == int(record['successes']) == 3
        rows.append([app, *[hu(record['minutes_' + k]) for k in ['mean', 'median', 'min', 'max']]])
    write_table('office_mi_tartomany.tex', '@{}lrrrr@{}', 'Alkalmazás & Átlag & Medián & Minimum & Maximum', rows)

    phases = [r for r in read('phase_sessions.csv') if r['model'] == 'gpt-5.5' and r['phase_partition_available'] == 'True']
    assert len(phases) == 38
    rows = []
    phase_stats = {}
    for label, key in [('Előkészítés', 'preparation_minutes'), ('Első feltárás', 'exploration_minutes'),
                       ('Feltárás utáni munka', 'post_completion_minutes'), ('Teljes munkamenet', 'total_minutes'),
                       ('Utolsó szkript belső futásideje', 'runtime_minutes')]:
        values = [float(r[key]) for r in phases]
        stats = [fmean(values), median(values), min(values), max(values)]
        phase_stats[key] = stats
        rows.append([label, hu(stats[0]), hu(stats[1]), hu(stats[2]) + '--' + hu(stats[3])])
    write_table('fazisidok.tex', '@{}lrrr@{}', 'Időszak, illetve mérőszám & Átlag & Medián & Minimum--maximum', rows)

    main_ids = {r['id'] for r in main if r['setup'] == 'mcp'}
    errors = [r for r in read('command_errors.csv') if r['session'] in main_ids]
    assert len(main_ids) == 39 and len(errors) == 353
    focus = {'InputFocusNotReady', 'InputFocusChanged', 'WindowActivationFailed'}
    error_stats = {}
    for name in ['TargetNotFound', 'AmbiguousTarget', 'Fókusz és aktiválás', 'WaitBlockedByDialog', 'ProviderTimeout']:
        codes = focus if name == 'Fókusz és aktiválás' else {name}
        selected = [r for r in errors if r['error_type'] in codes]
        error_stats[name] = {'commands': len(selected), 'sessions': len({r['session'] for r in selected}),
                             'applications': dict(Counter(r['application'] for r in selected))}
    expected_errors = {'TargetNotFound': (94, 28), 'AmbiguousTarget': (22, 17),
                       'Fókusz és aktiválás': (27, 16), 'WaitBlockedByDialog': (8, 6),
                       'ProviderTimeout': (0, 0)}
    for code, counts in expected_errors.items():
        assert (error_stats[code]['commands'], error_stats[code]['sessions']) == counts

    means = {}
    for setup in ['native', 'mcp', 'aionly']:
        records = [r for r in apps if r['model'] == 'gpt-5.5' and r['setup'] == setup]
        if setup == 'aionly':
            records = [r for r in records if r['app'] in ['Excel', 'PowerPoint', 'Word']]
        means[setup] = fmean(float(r['minutes_mean']) for r in records)
    assert [hu(means['native']), hu(means['mcp']), hu(means['aionly'])] == ['40,15', '18,86', '24,92']
    assert round(100*(1-means['mcp']/means['native']), 1) == 53.0
    assert len(read('route_audits.csv')) == 5
    for name in ['alkalmazasok.tex', 'modellek.tex', 'eroforrasok.tex', 'office_mi_tartomany.tex', 'fazisidok.tex']:
        actual = (OUT/name).read_text(encoding='utf-8')
        expected = (ROOT/'reference_tables'/name).read_text(encoding='utf-8')
        assert numbers(actual) == numbers(expected), ('Table numeric mismatch', name)
    report = {'included_sessions': len(sessions), 'five_row_signals': 103, 'main_AGATA_command_errors': len(errors),
              'known_route_bypasses': 5, 'equal_application_means': means,
              'phase_heuristic_estimates': phase_stats, 'error_summary': error_stats,
              'numeric_reference_tables_match': True,
              'raw_log_independence': 'These checks recompute published summaries, not the extraction or audit of private source logs.'}
    (ROOT/'output/verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Verified five numeric tables, 110 sessions, 353 errors and five known route audits.')

if __name__ == '__main__':
    build()
