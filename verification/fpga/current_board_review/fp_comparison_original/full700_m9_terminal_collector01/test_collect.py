"""Focused collector transport/exit tests, no DUT or active CSV access."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import collect as c


class Tests(unittest.TestCase):
    def properties(self):
        return dict(Id='producer.service', LoadState='loaded', ActiveState='active', SubState='exited',
                    MainPID='0', Result='success', ExecMainCode='1', ExecMainStatus='0', ControlGroup='')

    def test_retained_exited_service(self):
        self.assertTrue(c.successful_exit(self.properties()))

    def test_running_zero_is_not_exit(self):
        p = self.properties()
        p.update(MainPID='123', SubState='running')
        self.assertFalse(c.successful_exit(p))

    def test_kill_or_numeric_nonzero_not_success(self):
        for updates in (dict(ExecMainStatus='17'), dict(ExecMainCode='2'), dict(Result='timeout')):
            self.assertFalse(c.successful_exit(dict(self.properties(), **updates)))

    def test_gc_and_bus_fail_closed(self):
        for response in (subprocess.CompletedProcess([], 1, '', 'No medium found'),
                         subprocess.CompletedProcess([], 0, 'Id=producer.service\n', ''),
                         subprocess.CompletedProcess([], 0, '\n'.join(f'{k}={v}' for k, v in
                             dict(self.properties(), LoadState='not-found').items()), '')):
            with patch.object(c.subprocess, 'run', return_value=response):
                with self.assertRaises(ValueError):
                    c.systemd('producer.service')

    def test_actual_numeric_persisted_before_checker_exception(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(c.base, 'OUT', Path(directory)):
            start = time.monotonic()
            p = subprocess.Popen([sys.executable, '-c', 'raise SystemExit(17)'])
            code, timed = c.base.wait_child(p, start, 5)
            self.assertEqual(code, 17)
            self.assertFalse(timed)
            with self.assertRaises(ValueError):
                raise ValueError('deliberate postcheck rejection')
            self.assertEqual(c.read(Path(directory) / 'actual_exit_unvalidated.json')['returncode'], 17)

    def test_whole_hash_after_first_error_without_reparse(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'closed.csv'
            path.write_bytes(b'first\nsecond\nthird\n')
            stream = c.base.HashLines(path)
            self.assertEqual(next(stream), 'first\n')
            for block in iter(lambda: stream.stream.read(16), b''):
                stream.hash.update(block)
                stream.bytes += len(block)
            stream.stream.close()
            self.assertEqual(stream.hash.hexdigest(), c.sha(path))
            self.assertEqual(stream.bytes, path.stat().st_size)

    def test_actual_import_contract_and_spec(self):
        w, _, observer = c.modules()
        plan = c.read(c.RUN / 'plan.json')
        self.assertEqual(c.sha(c.RUN / 'plan.json'), c.PLAN)
        self.assertEqual(c.sha(c.WORK / 'ENTRY.json'), c.ENTRY)
        self.assertEqual(w.checker.specification(Path(plan['cases'][0]['elf'])), plan['specs'][w.NAME])
        self.assertEqual(w.TIMEOUT, 7200)
        self.assertTrue(callable(observer))
        self.assertTrue(callable(w.worker.monitor_command))
        with self.assertRaises(ValueError):
            c.success_gate(w, {}, Path('/unused'), {}, dict(self.properties(), ExecMainStatus='17'))


if __name__ == '__main__':
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    c.save(c.HERE / 'host01.json', dict(status='PASS_HOST_ONLY' if result.wasSuccessful() else 'FAIL_HOST_ONLY',
           tests=result.testsRun, failures=len(result.failures), errors=len(result.errors), output=output.getvalue(),
           pins={str(p):c.sha(p) for p in (c.HERE / 'collect.py', c.HERE / 'test_collect.py')}))
    print(output.getvalue())
    raise SystemExit(0 if result.wasSuccessful() else 1)
