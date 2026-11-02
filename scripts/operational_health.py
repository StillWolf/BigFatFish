"""Read-only operational status; never return messages, diaries or credentials."""
from datetime import datetime
import json
import os
from pathlib import Path
import socket
import time
import urllib.error
import urllib.request

from usage_stats import summarize_usage

_ACCOUNT_CACHE = {}


def read_json(path):
    try:
        path = Path(path)
        if path.is_symlink() or path.stat().st_size > 2_000_000: return {}
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def alive(pid, expected=''):
    try:
        pid = int(pid)
        if pid <= 1: return False
        os.kill(pid, 0)
        if expected:
            command = (Path('/proc') / str(pid) / 'cmdline').read_bytes()
            return expected.encode() in command
        return True
    except PermissionError:
        # An inaccessible process may still be alive; never restart blindly.
        return True
    except (OSError, ValueError, TypeError):
        return False


def age_seconds(value, now):
    try:
        if isinstance(value, str): value = datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
        value = float(value)
        if value > 10_000_000_000: value /= 1000
        age = now - value
        return round(age) if age >= -30 else None
    except (ValueError, TypeError, OverflowError):
        return None


def token_from(root, name):
    try:
        for line in (Path(root) / 'runtime.env').read_text().splitlines():
            key, sep, value = line.partition('=')
            if sep and key == name: return value.strip()
    except OSError:
        pass
    return ''


def request_json(port, path='/health', token='', timeout=3):
    try:
        kwargs = {}
        if token:
            kwargs = {'data': b'{}', 'headers': {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}}
        req = urllib.request.Request(f'http://127.0.0.1:{int(port)}{path}', **kwargs)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as response:
            if int(response.headers.get('Content-Length') or 0) > 1_000_000: return {}
            value = json.load(response)
            return value if isinstance(value, dict) else {}
    except (OSError, ValueError, urllib.error.URLError):
        return {}


def port_open(port):
    try:
        with socket.create_connection(('127.0.0.1', int(port)), timeout=1): return True
    except (OSError, ValueError):
        return False


def collect(project, *, bili_root=None, xhs_root=None, activity_pidfile=None, features=None, now=None):
    project = Path(project); now = time.time() if now is None else now
    bili_root = Path(bili_root or project / 'data/bilibili')
    xhs_root = Path(xhs_root or project / 'data/xiaohongshu')
    activity_pidfile = Path(activity_pidfile or project / 'data/logs/proactive-daemon.pid')
    features = features or {}
    qq = read_json(project / 'data/qq-bridge/qq-runtime.json')
    qq_age = age_seconds(qq.get('updatedAt'), now)
    qq_alive = alive(qq.get('pid'), 'dsh')
    if not qq_alive: qq_state = 'down'
    elif qq_age is None or qq_age > 180: qq_state = 'stale'
    elif qq.get('botOnline') is True: qq_state = 'online'
    elif qq.get('botOnline') is False: qq_state = 'offline'
    else: qq_state = 'unknown'
    try: activity_pid = activity_pidfile.read_text().strip()
    except OSError: activity_pid = ''
    pending = read_json(project / 'data/schedule-pending.json')
    retry = sum(1 for x in pending.values() if isinstance(x, dict) and x.get('status') == 'retry')
    uncertain = sum(1 for x in pending.values() if isinstance(x, dict) and x.get('status') in ('uncertain', 'writing'))
    diary = read_json(project / 'data/diary-service/runtime.json')
    diary_age = age_seconds(diary.get('updatedAt'), now)
    outbox = qq.get('outbox') if isinstance(qq.get('outbox'), dict) else {}
    activity = qq.get('activity') if isinstance(qq.get('activity'), dict) else {}
    result = {
        'updatedAt': int(now),
        'qq': {'state': qq_state, 'snapshotAgeSeconds': qq_age,
               'outboxChats': outbox.get('chatsPending'), 'activityRunning': bool(activity.get('active'))},
        'activities': {'running': alive(activity_pid, 'proactive-daemon.py'), 'retryPending': retry, 'uncertain': uncertain},
        'diary': {'running': alive(diary.get('pid'), 'fish-diary.py'), 'heartbeatAgeSeconds': diary_age},
    }
    for name, root, port, token_name in [('bilibili', bili_root, 18160, 'BILIBILI_TOKEN'), ('xiaohongshu', xhs_root, 18170, 'XHS_TOKEN')]:
        enabled = bool(features.get(name, (root / 'runtime.env').exists()))
        if not enabled:
            result[name] = {'enabled': False}; continue
        state = read_json(root / 'runtime.json'); supervisor_alive = alive(state.get('pid'), name + '-runtime.py')
        health = request_json(port)
        token = token_from(root, token_name)
        info = {}
        account_age = None
        if health.get('ready') and token:
            cached_at, cached = _ACCOUNT_CACHE.get(name, (0, {}))
            # Bilibili's status check contacts its platform; keep health checks light.
            if name != 'bilibili' or not cached or now - cached_at >= 180:
                raw = request_json(port, '/api/status', token, timeout=10)
                allowed = ('loggedIn', 'socialAvailable', 'socialMonitor') if name == 'bilibili' else ('guestAccess', 'loginRequired', 'restricted')
                info = {key: raw[key] for key in allowed if key in raw}
                if info: _ACCOUNT_CACHE[name] = (now, info); cached_at = now
            else:
                info = cached
            account_age = round(now - cached_at) if info else None
        row = {'enabled': True, 'supervisorRunning': supervisor_alive,
               'heartbeatAgeSeconds': age_seconds(state.get('updatedAt'), now), 'browserReady': health.get('ready') is True,
               'accountStatusAgeSeconds': account_age}
        if name == 'bilibili':
            row.update(loggedIn=info.get('loggedIn'), socialEnabled=info.get('socialAvailable'))
            monitor = info.get('socialMonitor') or {}
            row.update(socialMonitorHealthy=monitor.get('healthy'), socialMonitorAgeSeconds=age_seconds(monitor.get('lastCheck'), now))
        else:
            row.update(guestAccess=info.get('guestAccess'), loginRequired=info.get('loginRequired'), restricted=info.get('restricted'))
        result[name] = row
    tts = request_json(9880)
    result['tts'] = {'ready': tts.get('ok') is True}
    result['usage'] = summarize_usage(project)
    return result
