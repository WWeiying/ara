#!/usr/bin/env python3
"""Host-only scalar fixtures and gate negatives; all writes stay in owned G."""
import copy
import csv
import io
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
import replay as w
from replay import checker as c
from newscope import *


def synthetic_spec():
    routine = copy.deepcopy(c.read(c.REF / 'source_elf_proof.json')['soc_routine'])
    scalar = {0x13: 0x80009000, 0x23: 0x80009004, 0x1023: 0x80009008,
              0x4003: 0x8000900c, 0x5003: 0x80009010, 0xc2202573: 0x80009014}
    code = {str(pc): insn for insn, pc in scalar.items()}
    code.update({str(r['pc']): int(r['insn'], 16) for r in routine})
    capacity = dict(pc=0x80009018, insn='0022f557')
    exit_store = dict(pc=0x8000901c, insn='00a53023')
    park = dict(pc=0x80009020, insn='a001')
    code.update({str(r['pc']): int(r['insn'], 16) for r in (capacity, exit_store, park)})
    return dict(sew=SEW, lmul=LMUL_REGS, capacity=CAP, physical_predicate_bytes=PREDICATE_BYTES,
                routine=routine, capacity_vset=capacity, exit_store=exit_store, park=park,
                exit_address=0xd0000000, code=code, scalar_pcs=scalar,
                addresses=dict(input=0x90000000, indices=0x90001000, indices16=0x90002000,
                               predicate=0x90003000, output=0x90004000))


def fixture(spec, model, fault=None):
    order = cycle = 0
    def row(pc=None, insn=0x13, rd=0, value=0, address=0, rmask=0, wmask=0, wdata=0, event='retire'):
        nonlocal order, cycle
        if pc is None:
            pc = spec['scalar_pcs'][insn]
        result = dict(cycle=str(cycle), event=event, order=str(order), port='0', trans_id='0',
                      pc=f'{pc:x}', insn=f'{insn:x}', rd=str(rd), rd_wdata=f'{value:x}',
                      mem_addr=f'{address:x}', mem_rmask=f'{rmask:x}', mem_wmask=f'{wmask:x}',
                      mem_wdata=f'{wdata:x}', trap='0')
        cycle += 1
        if event == 'retire':
            order += 1
        return result
    for n in range(2):
        if fault == 'missing_vlenb' and n == 1:
            continue
        yield row(insn=0xc2202573, rd=10, value=64 if fault == 'vlenb' else VLENB)
    cap = spec['capacity_vset']
    yield row(pc=cap['pc'], insn=int(cap['insn'], 16), rd=10, value=1024 if fault == 'CAP' else CAP)
    a = spec['addresses']
    for j, gold in enumerate(model['rows']):
        for name, values, width in (
                ('input', model['input'], 1), ('indices', model['indices'], 1),
                ('indices16', model['indices16'], 2), ('predicate', gold['predicate'], 1),
                ('output', [91]*(CAP+2), 1)):
            for k, value in enumerate(values):
                if j == 0 and name == 'input' and k == 0:
                    if fault == 'missing_setup':
                        continue
                    if fault == 'rng':
                        value ^= 1
                if j == 0 and name == 'predicate' and k == 100 and fault == 'upper_predicate':
                    value = 1
                if j == 0 and name == 'predicate' and k == 0 and fault == 'mask_setup':
                    value ^= 1
                address = a[name]+width*k
                yield row(insn=0x1023 if width == 2 else 0x23, address=address,
                          wmask=((1 << width)-1) << (address % 8), wdata=value)
        args = [a['input'], a['indices'], a['output']+1, gold['vl'], CAP, a['predicate'], 0, gold['vstart']]
        if j == 0 and fault == 'args':
            args[7] += 1
        for reg, value in enumerate(args, 10):
            yield row(rd=reg, value=value)
        for i, instr in enumerate(spec['routine']):
            insn = int(instr['insn'], 16)
            if j == 0 and i == 8 and fault == 'immediate':
                insn ^= 1 << 15
            if j == 0 and i == 0 and fault == 'm8':
                insn ^= 1 << 20
            rd, value = 0, 0
            if i in (0, 5, 10):
                rd, value = 5, gold['vl'] if i == 5 else CAP
            elif i == 6:
                rd, value = 28, int(j == 0 and fault == 'wrong_scalar')
            elif i == 9:
                rd, value = 10, int(j == 0 and fault == 'vstart')
            yield row(pc=instr['pc'], insn=insn, rd=rd, value=value)
        for k, value in enumerate([91, *gold['output'], 91]):
            if j == 0 and k == 1 and fault == 'missing_oracle':
                continue
            if j == 0 and k == 0 and fault == 'guard0':
                value ^= 1
            if j == 0 and k == CAP+1 and fault == 'guard1':
                value ^= 1
            if j == 17 and k == 1 and fault == 'scalar0_output':
                value = model['input'][0]
            if j == 32 and k == 1 and fault == 'prestart':
                value = 177
            if j == 17 and k == 2 and fault == 'tail':
                value = 177
            if j == 41 and k == 2 and fault == 'inactive':
                value = 177
            if j == 65 and k == CAP and fault == 'missing_full_tail':
                continue
            address = a['output']+k
            opcode = 0x5003 if j == 0 and k == 1 and fault == 'wrong_load' else 0x4003
            mask = 3 if j == 0 and k == 1 and fault == 'load_mask' else 1 << (address % 8)
            yield row(insn=opcode, rd=5, value=value, address=address, rmask=mask)
        if j == 0 and fault == 'partial':
            return
    r = spec['exit_store']
    yield row(pc=r['pc'], insn=int(r['insn'], 16), address=spec['exit_address'], wmask=255,
              wdata=int(fault == 'exit'))
    r = spec['park']
    yield row(pc=r['pc'], insn=int(r['insn'], 16), rd=int(fault == 'park'))


