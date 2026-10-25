"""Rebuild published thesis measurements without private logs or GUI execution."""
from pathlib import Path
import subprocess
import hashlib
import json
import sys
ROOT=Path(__file__).resolve().parent
manifest=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
for name, expected in manifest['files'].items():
    assert hashlib.sha256((ROOT/'data'/name).read_bytes()).hexdigest()==expected, ('Public data checksum mismatch',name)
for name in ['build_thesis_assets.py','build_gains.py','build_extra_tables.py']:
    subprocess.run([sys.executable,str(ROOT/name)],cwd=ROOT,check=True)
print('Done. See output/images, output/tables and output/verification.json.')
