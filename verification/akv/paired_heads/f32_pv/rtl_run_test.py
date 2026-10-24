"""Fail-closed runner tests. All execution phases are synthetic."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import rtl_run as r


class WorkerTests(unittest.TestCase):
    def test_preparation_drift_stops_before_execute(self):
        with tempfile.TemporaryDirectory() as tmp:
            build = Path(tmp)/'build'
            build.mkdir()
            args = argparse.Namespace(build=build,output=Path(tmp)/'run',timeout=10800,preflight_only=False)
            with patch.object(r,'prepare',side_effect=ValueError('drift')), \
                 patch.object(r.Execution,'execute') as execute:
                with self.assertRaisesRegex(ValueError,'drift'):
                    r.run(args)
                execute.assert_not_called()
            result = json.loads((args.output/'result.json').read_text())
            status = json.loads((args.output/'status.json').read_text())
            self.assertEqual(result['state'],'FAIL')
            self.assertEqual(status['state'],'FAIL')
            self.assertIsNone(status['child_pid'])

    def test_phase_failure_records_exit_and_clears_child(self):
        for timeout in (False,True):
            with self.subTest(timeout=timeout), tempfile.TemporaryDirectory() as tmp:
                owner = r.Execution(Path(tmp))
                def child(argv,log,limit,env,started):
                    started(12345)
                    if timeout:
                        raise subprocess.TimeoutExpired(argv,limit)
                    return 3
                with patch.object(r.s,'run_command',side_effect=child):
                    with self.assertRaises((ValueError,subprocess.TimeoutExpired)):
                        owner.execute(['synthetic'],Path(tmp)/'test.log',7,'RUNNING')
                self.assertIsNone(owner.state['child_pid'])
                if not timeout:
                    self.assertEqual(owner.state['running_exit_code'],3)


if __name__ == '__main__':
    unittest.main()
