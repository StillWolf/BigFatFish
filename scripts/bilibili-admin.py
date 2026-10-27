#!/usr/bin/env python3
"""Local operator CLI. No comment, like or account-credential export actions."""
import argparse
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('action', choices=('status', 'feed', 'search', 'watch'))
parser.add_argument('value', nargs='?', default='')
parser.add_argument('--seconds', type=int, default=30)
parser.add_argument('--start', type=int, default=0)
args = parser.parse_args()
root = Path(os.environ.get('FISH_BILIBILI_ROOT', str(Path(os.environ.get('FISH_PROJECT_ROOT', Path(__file__).resolve().parents[1])) / 'data/bilibili')))
token = next(line.split('=', 1)[1].strip() for line in (root / 'runtime.env').read_text().splitlines() if line.startswith('BILIBILI_TOKEN='))
payload = ({'video': args.value, 'seconds': args.seconds, 'start': args.start} if args.action == 'watch'
           else {'query': args.value, 'limit': 5} if args.action == 'search' else {})
request = urllib.request.Request('http://127.0.0.1:18160/api/' + args.action,
    data=json.dumps(payload).encode(), headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(request, timeout=285) as response:
        print(json.dumps(json.load(response), ensure_ascii=False, indent=2))
except urllib.error.HTTPError as error:
    print(error.read().decode()[:500])
    raise SystemExit(1)
