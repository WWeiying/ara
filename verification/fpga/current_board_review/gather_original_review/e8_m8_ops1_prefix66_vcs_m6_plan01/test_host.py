#!/usr/bin/env python3
"""Host-only generated protocol fixtures; never DUT results or a substitute ELF."""
import copy
import csv
import io
import json
import os
import re
from pathlib import Path
import signal
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
import replay
from replay import checker as c

IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image')


def fixture(spec, model, fault=None):
    order = cycle = 0
    def row(pc=0x80001000, insn=0x13, rd=0, value=0, address=0, rmask=0, wmask=0, wdata=0, event='retire'):
        nonlocal order, cycle
        result = dict(cycle=str(cycle), event=event, order=str(order), port='0', trans_id='0',
            pc=f'{pc:x}', insn=f'{insn:x}', rd=str(rd), rd_wdata=f'{value:x}', mem_addr=f'{address:x}',
            mem_rmask=f'{rmask:x}', mem_wmask=f'{wmask:x}', mem_wdata=f'{wdata:x}', trap='0')
        cycle += 1
        if event == 'retire':
            order += 1
        return result
    from ara_verify.trace import is_vector_instruction
    a = spec['addresses']
    for j, gold in enumerate(model['rows']):
        for name, values, width in (('input', model['input'], 1), ('indices', model['indices'], 1),
                ('indices16', model['indices16'], 2), ('predicate', gold['predicate'], 1),
                ('output', [91]*1026, 1)):
            for k, value in enumerate(values):
                if j == k == 0 and name == 'input':
                    if fault == 'missing_setup':
                        continue
                    if fault == 'rng':
                        value ^= 1
                yield row(insn=0x1023 if width == 2 else 0x23, address=a[name]+width*k,
                          wmask=((1 << width)-1) << ((a[name]+width*k) % 8), wdata=value)
        args = [a['input'], a['indices'], a['output']+1, gold['vl'], 1024, a['predicate'], 0, gold['vstart']]
        if j == 0 and fault == 'args':
            args[7] += 1
        for reg, value in enumerate(args, 10):
            yield row(rd=reg, value=value)
        for i, instr in enumerate(spec['routine']):
            insn = int(instr['insn'], 16)
            if j == 0 and i == 8 and fault == 'encoding':
                insn ^= 0x100
            if is_vector_instruction(insn):
                yield row(insn=insn, event='cvx_req')
                yield row(insn=insn, event='cvx_resp')
            rd, value = 0, 0
            if i in (0, 5, 10):
                rd, value = 5, gold['vl'] if i == 5 else 1024
            elif i == 6:
                rd = 28
            elif i == 9:
                rd, value = 10, int(j == 0 and fault == 'csr')
            yield row(pc=instr['pc'], insn=insn, rd=rd, value=value)
        for k, value in enumerate([91, *gold['output'], 91]):
            if j == 0 and k == 1 and fault == 'missing_oracle':
                continue
            if j == 0 and ((k == 1 and fault == 'data') or (k == 1025 and fault == 'guard')):
                value ^= 1
            yield row(insn=0x4003, rd=5, value=value, address=a['output']+k,
                      rmask=1 << ((a['output']+k) % 8))
        if j == 0 and fault == 'truncated':
            return
    yield row(pc=spec['exit_store']['pc'], insn=int(spec['exit_store']['insn'], 16),
              address=spec['exit_address'], wmask=255, wdata=int(fault == 'bad_exit'))
    yield row(pc=spec['park']['pc'], insn=int(spec['park']['insn'], 16), rd=int(fault == 'bad_park'))


