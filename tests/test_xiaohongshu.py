import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
# The parsing and browser orchestration are tested without a live browser or network.
aiohttp = types.ModuleType('aiohttp'); web = types.ModuleType('aiohttp.web'); aiohttp.web = web
playwright = types.ModuleType('playwright'); playwright_async = types.ModuleType('playwright.async_api')
playwright_async.async_playwright = lambda: None
with patch.dict(sys.modules, {'aiohttp': aiohttp, 'aiohttp.web': web, 'playwright': playwright, 'playwright.async_api': playwright_async}):
    spec = importlib.util.spec_from_file_location('xhs_test_module', Path(__file__).resolve().parents[1] / 'scripts/xiaohongshu-browser.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)

ID = '1234567890abcdef12345678'
URL = 'https://www.xiaohongshu.com/explore/' + ID + '?xsec_token=opaque-token&xsec_source=pc_feed'


class Locator:
    def __init__(self, page, selector): self.page, self.selector = page, selector
    @property
    def first(self): return self
    async def wait_for(self, **_kwargs): pass
    async def evaluate_all(self, _script): return self.page.comment_rows if 'comment-item' in self.selector else self.page.cards
    async def count(self): return self.page.image_count if 'swiper-slide' in self.selector else 1 if 'comments-container' in self.selector else 0
    def nth(self, _index): return self
    async def is_visible(self): return self.page.close_available if 'close-button' in self.selector else True
    async def click(self, **_kwargs): self.page.closed_login_prompt = True
    async def screenshot(self, **_kwargs): return b'synthetic-image'
    async def evaluate(self, script, **_kwargs):
        if 'ended:v.ended' in script:
            self.page.video_time += 1
            return {'time': self.page.video_time, 'duration': 100, 'ended': False, 'paused': False}
        if 'duration:Number.isFinite' in script:
            return {'time': 0, 'duration': 100}
        return None


class Page:
    def __init__(self, login=False):
        self.login = login; self.closed = False; self.image_count = 0; self.close_available = False; self.closed_login_prompt = False; self.video_time = 0
        self.cards = [{'href': URL, 'title': '实际标题'}, {'href': URL, 'title': '重复'}]
        self.comment_rows = [{'author': '用户', 'text': '评论内容'} for _ in range(8)]
        self.details = {'title': '实际标题', 'content': '实际正文', 'imageCount': 0, 'videoPresent': True}
    async def goto(self, *_args, **_kwargs): pass
    async def wait_for_timeout(self, *_args): pass
    async def evaluate(self, _script, *_args):
        return {'title': '视频标题', 'audioSource': 'https://sns-video.xhscdn.com/example.mp4'} if _args else self.details
    def locator(self, selector): return Locator(self, selector)
    async def close(self): self.closed = True
    def is_closed(self): return self.closed


class Context:
    def __init__(self, login=False): self.login = login; self.pages = []
    async def new_page(self):
        page = Page(self.login); self.pages.append(page); return page


class XhsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.patch = patch.object(module, 'ROOT', Path(self.tmp.name)); self.patch.start()
        self.browser = module.Browser(); self.browser.context = Context()
        self.browser.page_state = AsyncMock(return_value={'loginRequired': False, 'restricted': False, 'host': 'www.xiaohongshu.com', 'path': '/explore'})
        self.browser.summarize_images = AsyncMock(return_value='')
    def tearDown(self): self.patch.stop(); self.tmp.cleanup()

    async def test_link_validation_blocks_non_official_hosts_and_preserves_private_ref(self):
        note, ref = module.canonical_note(URL)
        self.assertEqual(note, ID); self.assertIn('xsec_token=', ref)
        for bad in ('https://evil.example/explore/' + ID, 'http://www.xiaohongshu.com/explore/' + ID,
                    'https://attacker@www.xiaohongshu.com/explore/' + ID, 'https://www.xiaohongshu.com:443/explore/' + ID):
            with self.assertRaises(ValueError): module.canonical_note(bad)
        self.assertTrue(module.media_url('https://sns-video.xhscdn.com/example.mp4'))
        self.assertFalse(module.media_url('https://evil.example/video.mp4'))
        self.assertFalse(module.media_url('https://xhscdn.com.evil.example/video.mp4'))

    async def test_feed_and_read_are_compact_and_cache_previous_read(self):
        feed = await self.browser.listing()
        self.assertEqual(feed['notes'], [{'noteId': ID, 'title': '实际标题', 'noteType': 'unknown', 'previouslyObserved': False}])
        self.assertNotIn('opaque-token', json.dumps(feed))
        read = await self.browser.read(ID)
        self.assertEqual(read['content'], '实际正文'); self.assertTrue(read['videoPresent'])
        self.assertFalse(read['videoPlayed']); self.assertFalse(read['cached'])
        pages = len(self.browser.context.pages)
        again = await self.browser.read(ID)
        self.assertTrue(again['cached']); self.assertEqual(len(self.browser.context.pages), pages)
        self.assertTrue(module.observed_before(ID))
        self.assertNotIn('opaque-token', (module.ROOT / 'cache' / (ID + '.json')).read_text())

    async def test_login_gate_does_not_access_or_claim_note(self):
        self.browser.page_state = AsyncMock(return_value={'loginRequired': True, 'restricted': False, 'host': 'www.xiaohongshu.com', 'path': '/login'})
        with self.assertRaisesRegex(ValueError, '需要登录'): await self.browser.listing()
        self.assertEqual(self.browser.refs, {})
        self.assertTrue(self.browser.context.pages[0].closed)

    async def test_restriction_does_not_get_bypassed(self):
        self.browser.page_state = AsyncMock(return_value={'loginRequired': False, 'restricted': True, 'host': 'www.xiaohongshu.com'})
        with self.assertRaisesRegex(ValueError, '访问受限'): await self.browser.listing()

    async def test_id_needs_a_note_reference(self):
        with self.assertRaisesRegex(ValueError, '先从小红书'): await self.browser.read(ID)

    async def test_status_does_not_claim_login_without_evidence(self):
        self.browser.ready = True; self.browser.operator_page = Page()
        status = await self.browser.status()
        self.assertIsNone(status['loginRequired']); self.assertIsNone(status['loginVerified'])
        self.browser.last_access = 'login_required'; self.browser.last_access_at = module.time.time()
        self.assertTrue((await self.browser.status())['loginRequired'])
        self.browser.last_access_at -= 31
        self.assertIsNone((await self.browser.status())['loginRequired'])

    async def test_image_note_samples_at_most_two_images_and_caches_summary(self):
        async def new_page():
            page = Page(); page.image_count = 4
            page.details = {'title': '图片笔记', 'content': '', 'imageCount': 4, 'videoPresent': False}
            self.browser.context.pages.append(page); return page
        self.browser.context.new_page = new_page
        self.browser.summarize_images = AsyncMock(return_value='图片摘要')
        self.browser.refs[ID] = URL
        result = await self.browser.read(ID)
        self.assertEqual(result['sampledImages'], 2)
        self.assertEqual(result['imageSummary'], '图片摘要')
        self.assertEqual(len(self.browser.summarize_images.await_args.args[0]), 2)
        self.assertTrue((await self.browser.read(ID))['cached'])
        self.assertEqual(self.browser.summarize_images.await_count, 1)

    async def test_comments_are_limited_and_do_not_expose_reference(self):
        self.browser.refs[ID] = URL
        result = await self.browser.comments(ID, 5)
        self.assertEqual(len(result['comments']), 5)
        self.assertEqual(result['comments'][0]['text'], '评论内容')
        self.assertNotIn('opaque-token', json.dumps(result))
        self.browser.page_state = AsyncMock(return_value={'loginRequired': True, 'restricted': False, 'host': 'www.xiaohongshu.com', 'path': '/login'})
        with self.assertRaisesRegex(ValueError, '需要登录'): await self.browser.comments(ID)

    async def test_redirect_to_other_host_is_rejected(self):
        self.browser.page_state = AsyncMock(return_value={'loginRequired': False, 'restricted': False, 'host': 'evil.example'})
        with self.assertRaisesRegex(ValueError, '非小红书'): await self.browser.listing()

    async def test_dismisses_only_visible_guest_prompt(self):
        page = Page(); page.close_available = True
        self.browser.page_state = AsyncMock(side_effect=[
            {'loginRequired': True, 'restricted': False, 'host': 'www.xiaohongshu.com', 'path': '/explore'},
            {'loginRequired': False, 'restricted': False, 'host': 'www.xiaohongshu.com', 'path': '/explore'},
        ])
        state = await self.browser.require_access(page)
        self.assertTrue(page.closed_login_prompt); self.assertFalse(state['loginRequired'])

    async def test_guest_search_redirect_is_not_mislabeled_as_search_result(self):
        with self.assertRaisesRegex(ValueError, '搜索需要登录'):
            await self.browser.listing('宠物')

    async def test_video_requires_real_progress_and_caches_observed_clip(self):
        self.browser.refs[ID] = URL
        self.browser.speech = AsyncMock(return_value=('语音摘录', 'local_asr'))
        self.browser.summarize_images = AsyncMock(return_value='视频片段摘要')
        result = await self.browser.watch(ID, 12)
        self.assertTrue(result['videoPlayed']); self.assertFalse(result['watched']['fullVideo'])
        self.assertGreaterEqual(result['watched']['playedSeconds'], 12)
        self.assertEqual(result['sampledFrames'], 2); self.assertEqual(result['textSource'], 'local_asr')
        self.assertTrue((await self.browser.watch(ID, 12))['cached'])
        self.assertEqual(self.browser.speech.await_count, 1)

    async def test_failed_image_summary_is_cached_briefly(self):
        async def new_page():
            page = Page(); page.image_count = 1
            page.details = {'title': '图片笔记', 'content': '', 'imageCount': 1, 'videoPresent': False}
            self.browser.context.pages.append(page); return page
        self.browser.context.new_page = new_page
        self.browser.refs[ID] = URL
        with patch.object(module.time, 'time', return_value=1000):
            first = await self.browser.read(ID); second = await self.browser.read(ID)
            self.assertFalse(first['cached']); self.assertTrue(second['cached'])
            self.assertEqual(self.browser.summarize_images.await_count, 1)
        with patch.object(module.time, 'time', return_value=1301):
            self.assertFalse((await self.browser.read(ID))['cached'])
            self.assertEqual(self.browser.summarize_images.await_count, 2)


if __name__ == '__main__': unittest.main()
