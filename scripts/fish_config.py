"""Shared configuration and private runtime rendering."""
import json
import os
from pathlib import Path
import re

PROJECT = Path(os.environ.get('FISH_PROJECT_ROOT', Path(__file__).resolve().parents[1])).resolve()


def load_config(path=None):
    path = Path(path or os.environ.get('FISH_CONFIG', PROJECT / 'data/fish.config.json'))
    data = json.loads(path.read_text())
    qq = data.get('qq', {})
    for value in [qq.get('account'), *qq.get('family', {}).values(), *qq.get('allowUsers', []), *qq.get('allowGroups', []), *[f.get('qq') for f in qq.get('friends', [])], qq.get('proactiveGroup')]:
        if value not in ('', None) and not re.fullmatch(r'[1-9][0-9]{4,11}', str(value)):
            raise ValueError('QQ 账号或群号应为5—12位数字')
    if not qq.get('account'):
        raise ValueError('请配置 qq.account，即机器人的 QQ 号')
    if not any(qq.get('family', {}).values()) and not qq.get('allowUsers'):
        raise ValueError('至少配置一名家人或允许聊天的 QQ 用户')
    group = str(qq.get('proactiveGroup') or '')
    if group and group not in [str(x) for x in qq.get('allowGroups', [])]:
        raise ValueError('主动水群目标必须先加入 allowGroups')
    return data


def private_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    os.replace(temporary, path)
    path.chmod(0o600)


def update_private(path, value):
    """Avoid needless rewrites and keep the previous private file before changes."""
    path = Path(path)
    encoded = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if path.exists():
        old = path.read_text()
        if old == encoded:
            return
        private_write(path.with_name(path.name + '.bak'), old)
    private_write(path, encoded)


def read_profile_rows(path):
    if not path.exists():
        return []
    text = path.read_text()
    try:
        rows = json.loads(text)
    except ValueError:
        try:
            import yaml
            rows = yaml.safe_load(text)
        except Exception as error:
            raise ValueError('DSH profile YAML 无法安全读取；请修复该文件后重试') from error
    if not isinstance(rows, list):
        raise ValueError('DSH profile 必须是列表，原配置已保留')
    return rows


def merge_profile(path, defaults, app, wechat_enabled):
    old = read_profile_rows(path)
    # Copy before mutation so equality can avoid rewriting a user's YAML formatting.
    rows = json.loads(json.dumps(old, ensure_ascii=False))
    stash = app / 'wechat-bridge/disabled-profile.json'
    if not wechat_enabled:
        previous = [row for row in rows if isinstance(row, dict) and row.get('id') == 'wechat-ai-bridge']
        if previous:
            update_private(stash, previous[-1])
            rows = [row for row in rows if not (isinstance(row, dict) and row.get('id') == 'wechat-ai-bridge')]
    elif stash.exists() and not any(isinstance(row, dict) and row.get('id') == 'wechat-ai-bridge' for row in rows):
        saved = json.loads(stash.read_text())
        if isinstance(saved, dict) and saved.get('id') == 'wechat-ai-bridge':
            rows.append(saved)
    managed = {
        'agent-default-model': {'provider', 'model'},
        'dsh-qq-onebot-bridge': {'cwd', 'port', 'accessToken', 'botQq', 'botName', 'mentionAliases',
                                 'allowUsers', 'allowGroups', 'ttsApiKey', 'ttsVoice', 'ttsEnabled'},
        'wechat-ai-bridge': {'mcpUrl', 'tokenEnv', 'tokenFile', 'workspacePath', 'statePath', 'logPath', 'mentionNames', 'fish'},
    }
    for default in defaults:
        row_id = default['id']
        existing = next((row for row in reversed(rows) if isinstance(row, dict) and row.get('id') == row_id), None)
        if existing is None:
            rows.append(default)
            continue
        if row_id == 'agent-instructions':
            existing['disabled'] = False
        config = existing.setdefault('config', {})
        if not isinstance(config, dict):
            raise ValueError(f'DSH profile 的 {row_id} 配置不是对象，原配置已保留')
        for key, value in default.get('config', {}).items():
            if key in managed.get(row_id, set()) or key not in config:
                config[key] = value
    if rows != old:
        update_private(path, rows)


def merge_napcat(path, defaults):
    if not path.exists():
        private_write(path, defaults)
        return
    try:
        old = json.loads(path.read_text())
        if not isinstance(old, dict) or not isinstance(old.get('network', {}), dict):
            raise ValueError('invalid network config')
    except (ValueError, OSError) as error:
        raise ValueError(f'无法读取 NapCat 配置 {path.name}；原配置已保留') from error
    merged = json.loads(json.dumps(old))
    network = merged.setdefault('network', {})
    for field, fresh in defaults['network'].items():
        if field not in ('httpServers', 'websocketClients'):
            network.setdefault(field, fresh)
            continue
        items = network.setdefault(field, [])
        if not isinstance(items, list):
            raise ValueError(f'NapCat 的 {field} 不是列表，原配置已保留')
        required = fresh[0]
        existing = next((item for item in items if isinstance(item, dict) and item.get('name') == required['name']), None)
        if existing is None:
            key = 'url' if field == 'websocketClients' else 'port'
            existing = next((item for item in items if isinstance(item, dict) and item.get(key) == required[key]), None)
        if existing is None:
            items.append(required)
        else:
            existing.update(required)
    for key, value in defaults.items():
        if key != 'network':
            merged.setdefault(key, value)
    if merged != old:
        update_private(path, merged)


