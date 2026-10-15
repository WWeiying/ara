#!/usr/bin/env python3
"""Frozen predecessor tests plus fail-closed service-GC admission negatives."""
from contextlib import nullcontext
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import coordinator_successor as c
import test_host as previous

previous.c = c


def props(load='not-found', result='success', code='0', status='0'):
    return (f'Id={c.PRE_UNIT}\nLoadState={load}\nActiveState=inactive\nSubState=dead\nMainPID=0\n'
            f'Result={result}\nExecMainCode={code}\nExecMainStatus={status}\n'
            'ExecMainExitTimestamp=Sun 2026-10-11 13:30:00 PDT\n')


class SuccessorTests(previous.Tests):
    def test_gc_not_historical_success_and_loaded_timeout_refused(self):
        worker = SimpleNamespace(bus_environment=lambda: {})
        for text in (props(), props(result='exit-code', status='1'),
                     props(load='loaded', result='timeout'),
                     props(load='loaded', result='exit-code', code='1', status='1')):
            with patch.object(c.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stderr='', stdout=text)), \
                 patch.object(c, 'processes', return_value=[]):
                with self.assertRaises(ValueError): c.predecessor_state(worker)

    def test_actual_loaded_exit0_is_required(self):
        worker = SimpleNamespace(bus_environment=lambda: {})
        text = props(load='loaded', code='1')
        with patch.object(c.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stderr='', stdout=text)), \
             patch.object(c, 'processes', return_value=[]):
            quiet, proof = c.predecessor_state(worker)
            self.assertTrue(quiet)
            self.assertTrue(proof['historical_service_exit_verified'])
        text = text.replace('ActiveState=inactive', 'ActiveState=active')
        with patch.object(c.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stderr='', stdout=text)), \
             patch.object(c, 'processes', return_value=[]):
            quiet, proof = c.predecessor_state(worker)
            self.assertFalse(quiet)

    def test_full_pass_header_gc_or_bad_exit_cannot_launch(self):
        preplan, passed = previous.fixture()
        for text in (props(), props(status='1'), props(load='loaded', result='timeout'),
                     props(load='loaded', result='exit-code', code='1', status='1')):
            with tempfile.TemporaryDirectory() as d:
                root = Path(d); pre = root / 'pre'; pre.mkdir(); out = root / 'out'; out.mkdir()
                c.save(pre / 'complete.json', passed)
                plan = dict(pins={}, unit=c.UNIT, wait_seconds=c.WAIT_SECONDS, sleep_seconds=c.SLEEP_SECONDS,
                            regression_seconds=c.REG_SECONDS, service_seconds=c.SERVICE_SECONDS,
                            retries=0, no_build=True, command=c.regression_command(),
                            unknown_predecessor_exit='HOLD_NO_AUTOMATIC_FALLBACK', previous_pin_count=885)
                c.save(out / 'plan.json', plan)
                def publish(path, terminal, abort):
                    c.save(path / 'complete.json', terminal)
                worker = SimpleNamespace(bus_environment=lambda: {}, common=SimpleNamespace(
                    abort_signals=lambda _: nullcontext(), publish=publish))
                with patch.object(c, 'PRE', pre), patch.object(c, 'load_inputs', return_value=(preplan, {}, worker)), \
                     patch.object(c, 'service_owner', return_value={'MainPID': '101'}), \
                     patch.object(c, 'processes', return_value=[]), \
                     patch.object(c.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stderr='', stdout=text)), \
                     patch.object(c.subprocess, 'Popen') as launch, \
                     patch.object(c, 'shared_validation') as admission:
                    rc = c.run(out, c.sha(out / 'plan.json'), True)
                    self.assertEqual(rc, 1)
                    launch.assert_not_called(); admission.assert_not_called()
                terminal = c.read(out / 'complete.json')
                self.assertEqual(terminal['status'], 'BLOCKED_PREDECESSOR')
                self.assertIn('predecessor', terminal['error'].lower())
                self.assertFalse((out / 'child.json').exists())

    def test_all_previous885_pins_preserved(self):
        path = c.HERE / 'prepared01/plan.json'
        self.assertEqual(c.sha(path), '4765cdfc0805b304b593b4fed7be2542a66907b4890ae777f0707bbe0c6ae007')
        pins = c.read(path)['pins']
        self.assertEqual(len(pins), 885)
        c.verify(pins)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SuccessorTests))
    pins = dict(c.read(c.HERE / 'prepared01/plan.json')['pins'])
    for name in ('coordinator_successor.py', 'test_successor.py', 'prepared01/plan.json'):
        pins[str(c.HERE / name)] = c.sha(c.HERE / name)
    c.save(c.HERE / 'host_successor_final.json', dict(
        status='HOST_PASS_NOT_DUT' if result.wasSuccessful() else 'HOST_FAIL', tests=result.testsRun,
        failures=[(str(t), s) for t, s in result.failures], errors=[(str(t), s) for t, s in result.errors],
        simulator_started=False, service_started=False, previous_pin_count=885,
        unknown_predecessor_exit='HOLD_NO_AUTOMATIC_FALLBACK', pins=pins))
    raise SystemExit(not result.wasSuccessful())
