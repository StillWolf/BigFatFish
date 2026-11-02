import importlib.util
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/proactive-daemon.py'


class ScheduleRetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'FISH_PROJECT_ROOT': self.tmp.name, 'FISH_CONFIG': str(Path(self.tmp.name) / 'missing.json')})
        self.env.start()
        spec = importlib.util.spec_from_file_location('schedule_retry_test', SOURCE)
        self.m = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.m)
        self.now = datetime(2026, 11, 2, 12, 0, tzinfo=self.m.TZ)
        self.day = self.now.date()
        self.event = (self.now, 'meal', 'gege', 'meal:lunch', {'label': '午餐'})
        self.key = f'{self.day}:meal:lunch'

    def tearDown(self): self.env.stop(); self.tmp.cleanup()

    def test_definite_failure_is_persisted_and_retried_with_backoff(self):
        fired, pending, calls = set(), {}, []
        def fire(*_args):
            calls.append(1); return len(calls) > 1
        remaining = self.m.process_due_events([self.event], self.day, fired, pending, self.now, fire)
        self.assertNotIn(self.key, fired); self.assertEqual(pending[self.key]['status'], 'retry')
        self.assertEqual(self.m.load_pending()[self.key]['attempts'], 1)
        remaining = self.m.process_due_events(remaining, self.day, fired, pending, self.now + timedelta(seconds=10), fire)
        self.assertEqual(len(calls), 1)
        remaining = self.m.process_due_events(remaining, self.day, fired, pending, self.now + timedelta(seconds=31), fire)
        self.assertEqual(remaining, []); self.assertIn(self.key, fired); self.assertNotIn(self.key, pending)

    def test_uncertain_write_is_not_retried(self):
        fired, pending = set(), {}
        result = self.m.process_due_events([self.event], self.day, fired, pending, self.now, lambda *_: None)
        self.assertEqual(result, []); self.assertIn(self.key, fired)
        self.assertEqual(self.m.load_pending()[self.key]['status'], 'uncertain')

    def test_pending_event_is_recovered_without_randomized_replacement(self):
        pending = {self.key: {'status':'retry', 'scheduledAt':self.now.isoformat(), 'kind':'meal',
            'target':'gege', 'eventId':'meal:lunch', 'metadata':{'label':'午餐'}, 'nextRetryAt':0}}
        regenerated = [(self.now + timedelta(minutes=4), 'meal', 'gege', 'meal:lunch', {'label':'different'})]
        events = self.m.recover_pending(regenerated, self.day, set(), pending)
        self.assertEqual(events, [self.event])
        kept = self.m.skip_missed_events(events, self.day, set(), self.now + timedelta(minutes=7), pending)
        self.assertEqual(kept, [self.event])

    def test_bridge_must_be_fresh_and_online_for_proactive_chat(self):
        p = Path(self.m.QQ_RUNTIME_FILE); p.parent.mkdir(parents=True)
        with patch.object(self.m.time, 'time', return_value=1000):
            p.write_text(json.dumps({'pid':os.getpid(),'updatedAt':1000000,'injection':{'enabled':True},'botOnline':False}))
            self.assertTrue(self.m.bridge_available()); self.assertFalse(self.m.bridge_available(require_online=True))
            p.write_text(json.dumps({'pid':os.getpid(),'updatedAt':1000000,'injection':{'enabled':True},'botOnline':True}))
            self.assertTrue(self.m.bridge_available(require_online=True))
            p.write_text(json.dumps({'pid':os.getpid(),'updatedAt':700000,'injection':{'enabled':True},'botOnline':True}))
            self.assertFalse(self.m.bridge_available())

    def test_append_failure_after_open_is_uncertain(self):
        target = str(Path(self.tmp.name)/'inject.jsonl')
        with patch.object(self.m.os, 'fsync', side_effect=OSError('synthetic')):
            self.assertIsNone(self.m.append_injection({'kind':'activity'}, target))
        self.assertTrue(Path(target).exists())

    def test_interrupted_write_is_not_replayed(self):
        fired = set(); pending = {self.key: {'status':'writing','attempts':1}}
        def fail_if_called(*_): self.fail('uncertain write must not be retried')
        remaining = self.m.process_due_events([self.event], self.day, fired, pending, self.now, fail_if_called)
        self.assertEqual(remaining, []); self.assertIn(self.key, fired)
        self.assertEqual(pending[self.key]['status'], 'uncertain')

    def test_online_activity_is_not_retried_during_sleep(self):
        now = self.now.replace(hour=23, minute=2)
        event = (now - timedelta(minutes=3), 'activity', 'gege', 'activity:22', {'hint':'小红书'})
        fired, pending = set(), {}
        def fail_if_called(*_): self.fail('sleep-time activity must not run')
        remaining = self.m.process_due_events([event], self.day, fired, pending, now, fail_if_called)
        self.assertEqual(remaining, []); self.assertIn(f'{self.day}:activity:22', fired)

    def test_wechat_mirror_is_sent_once_when_qq_recovers(self):
        self.m.TARGETS['gege'] = {'user_id': 'synthetic', 'sender_name': 'test', 'label': '哥哥'}
        event = (self.now, 'chat', 'gege', 'chat:u:12', {})
        fired, pending = set(), {}
        with patch.object(self.m, 'bridge_available', side_effect=[False, True]), \
             patch.object(self.m, 'append_injection', return_value=True) as append, \
             patch.object(self.m, 'mirror_wechat_chat') as mirror:
            remaining = self.m.process_due_events([event], self.day, fired, pending, self.now)
            self.assertEqual(mirror.call_count, 1)
            self.m.process_due_events(remaining, self.day, fired, pending, self.now + timedelta(seconds=31))
            self.assertEqual(mirror.call_count, 1)
            self.assertEqual(append.call_count, 1)


if __name__ == '__main__': unittest.main()
