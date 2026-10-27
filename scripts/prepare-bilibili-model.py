#!/usr/bin/env python3
"""Download public ASR weights once; no API key, video or chat data is sent."""
import os
from pathlib import Path
from huggingface_hub import snapshot_download

name = os.environ.get('FISH_ASR_MODEL', 'small')
if name not in ('base', 'small'):
    raise SystemExit('FISH_ASR_MODEL 仅支持 base 或 small')
root = Path(os.environ['FISH_BILIBILI_ROOT']) / 'models' / name
if not all((root / f).exists() for f in ['model.bin', 'config.json', 'tokenizer.json']):
    snapshot_download('Systran/faster-whisper-' + name, local_dir=str(root),
                      allow_patterns=['*.json', 'model.bin', 'vocabulary.*'], token=False)
print('Local ASR model ready:', name)
