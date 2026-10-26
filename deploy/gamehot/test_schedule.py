import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import collector


def timestamp(value):
    return datetime.fromisoformat(value).timestamp()


class ScheduleTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'schedule.json'
        self.event = Path(temp.name) / 'event.json'
        env = patch.dict(os.environ, {'COLLECT_ENABLED': 'true', 'WERSS_AUTH_EVENT_FILE': str(self.event)})
        env.start()
        self.addCleanup(env.stop)
        clock = patch.object(collector.time, 'time', return_value=timestamp('2026-10-26T08:00:00+08:00'))
        self.now = clock.start()
        self.addCleanup(clock.stop)
        cycle = patch.object(collector, 'cycle', return_value=True)
        self.run = cycle.start()
        self.addCleanup(cycle.stop)
        self.schedule = collector.Schedule(self.path)
        self.notices = Mock()
        collector.stop.clear()

    def scan(self, value='scan-1'):
        self.event.write_text(json.dumps({'id': value}))

    def test_daily_uses_beijing_time_and_does_not_drift_with_duration(self):
        self.assertFalse(self.schedule.run_due(self.notices))
        self.now.return_value = timestamp('2026-10-26T01:00:03+00:00')
        self.run.side_effect = lambda _: setattr(self.now, 'return_value', self.now.return_value + 900)
        self.assertTrue(self.schedule.run_due(self.notices))
        self.assertEqual(self.schedule.state['due_at'], timestamp('2026-10-27T09:00:00+08:00'))
        self.assertFalse(collector.Schedule(self.path).run_due(self.notices))
        self.now.return_value = timestamp('2026-10-27T09:00:00+08:00')
        self.assertTrue(self.schedule.run_due(self.notices))
        self.assertEqual(self.run.call_count, 2)

    def test_migrates_four_hour_state_without_collecting_immediately(self):
        self.path.write_text(json.dumps({'due_at': 0, 'retry_at': 0, 'auth_event': 'old'}))
        self.scan('old')
        self.now.return_value = timestamp('2026-10-26T11:00:00+08:00')
        schedule = collector.Schedule(self.path)
        self.assertFalse(schedule.run_due(self.notices))
        self.assertEqual(schedule.state['due_at'], timestamp('2026-10-27T09:00:00+08:00'))
        self.assertNotIn('retry_at', schedule.state)

    def test_scan_collects_once_without_moving_daily_slot(self):
        self.schedule.run_due(self.notices)
        due = self.schedule.state['due_at']
        self.scan()
        self.assertTrue(self.schedule.run_due(self.notices))
        self.assertEqual(self.schedule.state['due_at'], due)
        self.assertFalse(collector.Schedule(self.path).run_due(self.notices))
        self.scan('scan-2')
        self.assertTrue(self.schedule.run_due(self.notices))
        self.assertEqual(self.run.call_count, 2)

    def test_scan_during_downtime_is_consumed_after_restart(self):
        self.schedule.run_due(self.notices)
        self.scan()
        self.assertTrue(collector.Schedule(self.path).run_due(self.notices))
        self.assertFalse(collector.Schedule(self.path).run_due(self.notices))

    def test_fresh_install_does_not_replay_existing_scan(self):
        self.scan()
        self.assertFalse(self.schedule.run_due(self.notices))
        self.assertFalse(collector.Schedule(self.path).run_due(self.notices))
        self.run.assert_not_called()

    def test_simultaneous_daily_and_scan_only_runs_once(self):
        self.schedule.run_due(self.notices)
        self.now.return_value = timestamp('2026-10-26T09:00:00+08:00')
        self.scan()
        self.assertTrue(self.schedule.run_due(self.notices))
        self.assertFalse(collector.Schedule(self.path).run_due(self.notices))
        self.run.assert_called_once()

    def test_missed_slot_does_not_collect_on_restart(self):
        self.schedule.run_due(self.notices)
        self.now.return_value = timestamp('2026-10-28T10:00:00+08:00')
        schedule = collector.Schedule(self.path)
        self.assertFalse(schedule.run_due(self.notices))
        self.assertEqual(schedule.state['due_at'], timestamp('2026-10-29T09:00:00+08:00'))
        self.run.assert_not_called()

    def test_failure_waits_for_next_daily_slot_or_new_scan(self):
        self.now.return_value = timestamp('2026-10-26T09:00:00+08:00')
        self.run.return_value = False
        self.assertTrue(self.schedule.run_due(self.notices))
        self.now.return_value += 4 * 3600
        self.assertFalse(self.schedule.run_due(self.notices))
        self.scan()
        self.assertTrue(self.schedule.run_due(self.notices))
        self.assertEqual(self.schedule.state['due_at'], timestamp('2026-10-27T09:00:00+08:00'))

    def test_disabled_does_not_consume_scan_or_update_state(self):
        self.schedule.run_due(self.notices)
        before = self.path.read_text()
        self.scan()
        with patch.dict(os.environ, {'COLLECT_ENABLED': 'false'}):
            self.assertFalse(self.schedule.run_due(self.notices))
        self.assertEqual(self.path.read_text(), before)
        self.run.assert_not_called()
        self.assertTrue(self.schedule.run_due(self.notices))

    def test_partial_event_does_not_trigger_collection(self):
        self.schedule.run_due(self.notices)
        for raw in ['{', 'null', '{}', '{"id": ""}', '{"id": 12}']:
            self.event.write_text(raw)
            self.assertFalse(self.schedule.run_due(self.notices))
        self.run.assert_not_called()

    def test_attempt_is_persisted_before_cycle_and_exception_does_not_replay(self):
        self.schedule.run_due(self.notices)
        self.scan()
        def fail(_):
            saved = json.loads(self.path.read_text())
            self.assertEqual(saved['auth_event'], 'scan-1')
            self.assertEqual(saved['last_attempt_at'], self.now.return_value)
            raise TimeoutError('private details')
        self.run.side_effect = fail
        self.assertTrue(self.schedule.run_due(self.notices))
        self.notices.enqueue.assert_called_once()
        self.assertNotIn('private details', str(self.notices.enqueue.call_args))
        self.assertFalse(collector.Schedule(self.path).run_due(self.notices))
