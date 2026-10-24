#!/usr/bin/env python3
"""Fail-closed worker boundaries without launching a simulator."""
import argparse
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import run_batch_qk as r


class WorkerBoundaryTests(unittest.TestCase):
    def test_guard_and_failed_preparation_never_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build,prior = root/'build',root/'prior'
            build.mkdir()
            prior.mkdir()
            a = argparse.Namespace(build=build,prerequisite=prior,output=build/'bad',timeout=1,preflight_only=False)
            with self.assertRaises(ValueError):
                r.run(a)
            a.output = root/'fresh'
            with mock.patch.object(r,'prepare',side_effect=ValueError('prior/source gate failed')), \
                 mock.patch.object(r.Execution,'execute') as launch:
                with self.assertRaises(ValueError):
                    r.run(a)
                launch.assert_not_called()
            self.assertEqual(r.s.read_json(a.output/'result.json')['state'],'FAIL')
            self.assertIsNone(r.s.read_json(a.output/'status.json')['child_pid'])


if __name__ == '__main__':
    unittest.main()
