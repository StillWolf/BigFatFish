"""Record model usage metadata without prompts, replies, URLs or credentials."""
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import timedelta

TZ = ZoneInfo('Asia/Shanghai')
SOURCES = {'bilibili', 'xiaohongshu'}


def record_usage(project, source, usage):
    if source not in SOURCES or not isinstance(usage, dict): return False
    fields = {}
    for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
        value = usage.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100_000_000:
            fields[key] = value
    if not fields: return False
    now = datetime.now(TZ)
    root = Path(project) / 'data/usage'; root.mkdir(parents=True, exist_ok=True, mode=0o700); root.chmod(0o700)
    path = root / (now.date().isoformat() + '.jsonl')
    row = {'at': now.isoformat(), 'source': source, 'usage': fields}
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a', encoding='utf-8') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')
        stream.flush()
        fcntl.flock(stream, fcntl.LOCK_UN)
    return True


def summarize_usage(project, days=7, now=None):
    """Aggregate only metadata recorded by this module; no conversation text."""
    days = max(1, min(90, int(days)))
    today = (now or datetime.now(TZ)).date()
    root = Path(project) / 'data/usage'
    totals = {}
    for offset in range(days):
        path = root / ((today - timedelta(days=offset)).isoformat() + '.jsonl')
        if path.is_symlink(): continue
        try:
            with path.open(encoding='utf-8') as stream:
                for line in stream:
                    try:
                        row = json.loads(line); source = row.get('source'); usage = row.get('usage') or {}
                        if source not in SOURCES or not isinstance(usage, dict): continue
                        target = totals.setdefault(source, {'calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0})
                        target['calls'] += 1
                        for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
                            value = usage.get(key)
                            if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100_000_000:
                                target[key] += value
                    except (ValueError, TypeError, AttributeError):
                        continue
        except OSError:
            continue
    return {'days': days, 'scope': 'browser_summaries_only', 'sources': totals}
