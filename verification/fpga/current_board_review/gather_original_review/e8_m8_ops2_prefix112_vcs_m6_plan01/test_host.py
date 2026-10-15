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
        if j == 0 and fault == 'index_pointer':
            args[1] = a['indices16']
        for reg, value in enumerate(args, 10):
            yield row(rd=reg, value=value)
        for i, instr in enumerate(spec['routine']):
            insn = int(instr['insn'], 16)
            if j == 0 and i == 8 and fault == 'encoding':
                insn ^= 0x100
            if j == 0 and i == 8 and fault == 'vx_encoding':
                insn = (insn & ~(7 << 12)) | (4 << 12)
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
            if j == 17 and k == 1 and fault in ('active_vi31', 'out_of_vl_zero'):
                assert gold['vl']==1 and gold['vstart']==0 and value==185
                value = model['input'][31] if fault == 'active_vi31' else 0
            if j == 65 and k == 512 and fault == 'signed_oor0':
                assert gold['vl']==512 and gold['vstart']==256 and value==185
                value = 0
            if j == 48 and k == 3 and fault == 'ei16_dynamic':
                assert model['indices16'][2]==1023 and value==185 and model['input'][1023]!=185
                value = model['input'][model['indices16'][2]]
            if j == 32 and k == 1 and fault == 'prestart':
                assert gold['vstart']==1 and gold['vl']==2 and value==91
                value = 185
            if j == 17 and k == 2 and fault == 'tail':
                assert gold['vstart']==0 and gold['vl']==1 and value==91
                value = 185
            if j == 41 and k == 2 and fault == 'inactive':
                assert gold['vstart']==1 and gold['vl']==2 and value==91
                assert not ((gold['predicate'][1//8] >> (1%8)) & 1)
                value = 185
            if j == 0 and k == 0 and fault == 'guard0':
                value ^= 1
            if j == 65 and k == 1024 and fault == 'missing_full_tail':
                assert gold['vl']==512 and value==91
                continue
            if fault == 'missing_last80' and j == 111 and (k == 0 or k >= 947):
                continue
            if fault == 'wrong_last_guard' and j == 111 and k == 1025:
                value ^= 1
            if fault == 'missing_upper512' and 513 <= k <= 1024:
                continue
            if fault == 'upper_vl1023_tail' and j == 80 and k == 1024:
                assert gold['vl'] == 1023 and value == 91
                value = 185
            if fault == 'upper_prestart' and j == 98 and k == 1023:
                assert gold['vstart'] == 1023 and value == 91
                value = 185
            if fault == 'upper_alloff' and j == 108 and k == 701:
                assert gold['vl'] == 1024 and gold['tuple'][4] == 3 and value == 91
                value = 185
            if fault == 'final_enabled' and j == 98 and k == 1024:
                assert gold['vstart'] == 1023 and value == 185
                value = 91
            if fault == 'final_disabled' and j == 106 and k == 1024:
                assert gold['vstart'] == 1023 and value == 91
                value = 185
            if fault == 'last_alloff' and j == 111 and k == 1024:
                assert gold['vstart'] == 1023 and value == 91
                value = 185
            insn = 0x5003 if j == 0 and k == 1 and fault == 'halfword_oracle' else 0x4003
            yield row(insn=insn, rd=5, value=value, address=a['output']+k,
                      rmask=1 << ((a['output']+k) % 8))
        if (j == 0 and fault == 'truncated') or (j == 65 and fault == 'old66_only'):
            return
    yield row(pc=spec['exit_store']['pc'], insn=(int(spec['exit_store']['insn'], 16) ^ (0x100 if fault == 'wrong_exit_code' else 0)),
              address=spec['exit_address'], wmask=255, wdata=int(fault == 'bad_exit'))
    yield row(pc=spec['park']['pc'], insn=int(spec['park']['insn'], 16), rd=int(fault == 'bad_park'))


class Gates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger, _, _ = c.common.image_context(IMAGE)
        cls.case, cls.spec = replay.scope()
        cls.model = c.source.model()
        cls.console = '\n'.join(['BOARD_CASE_BEGIN '+c.NAME, 'RVV_GATHER_PREFIX_PASS sew=8 cases=112 errors=0',
            'BOARD_CASE_PASS '+c.NAME, 'BOARD_REPLAY_PASS', 'Core Test *** SUCCESS *** (tohost = 0)', '$finish'])

    def test_full112_and_generic_positive(self):
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
            self.assertEqual(raw['target_hits'], 112)
            self.assertEqual(raw['actual_output_scalar_loads'], 114912)
            self.assertEqual(raw['routine_retire_counts'], [112]*13)
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
    def test_vi0_index_pointer(self): self.negative_trace('index_pointer', 'arguments differ')
    def test_vi0_active_vi31(self): self.negative_trace('active_vi31', 'call18 index1')
    def test_vi0_out_of_vl_zero(self): self.negative_trace('out_of_vl_zero', 'call18 index1')
    def test_vi0_signed_oor0(self): self.negative_trace('signed_oor0', 'call66 index512')
    def test_vi0_ei16_dynamic(self): self.negative_trace('ei16_dynamic', 'call49 index3')
    def test_vi0_prestart(self): self.negative_trace('prestart', 'call33 index1')
    def test_vi0_tail(self): self.negative_trace('tail', 'call18 index2')
    def test_vi0_inactive(self): self.negative_trace('inactive', 'call42 index2')
    def test_guard0(self): self.negative_trace('guard0', 'call1 index0')
    def test_vx_encoding(self): self.negative_trace('vx_encoding', 'Original13')
    def test_missing_full_tail(self): self.negative_trace('missing_full_tail', 'Missing full oracle')
    def test_halfword_oracle(self): self.negative_trace('halfword_oracle', 'Oracle must be LBU')
    def test_missing_oracle(self): self.negative_trace('missing_oracle', 'Missing full oracle')
    def test_truncated(self): self.negative_trace('truncated', 'Missing calls')
    def test_exit(self): self.negative_trace('bad_exit', 'CTRL exit')
    def test_park(self): self.negative_trace('bad_park', 'Post-exit')


    def test_missing_last80_reads(self): self.negative_trace('missing_last80', 'Missing full oracle')
    def test_wrong112_last_guard(self): self.negative_trace('wrong_last_guard', 'call112 index1025')
    def test_missing_upper512(self): self.negative_trace('missing_upper512', 'Missing full oracle')
    def test_upper_vl1023_tail(self): self.negative_trace('upper_vl1023_tail', 'call81 index1024')
    def test_upper_prestart1023(self): self.negative_trace('upper_prestart', 'call99 index1023')
    def test_upper_alloff(self): self.negative_trace('upper_alloff', 'call109 index701')
    def test_final_element_enabled(self): self.negative_trace('final_enabled', 'call99 index1024')
    def test_final_element_disabled(self): self.negative_trace('final_disabled', 'call107 index1024')
    def test_last_alloff(self): self.negative_trace('last_alloff', 'call112 index1024')
    def test_old66_only_trace(self): self.negative_trace('old66_only', 'Missing calls')
    def test_wrong_exit_encoding(self): self.negative_trace('wrong_exit_code', 'CTRL exit')
    
    def test_old66_marker_not112(self):
        with self.assertRaisesRegex(ValueError, 'Missing/ambiguous'):
            c.console_gate(self.console.replace('cases=112', 'cases=66'))

    def test_vi31_encoding_not_vi0(self):
        wrong = copy.deepcopy(self.spec)
        wrong['routine'][8]['insn'] = '308fbc57'
        with self.assertRaisesRegex(ValueError, 'Original13'):
            c.retirement(fixture(wrong, self.model), self.spec, self.model)

    def test_reference_step_limit_not_dut_limit(self):
        with patch.object(c.source, 'MAX_RETIRED', 1):
            raw = c.retirement(fixture(self.spec, self.model), self.spec, self.model)
        self.assertEqual(raw['target_hits'], 112)
        self.assertGreater(raw['retired_rows'], 1)

    def test_exact112_membership_and_boundary_oracle(self):
        rows = self.model['rows']
        self.assertEqual([r['tuple'] for r in rows],
                         [[0,2,0,l,m,t] for l in range(7) for m in range(4) for t in range(4)])
        self.assertEqual(self.model['input'][0], 185)
        self.assertEqual(self.model['capacity'], 1024)
        for m in range(4):
            self.assertEqual([r['vstart'] for r in rows[96+4*m:100+4*m]], [1,512,1023,1023])
        self.assertEqual(rows[80]['output'][1023], 91)
        self.assertEqual(rows[98]['output'][1022:], [91,185])
        self.assertEqual(rows[106]['output'][1023], 91)
        self.assertEqual(rows[111]['output'], [91]*1024)

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
        first = (c.PREP/'host/active.log').read_text().splitlines()[0]
        self.assertEqual(first, 'RVV_PERMUTE_DETAIL op=2 seed=0 scalar=0 vl=1 mask=0 '
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
        first = (c.PREP/'host/active.log').read_text().splitlines()[0]
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

    def test_terminal_disk_plan_freshread_and_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            original = {'status': 'original'}
            c.common.save(out/'plan.json', original)
            digest = c.sha(out/'plan.json')
            with patch.object(replay, 'validate') as validate:
                replay.terminal_plan_gate(out, digest, IMAGE)
                validate.assert_called_once_with(original, IMAGE)
                validate.reset_mock()
                c.common.save(out/'plan.json', {'status': 'changed after in-memory read'})
                with self.assertRaisesRegex(ValueError, 'Plan file drift'):
                    replay.terminal_plan_gate(out, digest, IMAGE)
                validate.assert_not_called()

    def test_parent_review_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'review.json'
            review = dict(decision='AUTHORIZE_E8_VI0_PREFIX112_ONCE', plan_sha256='a'*64,
                unit=replay.UNIT, budget_risk_accepted=True,
                reference_ready_sha256=replay.READY_SHA, source_review_sha256=replay.REVIEW_SHA)
            def check(r):
                c.common.save(path, r)
                return replay.authorization_gate({}, 'a'*64, path, c.sha(path))
            self.assertIn(str(c.REF/'READY.json'), check(review))
            for field, value in (('budget_risk_accepted', False), ('reference_ready_sha256', 'b'*64),
                                 ('source_review_sha256', 'b'*64), ('plan_sha256', 'b'*64),
                                 ('unit', 'wrong.service'), ('decision', 'NOT_AUTHORIZED')):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    check(dict(review, **{field: value}))
            with self.assertRaises(ValueError):
                replay.authorization_gate({}, 'a'*64, None, None)
            with self.assertRaises(ValueError):
                replay.authorization_gate({}, 'a'*64, path, '0'*64)

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