class Gates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger, _, _ = c.common.image_context(IMAGE)
        cls.case, cls.spec = replay.scope()
        cls.model = c.source.model()
        cls.console = '\n'.join(['BOARD_CASE_BEGIN '+c.NAME, 'RVV_GATHER_PREFIX_PASS sew=8 cases=66 errors=0',
            'BOARD_CASE_PASS '+c.NAME, 'BOARD_REPLAY_PASS', 'Core Test *** SUCCESS *** (tohost = 0)', '$finish'])

    def test_full66_and_generic_positive(self):
        from ara_verify.trace import validate_trace
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'host_synthetic.csv'
            rows = fixture(self.spec, self.model)
            first = next(rows)
            with path.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(first))
                writer.writeheader()
                writer.writerow(first)
                writer.writerows(rows)
            generic = validate_trace(path)
            with path.open() as stream:
                raw = c.retirement(csv.DictReader(stream), self.spec, self.model)
            self.assertEqual(raw['target_hits'], 66)
            self.assertEqual(raw['actual_output_scalar_loads'], 67716)
            self.assertEqual(raw['routine_retire_counts'], [66]*13)
            self.assertEqual(raw['retired_rows'], generic['retire_count'])
            self.assertEqual(raw['csv_rows'], generic['rows'])

    def negative_trace(self, fault, reason):
        with self.assertRaisesRegex(ValueError, reason):
            c.retirement(fixture(self.spec, self.model, fault), self.spec, self.model)

    def test_missing_setup(self): self.negative_trace('missing_setup', 'Missing initialized')
    def test_rng(self): self.negative_trace('rng', 'Setup/RNG mismatch')
    def test_args(self): self.negative_trace('args', 'arguments differ')
    def test_13asm(self): self.negative_trace('encoding', 'Original13')
    def test_csr(self): self.negative_trace('csr', 'vstart nonzero')
    def test_data(self): self.negative_trace('data', 'Full oracle mismatch')
    def test_guard(self): self.negative_trace('guard', 'Full oracle mismatch')
    def test_missing_oracle(self): self.negative_trace('missing_oracle', 'Missing full oracle')
    def test_truncated(self): self.negative_trace('truncated', 'Missing calls')
    def test_exit(self): self.negative_trace('bad_exit', 'CTRL exit')
    def test_park(self): self.negative_trace('bad_park', 'Post-exit')

    def test_console_positive(self): c.console_gate(self.console)

    def test_raw_failure_after_pass(self):
        for marker in ('RVV_GATHER_PREFIX_FAIL', 'BOARD_REPLAY_MISMATCH', 'RVV_PERMUTE_PASS',
                       'MATRIX_FAIL', 'ABORTED', 'TRAP', 'DETAIL'):
            with self.subTest(marker=marker), self.assertRaisesRegex(ValueError, 'veto'):
                c.console_gate(self.console+'\n'+marker)

    def test_missing_console_oracle(self):
        with self.assertRaisesRegex(ValueError, 'Missing/ambiguous'):
            c.console_gate(self.console.replace('RVV_GATHER_PREFIX_PASS', 'absent'))

    def test_actual_detail_partial_line_without_final_fail(self):
        first = (c.REF/'host/active.log').read_text().splitlines()[0]
        self.assertEqual(first, 'RVV_PERMUTE_DETAIL op=1 seed=0 scalar=0 vl=1 mask=0 '
                         'element=0 vstart=0 expected=185 actual=184')
        self.assertNotIn('FAIL', first)
        self.assertNotIn('\n', first)
        for partial in (first.split(' expected=', 1)[0], first):
            with self.subTest(partial=partial):
                # The runtime monitor uses this VETO too, before final oracle text exists.
                self.assertIsNotNone(c.VETO.search(partial))
                with self.assertRaisesRegex(ValueError, 'Raw failure/abort/parent-marker veto'):
                    c.console_gate(partial)
                with self.assertRaisesRegex(ValueError, 'Raw failure/abort/parent-marker veto'):
                    c.console_gate(self.console+'\n'+partial)

    def test_duplicate_console_oracle(self):
        with self.assertRaisesRegex(ValueError, 'Missing/ambiguous'):
            c.console_gate(self.console+'\nBOARD_REPLAY_PASS')

    def test_actual_detail_stops_real_host_monitor(self):
        import ara_verify.runner as engine
        first = (c.REF/'host/active.log').read_text().splitlines()[0]
        partial = first.split(' expected=', 1)[0]
        command = [sys.executable, '-c',
            'import os,time; os.write(1,'+repr(partial.encode())+'); time.sleep(30)']
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(engine, 'FAIL_RE', re.compile(engine.FAIL_RE.pattern+'|'+c.VETO.pattern, re.I)):
            code, elapsed, timed_out, failure_seen = engine._run_monitored(
                command, Path(tmp), Path(tmp)/'host.log', 10, threading.Event())
            self.assertTrue(failure_seen)
            self.assertFalse(timed_out)
            self.assertNotEqual(code, 0)
            self.assertLess(elapsed, 5)
            self.assertEqual((Path(tmp)/'host.log').read_text(), partial)
            abort = threading.Event()
            class Parent:
                def __init__(self): pass
                def _run_test(self, *_): return SimpleNamespace(status='FAIL', reason='raw marker')
            check = unittest.mock.Mock()
            replay.checked_runner(Parent, abort, check)()._run_test(None, None)
            self.assertTrue(abort.is_set())
            check.assert_not_called()

    def test_plan_drift(self):
        plan = dict(status='PREPARED_NOT_RUN', image=str(IMAGE), image_sha256=c.sha(IMAGE/'image.json'),
            case=self.case, spec=self.spec, jobs=1, timeout_s=9000, service_timeout_s=10200,
            unit=replay.UNIT, no_build=True, no_retry=True, no_fsdb=True,
            launch_requirements=replay.LAUNCH_REQUIREMENTS, reference_ready_sha256=replay.READY_SHA,
            pins={str(Path(replay.__file__).resolve()): c.sha(Path(replay.__file__))})
        replay.validate(plan, IMAGE)
        changes = [('timeout_s', 9001), ('service_timeout_s', 10800), ('jobs', 2),
            ('launch_requirements', []), ('no_build', False), ('image_sha256', '0'*64),
            ('case', dict(self.case, sha256='0'*64)), ('spec', dict(self.spec, element_bytes=2))]
        for key, value in changes:
            with self.subTest(key=key), self.assertRaises(ValueError):
                replay.validate(dict(plan, **{key: value}), IMAGE)

    def test_e16_acceptance_and_new_review_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root/'replay/tests/gather_prefix_e16_m8_ops1'
            (artifact/'work').mkdir(parents=True)
            rows = [dict(name='gather_prefix_e16_m8_ops1', status='PASS', returncode=0, elapsed_s=8000)]
            meta = dict(status='COMPLETE', status_counts={'PASS': 1},
                tests=['gather_prefix_e16_m8_ops1'], jobs=1, timeout_s=9000, completed_at='host-only')
            raw = dict(target_hits=98, fullcap_checks=50176, guards=196,
                returned_vstart_zero=98, routine_retire_counts=[98]*13)
            c.common.save(root/'replay/run.json', meta)
            c.common.save(root/'replay/summary.json', rows)
            c.common.save(artifact/'strict_prefix.json', dict(strict=raw))
            for n in ('input.elf', 'inputs.json', 'command.json', 'console.log', 'work/run.vcs.log',
                      'commit_trace.csv', 'trace_summary.json'):
                (artifact/n).write_text('synthetic host gate fixture only')
            plan = dict(image=str(IMAGE), image_sha256=c.sha(IMAGE/'image.json'))
            c.common.save(root/'plan.json', dict(plan, pins={str(artifact/'input.elf'): c.sha(artifact/'input.elf')}))
            complete = dict(status='PASS_M6_ORIGINAL_E16M8_PREFIX98_NOT_FULL_CHILD', aborted=False,
                pins_unchanged=True, plan_sha256=c.sha(root/'plan.json'), results=rows,
                evidence_pins={str(p): c.sha(p) for p in (root/'replay').rglob('*') if p.is_file()})
            c.common.save(root/'complete.json', complete)
            acceptance = root/'independent.md'
            acceptance.write_text('Synthetic parent-accepted review; not DUT evidence')
            review = dict(decision='AUTHORIZE_E8_PREFIX66_ONCE', plan_sha256='a'*64,
                unit=replay.UNIT, budget_risk_accepted=True, e16_terminal_accepted=True,
                e16_complete=dict(path=str(root/'complete.json'), sha256=c.sha(root/'complete.json')),
                e16_independent_acceptance=dict(path=str(acceptance), sha256=c.sha(acceptance)))
            path = root/'review.json'
            def check(r):
                c.common.save(path, r)
                return replay.authorization_gate(plan, 'a'*64, path, c.sha(path))
            self.assertIn(str(root/'complete.json'), check(review))
            for field, value in (('budget_risk_accepted', False), ('e16_terminal_accepted', False),
                                 ('plan_sha256', 'b'*64), ('decision', 'NOT_AUTHORIZED')):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    check(dict(review, **{field: value}))
            with self.assertRaises(ValueError):
                replay.authorization_gate(plan, 'a'*64, None, None)
            for field, value in (('status', 'RUNNING'), ('aborted', True), ('pins_unchanged', False),
                                 ('evidence_pins', {})):
                c.common.save(root/'complete.json', dict(complete, **{field: value}))
                changed = dict(review, e16_complete=dict(path=str(root/'complete.json'),
                                                        sha256=c.sha(root/'complete.json')))
                with self.subTest(terminal=field), self.assertRaises(ValueError):
                    check(changed)
            c.common.save(root/'complete.json', complete)
            acceptance.write_text('drift')
            with self.assertRaisesRegex(ValueError, 'Pinned input drift'):
                check(review)

    def test_elf_and_image_pin_drift(self):
        for label in ('elf', 'image'):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp)/label
                p.write_bytes(b'original')
                pins = {str(p): c.sha(p)}
                p.write_bytes(b'drift')
                with self.assertRaisesRegex(ValueError, 'Pinned input drift'):
                    c.common.base.verify_pins(pins)

    def test_late_abort_during_real_validation(self):
        abort = threading.Event()
        result = SimpleNamespace(status='PASS', reason='', returncode=0)
        class Parent:
            def __init__(self): self.cancel_event = threading.Event()
            def _run_test(self, *_): return result
        def check(_):
            rows = fixture(self.spec, self.model)
            def interrupt():
                for n, row in enumerate(rows):
                    if n == 3000:
                        abort.set()
                    yield row
            c.retirement(interrupt(), self.spec, self.model)
        got = replay.checked_runner(Parent, abort, check)()._run_test(None, None)
        self.assertTrue(abort.is_set())
        self.assertEqual(got.status, 'CANCELLED')

    def test_checker_exception_latches_abort(self):
        abort = threading.Event()
        class Parent:
            def __init__(self): pass
            def _run_test(self, *_): return SimpleNamespace(status='PASS')
        def check(_): raise ValueError('missing raw log')
        with self.assertRaisesRegex(ValueError, 'missing raw log'):
            replay.checked_runner(Parent, abort, check)()._run_test(None, None)
        self.assertTrue(abort.is_set())

    def test_terminal_complete_and_abort(self):
        abort = threading.Event()
        results = [SimpleNamespace(name=c.NAME, status='PASS', returncode=0)]
        meta = dict(status='COMPLETE', status_counts={'PASS': 1}, tests=[c.NAME], completed_at='now',
                    jobs=1, timeout_s=9000, simv=self.ledger['simv'], commit_trace=True, code_coverage=False)
        replay.terminal_gate(results, meta, abort, self.ledger)
        for field, value in (('status', 'INTERRUPTED'), ('tests', []), ('timeout_s', 12000), ('jobs', 2)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                replay.terminal_gate(results, dict(meta, **{field: value}), abort, self.ledger)
        abort.set()
        with self.assertRaisesRegex(ValueError, 'Sticky abort'):
            replay.terminal_gate(results, meta, abort, self.ledger)

    def test_publish_rejects_pending_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            abort = threading.Event()
            terminal = dict(status=replay.PASS)
            with patch.object(signal, 'sigpending', return_value={signal.SIGTERM}):
                c.common.publish(Path(tmp), terminal, abort)
            self.assertEqual(c.read(Path(tmp)/'complete.json')['status'], 'NOT_PASS')

    def test_capacity_alias(self):
        self.assertTrue(c.common.is_simv('renamed', ['/some/simv']))
        self.assertTrue(c.common.is_simv('simv', ['/some/renamed']))
        with self.assertRaises(ValueError):
            c.common.resource_math([dict(argv=['simv'])]*24, 64*1024**3, c.HERE, 1, 0)

    def test_sanitized_service_bus(self):
        unit = replay.UNIT
        group = '/user.slice/'+unit
        props = dict(Id=unit, LoadState='loaded', ActiveState='active', SubState='running',
            MainPID=str(os.getpid()), ControlGroup=group, RuntimeMaxUSec='2h 50min',
            KillMode='control-group', Restart='no')
        reply = SimpleNamespace(returncode=0, stderr='', stdout='\n'.join(k+'='+v for k, v in props.items()))
        real_read = Path.read_text
        def read_path(p, *args, **kwargs):
            return '0::'+group+'\n' if str(p) == '/proc/self/cgroup' else real_read(p, *args, **kwargs)
        with patch.dict(os.environ, {'PATH': '/usr/bin', 'HOME': os.environ['HOME']}, clear=True), \
             patch.object(replay.subprocess, 'run', return_value=reply) as query, \
             patch.object(Path, 'read_text', read_path):
            replay.service_identity(unit)
            env = query.call_args.kwargs['env']
            self.assertEqual(env['XDG_RUNTIME_DIR'], '/run/user/'+str(os.getuid()))
            self.assertEqual(env['DBUS_SESSION_BUS_ADDRESS'], 'unix:path='+env['XDG_RUNTIME_DIR']+'/bus')
            reply.returncode, reply.stdout, reply.stderr = 1, '', 'Failed to connect to bus: No medium found'
            with self.assertRaisesRegex(ValueError, 'Service query error'):
                replay.service_identity(unit)


if __name__ == '__main__':
    destination = c.HERE/'host01.json'
    c.require(not destination.exists(), 'Fresh host record only')
    log = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Gates)
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    c.common.save(destination, dict(status='PASS_HOST_ONLY' if result.wasSuccessful() else 'FAIL_HOST_ONLY',
        tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        log=log.getvalue(), synthetic_protocol_fixture_not_DUT=True,
        script_sha256=c.sha(Path(__file__))))
    print(log.getvalue(), flush=True)
    raise SystemExit(not result.wasSuccessful())

