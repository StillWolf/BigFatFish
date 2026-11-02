import importlib.util
import os
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/proactive-daemon.py'


class XhsScheduleTests(unittest.TestCase):
    def test_guest_activity_is_opt_in_and_respects_component_switch(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'FISH_PROJECT_ROOT': tmp, 'FISH_XHS_ROOT': str(Path(tmp) / 'data/xiaohongshu')}, clear=False):
            spec = importlib.util.spec_from_file_location('xhs_schedule_test', SOURCE)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            root = Path(tmp) / 'data/xiaohongshu'; root.mkdir(parents=True)
            def includes_xhs():
                return any(event[1] == 'activity' and event[4].get('hint') == '小红书'
                           for event in module.build_schedule(date(2026, 11, 2)))
            self.assertFalse(includes_xhs())
            (root / 'activity-enabled').write_text('1')
            with patch.dict(os.environ, {'FISH_XHS_ENABLED': '1'}):
                self.assertTrue(includes_xhs())
            with patch.dict(os.environ, {'FISH_XHS_ENABLED': '0'}):
                self.assertFalse(includes_xhs())


if __name__ == '__main__': unittest.main()
