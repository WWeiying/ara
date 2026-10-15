#!/usr/bin/env python3
"""Same 29 host checks against the narrowly corrected successor, no DUT."""
import argparse
from pathlib import Path
import unittest
import test_host
import worker_successor as worker

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    test_host.w = worker
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(test_host.HostTests))
    worker.save(args.report, dict(status='HOST_PASS_NOT_DUT' if result.wasSuccessful() else 'HOST_FAIL',
        tests=result.testsRun, failures=[(str(t), s) for t, s in result.failures],
        errors=[(str(t), s) for t, s in result.errors], VCS_launched=False,
        pins={str(worker.HERE / name): worker.sha(worker.HERE / name) for name in
              ('worker_successor.py', 'worker.py', 'checker.py', 'test_host.py', 'test_successor.py', 'capture.tcl')}))
    raise SystemExit(not result.wasSuccessful())
