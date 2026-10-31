import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from bilibili_profile import Profile


class Locator:
    def __init__(self, page, name): self.page, self.name = page, name
    async def wait_for(self, **kwargs): pass
    async def input_value(self): return self.page.signature
    async def is_enabled(self): return True
    async def is_visible(self): return self.name == '.common-noimg-box' and self.page.dialog
    async def inner_text(self): return self.page.filled['nickname']
    def locator(self, name): return Locator(self.page, name)
    async def fill(self, value): self.page.filled[self.name] = value
    async def set_input_files(self, value): self.page.upload = value
    async def click(self, **kwargs): self.page.clicked.append(self.name)


class Response:
    async def json(self): return {'code': 0}


class ResponseWait:
    async def __aenter__(self): return SimpleNamespace(value=self.response())
    async def __aexit__(self, *args): pass
    async def response(self): return Response()


class Page:
    def __init__(self): self.filled = {}; self.clicked = []; self.signature = '旧签名'; self.upload = None; self.dialog = False
    async def goto(self, *args, **kwargs): pass
    def get_by_placeholder(self, name): return Locator(self, 'nickname')
    def locator(self, name): return Locator(self, name)
    def get_by_role(self, *args, **kwargs): return Locator(self, 'save')
    async def wait_for_function(self, *args, **kwargs): pass
    async def wait_for_timeout(self, *args): pass
    def expect_response(self, *args, **kwargs): return ResponseWait()
    async def close(self): pass


class Browser:
    def __init__(self): self.page = Page(); self.context = SimpleNamespace(new_page=self.new_page); self.comments = self
    async def new_page(self): return self.page
    async def api(self, *args): return {'code': 0, 'data': {'uname': '旧名字', 'sign': '旧签名'}}


class ProfileTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name); self.browser = Browser(); self.profile = Profile(self.browser, self.root)
    def tearDown(self): self.tmp.cleanup()

    async def test_requires_enablement(self):
        with self.assertRaisesRegex(ValueError, '尚未启用'): await self.profile.update('nickname', '新名字')
        with self.assertRaisesRegex(ValueError, '尚未启用'): await self.profile.set_avatar('fish-blue.png')
        self.assertEqual(self.browser.page.clicked, [])

    async def test_nickname_only_updates_one_field_and_rate_limits(self):
        (self.root/'profile-enabled').write_text('1')
        out = await self.profile.update('nickname', '新名字')
        self.assertTrue(out['submitted']); self.assertEqual(self.browser.page.filled, {'nickname': '新名字'})
        with self.assertRaisesRegex(ValueError, '近期'): await self.profile.update('nickname', '另一个名字')
        self.assertEqual(self.browser.page.clicked, ['save'])

    async def test_rejects_stale_settings(self):
        (self.root/'profile-enabled').write_text('1'); self.browser.page.signature = '不同的签名'
        with self.assertRaisesRegex(ValueError, '尚未同步'): await self.profile.update('nickname', '新名字')
        self.assertEqual(self.browser.page.clicked, [])

    async def test_nickname_confirmation_requires_exact_requested_name(self):
        (self.root/'profile-enabled').write_text('1'); self.browser.page.dialog = True
        out = await self.profile.update('nickname', '新名字')
        self.assertTrue(out['submitted'])
        self.assertEqual(self.browser.page.clicked, ['save', '.no-img-btn'])

    async def test_avatars_are_local_safe_and_set_only_selected_picture(self):
        (self.root/'profile-enabled').write_text('1'); img = self.profile.make_avatar('blue')
        self.assertRegex(img['name'], r'^fish-blue-[0-9a-f]{8}\.png$')
        self.assertEqual(self.profile.candidates()['avatars'], [{'name': img['name']}])
        with self.assertRaises(ValueError): self.profile.avatar_bytes('../secret.png')
        out = await self.profile.set_avatar(img['name']); self.assertTrue(out['submitted'])
        self.assertTrue(self.browser.page.upload['buffer'].startswith(b'\x89PNG'))
        self.assertEqual(self.browser.page.clicked, ['input.btn-confirm:not(.disabled)'])

    async def test_symlink_is_not_a_candidate(self):
        self.profile.avatars.mkdir(); (self.profile.avatars/'link.png').symlink_to('/etc/passwd')
        self.assertEqual(self.profile.candidates()['avatars'], [])
        with self.assertRaises(ValueError): self.profile.avatar_bytes('link.png')


if __name__ == '__main__': unittest.main()
