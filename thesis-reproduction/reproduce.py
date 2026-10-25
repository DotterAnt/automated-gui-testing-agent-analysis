"""Rebuild published thesis measurements without private logs or GUI execution."""
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parent
for name in ['build_thesis_assets.py','build_gains.py','build_extra_tables.py']:
    subprocess.run([sys.executable,str(ROOT/name)],cwd=ROOT,check=True)
print('Done. See output/images, output/tables and output/verification.json.')