def merge_package(path, bundles, wechat_enabled):
    if path.exists():
        try:
            old = json.loads(path.read_text())
        except (ValueError, OSError) as error:
            raise ValueError('DSH profile package.json 无法读取；原配置已保留') from error
        if not isinstance(old, dict):
            raise ValueError('DSH profile package.json 不是对象，原配置已保留')
    else:
        old = {'name': 'bigfatfish-profile', 'private': True}
    package = json.loads(json.dumps(old))
    profile = package.setdefault('dsh', {}).setdefault('profile', {})
    prior = profile.get('bundles', [])
    if not isinstance(prior, list):
        raise ValueError('DSH profile bundles 不是列表，原配置已保留')
    result = list(prior)
    for i, name in enumerate(bundles):
        if name not in result:
            if name in ('@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app'):
                result.insert(min(i, len(result)), name)
            else:
                result.append(name)
    if not wechat_enabled:
        result = [name for name in result if name != 'dsh-wechat-ai-bridge']
    profile['bundles'] = result
    if not path.exists() or package != old:
        update_private(path, package)


def render_runtime(data):
    root = PROJECT
    app = root / 'data'
    home = Path(os.environ.get('DSH_HOME', app / 'dsh'))
    profile = home / 'profiles/web'
    qq = data['qq']
    family = {k: int(v) for k, v in qq.get('family', {}).items() if v}
    env = os.environ
    token = env.get('ONEBOT_ACCESS_TOKEN', '')
    if not token or not env.get('DEEPSEEK_API_KEY'):
        raise ValueError('缺少 API Key 或本地 OneBot token，请先运行 install.sh')
    os.environ['FISH_DIARY_FAMILY_QQ'] = ','.join(str(v) for v in family.values())
    workspace = app / 'qq-bridge'
    names = data.get('bot', {})
    template = (root / 'config/persona.md').read_text()
    family_lines = [f'- **{v} = {"哥哥" if k == "gege" else "姐姐"}**：按桥提供的准确 QQ 号识别家人。' for k, v in family.items()]
    friends = qq.get('friends', [])
    friend_lines = [f'- **{int(row["qq"])} = {str(row.get("name", "群友"))[:40]}**：普通群友，没有家人或管理员权限。' for row in friends]
    for key, value in {'BOT_NAME': names.get('name', '小肥鱼'), 'BOT_REAL_NAME': names.get('realName', '秦小鱼'),
                       'QQ_WORKSPACE': str(workspace), 'FAMILY_SECTION': '\n'.join(family_lines) or '尚未绑定家人，不按昵称识别。',
                       'FRIENDS_SECTION': '\n'.join(friend_lines) or '其他人均按普通群友相处。'}.items():
        template = template.replace('{{' + key + '}}', value)
    update_private(workspace / 'AGENTS.md', template)
    bindings = app / 'wechat-bridge/bindings.json'
    if not bindings.exists():
        private_write(bindings, {'enabled': False, 'contacts': [], 'groups': [], 'roles': {}, 'targets': {}})
    # Resolve plugins directly from this image/source checkout, without runtime downloads.
    profile.mkdir(parents=True, exist_ok=True, mode=0o700)
    (profile / 'node_modules').mkdir(exist_ok=True)
    bundles = ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app', 'dsh-qq-onebot-bridge']
    if data['features'].get('wechat'):
        bundles.append('dsh-wechat-ai-bridge')
    for name in ['dsh-qq-onebot-bridge', 'dsh-wechat-ai-bridge']:
        link = profile / 'node_modules' / name
        if not link.exists():
            link.symlink_to(root / name, target_is_directory=True)
    merge_package(profile / 'package.json', bundles, bool(data['features'].get('wechat')))
    users = sorted(set(int(v) for v in [*qq.get('allowUsers', []), *family.values(), *[f['qq'] for f in friends]] if v))
    bridge = {'cwd': str(workspace), 'port': 6700, 'accessToken': token, 'botQq': int(qq['account']),
              'botName': names.get('name', '小肥鱼'), 'mentionAliases': names.get('mentionNames', []), 'allowUsers': users,
              'allowGroups': [int(x) for x in qq.get('allowGroups', [])], 'allowAllChats': False,
              'acceptPrivate': True, 'replyOnlyWhenMentioned': False, 'sessionMode': 'chat',
              'quietHoursEnabled': False, 'chatTurnLimitEnabled': True, 'chatTurnsPerMinute': 10,
              'rateLimitEnabled': True, 'rateLimitWindowSeconds': 60, 'rateLimitMaxReplies': 3,
              'faceEnabled': True, 'qqBashEnabled': True, 'agentMediaToolsEnabled': True,
              'visionMode': 'tool', 'visionToolName': 'describe_image', 'memoryEnabled': True,
              'injectEnabled': True, 'injectDryRun': True, 'injectIntervalMs': 2000,
              'ttsEnabled': bool(data.get('speech', {}).get('autoReply')), 'ttsProvider': 'openai',
              'ttsBaseUrl': 'http://127.0.0.1:9880/v1', 'ttsApiKey': token if data['features'].get('tts') else '',
              'ttsModel': 'edge-tts', 'ttsVoice': data.get('speech', {}).get('voice', 'zh-CN-XiaoyiNeural'),
              'sttEnabled': False, 'forwardLongReplies': False}
    patch = [{'id': 'agent-instructions', 'disabled': False, 'config': {'maxBytes': 65536}},
             {'id': 'dsh-qq-onebot-bridge', 'config': bridge},
             {'id': 'permission', 'config': {'defaultPreset': 'danger-full-access', 'presets': {
                 'danger-full-access': {'sandbox': 'danger-full-access', 'approval': 'never'},
                 'read-only': {'sandbox': 'read-only', 'approval': 'never'}}}},
             {'id': 'agent-default-model', 'config': {'provider': 'deepseek-official', 'model': data.get('model', 'deepseek-flash')}}]
    if data['features'].get('wechat'):
        patch.append({'id': 'wechat-ai-bridge', 'config': {
            'mcpUrl': env.get('FISH_WECHAT_MCP_URL', 'http://wechat:8000/mcp'),
            'tokenEnv': 'WECHAT_AI_MCP_TOKEN', 'tokenFile': str(app / 'wechat-runtime/runtime.env'),
            'workspacePath': str(app / 'wechat-bridge/workspaces'), 'statePath': str(app / 'wechat-bridge/state.json'),
            'logPath': str(app / 'logs/wechat-bridge.log'), 'agentPreset': 'fish-wechat', 'permissionPreset': 'read-only',
            'workspaceMode': 'per-chat', 'pollIntervalMs': 2500, 'workspaceTools': False, 'turnTimeoutMs': 240000,
            'mentionNames': names.get('mentionNames', []),
            'toolAllowlist': ['web_search', 'web_fetch', 'wechat_recent_messages', 'fish_read_activity', 'fish_list_files', 'fish_read_file', 'wechat_send_image', 'wechat_say'],
            'fish': {'enabled': True, 'personaFile': str(workspace / 'AGENTS.md'), 'activityLog': str(workspace / 'activity-log.jsonl'),
                     'bindingsFile': str(bindings), 'injectFile': str(app / 'wechat-bridge/inject.jsonl'),
                     'cursorFile': str(app / 'wechat-bridge/inject-cursor.json')},
            'reply': {'private': True, 'groupMention': True, 'groupAll': True, 'maxRepliesPerMinute': 3, 'workingNoticeMs': 0}}})
    merge_profile(profile / 'cordis.patch.yml', patch, app, bool(data['features'].get('wechat')))  # JSON is a YAML subset.
    napcat = Path(env.get('FISH_NAPCAT_CONFIG', root / 'data/napcat-config'))
    ws = {'enable': True, 'name': 'fish', 'url': 'ws://127.0.0.1:6700', 'token': token,
          'messagePostFormat': 'array', 'reportSelfMessage': False, 'debug': False,
          'heartInterval': 30000, 'reconnectInterval': 3000}
    http = {'enable': True, 'name': 'fish-local', 'host': '127.0.0.1', 'port': 3000, 'token': token, 'enableCors': False, 'enableWebsocket': False}
    onebot = {'network': {'httpServers': [http], 'httpSseServers': [], 'httpClients': [], 'websocketServers': [], 'websocketClients': [ws], 'plugins': []},
              'musicSignUrl': '', 'enableLocalFile2Url': False, 'parseMultMsg': False}
    merge_napcat(napcat / 'onebot11.json', onebot)
    merge_napcat(napcat / f'onebot11_{qq["account"]}.json', onebot)
    if not (napcat / 'webui.json').exists():
        private_write(napcat / 'webui.json', {'host': '0.0.0.0', 'port': 6099, 'prefix': '', 'token': env['NAPCAT_WEBUI_TOKEN'], 'loginRate': 3})
    update_private(app / 'wechat-runtime/runtime.env', 'WECHAT_AI_MCP_TOKEN=' + env.get('WECHAT_AI_MCP_TOKEN', '') + '\n')
    return workspace
