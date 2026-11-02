#!/usr/bin/env python3
"""Supervise a separate Xiaohongshu browser desktop and read-only service."""
import fcntl
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time


def main():
    project = Path(os.environ.get('FISH_PROJECT_ROOT', Path(__file__).resolve().parents[1]))
    root = Path(os.environ.get('FISH_XHS_ROOT', project / 'data/xiaohongshu'))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    lock = (root / 'runtime.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    for directory in ('logs', 'profile', 'cache', 'desktop-web', 'xdg-runtime'):
        (root / directory).mkdir(exist_ok=True, mode=0o700)
    tokenfile = root / 'runtime.env'
    if not tokenfile.exists():
        fd = os.open(tokenfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write('XHS_TOKEN=' + secrets.token_urlsafe(40) + '\n')
    webroot = root / 'desktop-web'
    for file in Path('/usr/share/novnc').iterdir():
        target = webroot / file.name
        if not target.exists():
            target.symlink_to(file)
    (webroot / 'index.html').write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>小红书浏览器</title>
<style>body{font:18px sans-serif;max-width:680px;margin:50px auto;padding:16px}</style>
<h1>小红书浏览器</h1><p>请在专用浏览器中使用官方页面登录。登录态仅保存在私有目录。</p>
<p><a href="vnc_lite.html?scale=1">打开浏览器</a></p><p>当前只接入只读浏览。</p></html>''')
    display = int(os.environ.get('FISH_XHS_DISPLAY', '93'))
    vnc_port = int(os.environ.get('FISH_XHS_VNC_PORT', '5913'))
    web_port = int(os.environ.get('FISH_XHS_WEB_PORT_INTERNAL', '6083'))
    if Path(f'/tmp/.X11-unix/X{display}').exists():
        raise SystemExit('小红书显示编号已被占用；请设置 FISH_XHS_DISPLAY')
    env = dict(os.environ, DISPLAY=f':{display}', XDG_RUNTIME_DIR=str(root / 'xdg-runtime'), FISH_XHS_ROOT=str(root))
    for name in ('PYTHONHOME', 'PYTHONPATH'):
        env.pop(name, None)
    children, retry_at = {}, {}
    stopping = False

    def stop(*_args):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def start(name, args):
        if name in children and children[name].poll() is None: return
        if time.monotonic() < retry_at.get(name, 0): return
        retry_at[name] = time.monotonic() + 15
        with (root / 'logs' / (name + '.log')).open('ab', buffering=0) as log:
            children[name] = subprocess.Popen(args, env=env, cwd=root, stdin=subprocess.DEVNULL,
                                              stdout=log, stderr=subprocess.STDOUT, start_new_session=True)

    try:
        while not stopping:
            start('xvfb', ['Xvfb', f':{display}', '-screen', '0', '1280x900x24', '-nolisten', 'tcp', '-ac'])
            if children.get('xvfb') and children['xvfb'].poll() is None and Path(f'/tmp/.X11-unix/X{display}').exists():
                start('openbox', ['openbox', '--sm-disable'])
                start('browser', [os.environ.get('FISH_PYTHON', sys.executable), str(project / 'scripts/xiaohongshu-browser.py')])
                start('vnc', ['x11vnc', '-display', f':{display}', '-rfbport', str(vnc_port), '-localhost', '-forever', '-shared', '-nopw', '-noxdamage', '-quiet'])
                start('novnc', [sys.executable, '-c',
                    "import sys;sys.path.insert(0,'/usr/lib/python3/dist-packages');from websockify import websockify_init;websockify_init()",
                    f'--web={webroot}', f"{os.environ.get('FISH_XHS_WEB_BIND', '127.0.0.1')}:{web_port}", f'127.0.0.1:{vnc_port}'])
            state = {'updatedAt': time.time(), 'pid': os.getpid(),
                     'services': {name: {'pid': proc.pid, 'running': proc.poll() is None} for name, proc in children.items()}}
            temporary = root / 'runtime.json.tmp'
            temporary.write_text(json.dumps(state)); os.chmod(temporary, 0o600); os.replace(temporary, root / 'runtime.json')
            time.sleep(2)
    finally:
        for proc in children.values():
            if proc.poll() is None:
                try: os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError: pass
        for proc in children.values():
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: os.killpg(proc.pid, signal.SIGKILL)


if __name__ == '__main__':
    main()
