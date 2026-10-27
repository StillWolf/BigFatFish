#!/usr/bin/env python3
"""Supervise the independent Linux WeChat desktop and MCP runtime."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import sys
import subprocess
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default=os.environ.get('FISH_WECHAT_RUNTIME', str(Path(__file__).resolve().parents[1] / 'data/wechat-runtime')))
    args = parser.parse_args()
    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    lock = (root / 'supervisor.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('WeChat runtime already running', flush=True)
        return
    lock.write(str(os.getpid()))
    lock.flush()
    for directory in ('logs', 'xdg-runtime', 'xdg-config', 'xdg-data', 'exports', 'desktop-web'):
        (root / directory).mkdir(exist_ok=True)
    webroot = root / 'desktop-web'
    for file in Path('/usr/share/novnc').iterdir():
        link = webroot / file.name
        if not link.exists():
            link.symlink_to(file)
    (webroot / 'login.html').write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>小肥鱼 · 微信登录</title>
<style>body{font:18px sans-serif;max-width:760px;margin:32px auto;padding:0 16px;background:#f4f8fb;color:#123}img{width:100%;border-radius:12px}a{color:#1673b1}</style>
<h1>小肥鱼 · 微信登录</h1><p>用小肥鱼的微信账号扫描桌面中的二维码，再在手机上确认登录。</p>
<p>需要点击或刷新二维码时，<a href="vnc_lite.html?scale=1">打开微信桌面</a>。</p>
<img id="desktop" src="login.png" alt="微信桌面正在准备">
<script>setInterval(()=>document.getElementById('desktop').src='login.png?t='+Date.now(),12000)</script></html>''')
    (root / 'xdg-runtime').chmod(0o700)
    env = dict(os.environ, DISPLAY=':91', XDG_RUNTIME_DIR=str(root / 'xdg-runtime'),
               XDG_CONFIG_HOME=str(root / 'xdg-config'), XDG_DATA_HOME=str(root / 'xdg-data'),
               QT_AUTO_SCREEN_SCALE_FACTOR='0', QT_SCALE_FACTOR='1', QT_FONT_DPI='96',
               LANG='C.UTF-8', OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2',
               YOLO_CONFIG_DIR=str(root / 'xdg-config/Ultralytics'))
    secrets_file = root / 'runtime.env'
    if secrets_file.exists():
        for line in secrets_file.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env[key.strip()] = value.strip()
    children = {}
    retry_at = {}
    stopping = False
    preview_at = 0

    def stop_signal(*_args):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop_signal)
    signal.signal(signal.SIGINT, stop_signal)

    def stop_children():
        for proc in children.values():
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + 5
        for proc in children.values():
            try:
                proc.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        children.clear()

    def start(name, command, cwd=None):
        proc = children.get(name)
        if proc and proc.poll() is None:
            return
        if time.monotonic() < retry_at.get(name, 0):
            return
        retry_at[name] = time.monotonic() + 10
        with (root / 'logs' / f'{name}.log').open('ab', buffering=0) as log:
            children[name] = subprocess.Popen(command, cwd=cwd or root, env=env,
                                              stdin=subprocess.DEVNULL, stdout=log,
                                              stderr=subprocess.STDOUT, start_new_session=True)
        print(f'{name} started pid={children[name].pid}', flush=True)

    try:
        while not stopping:
            xvfb = children.get('xvfb')
            if xvfb and xvfb.poll() is not None:
                stop_children()
            start('xvfb', ['Xvfb', ':91', '-screen', '0', '1280x1200x24', '-nolisten', 'tcp', '-ac'])
            if Path('/tmp/.X11-unix/X91').exists():
                start('openbox', ['openbox', '--sm-disable'])
                start('wechat', [str(root / 'client/opt/wechat/wechat'), '--no-sandbox'], root / 'client/opt/wechat')
                # Both listeners are loopback-only; access goes through SSH.
                start('vnc', ['x11vnc', '-display', ':91', '-rfbport', '5911', '-localhost',
                              '-forever', '-shared', '-nopw', '-noxdamage', '-quiet'])
                start('novnc', [sys.executable, '-c',
                                "import sys; sys.path.insert(0, '/usr/lib/python3/dist-packages'); from websockify import websockify_init; websockify_init()",
                                f'--web={webroot}',
                                '127.0.0.1:6081', '127.0.0.1:5911'])
                if (root / 'python-ready').exists():
                    start('mcp', [str(root / 'venv/bin/python'), '-m', 'wechat_ai_bot.bot',
                                  '--config', str(root / 'config.yaml')], root / 'source/wechat-ai-master')
                # Stop desktop previews once account storage appears; don't keep
                # publishing screenshots of private chats after login.
                if time.monotonic() > preview_at and not any(Path(os.environ.get('WECHAT_FILES_ROOT', str(Path.home() / 'xwechat_files'))).glob('*_*/db_storage')):
                    preview_at = time.monotonic() + 12
                    temporary_image = webroot / 'login-next.png'
                    try:
                        result = subprocess.run(['scrot', '-o', str(temporary_image)], env=env,
                                                stdin=subprocess.DEVNULL, capture_output=True, timeout=5)
                        if result.returncode == 0:
                            os.replace(temporary_image, webroot / 'login.png')
                    except subprocess.TimeoutExpired:
                        pass
            for logfile in (root / 'logs').glob('*.log'):
                if logfile.stat().st_size > 10 * 1024 * 1024:
                    with logfile.open('rb') as stream:
                        stream.seek(-128 * 1024, 2)
                        recent = stream.read()
                    logfile.write_bytes(recent)
            state = {'updatedAt': time.time(), 'supervisorPid': os.getpid(), 'display': ':91',
                     'desktopUrl': 'http://127.0.0.1:6081/vnc.html',
                     'services': {name: {'pid': proc.pid, 'running': proc.poll() is None,
                                         'exitCode': proc.poll()} for name, proc in children.items()}}
            temporary = root / 'runtime.json.tmp'
            temporary.write_text(json.dumps(state, indent=2) + '\n')
            os.replace(temporary, root / 'runtime.json')
            time.sleep(2)
    finally:
        stop_children()


if __name__ == '__main__':
    main()