class Host(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec, cls.model = synthetic_spec(), c.model()
        cls.console = '\n'.join(['BOARD_CASE_BEGIN '+RUNTIME_ID,
            'RVV_GATHER_PREFIX_PASS sew=8 cases=66 errors=0', 'BOARD_CASE_PASS '+RUNTIME_ID,
            'BOARD_REPLAY_PASS', 'Core Test *** SUCCESS *** (tohost = 0)', '$finish'])

    def test_full_scope_positive(self):
        report = c.retirement(fixture(self.spec, self.model), self.spec, self.model)
        self.assertEqual((report['fullcap_checks'], report['guards'], report['actual_output_scalar_loads']),
                         (33792, 132, 33924))
        self.assertEqual(report['routine_retire_counts'], [66]*13)
        self.assertEqual((report['setup_values_per_call'], report['setup_bytes_per_call']), (2178, 2690))
        self.assertEqual(report['calls'][-1]['original_tuple'], ENDPOINT)
        self.assertEqual(report['returned_vstart_zero'], 66)

    def trace_negative(self, fault, message):
        with self.assertRaisesRegex(ValueError, message):
            c.retirement(fixture(self.spec, self.model, fault), self.spec, self.model)

    def test_wrong_scalar(self): self.trace_negative('wrong_scalar', 'scalar/start/VL')
    def test_wrong_immediate(self): self.trace_negative('immediate', 'PC/code')
    def test_wrong_cap(self): self.trace_negative('CAP', 'capacity not512')
    def test_m4_not_m8(self): self.trace_negative('m8', 'PC/code')
    def test_guard0(self): self.trace_negative('guard0', 'Full oracle')
    def test_guard1(self): self.trace_negative('guard1', 'Full oracle')
    def test_prestart(self): self.trace_negative('prestart', 'Full oracle')
    def test_tail(self): self.trace_negative('tail', 'Full oracle')
    def test_masked_inactive(self): self.trace_negative('inactive', 'Full oracle')
    def test_vstart(self): self.trace_negative('vstart', 'vstart nonzero')
    def test_scalar0_not_vi31(self): self.trace_negative('scalar0_output', 'Full oracle')
    def test_missing_full_tail(self): self.trace_negative('missing_full_tail', 'Missing full oracle')
    def test_missing_oracle(self): self.trace_negative('missing_oracle', 'Missing full oracle')
    def test_setup_missing(self): self.trace_negative('missing_setup', 'Missing initialized')
    def test_setup_rng(self): self.trace_negative('rng', 'Setup/RNG')
    def test_mask_setup(self): self.trace_negative('mask_setup', 'Setup/RNG')
    def test_physical_upper_predicate(self): self.trace_negative('upper_predicate', 'Setup/RNG')
    def test_wrong_args(self): self.trace_negative('args', 'arguments differ')
    def test_wrong_scalar_load(self): self.trace_negative('wrong_load', 'Oracle must be scalar LBU')
    def test_wrong_load_mask(self): self.trace_negative('load_mask', 'Oracle must be scalar LBU')
    def test_actual_vlenb(self): self.trace_negative('vlenb', 'vlenb not128')
    def test_two_vlenb_reads(self): self.trace_negative('missing_vlenb', 'Missing actual')
    def test_partial_trace(self): self.trace_negative('partial', 'Missing calls')
    def test_exit_code(self): self.trace_negative('exit', 'CTRL exit')
    def test_post_exit_park(self): self.trace_negative('park', 'Post-exit')

    def test_wrong_pc(self):
        rows = fixture(self.spec, self.model)
        def changed():
            for n, row in enumerate(rows):
                if n == 0:
                    row['pc'] = 'deadbeef'
                yield row
        with self.assertRaisesRegex(ValueError, 'PC/code'):
            c.retirement(changed(), self.spec, self.model)

    def test_console_positive_and_runtime_id(self):
        c.console_gate(self.console)
        with self.assertRaisesRegex(ValueError, 'runtime oracle'):
            c.console_gate(self.console.replace(RUNTIME_ID, SOURCE_LABEL))

    def test_console_fail_even_with_pass(self):
        for marker in ('RVV_GATHER_PREFIX_FAIL', 'RVV_PERMUTE_DETAIL op=3', 'RVV_PERMUTE_PASS',
                       'FAIL', 'TRAP', 'ABORTED', 'BOARD_REPLAY_MISMATCH'):
            with self.subTest(marker=marker), self.assertRaisesRegex(ValueError, 'veto'):
                c.console_gate(self.console+'\n'+marker)

    def test_missing_duplicate_console(self):
        for text in (self.console.replace('$finish', ''), self.console+'\nBOARD_REPLAY_PASS'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                c.console_gate(text)

    def temp(self):
        return tempfile.TemporaryDirectory(prefix='host-', dir=c.HERE)

    def runner_fixture(self, root, rc=0, command=True):
        result = SimpleNamespace(name=RUNTIME_ID, status='PASS' if rc == 0 else 'FAIL',
                                 returncode=rc, elapsed_s=2.0, reason='' if rc == 0 else 'first child failure',
                                 artifact_dir=root)
        args = w.monitor_command([], root, '/synthetic-host-fixture/simv')
        if command:
            w.durable(root / 'command.json', dict(command=args, cwd=str(root / 'work')))
        class Parent:
            def __init__(self): pass
            def _run_test(self, *_):
                callback = w.monitored(lambda *a, **k: (rc, 2.0, False, False), self.cancel_event,
                                       root, '/synthetic-host-fixture/simv')
                callback(args, root / 'work', root / 'console.log', TIMEOUT, self.cancel_event)
                return result
        return Parent, result

    def test_postcheck_preserves_rc0_and17(self):
        for rc in (0, 17):
            with self.subTest(rc=rc), self.temp() as folder:
                root = Path(folder)
                parent, result = self.runner_fixture(root, rc, command=False)
                abort = threading.Event()
                check = Mock(side_effect=ValueError('strict checker failure'))
                with self.assertRaises(FileNotFoundError):
                    w.checked_runner(parent, abort, check, Mock())()._run_test(SimpleNamespace(name=RUNTIME_ID), None)
                child = c.read(root / 'child_outcome.unvalidated.json')
                self.assertIs(type(child['returncode']), int)
                self.assertEqual(child['returncode'], rc)
                self.assertFalse(child['architectural_acceptance'])
                self.assertTrue(abort.is_set())
                self.assertEqual(c.read(root / 'first_cause.json')['kind'],
                                 'POSTCHECK_EXCEPTION' if rc == 0 else 'MONITOR_OUTCOME')

    def test_checker_exception_preserves_rc0(self):
        with self.temp() as folder:
            root = Path(folder)
            parent, _ = self.runner_fixture(root)
            abort = threading.Event()
            def check(result):
                self.assertEqual(c.read(root / 'child_outcome.unvalidated.json')['returncode'], 0)
                raise ValueError('postcheck evidence error')
            with self.assertRaisesRegex(ValueError, 'postcheck evidence error'):
                w.checked_runner(parent, abort, check, Mock())()._run_test(SimpleNamespace(name=RUNTIME_ID), None)
            self.assertTrue(abort.is_set())
            self.assertEqual(c.read(root / 'first_cause.json')['returncode'], 0)

    def test_failure_firstcause_not_replaced(self):
        with self.temp() as folder:
            root = Path(folder)
            w.first_cause(root, dict(kind='original'))
            w.first_cause(root, dict(kind='later'))
            self.assertEqual(c.read(root / 'first_cause.json'), dict(kind='original'))

    def test_no_retry(self):
        with self.temp() as folder:
            root = Path(folder)
            parent, result = self.runner_fixture(root)
            w.persist_unvalidated(result)
            with self.assertRaises(FileExistsError):
                w.persist_unvalidated(result)

    def test_late_abort(self):
        with self.temp() as folder:
            root = Path(folder)
            parent, _ = self.runner_fixture(root)
            abort = threading.Event()
            got = w.checked_runner(parent, abort, lambda _: abort.set(), Mock())()._run_test(
                SimpleNamespace(name=RUNTIME_ID), None)
            self.assertEqual(got.status, 'CANCELLED')
            self.assertEqual(c.read(root / 'child_outcome.unvalidated.json')['returncode'], 0)
            self.assertTrue(abort.is_set())

    def test_publication_late_signal(self):
        with self.temp() as folder:
            with patch.object(signal, 'sigpending', return_value={signal.SIGTERM}):
                abort = threading.Event()
                c.common.publish(Path(folder), dict(status=PASS), abort)
            self.assertEqual(c.read(Path(folder) / 'complete.json')['status'], 'NOT_PASS')

    def test_terminal_membership_and_complete(self):
        result = SimpleNamespace(name=RUNTIME_ID, status='PASS', returncode=0, elapsed_s=2, reason='')
        meta = dict(status='COMPLETE', status_counts={'PASS': 1}, tests=[RUNTIME_ID], completed_at='host',
                    jobs=1, timeout_s=5400, seed=1, simv='frozen-host-fixture', commit_trace=True, code_coverage=False)
        ledger = dict(simv='frozen-host-fixture')
        w.terminal_gate([result], meta, threading.Event(), ledger)
        for results, metadata in (([], meta), ([result, result], meta),
                ([result], dict(meta, tests=[SOURCE_LABEL])), ([result], dict(meta, status='RUNNING')),
                ([result], dict(meta, jobs=2)), ([result], dict(meta, timeout_s=5401)),
                ([result], dict(meta, code_coverage=True))):
            with self.subTest(metadata=metadata), self.assertRaises(ValueError):
                w.terminal_gate(results, metadata, threading.Event(), ledger)
        abort = threading.Event()
        abort.set()
        with self.assertRaisesRegex(ValueError, 'Sticky abort'):
            w.terminal_gate([result], meta, abort, ledger)

    def test_pin_drift(self):
        with self.temp() as folder:
            path = Path(folder) / 'source-image-fixture'
            path.write_bytes(b'old')
            pins = {str(path): c.sha(path)}
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'Pinned input drift'):
                c.common.base.verify_pins(pins)

    def test_late_disk_plan_drift(self):
        with self.temp() as folder:
            root = Path(folder)
            w.durable(root / 'plan.json', dict(status='host-fixture'))
            digest = c.sha(root / 'plan.json')
            with patch.object(w, 'validate') as validate:
                w.terminal_plan_gate(root, digest, Path(IMAGE))
                validate.assert_called_once()
                (root / 'plan.json').write_text('{}')
                with self.assertRaisesRegex(ValueError, 'disk plan drift'):
                    w.terminal_plan_gate(root, digest, Path(IMAGE))

    def test_resource_caps(self):
        self.assertEqual(c.common.resource_math([], 32*1024**3, c.HERE, 1, 23)['total'], 24)
        for available, reserve in ((32*1024**3-1, 0), (64*1024**3, 24)):
            with self.assertRaisesRegex(ValueError, 'Resource cap/memory'):
                c.common.resource_math([], available, c.HERE, 1, reserve)

    def test_owned_direct_worker(self):
        group = '/user.slice/'+UNIT
        props = dict(Id=UNIT, LoadState='loaded', ActiveState='active', SubState='running', MainPID='123',
                     ControlGroup=group, RuntimeMaxUSec='1h 50min', KillMode='control-group', Restart='no')
        w.owner_gate(props, '0::'+group, 123)
        for key, value in (('MainPID', '124'), ('KillMode', 'process'), ('RuntimeMaxUSec', '3h'), ('Restart', 'always')):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'Direct owning'):
                w.owner_gate(dict(props, **{key: value}), '0::'+group, 123)

    def test_unresolved_audit_and_parent(self):
        with self.assertRaisesRegex(ValueError, 'unresolved HOLD'):
            w.accepted_reference(None, None, None, None)
        with self.assertRaisesRegex(ValueError, 'parent authorization'):
            w.authorization_gate({}, None, None, None)
        with self.temp() as folder:
            out = Path(folder) / 'cannot_prepare'
            with self.assertRaises(ValueError):
                w.prepare(Path(IMAGE), out, 0, None, None, None, None)
            self.assertFalse(out.exists())

    def test_old_ready_refused_before_audit(self):
        with self.assertRaisesRegex(ValueError, 'old READY refused'):
            w.accepted_reference(c.REF / 'READY.json', OLD_READY_SHA,
                                 c.HERE.parent / 'e8_m4_ops3_prefix66_reference_audit01/missing.json', '0'*64)

    def actual_audit_payload(self):
        root = c.HERE.parent / 'e8_m4_ops3_prefix66_reference_audit01'
        return (c.read(c.REF / 'READY02.json'), c.read(root / 'audit.json'),
                c.read(root / 'execution.json'), c.read(root / 'execution_started.json'),
                c.read(c.REF / 'reference/reference.json'))

    def test_actual_audit_payload(self):
        w.audit_payload_gate(*self.actual_audit_payload())

    def test_actual_audit_payload_negatives(self):
        ready, audit, execution, started, reference = self.actual_audit_payload()
        changes = [('calls', audit['calls'][:-1]), ('full_results', 67584), ('guards', 131),
                   ('helper_counts', [65]*13), ('physical_predicate_bytes', 64),
                   ('firmware_retired', 2621149), ('pins_pre_post_unchanged', False),
                   ('full_original_binary_proof_sha256', OLD_READY_SHA), ('raw_parses', 2),
                   ('full2688_execution', True), ('DUT', True)]
        for key, value in changes:
            with self.subTest(key=key), self.assertRaises(ValueError):
                w.audit_payload_gate(ready, dict(audit, **{key: value}), execution, started, reference)

    def test_actual_independent_execution_negatives(self):
        ready, audit, execution, started, reference = self.actual_audit_payload()
        for key, value in [('returncode', 17), ('returncode', None), ('timed_out', True),
                           ('retries', 1), ('elapsed_s', 601), ('child_pid', 0),
                           ('command', ['not-the-authorized-auditor']), ('audit_pins_sha256', OLD_READY_SHA)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                w.audit_payload_gate(ready, audit, dict(execution, **{key: value}), started, reference)

    def test_actual_reference_binding(self):
        root = c.HERE.parent / 'e8_m4_ops3_prefix66_reference_audit01'
        ready, pins = w.accepted_reference(c.REF / 'READY02.json', READY02_SHA, root / 'audit.json', AUDIT_SHA)
        self.assertTrue(ready['entire_original_linux_binary_rebuild_proven'])
        self.assertEqual(pins[str(root / 'execution.json')], AUDIT_EXECUTION_SHA)
        self.assertEqual(pins[str(root / 'REVIEW.md')], REVIEW_SHA)
        self.assertEqual(pins[str(c.REF / 'original_linux_rebuild02/proof.json')], ORIGINAL_PROOF_SHA)

    def test_conflicting_source_image_pins(self):
        with self.assertRaisesRegex(ValueError, 'Conflicting input pin'):
            w.merge_pins({'source': READY02_SHA}, {'source': OLD_READY_SHA})

    def test_fixed_runner_options_and_dryrun(self):
        def options(**kwargs):
            return SimpleNamespace(code_coverage=False, **kwargs)
        for dry in (False, True):
            with self.subTest(dry=dry):
                opts = w.build_options(options, Path('/readonly-host-fixture'), c.HERE,
                                       dict(simv='/readonly-host-fixture/simv'), dry)
                self.assertEqual((opts.jobs, opts.seed, opts.timeout_s), (1, 1, 5400))
                self.assertEqual(opts.dry_run, dry)
                self.assertFalse(opts.build_only or opts.code_coverage)
                self.assertTrue(opts.skip_build)

    def test_reference_metadata_and_raw_distinct_hashes(self):
        ready, audit, execution, started, reference = self.actual_audit_payload()
        self.assertEqual(c.sha(c.REF / 'reference/reference.json'), ready['reference_sha256'])
        self.assertNotEqual(ready['reference_sha256'], audit['raw_sha256'])
        self.assertEqual(reference['commit_sha256'], audit['raw_sha256'])
        w.audit_payload_gate(ready, audit, execution, started, reference)
        with self.assertRaisesRegex(ValueError, 'full-EOF/raw identity'):
            w.audit_payload_gate(ready, audit, execution, started,
                                 dict(reference, commit_sha256=ready['reference_sha256']))

    def frozen_parent(self, folder):
        # Load the actual sealed M6 parent, but never call its build/run or monitor process.
        ledger, repo, (parent, options, testcase, _) = c.common.image_context(Path(IMAGE))
        import ara_verify.runner as engine
        self.assertTrue(Path(engine.__file__).resolve().is_relative_to(repo))
        out = Path(folder) / 'replay'
        root = out / 'tests' / RUNTIME_ID
        root.mkdir(parents=True)
        elf = c.REF / 'soc01' / (RUNTIME_ID+'.elf')
        (root / 'input.elf').write_bytes(elf.read_bytes())
        case = testcase(RUNTIME_ID, 'app', '', elf, RUNTIME_ID, TIMEOUT)
        # Construct options without the production output suffix helper.
        opts = options(repo_root=repo, output_root=out, config='default', jobs=1, seed=1,
                       dry_run=False, build_only=False, skip_build=True, simv=Path(ledger['simv']),
                       commit_trace=True, timeout_s=TIMEOUT)
        abort = threading.Event()
        check = Mock()
        runner = w.checked_runner(parent, abort, check, Mock())(opts, [case], ['HOST_ONLY_NOT_DUT'])
        runner._frozen_binaries[RUNTIME_ID] = c.sha(elf)
        runner._suite_frozen = True
        return ledger, engine, runner, case, root, abort, check

    def frozen_generic_error(self, rc, stage):
        with self.temp() as folder:
            ledger, engine, runner, case, root, abort, check = self.frozen_parent(folder)
            def fake_monitor(*args):
                (root / 'console.log').write_text(self.console)
                if stage == 'trace':
                    (root / 'commit_trace.csv').write_text('host fixture,not DUT\n')
                return rc, 2.0, False, False
            real_read = Path.read_text
            def read_path(path, *args, **kwargs):
                if stage == 'console' and path == root / 'console.log':
                    self.assertEqual(c.read(root / 'child_outcome.unvalidated.json')['returncode'], rc)
                    raise OSError('actual frozen generic console postcheck')
                return real_read(path, *args, **kwargs)
            def generic_failure(*args, **kwargs):
                self.assertEqual(c.read(root / 'child_outcome.unvalidated.json')['returncode'], rc)
                raise OSError('actual frozen generic '+stage+' postcheck')
            target = 'validate_trace' if stage == 'trace' else 'check_inputs'
            with patch.object(engine, '_run_monitored', fake_monitor), \
                 patch.object(engine, 'simulation_image', return_value=ledger['files']), \
                 patch.object(Path, 'read_text', read_path), \
                 patch.object(engine, target, side_effect=generic_failure), \
                 w.engine_hooks(engine, abort, root, ledger['simv']):
                with self.assertRaisesRegex(OSError, 'actual frozen generic'):
                    runner._run_test(case, Path(ledger['simv']))
            child = c.read(root / 'child_outcome.unvalidated.json')
            self.assertEqual(child['returncode'], rc)
            self.assertFalse(child['architectural_acceptance'])
            self.assertEqual(child['name'], RUNTIME_ID)
            self.assertEqual(child['source_label'], SOURCE_LABEL)
            self.assertFalse((root / 'runner_result.unvalidated.json').exists())
            self.assertTrue(abort.is_set())
            check.assert_not_called()
            self.assertEqual(c.read(root / 'first_cause.json')['kind'],
                             'POSTCHECK_EXCEPTION' if rc == 0 else 'MONITOR_OUTCOME')

    def test_actual_frozen_parent_console_error_rc0_and17(self):
        for rc in (0, 17):
            with self.subTest(rc=rc):
                self.frozen_generic_error(rc, 'console')

    def test_actual_frozen_parent_inputs_error_rc0_and17(self):
        for rc in (0, 17):
            with self.subTest(rc=rc):
                self.frozen_generic_error(rc, 'inputs')

    def test_actual_frozen_parent_trace_error_preserves_rc0(self):
        self.frozen_generic_error(0, 'trace')

    def test_actual_frozen_parent_timeout_preserves_numeric_wait(self):
        with self.temp() as folder:
            ledger, engine, runner, case, root, abort, check = self.frozen_parent(folder)
            with patch.object(engine, '_run_monitored', return_value=(-9, 5400.0, True, False)), \
                 patch.object(engine, 'simulation_image', return_value=ledger['files']), \
                 w.engine_hooks(engine, abort, root, ledger['simv']):
                result = runner._run_test(case, Path(ledger['simv']))
            self.assertEqual(result.status, 'TIMEOUT')
            self.assertIsNone(result.returncode)
            child = c.read(root / 'child_outcome.unvalidated.json')
            self.assertEqual(child['returncode'], -9)
            self.assertTrue(child['timed_out'])
            self.assertIsNone(c.read(root / 'runner_result.unvalidated.json')['returncode'])
            self.assertEqual(c.read(root / 'first_cause.json')['kind'], 'MONITOR_OUTCOME')
            self.assertTrue(abort.is_set())
            check.assert_not_called()

    def test_monitor_private_runtime_command_gate(self):
        with self.temp() as folder:
            root = Path(folder)
            original = Mock(return_value=(0, 1.0, False, False))
            abort = threading.Event()
            callback = w.monitored(original, abort, root, '/host-fixture/simv')
            args = w.monitor_command([], root, '/host-fixture/simv')
            args[5] = '+TESTCASE='+SOURCE_LABEL
            with self.assertRaisesRegex(ValueError, 'runtime/private-CWD'):
                callback(args, root / 'work', root / 'console.log', TIMEOUT, abort)
            original.assert_not_called()
            self.assertTrue(abort.is_set())
            self.assertFalse((root / 'child_outcome.unvalidated.json').exists())


if __name__ == '__main__':
    destination = c.HERE / w.HOST_REPORT
    c.require(not destination.exists(), 'Fresh host evidence only; no automatic retry')
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Host))
    names = ('newscope.py', 'checker.py', 'replay.py', 'test_host.py', 'README.md')
    pins = {str(c.HERE / name): c.sha(c.HERE / name) for name in names}
    pins[str(c.REF / 'reference_check.py')] = c.sha(c.REF / 'reference_check.py')
    pins[str(c.REF / 'scope.py')] = c.sha(c.REF / 'scope.py')
    audit_root = c.HERE.parent / 'e8_m4_ops3_prefix66_reference_audit01'
    for path in (c.REF / 'READY02.json', audit_root / 'audit.json', audit_root / 'execution.json',
                 audit_root / 'execution_started.json', audit_root / 'REVIEW.md',
                 c.REF / 'original_linux_rebuild02/proof.json'):
        pins[str(path)] = c.sha(path)
    pins[str(c.REF / 'reference/reference.json')] = c.sha(c.REF / 'reference/reference.json')
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).is_file() and 'current_board_memory_candidate06/frozen/' in str(path):
            pins[str(Path(path).resolve())] = c.sha(Path(path))
    w.durable(destination, dict(status='PASS_HOST_ONLY_NOT_DUT' if result.wasSuccessful() else 'FAIL_HOST_ONLY_NOT_DUT',
                               tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                               log=stream.getvalue(), pins=pins,
                               actual_independent_acceptance='ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT',
                               independent_audit_sha256=AUDIT_SHA, reference_ready_sha256=READY02_SHA,
                               parent_approval='UNRESOLVED', prepared_plan=False, VCS_started=False,
                               synthetic_protocol_fixture_not_DUT=True))
    print(stream.getvalue(), flush=True)
    raise SystemExit(not result.wasSuccessful())
