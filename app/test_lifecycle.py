"""Lifecycle ownership invariants; actual Windows start/stop is verified separately."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import manage


class LifecycleTests(unittest.TestCase):
    def test_python_child_can_own_listener(self):
        state = {'processes': [{'pid': 10, 'parent': 1}, {'pid': 20, 'parent': 10}], 'listeners': [20]}
        self.assertTrue(manage.listeners_belong_to_launch(state, 10))

    def test_unrelated_listener_cannot_claim_success(self):
        state = {'processes': [{'pid': 10, 'parent': 1}, {'pid': 30, 'parent': 1}], 'listeners': [30]}
        self.assertFalse(manage.listeners_belong_to_launch(state, 10))

    def test_other_checkout_cannot_mutate_database_on_start(self):
        state = {'processes': [], 'listeners': [20], 'recorded_present': True, 'recorded_owned': False}
        with patch.object(manage, 'backend_state', return_value=state), patch.object(manage, 'initialize') as initialize:
            with self.assertRaises(RuntimeError): manage.start()
            initialize.assert_not_called()

    def test_repeated_start_reuses_this_checkout(self):
        state = {'processes': [{'pid': 20, 'parent': 10}], 'listeners': [20], 'recorded_present': True, 'recorded_owned': True}
        with patch.object(manage, 'backend_state', return_value=state), patch.object(manage, 'initialize') as initialize, \
             patch.object(manage, 'show_address') as address, patch.object(manage.subprocess, 'Popen') as spawn:
            manage.start()
            address.assert_called_once()
            initialize.assert_not_called()
            spawn.assert_not_called()

    def test_rejected_stop_keeps_pid_and_mysql(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            (runtime / 'server.pid').write_text('20')
            with patch.object(manage, 'RUNTIME', runtime), \
                 patch.object(manage.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'control')), \
                 patch.object(manage, 'connect') as connect:
                with self.assertRaises(subprocess.CalledProcessError): manage.stop()
                self.assertEqual((runtime / 'server.pid').read_text(), '20')
                connect.assert_not_called()

    def test_surviving_listener_keeps_pid_and_mysql(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            (runtime / 'server.pid').write_text('20')
            with patch.object(manage, 'RUNTIME', runtime), patch.object(manage.subprocess, 'run'), \
                 patch.object(manage, 'port_open', return_value=True), patch.object(manage.time, 'sleep'), \
                 patch.object(manage, 'connect') as connect:
                with self.assertRaises(RuntimeError): manage.stop()
                self.assertTrue((runtime / 'server.pid').exists())
                connect.assert_not_called()


if __name__ == '__main__': unittest.main(verbosity=2)
