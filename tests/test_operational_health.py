import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import operational_health as health
from usage_stats import record_usage, summarize_usage

spec = importlib.util.spec_from_file_location('fish_monitor_test', Path(__file__).resolve().parents[1] / 'scripts/fish-monitor.py')
monitor = importlib.util.module_from_spec(spec); spec.loader.exec_module(monitor)


class OperationalHealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);health._ACCOUNT_CACHE.clear()
    def tearDown(self): self.tmp.cleanup()

    def test_usage_records_only_numeric_metadata(self):
        self.assertTrue(record_usage(self.root,'xiaohongshu',{'prompt_tokens':12,'completion_tokens':3,'total_tokens':15,
            'prompt':'private note','token':'private credential'}))
        files=list((self.root/'data/usage').glob('*.jsonl'));self.assertEqual(len(files),1)
        text=files[0].read_text();self.assertNotIn('private',text)
        result=summarize_usage(self.root);self.assertEqual(result['sources']['xiaohongshu']['total_tokens'],15)
        self.assertEqual(result['sources']['xiaohongshu']['calls'],1)
        self.assertFalse(record_usage(self.root,'other',{'total_tokens':10}))

    def test_status_does_not_return_browsing_content_or_credentials(self):
        q=self.root/'data/qq-bridge';q.mkdir(parents=True)
        (q/'qq-runtime.json').write_text(json.dumps({'pid':os.getpid(),'updatedAt':1_700_000_000_000,'botOnline':True,
            'outbox':{'chatsPending':0},'activity':{},'sessions':[{'text':'private chat'}]}))
        bili=self.root/'data/bilibili';bili.mkdir(parents=True)
        (bili/'runtime.env').write_text('BILIBILI_TOKEN=synthetic-secret\n')
        (bili/'runtime.json').write_text(json.dumps({'pid':os.getpid(),'updatedAt':1_700_000_000}))
        def request(_port,path='/health',token='',timeout=3):
            if path=='/api/status': return {'loggedIn':True,'socialAvailable':True,'socialMonitor':{'healthy':True,'lastCheck':1_700_000_000},'lastWatch':{'summary':'private content'}}
            return {'ready':True,'ok':True}
        with patch.object(health,'request_json',side_effect=request),patch.object(health,'alive',return_value=True):
            value=health.collect(self.root,features={'bilibili':True,'xiaohongshu':False},now=1_700_000_000)
        self.assertEqual(value['qq']['state'],'online');self.assertTrue(value['bilibili']['loggedIn'])
        raw=json.dumps(value);self.assertNotIn('private',raw);self.assertNotIn('synthetic-secret',raw)

    def test_watchdog_waits_and_does_not_restart_offline_login(self):
        c=monitor.RetryController(cooldown=300)
        self.assertFalse(c.should_restart('dsh',True,100))
        self.assertTrue(c.should_restart('dsh',True,130))
        self.assertFalse(c.should_restart('dsh',True,160))
        self.assertFalse(c.should_restart('dsh',False,190))
        with patch.object(monitor,'port_open',return_value=False), patch.object(monitor,'dsh_process_exists',return_value=False):
            self.assertFalse(monitor.restart_absent('dsh',{'qq':{'state':'offline'}}))
            self.assertTrue(monitor.restart_absent('dsh',{'qq':{'state':'down'}}))

    def test_watchdog_does_not_restart_an_existing_process(self):
        with patch.object(monitor,'process_exists',return_value=True):
            self.assertFalse(monitor.restart_absent('activities',{'activities':{'running':False}}))
        with patch.object(monitor,'dsh_process_exists',return_value=True), patch.object(monitor,'port_open',return_value=False):
            self.assertFalse(monitor.restart_absent('dsh',{'qq':{'state':'down'}}))


if __name__=='__main__':unittest.main()
