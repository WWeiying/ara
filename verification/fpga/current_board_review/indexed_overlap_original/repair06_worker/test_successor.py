#!/usr/bin/env python3
"""Read-only reference validation and host negatives; never starts Spike or VCS."""
import argparse
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import worker as w
import test_host


class SuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, cls.reference_pins = w.reference_scope(w.OWNER / 'reference03')

    def test_exact_reference_and_unmodified_checker(self):
        self.assertEqual([c['id'] for c in self.cases], list(w.NAMES))
        self.assertEqual([c['timeout_s'] for c in self.cases], [4200, 2400, 4200])
        self.assertEqual([c['checks'] for c in self.cases], [21595, 5215, 21595])
        self.assertTrue(all(c['rounds'] == 50 for c in self.cases))
        for name in ('checker.py', 'test_host.py'):
            self.assertEqual(w.sha(w.HERE / name), w.sha(w.BASELINE / name))
        with self.assertRaises(ValueError):
            w.reference_scope(w.OWNER / 'reference02')

    def test_wrong_image_and_frozen_owner_refused(self):
        with patch.object(w.common, 'image_context') as ctx:
            with self.assertRaises(ValueError):
                w.image_context(Path(str(w.IMAGE).replace('candidate06', 'candidate05')))
            ctx.assert_not_called()
            ctx.return_value = ({'snapshot': '/tmp/current_board_memory_candidate05/frozen'}, Path('/tmp'), ())
            with self.assertRaises(ValueError):
                w.image_context(w.IMAGE)

    def test_common_configuration_gate_retained(self):
        with tempfile.TemporaryDirectory() as d:
            simv = Path(d) / 'simv'
            simv.write_text('not an executable simulation; never executed')
            simv.chmod(0o700)
            ledger = {'simv': str(simv), 'configuration_sha256': 'wrong'}
            with patch.object(w.common.base, 'image_context', return_value=(ledger, Path(d), ())):
                with self.assertRaisesRegex(ValueError, 'Image settings'):
                    w.common.image_context(w.IMAGE)

    def test_plan_membership_oracle_budgets_and_pins(self):
        plan = dict(status='PREPARED_NOT_RUN', reference=str(w.OWNER / 'reference03'),
                    pilot_capture=str(w.HERE / 'capture.tcl'), image=str(w.IMAGE),
                    image_sha256='host-image-digest', no_build=True, retries=0, stop_first_fail=True,
                    service_seconds=9600, worker_deadline_s=8800, debug_plusarg=w.DEBUG,
                    stages=[dict(name=n, jobs=j, cases=list(cs)) for n, j, cs in w.STAGES],
                    pins={str(w.HERE / 'worker.py'): w.sha(w.HERE / 'worker.py')},
                    cases=copy.deepcopy(self.cases))
        real_sha = w.sha
        def host_sha(p):
            return 'host-image-digest' if Path(p) == w.IMAGE / 'image.json' else real_sha(p)
        with patch.object(w, 'sha', side_effect=host_sha):
            w.validate_plan(plan, w.IMAGE)
            mutations = [('image_sha256', 'bad'), ('worker_deadline_s', 8801),
                         ('service_seconds', 9601), ('retries', 1), ('reference', str(w.OWNER / 'reference02'))]
            for key, value in mutations:
                bad = copy.deepcopy(plan); bad[key] = value
                with self.subTest(key=key), self.assertRaises(ValueError): w.validate_plan(bad, w.IMAGE)
            for key, value in [('rounds', 49), ('fault', False), ('overlap', 0), ('timeout_s', 4201),
                               ('checks', 1), ('sha256', 'bad'), ('pass_markers', [w.common.SUCCESS])]:
                bad = copy.deepcopy(plan); bad['cases'][0][key] = value
                with self.subTest(case_key=key), self.assertRaises(ValueError): w.validate_plan(bad, w.IMAGE)
            bad = copy.deepcopy(plan); bad['stages'][0]['cases'] = list(w.NAMES)
            with self.assertRaises(ValueError): w.validate_plan(bad, w.IMAGE)
            bad = copy.deepcopy(plan); bad['cases'].pop()
            with self.assertRaises(ValueError): w.validate_plan(bad, w.IMAGE)
            bad = copy.deepcopy(plan); bad['pins'][str(w.HERE / 'worker.py')] = 'bad'
            with self.assertRaises(ValueError): w.validate_plan(bad, w.IMAGE)

    def test_private_input_image_provenance_refused_before_csv(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root / 'work').mkdir()
            private = root / 'input.elf'; private.write_bytes(b'host dummy ELF, never executed')
            case = dict(self.cases[0], sha256=w.sha(private))
            log = w.marker(case) + '\nINDEXED_ORIGINAL_PASS\n' + w.common.SUCCESS + '\n$finish\n'
            (root / 'console.log').write_text(log); (root / 'work/run.vcs.log').write_text(log)
            ledger = dict(simv='/host/simv', files={'/host/simv': 'pinned'})
            good = dict(binary=dict(source=case['elf'], path=str(private), sha256=case['sha256']),
                        simv=dict(path=ledger['simv'], image_sha256=ledger['files']))
            result = SimpleNamespace(artifact_dir=root, returncode=0, elapsed_s=1)
            for section, key in [('binary', 'source'), ('binary', 'sha256'), ('simv', 'path'),
                                 ('simv', 'image_sha256')]:
                bad = copy.deepcopy(good); bad[section][key] = 'changed'
                (root / 'inputs.json').write_text(json.dumps(bad))
                with patch.object(w.checker, 'analyze') as analyze:
                    with self.assertRaisesRegex(ValueError, 'input/image provenance'):
                        w.artifacts(result, case, ledger, w.OWNER / 'reference03', threading.Event())
                    analyze.assert_not_called()
            private.write_bytes(b'changed ELF')
            with self.assertRaisesRegex(ValueError, 'Private ELF changed'):
                w.artifacts(result, case, ledger, w.OWNER / 'reference03', threading.Event())

    def test_no_authority_no_run_and_old_output_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): w.run(w.IMAGE, Path(d), None, None, False)
        with self.assertRaises(ValueError): w.owned(w.BASELINE / 'prepared02')
        with self.assertRaises(ValueError): w.service_owner('ara-indexed-overlap-m5-01.service')

    def test_profile_tokens_local_only_not_m6_validation(self):
        w.profile_sources(w.checker.ROOT)
        text = (w.HERE / 'capture.tcl').read_text()
        for name in ('indexed_mixed_vs2_layout', 'reshuffle_req_q', 'reshuffle_req_d', 'eew_valid_q',
                     'eew_valid_d', 'addrgen_operand_i', 'addrgen_operand_valid_i', 'addrgen_operand_ready_o'):
            self.assertIn(name, text)

    def test_real_timer_during_terminal_filesystem_write(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d); abort = w.TerminalAbort()
            terminal = {'status': 'PASS_3_REFERENCE03_FULL50_M6'}
            real_save = w.save
            fired = threading.Event()
            def timeout():
                abort.set(); fired.set()
            def slow_save(path, data):
                real_save(path, data)
                timer = threading.Timer(0.01, timeout)
                timer.start()
                self.assertTrue(fired.wait(2))
                timer.join()
            with patch.object(w, 'save', side_effect=slow_save):
                w.publish_terminal(out, terminal, abort, time.monotonic() + 10)
            actual = w.read(out / 'complete.json')
            self.assertEqual(actual['status'], 'NOT_PASS')
            self.assertTrue(actual['aborted'])
            self.assertFalse((out / 'complete.pending.json').exists())

    def test_expired_deadline_without_timer_and_pending_signal(self):
        for expired in (True, False):
            with tempfile.TemporaryDirectory() as d:
                abort = w.TerminalAbort(); terminal = {'status': 'PASS_3_REFERENCE03_FULL50_M6'}
                with patch.object(w.signal, 'sigpending', return_value=set() if expired else {w.signal.SIGTERM}):
                    w.publish_terminal(Path(d), terminal, abort, time.monotonic() + (-1 if expired else 10))
                self.assertEqual(w.read(Path(d) / 'complete.json')['status'], 'NOT_PASS')

    def test_terminal_success_closes_late_timer_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d); abort = w.TerminalAbort(); terminal = {'status': 'PASS_3_REFERENCE03_FULL50_M6'}
            w.publish_terminal(out, terminal, abort, time.monotonic() + 10)
            abort.set()
            self.assertFalse(abort.is_set())
            before = (out / 'complete.json').read_bytes()
            with self.assertRaises(ValueError):
                w.publish_terminal(out, terminal, abort, time.monotonic() + 10)
            self.assertEqual((out / 'complete.json').read_bytes(), before)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(test_host.HostTests),
                               unittest.defaultTestLoader.loadTestsFromTestCase(SuccessorTests)])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    pins = {str(w.HERE / name): w.sha(w.HERE / name) for name in
            ('worker.py', 'checker.py', 'test_host.py', 'test_successor.py', 'capture.tcl', 'README.md')}
    pins.update(getattr(SuccessorTests, 'reference_pins', {}))
    for name in ('worker_successor.py', 'checker.py', 'test_host.py'):
        pins[str(w.BASELINE / name)] = w.sha(w.BASELINE / name)
    w.save(args.report, dict(status='HOST_PASS_NOT_DUT' if result.wasSuccessful() else 'HOST_FAIL',
        tests=result.testsRun, failures=[(str(t), s) for t, s in result.failures],
        errors=[(str(t), s) for t, s in result.errors], VCS_launched=False, build_launched=False,
        image_verified=False, profile_scope='Workspace and M5 token existence only; M6 frozen check at prepare',
        cases=getattr(SuccessorTests, 'cases', []), pins=pins))
    raise SystemExit(not result.wasSuccessful())
