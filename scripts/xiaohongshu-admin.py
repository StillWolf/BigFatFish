#!/usr/bin/env python3
"""Local read-only Xiaohongshu operator commands and activity toggle."""
import argparse
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('action', choices=('status', 'feed', 'search', 'read', 'comments', 'watch', 'activity-enable', 'activity-disable'))
parser.add_argument('value', nargs='?', default='')
args = parser.parse_args()
project = Path(os.environ.get('FISH_PROJECT_ROOT', Path(__file__).resolve().parents[1]))
root = Path(os.environ.get('FISH_XHS_ROOT', project / 'data/xiaohongshu'))
if args.action in ('activity-enable', 'activity-disable'):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    flag = root / 'activity-enabled'
    if args.action == 'activity-disable':
        flag.unlink(missing_ok=True); print('小红书随机活动已关闭')
    else:
        fd = os.open(flag, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream: stream.write('1\n')
        print('小红书随机活动已启用，作息守护进程下次排程时生效')
    raise SystemExit(0)
token = next(line.split('=', 1)[1].strip() for line in (root / 'runtime.env').read_text().splitlines() if line.startswith('XHS_TOKEN='))
payload = {'keyword': args.value} if args.action == 'search' else {'note': args.value} if args.action in ('read', 'comments', 'watch') else {}
port = int(os.environ.get('FISH_XHS_API_PORT', '18170'))
request = urllib.request.Request(f'http://127.0.0.1:{port}/api/{args.action}', data=json.dumps(payload).encode(),
    headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
try:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=300 if args.action == 'watch' else 125) as response:
        print(json.dumps(json.load(response), ensure_ascii=False, indent=2))
except urllib.error.HTTPError as error:
    print(error.read().decode()[:500])
    raise SystemExit(1)
