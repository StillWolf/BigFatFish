#!/usr/bin/env python3
"""Print sanitized operational status without messages or credentials."""
import json
import os
import time
from fish_config import PROJECT, load_config
from operational_health import collect, read_json

cached = read_json(PROJECT / 'data/health/status.json')
if cached and isinstance(cached.get('updatedAt'), (int, float)) and 0 <= time.time() - cached['updatedAt'] < 120:
    print(json.dumps(cached, ensure_ascii=False, indent=2))
else:
    try: features = load_config().get('features', {})
    except (OSError, ValueError, KeyError): features = {}
    result = collect(PROJECT, bili_root=os.environ.get('FISH_BILIBILI_ROOT'),
          xhs_root=os.environ.get('FISH_XHS_ROOT'), activity_pidfile=os.environ.get('FISH_ACTIVITY_PIDFILE'),
          features=features)
    result['monitor'] = {'state': 'stale_or_unavailable'}
    print(json.dumps(result, ensure_ascii=False, indent=2))
