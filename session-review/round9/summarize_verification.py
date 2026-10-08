"""Consolidate latest checks while retaining unsuccessful earlier attempts."""
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parent
latest = {}
attempts = []
for name in ('verification.json', 'final-verification.json', 'gui-final-verification.json', 'unicode-final-verification.json', 'gui-correctness-verification.json'):
    path = root / name
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    records = value.get('tests', [value]) if isinstance(value, dict) else value
    for record in records:
        latest[record['test']] = dict(record, source=name)
        attempts.append(dict(record, source=name))
checks = sum(sum(map(int, re.findall(r'(\d+) passed', value['output']))) + int('CLI stream failure-stop check: passed' in value['output']) for name, value in latest.items() if not name.endswith('Gui.Smoke.Tests.ps1'))
summary = dict(ok=len(latest)==14 and all(value['exitCode']==0 for value in latest.values()), checks=checks,
    timingReliable=False, timingNote='User reported hardware issues. Treat timings as provisional; use correctness outcomes separately.',
    tests=list(latest.values()), earlierFailures=[value for value in attempts if value['exitCode'] != 0])
(root / 'verification-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps({key: summary[key] for key in ('ok','checks','timingReliable')}))
if not summary['ok']:
    raise SystemExit(1)
