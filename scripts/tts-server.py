#!/usr/bin/env python3
"""小肥鱼本地 TTS 垫片：把 OpenAI 兼容的 /v1/audio/speech 转成 edge-tts 合成。

桥的 ttsProvider=openai 只要一个 OpenAI 兼容端点，edge-tts（微软 Edge 朗读）免费且不用 key，
这里做一层薄封装；不需要 GPU，但合成音频需要访问在线语音服务。
环境变量：TTS_PORT(9880) TTS_VOICE(zh-CN-XiaoyiNeural) TTS_RATE(+6%) TTS_PITCH(+8Hz)
"""
import os
import logging
from aiohttp import web
import edge_tts

PORT = int(os.environ.get('TTS_PORT', '9880'))
DEFAULT_VOICE = os.environ.get('TTS_VOICE', 'zh-CN-XiaoyiNeural')
RATE = os.environ.get('TTS_RATE', '+6%')
PITCH = os.environ.get('TTS_PITCH', '+8Hz')
# OpenAI 声音名 → edge 中文声线，方便以后换名不加代码
ALIAS = {
    'alloy': DEFAULT_VOICE, 'shimmer': DEFAULT_VOICE, 'nova': DEFAULT_VOICE,
    'zh-CN-XiaoyiNeural': 'zh-CN-XiaoyiNeural',
    'zh-CN-XiaoxiaoNeural': 'zh-CN-XiaoxiaoNeural',
    'zh-CN-XiaochenNeural': 'zh-CN-XiaochenNeural',
    'zh-CN-XiaomengNeural': 'zh-CN-XiaomengNeural',
    'zh-CN-XiaoyouNeural': 'zh-CN-XiaoyouNeural',
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('tts')


async def speech(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'invalid json'}, status=400)
    text = str(body.get('input') or '').strip()
    if not text:
        return web.json_response({'error': 'empty input'}, status=400)
    if len(text) > 500:
        text = text[:500]
    voice = ALIAS.get(str(body.get('voice') or ''), DEFAULT_VOICE)
    try:
        communicate = edge_tts.Communicate(text, voice, rate=RATE, pitch=PITCH)
        audio = bytearray()
        async for chunk in communicate.stream():
            if chunk.get('type') == 'audio':
                audio.extend(chunk['data'])
    except Exception as error:  # noqa: BLE001
        log.warning('synthesize failed: %s', error)
        return web.json_response({'error': f'tts failed: {error}'}, status=502)
    if not audio:
        return web.json_response({'error': 'empty audio'}, status=502)
    log.info('tts %d chars -> %d bytes (%s)', len(text), len(audio), voice)
    return web.Response(body=bytes(audio), content_type='audio/mpeg')


async def health(_request: web.Request) -> web.Response:
    return web.json_response({'ok': True, 'voice': DEFAULT_VOICE, 'rate': RATE, 'pitch': PITCH})


def main() -> None:
    app = web.Application(client_max_size=1 << 20)
    app.router.add_post('/v1/audio/speech', speech)
    app.router.add_get('/health', health)
    log.info('tts shim listening on 127.0.0.1:%d voice=%s', PORT, DEFAULT_VOICE)
    web.run_app(app, host='127.0.0.1', port=PORT, print=None)


if __name__ == '__main__':
    main()
