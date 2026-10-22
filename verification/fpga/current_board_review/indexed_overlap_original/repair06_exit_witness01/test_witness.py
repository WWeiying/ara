import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import witness as w


class Fake:
    def __init__(self, status=0):
        self.calls = []
        self.data = dict(Id=w.UNIT, LoadState='loaded', InvocationID=w.INVOCATION,
                         ActiveState='active', MainPID=620452, ControlGroup=w.GROUP,
                         ExecMainCode=0, ExecMainStatus=0, ExecMainExitTimestamp=0)
        self.status = status

    def facts(self, unit):
        return dict(self.data)

    def ref(self, unit):
        self.calls.append('ref')
        self.data.update(ActiveState='failed' if self.status else 'inactive', MainPID=0,
                         ExecMainCode=1, ExecMainStatus=self.status, ExecMainExitTimestamp=123)

    def unref(self, unit):
        self.calls.append('unref')

    def close(self):
        self.calls.append('close')


class Tests(unittest.TestCase):
    def test_zero_and_nonzero(self):
        for status in (0, 7):
            with tempfile.TemporaryDirectory() as temp:
                out = Path(temp)
                done = out / 'followup'
                done.touch()
                bus = Fake(status)
                with patch.object(w, 'FOLLOWUP', done):
                    w.observe(bus, out, threading.Event())
                data = json.loads((out / 'actualexit.json').read_text())
                self.assertEqual(data['properties']['ExecMainStatus'], status)
                self.assertNotIn('PASS', json.dumps(data))
                self.assertEqual(bus.calls, ['ref', 'unref', 'close'])

    def test_identity_reject(self):
        bus = Fake()
        bus.data['MainPID'] = 1
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(RuntimeError):
                w.observe(bus, Path(temp), threading.Event())
        self.assertEqual(bus.calls, ['close'])

    def test_exclusive_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            (out / 'startup.json').touch()
            bus = Fake()
            with self.assertRaises(FileExistsError):
                w.observe(bus, out, threading.Event())
            self.assertEqual(bus.calls, ['ref', 'unref', 'close'])

    def test_cancel_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            stop = threading.Event()
            stop.set()
            bus = Fake()
            w.observe(bus, Path(temp), stop)
            self.assertFalse((Path(temp) / 'actualexit.json').exists())
            self.assertEqual(bus.calls, ['ref', 'unref', 'close'])


if __name__ == '__main__':
    unittest.main()
