#!/usr/bin/env python3
"""Container supervisor. Owns its children only and keeps all state in volumes."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from fish_config import PROJECT, load_config, private_write, render_runtime


def main():
    config = load_config()
    workspace = render_runtime(config)
    features = config['features']
    logs = PROJECT / 'data/logs'
    logs.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env['FISH_PROJECT_ROOT'] = str(PROJECT)
    env['FISH_DIARY_FAMILY_QQ'] = os.environ['FISH_DIARY_FAMILY_QQ']
    env['FISH_BILIBILI_ROOT'] = str(PROJECT / 'data/bilibili')
    env['FISH_WECHAT_RUNTIME'] = str(PROJECT / 'data/wechat-runtime')
    env['TTS_VOICE'] = config.get('speech', {}).get('voice', 'zh-CN-XiaoyiNeural')
    for name in ('PYTHONHOME', 'PYTHONPATH'):
        env.pop(name, None)
    host = socket.gethostbyname(socket.gethostname())
    public_port = os.environ.get('FISH_WEB_PORT', '3080')
    commands = {'dsh': [str(PROJECT / 'node_modules/.bin/dsh'), 'web', '--host', host, '--port', '3080', '--no-open',
                        '--public-url', f'http://127.0.0.1:{public_port}', '--trusted-host', f'127.0.0.1:{public_port}', f'localhost:{public_port}']}
    if features.get('activities'):
        commands['activities'] = [sys.executable, str(PROJECT / 'scripts/proactive-daemon.py')]
    if features.get('diary'):
        commands['diary'] = [sys.executable, str(PROJECT / 'scripts/fish-diary.py'), '--daemon']
    if features.get('tts'):
        commands['tts'] = [sys.executable, str(PROJECT / 'scripts/tts-server.py')]
    if features.get('bilibili'):
        commands['bilibili'] = [sys.executable, str(PROJECT / 'scripts/bilibili-runtime.py')]
        commands['speech-model'] = [sys.executable, str(PROJECT / 'scripts/prepare-bilibili-model.py')]
    children, retry = {}, {}
    stopping = False

    def stop(*_args):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while not stopping:
            for name, command in commands.items():
                if name == 'activities':
                    try:
                        with socket.create_connection(('127.0.0.1', 6700), timeout=.3):
                            pass
                    except OSError:
                        continue
                process = children.get(name)
                if process and process.poll() is None:
                    continue
                if name == 'speech-model' and process and process.returncode == 0:
                    continue
                if time.monotonic() < retry.get(name, 0):
                    continue
                retry[name] = time.monotonic() + (300 if name == 'speech-model' else 15)
                with (logs / (name + '.log')).open('ab', buffering=0) as log:
                    children[name] = subprocess.Popen(command, env=env, cwd=workspace if name == 'dsh' else PROJECT,
                        stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
                print(f'{name} started pid={children[name].pid}', flush=True)
            private_write(PROJECT / 'data/runtime.json', {'updatedAt': time.time(), 'pid': os.getpid(), 'webBind': host,
                'services': {name: {'pid': p.pid, 'running': p.poll() is None, 'exitCode': p.poll()} for name, p in children.items()}})
            for file in logs.glob('*.log'):
                if file.stat().st_size > 10 * 1024 * 1024:
                    with file.open('rb') as stream:
                        stream.seek(-128 * 1024, 2)
                        tail = stream.read()
                    file.write_bytes(tail)
            time.sleep(2)
    finally:
        for child in children.values():
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + 8
        for child in children.values():
            try:
                child.wait(timeout=max(.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


if __name__ == '__main__':
    main()
