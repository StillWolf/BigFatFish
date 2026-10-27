#!/usr/bin/env python3
"""Operational readiness only; does not call a model or send a message."""
import json
from pathlib import Path
import socket
import time
from fish_config import PROJECT

try:
    state = json.loads((PROJECT / 'data/runtime.json').read_text())
    assert time.time() - state['updatedAt'] < 20
    assert state['services']['dsh']['running']
    for host, port in [(state['webBind'], 3080), ('127.0.0.1', 6700)]:
        with socket.create_connection((host, port), timeout=2):
            pass
except (OSError, ValueError, AssertionError, KeyError):
    raise SystemExit(1)
