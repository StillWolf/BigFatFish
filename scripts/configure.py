#!/usr/bin/env python3
"""Interactive install configuration. Never prints credentials."""
import argparse
import copy
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import shlex
from fish_config import PROJECT, load_config, private_write


def read_env(path):
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if not line.strip() or line.lstrip().startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            parsed = shlex.split(value, comments=True)
            values[key.strip()] = parsed[0] if parsed else ''
    return values


def main():
    parser = argparse.ArgumentParser(description='生成私有安装配置；不发送消息、不登录账号')
    parser.add_argument('--non-interactive', action='store_true')
    parser.add_argument('--config', help='导入配置 JSON；默认复用 data/fish.config.json')
    parser.add_argument('--wechat', action='store_true')
    parser.add_argument('--configure-only', action='store_true')
    args = parser.parse_args()
    target = PROJECT / 'data/fish.config.json'
    source = Path(args.config) if args.config else target if target.exists() else PROJECT / 'config/fish.example.json'
    data = json.loads(source.read_text())
    original = copy.deepcopy(data)
    saved = read_env(PROJECT / '.env')
    values = {**saved, **{k: v for k, v in os.environ.items() if k in ('DEEPSEEK_API_KEY', 'ONEBOT_ACCESS_TOKEN', 'NAPCAT_WEBUI_TOKEN', 'WECHAT_AI_MCP_TOKEN', 'WECHAT_DESKTOP_PASSWORD', 'HF_ENDPOINT')}}

    def ask(label, default=''):
        return input(f'{label}' + (f' [{default}]' if default else '') + ': ').strip() or str(default)

    if not args.non_interactive:
        print('BigFatFish 安装配置（回车保留当前值）')
        data['qq']['account'] = ask('机器人的 QQ 号', data['qq'].get('account', ''))
        data['qq']['family']['gege'] = ask('主人/哥哥的 QQ 号', data['qq']['family'].get('gege', ''))
        data['qq']['family']['jiejie'] = ask('姐姐的 QQ 号，可留空', data['qq']['family'].get('jiejie', ''))
        data['qq']['allowGroups'] = [x.strip() for x in ask('允许聊天的群号，逗号分隔，可留空', ','.join(map(str, data['qq'].get('allowGroups', [])))).split(',') if x.strip()]
        data['qq']['proactiveGroup'] = ask('主动水群的群号，可留空', data['qq'].get('proactiveGroup', ''))
        data['bot']['name'] = ask('日常名字', data['bot'].get('name', '小肥鱼'))
        for feature, label in [('bilibili', '安装 B站浏览器和本地语音识别'), ('wechat', '安装实验性 Linux 微信组件（下载和构建较大）')]:
            default = 'y' if data['features'].get(feature) or (feature == 'wechat' and args.wechat) else 'n'
            data['features'][feature] = ask(label + ' y/n', default).lower() in ('y', 'yes', '是')
        if not values.get('DEEPSEEK_API_KEY'):
            values['DEEPSEEK_API_KEY'] = getpass.getpass('DeepSeek API Key（隐藏输入）: ').strip()
        else:
            replacement = getpass.getpass('DeepSeek API Key 已保存，回车保留或输入新 Key: ').strip()
            if replacement:
                values['DEEPSEEK_API_KEY'] = replacement
    if args.wechat:
        data['features']['wechat'] = True
    if not values.get('DEEPSEEK_API_KEY'):
        raise ValueError('缺少 DEEPSEEK_API_KEY；非交互安装请通过环境变量传入')
    for key in ['ONEBOT_ACCESS_TOKEN', 'NAPCAT_WEBUI_TOKEN', 'WECHAT_AI_MCP_TOKEN', 'WECHAT_DESKTOP_PASSWORD']:
        if not values.get(key) or values[key] in ('change-me-to-a-random-string', 'replace-me'):
            values[key] = secrets.token_urlsafe(32)
    defaults = {'NAPCAT_IMAGE': 'mlikiowa/napcat-docker:latest', 'FISH_WEB_PORT': '3080', 'NAPCAT_WEB_PORT': '6099',
                'BILIBILI_WEB_PORT': '6082', 'WECHAT_WEB_PORT': '6081', 'FISH_ASR_MODEL': 'small', 'HF_ENDPOINT': 'https://huggingface.co'}
    for key, default in defaults.items():
        values.setdefault(key, default)
    values['ACCOUNT'] = str(data['qq']['account'])
    values['FISH_INSTALL_BILIBILI'] = '1' if data['features'].get('bilibili') else '0'
    values['COMPOSE_PROFILES'] = 'wechat' if data['features'].get('wechat') else ''
    for key in ['FISH_WEB_PORT', 'NAPCAT_WEB_PORT', 'BILIBILI_WEB_PORT', 'WECHAT_WEB_PORT']:
        if not values[key].isdigit() or not 1024 <= int(values[key]) <= 65535:
            raise ValueError(f'{key} 需要1024—65535之间的端口')
    data['bot']['mentionNames'] = sorted(set([data['bot']['name'], data['bot'].get('realName', ''), *data['bot'].get('mentionNames', [])]) - {''})
    # Validate before replacing the private active config.
    temporary = PROJECT / 'data/install-config.pending.json'
    private_write(temporary, data)
    try:
        load_config(temporary)
    finally:
        temporary.unlink(missing_ok=True)
    if target.exists() and original != data:
        private_write(target.with_suffix('.json.bak'), target.read_text())
    private_write(target, data)
    entries = []
    for key, value in values.items():
        if key not in set(defaults) | {'DEEPSEEK_API_KEY', 'ONEBOT_ACCESS_TOKEN', 'NAPCAT_WEBUI_TOKEN', 'WECHAT_AI_MCP_TOKEN', 'WECHAT_DESKTOP_PASSWORD', 'ACCOUNT', 'COMPOSE_PROFILES', 'FISH_INSTALL_BILIBILI'}:
            continue
        # Compose dotenv single quotes preserve literal $, # and spaces.
        if any(c in str(value) for c in "'\n\r\x00"):
            raise ValueError(f'{key} 含不支持的换行或单引号')
        entries.append(key + "='" + str(value) + "'")
    private_write(PROJECT / '.env', '\n'.join(entries) + '\n')
    print('配置已保存到 .env 与 data/fish.config.json；未输出任何密钥')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        raise SystemExit(str(error))
