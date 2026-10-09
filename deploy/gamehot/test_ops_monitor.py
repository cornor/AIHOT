import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from ops_monitor import Monitor, database_findings, backup_finding, DEBOUNCE, SEND_INTERVAL, REPEAT_INTERVAL
from backup_status import record


class MonitorTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'monitor.json'
        self.monitor = Monitor(self.path)
        self.sender = Mock(return_value=True)
        self.now = 1000000

    def tick(self, observations, seconds=0):
        now = self.now + seconds
        self.monitor.update(observations, now)
        self.monitor.deliver(now, self.sender)

    def test_short_fault_is_silent(self):
        self.tick({'db': (True, 'db')})
        self.tick({'db': (False, 'db')}, 600)
        self.tick({'db': (False, 'db')}, 1800)
        self.sender.assert_not_called()

    def test_faults_grouped_and_daily_reminders_survive_restart(self):
        bad = {'db': (True, 'db'), 'model': (True, 'model')}
        self.tick(bad)
        self.tick(bad, DEBOUNCE)
        self.assertEqual(self.sender.call_count, 1)
        self.assertIn('db', self.sender.call_args.args[0])
        self.assertIn('model', self.sender.call_args.args[0])
        self.monitor = Monitor(self.path)
        self.tick(bad, DEBOUNCE + SEND_INTERVAL)
        self.assertEqual(self.sender.call_count, 1)
        self.tick(bad, DEBOUNCE + REPEAT_INTERVAL)
        self.assertEqual(self.sender.call_count, 2)

    def test_recovery_is_stable_and_waits_for_global_cooldown(self):
        self.tick({'db': (True, 'down')})
        self.tick({'db': (True, 'down')}, DEBOUNCE)
        self.tick({'db': (False, 'up')}, 1800)
        self.tick({'db': (False, 'up')}, 3000)
        self.assertEqual(self.sender.call_count, 1)
        self.tick({'db': (False, 'up')}, DEBOUNCE + SEND_INTERVAL)
        self.assertEqual(self.sender.call_count, 2)
        self.assertIn('恢复：up', self.sender.call_args.args[0])
        self.tick({'db': (False, 'up')}, DEBOUNCE + SEND_INTERVAL * 2)
        self.assertEqual(self.sender.call_count, 2)

    def test_new_faults_also_respect_global_cooldown(self):
        self.tick({'db': (True, 'db')})
        self.tick({'db': (True, 'db')}, DEBOUNCE)
        self.tick({'db': (True, 'db'), 'disk': (True, 'disk')}, 1800)
        self.tick({'db': (True, 'db'), 'disk': (True, 'disk')}, 3600)
        self.assertEqual(self.sender.call_count, 1)
        self.tick({'db': (True, 'db'), 'disk': (True, 'disk')}, DEBOUNCE + SEND_INTERVAL)
        self.assertEqual(self.sender.call_count, 2)

    def test_timeout_never_causes_rapid_retries(self):
        self.sender.side_effect = TimeoutError('sensitive URL')
        self.tick({'db': (True, 'db')})
        self.tick({'db': (True, 'db')}, DEBOUNCE)
        self.monitor = Monitor(self.path)
        self.tick({'db': (True, 'db')}, DEBOUNCE + 600)
        self.assertEqual(self.sender.call_count, 1)
        self.sender.side_effect = None
        self.tick({'db': (True, 'db')}, DEBOUNCE + SEND_INTERVAL)
        self.assertEqual(self.sender.call_count, 2)
        self.assertTrue(self.monitor.state['checks']['db']['notified'])

    def test_unknown_and_missing_probes_do_not_claim_recovery(self):
        self.tick({'model': (True, 'failure')})
        self.tick({'model': (True, 'failure')}, DEBOUNCE)
        self.tick({'model': (None, 'unknown')}, SEND_INTERVAL * 2)
        self.tick({}, SEND_INTERVAL * 3)
        self.assertEqual(self.sender.call_count, 1)

    def test_flapping_does_not_bypass_daily_problem_limit(self):
        self.tick({'db': (True, 'db')})
        self.tick({'db': (True, 'db')}, DEBOUNCE)
        self.tick({'db': (False, 'db')}, 1800)
        self.tick({'db': (False, 'db')}, DEBOUNCE + SEND_INTERVAL)
        self.tick({'db': (True, 'db')}, SEND_INTERVAL * 2)
        self.tick({'db': (True, 'db')}, SEND_INTERVAL * 2 + DEBOUNCE)
        self.assertEqual(self.sender.call_count, 2)

    def test_model_aging_out_without_success_is_not_recovery(self):
        data = {'model_failed': 0, 'model_last_failed': 200, 'model_last_ok': 100,
                'worker_age': 60, 'waiting': 0, 'failed': 0}
        self.assertIsNone(database_findings(data)['model.calls'][0])
        data['model_last_ok'] = 300
        self.assertFalse(database_findings(data)['model.calls'][0])
        data['model_last_failed'] = 400; data['model_failed'] = 3
        self.assertTrue(database_findings(data)['model.calls'][0])

    def test_backup_failure_retains_last_success_and_detects_staleness(self):
        (self.root / 'private').mkdir()
        path = self.root / 'private/backup-status.json'
        record(self.root, 'success', 'snapshot-a', now=self.now)
        self.assertFalse(backup_finding(path, self.now + 3600)[0])
        record(self.root, 'failed', 'snapshot-b', now=self.now + 4000)
        self.assertTrue(backup_finding(path, self.now + 4000)[0])
        record(self.root, 'success', 'snapshot-c', now=self.now + 8000)
        self.assertFalse(backup_finding(path, self.now + 8000)[0])
        self.assertTrue(backup_finding(path, self.now + 8000 + 31 * 3600)[0])


if __name__ == '__main__':
    unittest.main()
