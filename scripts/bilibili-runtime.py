#!/usr/bin/env python3
"""Own a separate browser display; QQ and WeChat desktops are unaffected."""
import fcntl
import json
import os
from pathlib import Path
import secrets
import signal
import sys
import subprocess
import time


def main():
    root = Path(os.environ.get('FISH_BILIBILI_ROOT', str(Path(os.environ.get('FISH_PROJECT_ROOT', Path(__file__).resolve().parents[1])) / 'data/bilibili')))
    project = Path(os.environ.get('FISH_PROJECT_ROOT', str(Path(__file__).resolve().parents[1])))
    root.mkdir(exist_ok=True, mode=0o700)
    root.chmod(0o700)
    lock = (root / 'runtime.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    for directory in ('logs', 'profile', 'cache', 'scratch', 'desktop-web', 'xdg-runtime'):
        (root / directory).mkdir(exist_ok=True, mode=0o700)
    envfile = root / 'runtime.env'
    if not envfile.exists():
        fd = os.open(envfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write('BILIBILI_TOKEN=' + secrets.token_urlsafe(40) + '\n')
    webroot = root / 'desktop-web'
    for file in Path('/usr/share/novnc').iterdir():
        target = webroot / file.name
        if not target.exists():
            target.symlink_to(file)
    (webroot / 'index.html').write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>小肥鱼 · B站</title>
<style>body{font:18px sans-serif;max-width:680px;margin:50px auto;padding:16px;color:#234;background:#f4f8fb}a{color:#1673b1}</style>
<h1>小肥鱼的 B站浏览器</h1><p>游客可看公开可播放的视频。需要自己的推荐和账号功能时，可在浏览器里完成官方扫码登录。</p>
<p><a href="vnc_lite.html?scale=1">打开 B站浏览器</a></p>
<p>当前已接入浏览与视频片段理解。评论功能尚未接通。</p></html>''')
    env = dict(os.environ, DISPLAY=':92', XDG_RUNTIME_DIR=str(root / 'xdg-runtime'),
               PLAYWRIGHT_BROWSERS_PATH=os.environ.get('PLAYWRIGHT_BROWSERS_PATH', str(root / 'browsers')), FISH_BILIBILI_ROOT=str(root),
               OMP_NUM_THREADS='4', OPENBLAS_NUM_THREADS='4', HF_HUB_DISABLE_TELEMETRY='1')
    for name in ('PYTHONHOME', 'PYTHONPATH'):
        env.pop(name, None)
    children = {}
    retry_at = {}
    stopping = False

    def stop(*_args):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def start(name, args):
        if name in children and children[name].poll() is None:
            return
        if time.monotonic() < retry_at.get(name, 0):
            return
        retry_at[name] = time.monotonic() + 15
        with (root / 'logs' / (name + '.log')).open('ab', buffering=0) as log:
            children[name] = subprocess.Popen(args, env=env, cwd=root, stdin=subprocess.DEVNULL,
                                              stdout=log, stderr=subprocess.STDOUT, start_new_session=True)

    try:
        while not stopping:
            start('xvfb', ['Xvfb', ':92', '-screen', '0', '1440x1000x24', '-nolisten', 'tcp', '-ac'])
            if Path('/tmp/.X11-unix/X92').exists():
                start('openbox', ['openbox', '--sm-disable'])
                start('browser', [os.environ.get('FISH_PYTHON', str(root / 'venv/bin/python') if (root / 'venv/bin/python').exists() else sys.executable), str(project / 'scripts/bilibili-browser.py')])
                start('vnc', ['x11vnc', '-display', ':92', '-rfbport', '5912', '-localhost', '-forever', '-shared', '-nopw', '-noxdamage', '-quiet'])
                start('novnc', [sys.executable, '-c',
                               "import sys;sys.path.insert(0,'/usr/lib/python3/dist-packages');from websockify import websockify_init;websockify_init()",
                               f'--web={webroot}', os.environ.get('FISH_BILIBILI_WEB_BIND', '127.0.0.1') + ':6082', '127.0.0.1:5912'])
            state = {'updatedAt': time.time(), 'pid': os.getpid(),
                     'services': {name: {'pid': proc.pid, 'running': proc.poll() is None} for name, proc in children.items()}}
            temp = root / 'runtime.json.tmp'
            temp.write_text(json.dumps(state))
            os.replace(temp, root / 'runtime.json')
            for file in (root / 'logs').glob('*.log'):
                if file.stat().st_size > 5 * 1024 * 1024:
                    with file.open('rb') as stream:
                        stream.seek(-65536, 2)
                        content = stream.read()
                    file.write_bytes(content)
            time.sleep(2)
    finally:
        for proc in children.values():
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        for proc in children.values():
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)


if __name__ == '__main__':
    main()
