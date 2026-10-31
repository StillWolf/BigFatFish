import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from bilibili_comments import Comments

BV = 'BV1234567890'


class FakeComments(Comments):
    def __init__(self, root):
        browser = SimpleNamespace(seen={BV}, context=SimpleNamespace(cookies=self.cookies))
        super().__init__(browser, root, lambda value: (value, 'https://www.bilibili.com/video/' + value))
        self.sent = []
        self.fail = False

    async def cookies(self, _url):
        return [{'name': 'bili_jct', 'value': 'test-csrf'}]

    async def api(self, method, url, **kwargs):
        if '/nav' in url:
            return {'data': {'isLogin': True, 'wbi_img': {'img_url': 'https://example.test/' + 'a'*32 + '.png', 'sub_url': 'https://example.test/' + 'b'*32 + '.png'}}}
        if '/view?' in url:
            return {'code': 0, 'data': {'aid': 42}}
        if '/wbi/main?' in url:
            return {'code': 0, 'data': {'replies': [{'rpid_str': '123456789012345678', 'member': {'uname': 'a'},
                'content': {'message': 'hello'}, 'replies': [{'rpid_str': '987654321012345678', 'content': {'message': 'world'}}]}]}}
        if '/reply/add' in url:
            self.sent.append(kwargs['form'])
            if self.fail: raise TimeoutError()
            return {'code': 0, 'data': {'rpid_str': '99'}}
        raise AssertionError('unexpected request')


class CommentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.comments = FakeComments(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    async def test_disabled_and_unknown_reply_do_not_post(self):
        with self.assertRaisesRegex(ValueError, '尚未启用'):
            await self.comments.send(BV, 'hello')
        (self.root/'comment-enabled').write_text('1')
        with self.assertRaisesRegex(ValueError, '重新读取'):
            await self.comments.send(BV, 'reply', '123', '456')
        self.assertEqual(self.comments.sent, [])

    async def test_read_then_reply_preserves_full_ids_and_limits_duplicates(self):
        (self.root/'comment-enabled').write_text('1')
        rows = await self.comments.read(BV)
        child = rows['comments'][0]['replies'][0]
        result = await self.comments.send(BV, 'reply', child['root'], child['parent'])
        self.assertTrue(result['submitted'])
        self.assertEqual(self.comments.sent[0]['root'], '123456789012345678')
        self.assertEqual(self.comments.sent[0]['parent'], '987654321012345678')
        with self.assertRaises(ValueError):
            await self.comments.send(BV, 'again')
        self.assertEqual(len(self.comments.sent), 1)

    async def test_unknown_result_does_not_retry(self):
        (self.root/'comment-enabled').write_text('1')
        self.comments.fail = True
        with self.assertRaisesRegex(ValueError, '结果未知'):
            await self.comments.send(BV, 'hello')
        with self.assertRaises(ValueError):
            await self.comments.send(BV, 'hello')
        self.assertEqual(len(self.comments.sent), 1)

    async def test_unwatched_video_is_rejected(self):
        (self.root/'comment-enabled').write_text('1')
        self.comments.browser.seen.clear()
        with self.assertRaisesRegex(ValueError, '实际观看'):
            await self.comments.send(BV, 'hello')
        self.assertEqual(self.comments.sent, [])


if __name__ == '__main__':
    unittest.main()
