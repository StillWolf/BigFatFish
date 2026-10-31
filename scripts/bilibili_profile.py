"""Bilibili profile tools, using the bot's authorized browser session."""
from contextlib import closing
from io import BytesIO
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time

from PIL import Image, ImageDraw, ImageOps


class Profile:
    def __init__(self, browser, root):
        self.browser, self.root = browser, root
        self.avatars = root / 'avatars'

    def enabled(self):
        try:
            return (self.root / 'profile-enabled').read_text().strip() == '1'
        except OSError:
            return False

    async def read(self):
        data = await self.browser.comments.api('get', 'https://api.bilibili.com/x/member/web/account')
        if data.get('code') != 0:
            raise ValueError('无法读取账号资料，请检查B站登录状态')
        info = data.get('data') or {}
        result = {'nickname': str(info.get('uname') or '')[:40], 'signature': str(info.get('sign') or '')[:100]}
        try:
            nav = await self.browser.comments.api('get', 'https://api.bilibili.com/x/web-interface/nav')
            level = ((nav.get('data') or {}).get('level_info') or {}).get('current_level')
            if isinstance(level, int):
                result['level'] = level
        except Exception:
            pass
        return result

    def candidates(self):
        self.avatars.mkdir(parents=True, exist_ok=True, mode=0o700)
        options = []
        for path in sorted(self.avatars.iterdir()):
            if path.is_symlink() or not path.is_file() or path.suffix.lower() not in ('.png', '.jpg', '.jpeg'):
                continue
            if not re.fullmatch(r'[\w\-\u4e00-\u9fff]{1,60}\.(?:png|jpg|jpeg)', path.name, re.I):
                continue
            if path.stat().st_size > 2 * 1024 * 1024:
                continue
            options.append({'name': path.name})
            if len(options) >= 20: break
        return {'avatars': options, 'notice': '只列出专用头像目录中的图片；没有合适的图片时可自行制作鱼形图标。'}

    def make_avatar(self, colour):
        palette = {'blue': ('#d7f1ff', '#419bdf'), 'pink': ('#ffe5ee', '#ee82aa'),
                   'green': ('#e0f8e8', '#59bd91'), 'purple': ('#efe9ff', '#a78adf')}
        if colour not in palette:
            raise ValueError('颜色请选择 blue、pink、green 或 purple')
        self.avatars.mkdir(parents=True, exist_ok=True, mode=0o700)
        name = 'fish-' + colour + '-' + secrets.token_hex(4) + '.png'
        path = self.avatars / name
        bg, fish = palette[colour]
        image = Image.new('RGB', (512, 512), bg); draw = ImageDraw.Draw(image)
        draw.ellipse((68, 85, 452, 455), fill='#ffffff', outline=fish, width=8)
        draw.polygon(((322, 244), (402, 190), (401, 321), (322, 275)), fill=fish)
        draw.ellipse((122, 180, 350, 326), fill=fish)
        draw.ellipse((165, 218, 188, 241), fill='#182e45')
        draw.arc((154, 235, 201, 270), 15, 125, fill='#182e45', width=5)
        for x, y, size in ((114, 146, 14), (356, 125, 11), (390, 355, 16)):
            draw.ellipse((x-size, y-size, x+size, y+size), outline=fish, width=5)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as output: image.save(output, format='PNG')
        return {'name': name, 'description': colour + ' 色的简洁小鱼图标', 'created': True}

    def avatar_bytes(self, name):
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError('请选择头像候选列表中的图片')
        if name not in [item['name'] for item in self.candidates()['avatars']]:
            raise ValueError('请选择头像候选列表中的图片')
        path = self.avatars / name
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as file:
            if os.fstat(file.fileno()).st_size > 2 * 1024 * 1024: raise ValueError('头像图片过大')
            with Image.open(file) as img:
                if img.width * img.height > 16_000_000: raise ValueError('头像图片尺寸过大')
                image = ImageOps.fit(ImageOps.exif_transpose(img).convert('RGB'), (512, 512))
                output = BytesIO(); image.save(output, 'PNG', optimize=True)
        return output.getvalue()

    def reserve(self, kind):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with closing(sqlite3.connect(self.root / 'profile-actions.sqlite3', timeout=5)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS actions (id INTEGER PRIMARY KEY, at REAL NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL)')
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM actions WHERE kind=? AND at>?', (kind, time.time()-86400)).fetchone():
                raise ValueError('该资料近期刚尝试修改，请明天再试')
            return db.execute('INSERT INTO actions(at,kind,status) VALUES (?,?,?)', (time.time(), kind, 'pending')).lastrowid

    def finish(self, action_id, status):
        with closing(sqlite3.connect(self.root / 'profile-actions.sqlite3', timeout=5)) as db, db:
            db.execute('UPDATE actions SET status=? WHERE id=?', (status, action_id))

    async def update(self, kind, value):
        if not self.enabled():
            raise ValueError('B站资料修改功能尚未启用')
        if kind not in ('nickname', 'signature'):
            raise ValueError('仅支持修改昵称或签名')
        value = str(value or '').strip()
        if not value or len(value) > (16 if kind == 'nickname' else 70):
            raise ValueError('昵称或签名长度无效')
        current = await self.read()
        if current[kind] == value: return {'changed': False, 'notice': '资料已经是这个内容'}
        page = await self.browser.context.new_page()
        action = None
        try:
            await page.goto('https://account.bilibili.com/account/setting', wait_until='domcontentloaded', timeout=40000)
            name = page.get_by_placeholder('你的昵称'); signature = page.locator('textarea.el-textarea__inner')
            await name.wait_for(timeout=25000); await signature.wait_for(timeout=25000)
            # Wait for the account page to populate before altering one field.
            await page.wait_for_function('(expected) => document.querySelector("input[placeholder=你的昵称]")?.value === expected', arg=current['nickname'], timeout=15000)
            if await signature.input_value() != current['signature']:
                raise ValueError('B站页面资料尚未同步，未进行修改')
            if kind == 'nickname' and not await name.is_enabled():
                raise ValueError('B站当前不允许修改昵称')
            await (name if kind == 'nickname' else signature).fill(value)
            action = self.reserve(kind)
            async with page.expect_response(lambda r: '/x/member/web/update' in r.url and r.request.method == 'POST', timeout=20000) as pending:
                await page.get_by_role('button', name='保存', exact=True).click(timeout=10000)
                if kind == 'nickname':
                    await page.wait_for_timeout(700)
                    dialog = page.locator('.common-noimg-box')
                    if await dialog.is_visible():
                        shown = (await dialog.locator('.common-noimg-uname').inner_text()).strip()
                        if shown != value:
                            self.finish(action, 'rejected')
                            raise ValueError('B站确认的昵称与请求不一致，已停止')
                        await dialog.locator('.no-img-btn').click(timeout=10000)
                    elif await page.locator('.bind-tel').is_visible():
                        self.finish(action, 'rejected')
                        raise ValueError('B站要求先绑定或验证手机号')
            result = await (await pending.value).json()
            if result.get('code') != 0 or (result.get('data') or {}).get('code') == 40014:
                self.finish(action, 'rejected')
                raise ValueError('B站未接受资料修改，可能需要验证、硬币或其他操作')
            self.finish(action, 'accepted')
            return {'submitted': True, 'field': kind, 'notice': '已提交；最终显示以B站审核和页面为准。'}
        except ValueError:
            raise
        except Exception:
            if action: self.finish(action, 'unknown')
            raise ValueError('未能确认B站资料修改结果，请先查看资料再决定是否重试')
        finally:
            await page.close()

    async def set_avatar(self, name):
        if not self.enabled():
            raise ValueError('B站资料修改功能尚未启用')
        content = self.avatar_bytes(name)
        page = await self.browser.context.new_page()
        action = None
        try:
            await page.goto('https://account.bilibili.com/account/face/upload', wait_until='domcontentloaded', timeout=40000)
            upload = page.locator('input[type=file]')
            await upload.wait_for(state='attached', timeout=25000)
            await upload.set_input_files({'name': 'avatar.png', 'mimeType': 'image/png', 'buffer': content})
            button = page.locator('input.btn-confirm:not(.disabled)')
            await button.wait_for(state='visible', timeout=20000)
            action = self.reserve('avatar')
            async with page.expect_response(lambda r: '/x/member/web/face/update' in r.url and r.request.method == 'POST', timeout=30000) as pending:
                await button.click(timeout=10000)
            result = await (await pending.value).json()
            if result.get('code') != 0:
                self.finish(action, 'rejected')
                raise ValueError('B站未接受头像，可能需要验证或审核')
            self.finish(action, 'accepted')
            return {'submitted': True, 'avatar': name, 'notice': '已提交；最终显示以B站审核和页面为准。'}
        except ValueError:
            raise
        except Exception:
            if action: self.finish(action, 'unknown')
            raise ValueError('未能确认B站头像修改结果，请先查看头像再决定是否重试')
        finally:
            await page.close()
