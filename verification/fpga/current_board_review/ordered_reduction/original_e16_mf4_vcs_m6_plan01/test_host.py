#!/usr/bin/env python3
"""Synthetic protocol fixtures and monitor tests, not DUT or reference runs."""
import copy
import csv
import json
from pathlib import Path
import re
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
import replay
from replay import checker as c


def fixture(spec, fault=None):
    order = cycle = 0
    symbols, sites = spec['symbols'], spec['sites']
    lookup = spec['instructions']
    from ara_verify.trace import is_vector_instruction

    def row(pc, rd=0, value=0, address=0, rmask=0, wmask=0, wdata=0, event='retire', insn=None):
        nonlocal order, cycle
        code = int(lookup[f'{pc:x}']['insn'], 16) if insn is None else insn
        out = dict(cycle=str(cycle), event=event, order=str(order), port='0', trans_id='0',
                   pc=f'{pc:x}', insn=f'{code:x}', rd=str(rd), rd_wdata=f'{value:x}',
                   mem_addr=f'{address:x}', mem_rmask=f'{rmask:x}', mem_wmask=f'{wmask:x}',
                   mem_wdata=f'{wdata:x}', trap='0')
        cycle += 1
        if event == 'retire':
            order += 1
        return out

    def store(site, address, value, width):
        return row(sites[site], address=address, wmask=((1 << width) - 1) << (address % 8), wdata=value)

    def reg(regno, value):
        code = next(v for v in lookup.values() if
                    (int(v['insn'], 16) >> 7) & 31 == regno and
                    (int(v['insn'], 16) & 127 == 0x13 or
                     (int(v['insn'], 16) & 3 == 1 and int(v['insn'], 16) >> 13 == 2)))
        return row(code['pc'], rd=regno, value=value)

    yield row(symbols['capacity'], rd=5, value=(1 << 64) - 1)
    for index in range(3360):
        if index % 420 == 0:
            for i in range(16):
                value = 0xfc00 if i % 2 else 0x7c00
                if index == 1260 and i == 5 and fault == 'input':
                    value = 0x7c00
                yield store('input_store', symbols['input'] + 2 * i, value, 2)
            for i in range(64):
                value = 0x7c00
                if index == 1260 and i == 63 and fault == 'seed':
                    value = 0
                yield store('seed_store', symbols['seed'] + 2 * i, value, 2)
        for field in (0, 8):
            value = spec['fixtures'][3360 + index][field // 8]
            if index == 1545 and fault == 'bank':
                value = spec['fixtures'][index][field // 8]
            yield row(sites['fixture_bits' if field == 0 else 'fixture_flags'],
                      rd=14 if field == 0 else 15, value=value,
                      address=symbols['fixtures'] + (3360 + index) * 16 + field,
                      rmask=255 if field == 0 else 15)
        for i in range(64):
            if index == 0 and i == 0 and fault == 'missing_loop':
                continue
            value = 0x24 if not (fault == 'mask' and index == 1545 and i == 0) else 0
            yield store('mask_store', symbols['mask'] + i, value, 1)
        if index != 1545:
            continue
        for i in range(144):
            yield store('output_init', symbols['output'] + i, 0x5b, 1)
        args = [symbols['input'], symbols['seed'], symbols['output'] + 8, 8, 16, symbols['mask'], 0, 0]
        if fault == 'args':
            args[3] = 4
        if fault == 'pointer':
            args[1] = symbols['input']
        for r, value in enumerate(args, 10):
            yield reg(r, value)
        for i, instr in enumerate(spec['routine']):
            if i == 17 and fault == 'missing_restore':
                continue
            encoding = int(instr['insn'], 16)
            if i == 11 and fault == 'encoding':
                encoding ^= 1 << 25
            if is_vector_instruction(encoding):
                yield row(instr['pc'], event='cvx_req', insn=encoding)
                yield row(instr['pc'], event='cvx_resp', insn=encoding)
            values = {0: (5, 64), 3: (5, 16), 6: (5, 8), 7: (29, 0), 8: (30, 0),
                      12: (10, 0), 13: (6, 16), 14: (6, 16 << 32), 15: (10, 16 << 32), 18: (5, 64)}
            r, value = values.get(i, (0, 0))
            if fault == 'NV' and i == 13:
                value = 0
            if fault == 'vstart' and i == 12:
                value = 1
            if fault == 'saved_csr' and i == 7:
                value = 1
            if fault == 'type' and i == 3:
                value = 32
            yield row(instr['pc'], rd=r, value=value, insn=encoding)
        for i in range(144):
            if fault == 'missing_oracle' and i == 143:
                continue
            value = 0 if i == 8 else 0x7e if i == 9 else 0x5b
            corrupted = {'nan': 9, 'guard_left': 0, 'guard_right': 143, 'tail_first': 10, 'tail_last': 135}
            if fault in corrupted and i == corrupted[fault]:
                value ^= 1
            yield row(sites['output_read'], rd=16, value=value, address=symbols['output'] + i,
                      rmask=1 << ((symbols['output'] + i) % 8))
        if fault == 'truncated':
            return
    yield row(spec['exit_store']['pc'], address=spec['exit_address'], wmask=255, wdata=int(fault == 'exit'))
    yield row(spec['park']['pc'], rd=int(fault == 'park'))


class Gates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Only immutable file reads/imports; no process/service/resource queries.
        cls.ledger, _, _ = c.common.image_context(replay.IMAGE)
        replay.accepted_reference()
        cls.spec = c.specification()
        cls.console = '\n'.join(['BOARD_CASE_BEGIN ' + c.NAME, c.MARKER,
                'BOARD_CASE_PASS ' + c.NAME, 'BOARD_REPLAY_PASS', c.common.SUCCESS, '$finish'])

    def test_full_original_positive_with_generic_trace(self):
        from ara_verify.trace import validate_trace
        with tempfile.TemporaryDirectory(dir=c.HERE) as tmp:
            path = Path(tmp) / 'synthetic.csv'
            rows = fixture(self.spec)
            first = next(rows)
            with path.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(first))
                writer.writeheader()
                writer.writerow(first)
                writer.writerows(rows)
            generic = validate_trace(path)
            with path.open() as stream:
                strict = c.retirement(csv.DictReader(stream), self.spec)
            self.assertEqual(strict['output_bytes'], 144)
            self.assertEqual(strict['target_calls'], 1)
            self.assertEqual(strict['fixture_field_reads'], 6720)
            self.assertEqual(strict['retired_rows'], generic['retire_count'])

    def negative(self, fault, reason):
        with self.assertRaisesRegex(ValueError, reason):
            c.retirement(fixture(self.spec, fault), self.spec)

    def test_wrong_source(self): self.negative('input', 'setup: input')
    def test_missing_seed_last(self): self.negative('seed', 'setup: seed')
    def test_wrong_mask(self): self.negative('mask', 'setup: mask')
    def test_wrong_args(self): self.negative('args', 'arguments')
    def test_wrong_pointer(self): self.negative('pointer', 'arguments')
    def test_wrong_bank(self): self.negative('bank', 'Fixture')
    def test_encoding(self): self.negative('encoding', 'Actual ELF')
    def test_NV(self): self.negative('NV', 'flags/vstart')
    def test_vstart(self): self.negative('vstart', 'flags/vstart')
    def test_saved_CSR(self): self.negative('saved_csr', 'saved CSR')
    def test_restore_missing(self): self.negative('missing_restore', 'consecutively')
    def test_type_capacity(self): self.negative('type', 'vset')
    def test_nan(self): self.negative('nan', 'Original144')
    def test_guard_left(self): self.negative('guard_left', 'Original144')
    def test_guard_right(self): self.negative('guard_right', 'Original144')
    def test_tail_first(self): self.negative('tail_first', 'Original144')
    def test_tail_last(self): self.negative('tail_last', 'Original144')
    def test_missing_byte_oracle(self): self.negative('missing_oracle', 'Incomplete oracle')
    def test_missing_original_loop(self): self.negative('missing_loop', 'Incomplete original loops')
    def test_truncated(self): self.negative('truncated', 'Incomplete original loops')
    def test_exit(self): self.negative('exit', 'CTRL exit')
    def test_park(self): self.negative('park', 'Post-exit')

    def test_console(self):
        c.console_gate(self.console)
        for text in (self.console.replace(c.MARKER, ''), self.console + '\nBOARD_REPLAY_PASS',
                     self.console + '\nRVV_FP_REDSPECIAL_DETAIL scenario=3',
                     self.console + '\nRVV_FP_REDSPECIAL_FAIL sew=16'):
            with self.subTest(text=text[-60:]), self.assertRaises(ValueError):
                c.console_gate(text)

    def test_actual_partial_DETAIL_immediate_monitor(self):
        import ara_verify.runner as engine
        lines = (c.REF / 'host/missing_nv.log').read_text().splitlines()
        first, = [s for s in lines if s.startswith('RVV_FP_REDSPECIAL_DETAIL')]
        partial = first.split(' expected_flags=', 1)[0]
        self.assertNotIn('FAIL', partial)
        self.assertIsNotNone(c.VETO.search(partial))
        with tempfile.TemporaryDirectory(dir=c.HERE) as tmp, patch.object(engine, 'FAIL_RE',
                re.compile(engine.FAIL_RE.pattern + '|' + c.VETO.pattern, re.I)):
            cmd = [sys.executable, '-c', 'import os,time;os.write(1,' + repr(partial.encode()) + ');time.sleep(30)']
            rc, elapsed, timed_out, failure = engine._run_monitored(cmd, Path(tmp), Path(tmp) / 'host.log',
                                                                  10, threading.Event())
            self.assertTrue(failure)
            self.assertFalse(timed_out)
            self.assertNotEqual(rc, 0)
            self.assertLess(elapsed, 5)

    def test_checked_failure_and_late_abort(self):
        for status, cancel in [('FAIL', False), ('PASS', True)]:
            abort = threading.Event()
            class Parent:
                def __init__(self): pass
                def _run_test(self, *_): return SimpleNamespace(status=status, reason='')
            check = Mock(side_effect=lambda _: abort.set() if cancel else None)
            result = replay.checked_runner(Parent, abort, check)()._run_test(None, None)
            self.assertTrue(abort.is_set())
            self.assertNotEqual(result.status, 'PASS')
            self.assertEqual(check.call_count, int(status == 'PASS'))

    def test_publish_sticky_abort(self):
        with tempfile.TemporaryDirectory(dir=c.HERE) as tmp:
            abort = threading.Event()
            abort.set()
            terminal = dict(status=replay.PASS)
            c.common.publish(Path(tmp), terminal, abort)
            self.assertEqual(c.read(Path(tmp) / 'complete.json')['status'], 'NOT_PASS')

    def test_terminal_fresh_disk_SHA(self):
        with tempfile.TemporaryDirectory(dir=c.HERE) as tmp, patch.object(replay, 'validate') as valid:
            out = Path(tmp)
            c.common.save(out / 'plan.json', {'old': True})
            digest = c.sha(out / 'plan.json')
            replay.terminal_plan_gate(out, digest, replay.IMAGE)
            valid.assert_called_once_with({'old': True}, replay.IMAGE)
            c.common.save(out / 'plan.json', {'late_drift': True})
            with self.assertRaisesRegex(ValueError, 'Late disk'):
                replay.terminal_plan_gate(out, digest, replay.IMAGE)

    def test_pinned_ELF_and_image_and_plan_drift(self):
        plan = dict(status='PREPARED_NOT_RUN', image=str(replay.IMAGE), image_sha256=c.sha(replay.IMAGE / 'image.json'),
            case=replay.scope(), spec=self.spec, jobs=1, timeout_s=5400, service_timeout_s=6600, unit=replay.UNIT,
            no_build=True, no_retry=True, no_fsdb=True, stop_first_fail=True, reserved_slots=0,
            reference_ready_sha256=replay.READY_SHA, source_review_sha256=replay.REVIEW_SHA,
            pins={str(Path(replay.__file__).resolve()): c.sha(Path(replay.__file__))})
        replay.validate(plan, replay.IMAGE)
        for key, bad in [('timeout_s', 5401), ('service_timeout_s', 6601), ('jobs', 2),
                         ('case', dict(plan['case'], sha256='0' * 64)), ('image_sha256', '0' * 64),
                         ('no_retry', False), ('reserved_slots', -1), ('spec', {})]:
            with self.subTest(field=key), self.assertRaises(ValueError):
                replay.validate(dict(plan, **{key: bad}), replay.IMAGE)

    def test_service_direct_and_deadline(self):
        props = dict(Id=replay.UNIT, LoadState='loaded', ActiveState='active', SubState='running',
                     MainPID='123', ControlGroup='/user/' + replay.UNIT, RuntimeMaxUSec='1h 50min',
                     KillMode='control-group', Restart='no')
        replay.owner_gate(props, '0::/user/' + replay.UNIT, 123)
        for key, value in [('MainPID', '124'), ('RuntimeMaxUSec', '2h'), ('ActiveState', 'inactive'),
                           ('LoadState', 'not-found'), ('KillMode', 'process'), ('Restart', 'always')]:
            with self.subTest(field=key), self.assertRaises(ValueError):
                replay.owner_gate(dict(props, **{key: value}), '0::/user/' + replay.UNIT, 123)

    def test_COMPLETE_and_noabort(self):
        result = SimpleNamespace(name=c.NAME, status='PASS', returncode=0)
        metadata = dict(status='COMPLETE', status_counts={'PASS': 1}, tests=[c.NAME], completed_at='now', jobs=1, timeout_s=5400,
                        simv=self.ledger['simv'], commit_trace=True, code_coverage=False)
        replay.terminal_gate([result], metadata, threading.Event(), self.ledger)
        for key, value in [('status', 'INTERRUPTED'), ('tests', []), ('jobs', 2), ('completed_at', None)]:
            with self.subTest(field=key), self.assertRaises(ValueError):
                replay.terminal_gate([result], dict(metadata, **{key: value}), threading.Event(), self.ledger)
        abort = threading.Event()
        abort.set()
        with self.assertRaises(ValueError):
            replay.terminal_gate([result], metadata, abort, self.ledger)


if __name__ == '__main__':
    path = c.HERE / 'host03.json'
    if path.exists():
        raise SystemExit('Preserve previous Host output')
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Gates)
    with (c.HERE / 'host03.log').open('x') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    c.common.save(path, dict(status='PASS_HOST_ONLY' if result.wasSuccessful() else 'HOST_FAIL',
        tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        script_sha256=c.sha(Path(__file__)), checker_sha256=c.sha(c.HERE / 'checker.py'),
        runner_sha256=c.sha(c.HERE / 'replay.py'), live_queries=False, DUT_started=False))
    print(json.dumps(c.read(path)), flush=True)
    raise SystemExit(not result.wasSuccessful())
