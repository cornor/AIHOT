import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import collector


class ScheduleTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'schedule.json'
        self.event = Path(temp.name) / 'event.json'
        self.env = patch.dict(os.environ, {'COLLECT_ENABLED': 'true', 'WERSS_AUTH_EVENT_FILE': str(self.event)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.clock = patch.object(collector.time, 'time', return_value=100000)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.cycle = patch.object(collector, 'cycle', return_value=True)
        self.run = self.cycle.start()
        self.addCleanup(self.cycle.stop)
        self.schedule = collector.Schedule(self.path)
        self.notices = Mock()
        collector.stop.clear()

    def scan(self, value='scan-1'):
        self.event.write_text(json.dumps({'id': value}))

    def test_expired_cycle_stays_due_and_scan_runs_it_once_before_retry(self):
        self.run.return_value = False
        self.assertTrue(self.schedule.run_due(self.notices))
        self.assertEqual(self.schedule.state['due_at'], 0)
        self.now.return_value += 60
        self.assertFalse(self.schedule.run_due(self.notices))
        self.scan()
        self.run.return_value = True
        self.assertTrue(self.schedule.run_due(self.notices))
        self.assertEqual(self.schedule.state['due_at'], 100060 + collector.INTERVAL)
        self.assertFalse(self.schedule.run_due(self.notices))
        self.assertFalse(collector.Schedule(self.path).run_due(self.notices))
        self.assertEqual(self.run.call_count, 2)

    def test_scan_before_due_does_not_move_schedule_or_collect_early(self):
        self.schedule.run_due(self.notices)
        due = self.schedule.state['due_at']
        self.scan()
        self.now.return_value += 60
        self.assertFalse(self.schedule.run_due(self.notices))
        self.assertEqual(self.schedule.state['due_at'], due)
        self.now.return_value = due
        self.assertTrue(self.schedule.run_due(self.notices))
        self.assertEqual(self.run.call_count, 2)

    def test_scan_during_downtime_is_seen_after_restart(self):
        self.run.return_value = False
        self.schedule.run_due(self.notices)
        self.scan()
        self.assertTrue(collector.Schedule(self.path).run_due(self.notices))
        self.assertEqual(self.run.call_count, 2)

    def test_missing_or_partial_event_never_repeats_attempt(self):
        self.run.return_value = False
        self.schedule.run_due(self.notices)
        for raw in ['{', 'null', '{}', '{"id": ""}', '{"id": 12}']:
            self.event.write_text(raw)
            self.assertFalse(self.schedule.run_due(self.notices))
        self.run.assert_called_once()

    def test_expiry_retries_after_four_hours_without_scan(self):
        self.run.return_value = False
        self.schedule.run_due(self.notices)
        self.now.return_value += collector.INTERVAL
        self.assertTrue(self.schedule.run_due(self.notices))

    def test_disabled_collection_does_not_consume_scan_or_call_cycle(self):
        self.scan()
        with patch.dict(os.environ, {'COLLECT_ENABLED': 'false'}):
            self.assertFalse(self.schedule.run_due(self.notices))
        self.run.assert_not_called()
        self.assertFalse(self.path.exists())
        self.assertTrue(self.schedule.run_due(self.notices))

    def test_exception_waits_for_retry_or_new_scan_and_keeps_due(self):
        self.run.side_effect = TimeoutError('private details')
        self.schedule.run_due(self.notices)
        self.assertEqual(self.schedule.state['due_at'], 0)
        self.notices.enqueue.assert_called_once()
        self.assertNotIn('private details', str(self.notices.enqueue.call_args))
        self.assertFalse(self.schedule.run_due(self.notices))
        self.scan()
        self.assertTrue(self.schedule.run_due(self.notices))
