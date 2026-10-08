"""Package updated sources without Git history, desktop state, or run artifacts."""
import hashlib
import json
from pathlib import Path
import zipfile

workspace = Path(r'C:\diplomamunka')
out = workspace / 'outputs'
out.mkdir(exist_ok=True)
manifest = []
for name in ('potato-cli', 'automated-gui-testing-agent-framework'):
    root = workspace / name
    target = out / (name + '-improved-20260930-round5.zip')
    files = []
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob('*')):
            if not path.is_file() or any(part in ('.git', '.state', 'runs', '__pycache__') for part in path.relative_to(root).parts):
                continue
            relative = path.relative_to(workspace).as_posix()
            archive.write(path, relative)
            files.append({'path': relative, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(files)
    manifest.append({'archive': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'files': files})
    print(f'{target}: {len(files)} files, {target.stat().st_size} bytes')
Path(__file__).with_name('package-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
