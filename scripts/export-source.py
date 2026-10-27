#!/usr/bin/env python3
"""Build a source-only archive from an allowlist, including third-party licenses."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
from fish_config import PROJECT

parser = argparse.ArgumentParser(description='导出可公开的源码，不读取日记/聊天/浏览器 profile')
parser.add_argument('--output', default=str(PROJECT / 'dist'))
args = parser.parse_args()
version = json.loads((PROJECT / 'package.json').read_text())['version']
roots = ['README.md', 'LICENSE', 'NOTICE.md', 'CONTRIBUTING.md', 'SECURITY.md', 'AGENTS.md',
         '.gitignore', '.dockerignore', '.env.example', 'install.sh', 'fishctl', 'compose.yaml',
         'package.json', 'package-lock.json', 'config', 'deploy', 'scripts', 'docs', 'tests',
         'dsh-qq-onebot-bridge', 'dsh-wechat-ai-bridge', 'vendor/wechat-ai']
ignored = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', '.pytest_cache', '.mypy_cache'}
files = []
for name in roots:
    path = PROJECT / name
    if not path.exists():
        raise SystemExit('源码缺少必需文件：' + name)
    for item in sorted(path.rglob('*')) if path.is_dir() else [path]:
        relative = item.relative_to(PROJECT)
        if item.is_symlink() or not item.is_file() or any(x in ignored for x in relative.parts):
            continue
        if item.name == '.env' or (item.name.endswith(('.pyc', '.log', '.pid', '.db', '.sqlite'))):
            continue
        files.append(item)
# Compare against locally known private values without embedding those values in public code.
private_values = set()
env = PROJECT / '.env'
if env.exists():
    for line in env.read_text().splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            value = value.strip().strip('\"\'')
            if any(word in key for word in ('KEY', 'TOKEN', 'PASSWORD')) and len(value) >= 16:
                private_values.add(value)
old_card = PROJECT / 'data/maintenance/open-source-backup/AGENTS.md'
if old_card.exists():
    private_values.update(re.findall(r'(?<!\d)[1-9]\d{6,11}(?!\d)', old_card.read_text()))
manifest = []
for file in files:
    raw = file.read_bytes()
    text = raw.decode('utf8', errors='replace')
    if any(value in text for value in private_values):
        raise SystemExit('发现私有配置值，停止导出；请整理：' + str(file.relative_to(PROJECT)))
    manifest.append({'path': str(file.relative_to(PROJECT)), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
output = Path(args.output)
output.mkdir(parents=True, exist_ok=True)
archive = output / f'bigfatfish-{version}-source.tar.gz'
prefix = 'bigfatfish-' + version
with tarfile.open(archive, 'w:gz') as tar:
    for file in files:
        raw = file.read_bytes()
        item = tarfile.TarInfo(prefix + '/' + str(file.relative_to(PROJECT)))
        item.size = len(raw)
        item.mode = 0o755 if file.stat().st_mode & 0o111 else 0o644
        tar.addfile(item, io.BytesIO(raw))
    raw = (json.dumps({'version': version, 'files': manifest}, ensure_ascii=False, indent=2) + '\n').encode()
    item = tarfile.TarInfo(prefix + '/SOURCE-MANIFEST.json')
    item.size = len(raw)
    item.mode = 0o644
    tar.addfile(item, io.BytesIO(raw))
checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
(archive.with_suffix(archive.suffix + '.sha256')).write_text(checksum + '  ' + archive.name + '\n')
print(f'已导出 {len(files)} 个源码文件：{archive}')
print('SHA256 ' + checksum)
