#!/usr/bin/env python3
"""Offline checks for private config generation and upgrade preservation."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='fish-config-check-')
        self.root = Path(self.tmp.name)
        (self.root / 'config').mkdir()
        shutil.copy2(SOURCE / 'config/persona.md', self.root / 'config/persona.md')
        for name in ('dsh-qq-onebot-bridge', 'dsh-wechat-ai-bridge'):
            (self.root / name).mkdir()
        self.home = self.root / 'private-dsh'
        self.napcat = self.root / 'private-napcat'
        self.env = patch.dict(os.environ, {
            'FISH_PROJECT_ROOT': str(self.root), 'DSH_HOME': str(self.home), 'FISH_NAPCAT_CONFIG': str(self.napcat),
            'DEEPSEEK_API_KEY': 'sk-synthetic-only', 'ONEBOT_ACCESS_TOKEN': 'synthetic-onebot-token',
            'NAPCAT_WEBUI_TOKEN': 'synthetic-webui-token', 'WECHAT_AI_MCP_TOKEN': 'synthetic-wechat-token',
        })
        self.env.start()
        spec = importlib.util.spec_from_file_location('fish_config_isolated', SOURCE / 'scripts/fish_config.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.data = json.loads((SOURCE / 'config/fish.example.json').read_text())
        self.data['qq'].update(account='100000001', family={'gege': '100000002', 'jiejie': ''},
                               allowGroups=['100000003'], proactiveGroup='100000003')
        self.profile = self.home / 'profiles/web/cordis.patch.yml'
        self.package = self.home / 'profiles/web/package.json'

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def rows(self):
        import yaml
        return yaml.safe_load(self.profile.read_text())

    def test_first_install_and_restart_preserve_unmanaged_settings(self):
        import yaml
        self.module.render_runtime(self.data)
        rows = self.rows()
        qq = next(row['config'] for row in rows if row['id'] == 'dsh-qq-onebot-bridge')
        self.assertEqual(qq['allowUsers'], [100000002])
        self.assertEqual(qq['allowGroups'], [100000003])
        self.assertEqual(self.profile.stat().st_mode & 0o777, 0o600)
        qq['maxMessageLength'] = 777
        qq['qqBashEnabled'] = False
        rows.append({'id': 'my-custom-plugin', 'config': {'keep': True}})
        original_yaml = '# local UI preferences\n' + yaml.safe_dump(rows, allow_unicode=True, sort_keys=False)
        self.profile.write_text(original_yaml)
        pkg = json.loads(self.package.read_text())
        pkg['dsh']['profile']['bundles'].append('my-custom-bundle')
        self.package.write_text(json.dumps(pkg))
        nap = self.napcat / 'onebot11_100000001.json'
        nap_data = json.loads(nap.read_text())
        nap_data['customOwnerSetting'] = 'keep'
        nap_data['network']['websocketClients'].append({'name': 'other-service', 'url': 'ws://127.0.0.1:11223'})
        nap.write_text(json.dumps(nap_data))
        self.module.render_runtime(self.data)
        self.assertEqual(self.profile.read_text(), original_yaml)
        saved = self.rows()
        preserved = next(row['config'] for row in saved if row['id'] == 'dsh-qq-onebot-bridge')
        self.assertEqual(preserved['maxMessageLength'], 777)
        self.assertIs(preserved['qqBashEnabled'], False)
        self.assertTrue(any(row['id'] == 'my-custom-plugin' for row in saved))
        self.assertIn('my-custom-bundle', json.loads(self.package.read_text())['dsh']['profile']['bundles'])
        saved_nap = json.loads(nap.read_text())
        self.assertEqual(saved_nap['customOwnerSetting'], 'keep')
        self.assertTrue(any(item.get('name') == 'other-service' for item in saved_nap['network']['websocketClients']))
        self.assertEqual(os.environ['FISH_DIARY_FAMILY_QQ'], '100000002')
        self.assertFalse((self.root / 'data' / 'dsh' / 'private/fish-private-diary').exists())

        self.data['qq']['family']['gege'] = '100000005'
        os.environ['ONEBOT_ACCESS_TOKEN'] = 'another-synthetic-onebot-token'
        self.module.render_runtime(self.data)
        changed = next(row['config'] for row in self.rows() if row['id'] == 'dsh-qq-onebot-bridge')
        self.assertEqual(changed['allowUsers'], [100000005])
        self.assertEqual(changed['maxMessageLength'], 777)
        self.assertEqual(changed['accessToken'], 'another-synthetic-onebot-token')
        self.assertIn('100000005 = 哥哥', (self.root / 'data/qq-bridge/AGENTS.md').read_text())
        self.assertTrue(self.profile.with_name(self.profile.name + '.bak').exists())
        self.assertTrue(nap.with_name(nap.name + '.bak').exists())
        self.assertEqual(json.loads(nap.read_text())['customOwnerSetting'], 'keep')

    def test_wechat_toggle_restores_nonmanaged_preferences(self):
        self.data['features']['wechat'] = True
        self.module.render_runtime(self.data)
        rows = self.rows()
        wechat = next(row for row in rows if row['id'] == 'wechat-ai-bridge')
        wechat['config']['pollIntervalMs'] = 7000
        wechat['config']['reply']['maxRepliesPerMinute'] = 2
        self.profile.write_text(json.dumps(rows))
        self.data['features']['wechat'] = False
        self.module.render_runtime(self.data)
        self.assertFalse(any(row['id'] == 'wechat-ai-bridge' for row in self.rows()))
        self.assertNotIn('dsh-wechat-ai-bridge', json.loads(self.package.read_text())['dsh']['profile']['bundles'])
        self.data['features']['wechat'] = True
        self.module.render_runtime(self.data)
        saved = next(row['config'] for row in self.rows() if row['id'] == 'wechat-ai-bridge')
        self.assertEqual(saved['pollIntervalMs'], 7000)
        self.assertEqual(saved['reply']['maxRepliesPerMinute'], 2)

    def test_invalid_napcat_config_is_not_overwritten(self):
        self.napcat.mkdir(parents=True)
        damaged = self.napcat / 'onebot11.json'
        damaged.write_text('{unparseable')
        with self.assertRaises(ValueError):
            self.module.render_runtime(self.data)
        self.assertEqual(damaged.read_text(), '{unparseable')

    def test_xiaohongshu_installs_browser_dependencies_without_bilibili(self):
        self.data['features']['bilibili'] = False
        self.data['features']['xiaohongshu'] = True
        source = self.root / 'config/input.json'
        source.write_text(json.dumps(self.data))
        subprocess.run([sys.executable, str(SOURCE / 'scripts/configure.py'), '--non-interactive', '--config', str(source)],
                       check=True, capture_output=True, text=True)
        env = (self.root / '.env').read_text()
        self.assertIn("FISH_INSTALL_BILIBILI='1'", env)
        self.assertIn("XIAOHONGSHU_WEB_PORT='6083'", env)

    def test_install_entrypoint_configure_only_is_offline(self):
        shutil.copy2(SOURCE / 'install.sh', self.root / 'install.sh')
        (self.root / 'scripts').mkdir()
        for name in ('configure.py','fish_config.py'):
            shutil.copy2(SOURCE / 'scripts' / name, self.root / 'scripts' / name)
        source = self.root / 'config/input.json';source.write_text(json.dumps(self.data))
        subprocess.run(['bash', str(self.root/'install.sh'), '--non-interactive', '--config', str(source), '--configure-only'],
                       cwd=self.root, check=True, capture_output=True, text=True)
        self.assertTrue((self.root/'.env').is_file())
        self.assertTrue((self.root/'data/fish.config.json').is_file())
        self.assertEqual((self.root/'.env').stat().st_mode & 0o777, 0o600)

    def test_explicit_web_bind_does_not_require_dns(self):
        spec = importlib.util.spec_from_file_location('fish_runtime_test', SOURCE / 'scripts/runtime.py')
        runtime = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'fish_config': self.module}):
            spec.loader.exec_module(runtime)
        with patch.dict(os.environ, {'FISH_WEB_BIND': '127.0.0.1'}), \
             patch.object(runtime.socket, 'gethostbyname', side_effect=AssertionError('unexpected DNS lookup')):
            self.assertEqual(runtime.web_bind(), '127.0.0.1')


if __name__ == '__main__':
    unittest.main(verbosity=2)
