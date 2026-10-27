#!/usr/bin/env python3
from pathlib import Path
import json
from fish_config import PROJECT

for label, path in [('进程', PROJECT / 'data/runtime.json'), ('QQ', PROJECT / 'data/qq-bridge/qq-runtime.json')]:
    if path.exists():
        data = json.loads(path.read_text())
        if label == 'QQ':
            data = {k: data.get(k) for k in ['version', 'uptimeSeconds', 'sessionCount', 'botOnline', 'outbox']}
        print(label + ': ' + json.dumps(data, ensure_ascii=False))
