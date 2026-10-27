#!/usr/bin/env python3
import argparse
from configure import read_env
from fish_config import PROJECT

p = argparse.ArgumentParser(description='访问入口；仅显式 --show-secrets 时显示本地管理密码')
p.add_argument('--show-secrets', action='store_true')
args = p.parse_args()
e = read_env(PROJECT / '.env')
for label, key, default, suffix in [('DSH 管理', 'FISH_WEB_PORT', '3080', '/'), ('QQ 登录', 'NAPCAT_WEB_PORT', '6099', '/webui'), ('B站桌面', 'BILIBILI_WEB_PORT', '6082', '/'), ('微信桌面（选装）', 'WECHAT_WEB_PORT', '6081', '/')]:
    print(f'{label}: http://127.0.0.1:{e.get(key, default)}{suffix}')
if args.show_secrets:
    for name in ['NAPCAT_WEBUI_TOKEN', 'WECHAT_DESKTOP_PASSWORD']:
        print(name + '=' + e.get(name, '未设置'))
else:
    print('管理网页密码保存在 .env；本机执行 bash fishctl access --show-secrets 查看。')
