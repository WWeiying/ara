#!/usr/bin/env python3
"""Host-only checker negatives and existing CSV decoder compatibility; no DUT."""
import argparse
import csv
import json
from pathlib import Path
import re
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import checker as ck
import worker as w

REF = w.OWNER / 'reference03'


def make(fault=True):
    work = REF / (w.NAMES[0] if fault else w.NAMES[1])
    return ck.Checker(w.read(work / 'soc.symbols.json'), ck.instructions((work / 'soc.dis').read_text()), fault, 1)


def put(c, name, value, index=0):
    address = c.s[name] + 8 * index
    for i in range(8):
        c.mem[address + i] = (value >> (8 * i)) & 255


def event(kind, **kw):
    row = {field: '0' for field in ck.FIELDS}
    row.update(event=kind, **{k: str(v) for k, v in kw.items()})
    return row


def cvx(c, op, tag=1):
    c.cvx(event('cvx_req', trans_id=tag, insn=f'{op:08x}'))


def respond(c, trap=0, tag=1):
    c.cvx(event('cvx_resp', trans_id=tag, trap=trap))


def complete_model(fault=True):
    """Synthetic terminal state only, never passed to a DUT result or CSV gate."""
    c = make(fault)
    n = 50 if fault else 51
    c.points = [dict(round=i) for i in range(n)]
    c.reloads = c.reload_retires = c.success_responses = c.success_retires = n
    c.requests = 1650 if fault else 51
    c.fault_responses = c.retries = 1600 if fault else 0
    c.traps = [{} for _ in range(c.retries)]
    c.exits = [0]
    c.after_resume = True
    c.helper_calls = 50
    c.masked_calls = 0 if fault else 1
    c.calls = 21595 if fault else 5215
    c.pages_read = list(range(32768))
    c.pt_read = list(range(1536))
    for name, v in dict(io_errors=0, io_exit_code=0, io_round=50, io_mask_count=0 if fault else 1,
                        io_minor=1600 if fault else 0, io_maps=50 if fault else 0,
                        io_unmaps=50 if fault else 0,
                        io_done=0x525656303146494e, io_checks=c.calls).items():
        put(c, name, v)
    if fault:
        put(c, 'faults', 1600)
    for i in range(50):
        put(c, 'io_fault_count', 32 if fault else 0, i)
    return c


def fault_capture(c):
    c.await_handler = {'ordinal': 0}
    return dict(csr=dict(zip(ck.CSR, [13, c.target, 0x40007000, 0, 32, 17, 117, 5])),
                repair=True, pte=True, oldpte=True, fence=True, mepc_writes=[], regs=dict(c.regs),
                records=list(range(7)), cycle=10)


def checkpoint_model():
    c = make()
    c.post_active = True; c.post_checks = 0; c.calls = 72
    c.round_requests = 33; c.round_success = c.round_retired = 1
    c.round_stores = c.round_store_responses = c.round_store_retires = 1
    c.reloads = c.reload_retires = 1
    c.post_output = c.post_indices = [i for i in range(32) for _ in range(2)]
    c.post_guards = [0, 33, 0, 33]
    put(c, 'io_round', 0); put(c, 'io_errors', 0); put(c, 'io_fault_count', 32)
    for i, v in enumerate([32, 17, 0, 117, 5] + [ck.value(i) for i in range(32)] + [0x5b12] * 2):
        put(c, 'io_result', v, i)
    for i in range(32):
        vals = [13, c.target, 0x40000000 + ((i * 13 + 7) % 32) * 4096, i, 32, 17, 117, 5]
        c.traps.append(dict(values=vals))
        for j, v in enumerate(vals[1:]): put(c, 'io_records', v, i * 7 + j)
    return c


class HostTests(unittest.TestCase):
    def test_fault_mret_positive_and_missing_record(self):
        c = make(); c.capture = fault_capture(c)
        put(c, 'io_fault_count', 1); put(c, 'io_minor', 1)
        row = event('retire', pc=f"{c.s['io_retry_mret']:x}", insn='30200073')
        c.row(row); self.assertEqual(c.retry, c.target)
        for field, replacement in (('records', [0, 1, 2]), ('mepc_writes', [c.target]), ('repair', False)):
            c = make(); c.capture = fault_capture(c); c.capture[field] = replacement
            put(c, 'io_fault_count', 1); put(c, 'io_minor', 1)
            with self.assertRaises(ValueError): c.row(row)

    def test_repair_sfence_address_and_fence(self):
        c = make(); c.capture = fault_capture(c); c.capture['repair'] = False
        pc = c.s['io_repair_sfence']; op = c.ops[pc]
        c.regs[(op >> 15) & 31] = 0x40007000
        r = event('retire', pc=f'{pc:x}', insn=f'{op:x}')
        c.row(r); self.assertTrue(c.capture['repair'])
        for wrong_address in (True, False):
            c = make(); c.capture = fault_capture(c); c.capture['repair'] = False
            c.regs[(op >> 15) & 31] = 0x40008000 if wrong_address else 0x40007000
            c.capture['fence'] = wrong_address
            with self.assertRaises(ValueError): c.row(r)

    def test_checkpoint_full_and_negative_ledger(self):
        c = checkpoint_model(); c.checkpoint(); self.assertEqual(len(c.points), 1)
        for field, value in (('calls', 71), ('round_requests', 32), ('post_guards', [0, 33]),
                             ('post_output', []), ('round_store_retires', 0), ('reload_retires', 0)):
            c = checkpoint_model(); setattr(c, field, value)
            with self.assertRaises(ValueError): c.checkpoint()
        c = checkpoint_model(); del c.mem[c.s['io_records'] + 7]
        with self.assertRaises(ValueError): c.checkpoint()
        c = checkpoint_model(); put(c, 'io_records', 1, 4)
        with self.assertRaises(ValueError): c.checkpoint()

    def test_deadline_is_global_and_within_service(self):
        self.assertLess(w.WORKER_SECONDS, w.SERVICE_SECONDS)
        self.assertLessEqual(w.SERVICE_SECONDS + 60, 10800)
        c = threading.Event(); c.set()
        with self.assertRaises(ValueError):
            w.common.check_stage([], {'status': 'COMPLETE', 'status_counts': {'PASS': 0}}, [], c)

    def test_oracle_last_round_and_masked(self):
        for r in (0, 49, 50):
            expected = [32, 17, 0, 117, 5] + [ck.value(i) if r < 50 or 7 <= i < 17 and i % 2
                       else 0xfffffff9 for i in range(32)] + [0x5b12] * 2
            ck.point(expected, r)
            for i in range(39):
                wrong = expected.copy(); wrong[i] ^= 1
                with self.assertRaises(ValueError): ck.point(wrong, r)

    def test_missing_zero_byte_is_not_zero(self):
        c = make(); put(c, 'io_errors', 0)
        self.assertEqual(c.named('io_errors'), 0)
        del c.mem[c.s['io_errors'] + 3]
        with self.assertRaisesRegex(ValueError, 'Missing observed'): c.named('io_errors')

    def test_handler_readonly_vector_csr_transport(self):
        c = make(); c.capture = {'csr': {0x342: 13}}
        for csr in (8, 0xc20, 0xc21, 15):
            cvx(c, (csr << 20) | 0x2573); respond(c)
        self.assertFalse(c.inflight)
        for op in (ck.RELOAD, 0x0da2f357, 0x00839073):
            with self.subTest(op=op), self.assertRaises(ValueError):
                d = make(); d.capture = {'csr': {0x342: 13}}; cvx(d, op)

    def test_cvxtag_generation_and_unpaired(self):
        c = make()
        with self.assertRaises(ValueError): respond(c)
        c = make(); cvx(c, 0xc2002573)
        with self.assertRaises(ValueError): cvx(c, 0xc2102573)
        respond(c); cvx(c, 0xc2102573); respond(c)
        with self.assertRaises(ValueError): respond(c)

    def test_reload_requires_round_boundary(self):
        c = make(); cvx(c, ck.RELOAD); respond(c)
        with self.assertRaises(ValueError): cvx(c, ck.RELOAD)
        c = make(); c.retry = c.target
        with self.assertRaises(ValueError): cvx(c, ck.RELOAD)

    def test_target_retry_requires_mret(self):
        c = make(); cvx(c, ck.RELOAD); respond(c); cvx(c, c.op); respond(c, 1)
        with self.assertRaises(ValueError): cvx(c, c.op)
        c.inflight.clear(); c.await_handler = None; c.retry = c.target
        cvx(c, c.op); respond(c, 1)
        self.assertEqual(c.retries, 1)

    def test_wrong_target_branch(self):
        c = make(); cvx(c, ck.RELOAD); respond(c)
        with self.assertRaises(ValueError): cvx(c, 0x0645f807)

    def test_fault_csr_chain_and_wrong_pc(self):
        c = make(); c.await_handler = {'ordinal': 0}
        values = [13, c.target, 0x40007000, 0, 32, 17, 117, 5]
        cap = dict(csr=dict(zip(ck.CSR, values)))
        self.assertEqual(c.fault_values(cap), values)
        for csr in ck.CSR:
            bad = dict(csr=cap['csr'].copy()); bad['csr'][csr] ^= 1
            with self.assertRaises(ValueError): c.fault_values(bad)

    def test_missing_mret_repair(self):
        c = make(); c.await_handler = {'ordinal': 0}
        c.capture = dict(csr=dict(zip(ck.CSR, [13, c.target, 0x40007000, 0, 32, 17, 117, 5])),
                         repair=False, pte=True)
        r = event('retire', pc=f"{c.s['io_retry_mret']:x}", insn='30200073')
        with self.assertRaisesRegex(ValueError, 'MRET before repair'): c.row(r)

    def test_fault_mepc_write_rejected(self):
        c = make(); c.capture = dict(csr={0x342: 13})
        pc = next(p for p, op in c.ops.items() if op == 0x34129073)
        with self.assertRaisesRegex(ValueError, 'Fault handler reconstructs'):
            c.row(event('retire', pc=f'{pc:x}', insn='34129073'))

    def test_syscall_pc_and_number(self):
        c = make(); pc = next(p for p, op in c.ops.items() if op == 0x73)
        regs = dict(c.regs); regs[17] = 64
        cap = dict(csr=dict(zip(ck.CSR, [9, pc, 0, 0, 32, 17, 117, 5])), regs=regs)
        c.fault_values(cap)
        cap['csr'][0x341] += 2
        with self.assertRaises(ValueError): c.fault_values(cap)

    def test_nonzero_or_duplicate_control(self):
        c = complete_model(); c.finish()
        c.exits = [0, 0]
        with self.assertRaises(ValueError): c.finish()
        c = complete_model(); c.exits = [1]
        with self.assertRaises(ValueError): c.finish()

    def test_terminal_counters_and_missing_bytes(self):
        for fault in (True, False):
            c = complete_model(fault); c.finish()
            for name in ('io_round', 'io_minor', 'io_maps', 'io_unmaps', 'faults', 'io_checks', 'io_done'):
                if name == 'faults' and not fault: continue
                d = complete_model(fault); put(d, name, d.named(name) ^ 1)
                with self.assertRaises(ValueError): d.finish()
            del c.mem[c.s['io_errors']]
            with self.assertRaises(ValueError): c.finish()

    def test_missing_actual_full_memory_loads(self):
        c = complete_model(); c.pages_read.pop()
        with self.assertRaises(ValueError): c.finish()
        c = complete_model(); c.pt_read.pop()
        with self.assertRaises(ValueError): c.finish()

    def test_corrupt_actual_backing_read_not_shadow(self):
        c = make(); c.after_resume = True
        pc = next(p for p, op in c.ops.items() if c.s['main'] <= p < c.s['io_handler'] and op == 0x421c)
        c.regs[12] = c.s['pages']
        row = event('retire', pc=f'{pc:x}', insn='421c', rd=15, rd_wdata='a5a50f0f',
                    mem_addr=f"{c.s['pages']:x}", mem_rmask='0f')
        c.row(row); self.assertEqual(len(c.pages_read), 1)
        d = make(); d.after_resume = True; d.regs[12] = d.s['pages']; row['rd_wdata'] = 'a5a50f0e'
        with self.assertRaisesRegex(ValueError, 'backing-memory'): d.row(row)

    def test_scalar_store_mask_address_data(self):
        regs = {i: 0 for i in range(32)}; regs[10] = 0x80000004; regs[11] = 0x12345678
        r = event('retire', insn='00b52023', mem_addr='80000004', mem_wmask='f0', mem_wdata='12345678')
        self.assertEqual(ck.memory_access(r, regs, True), (0x80000004, 0x12345678, 4))
        for key, val in (('mem_wmask', '0f'), ('mem_addr', '80000000'), ('mem_wdata', '12345679')):
            wrong = dict(r); wrong[key] = val
            with self.assertRaises(ValueError): ck.memory_access(wrong, regs, True)

    def test_truncated_csv(self):
        c = make(); r = event('retire'); del r['trap']
        with self.assertRaises(ValueError): c.row(r)

    def test_raw_failure_after_success_and_missing_oracle(self):
        c = dict(fault=True, overlap=1)
        text = w.marker(c) + '\nINDEXED_ORIGINAL_PASS\n' + w.common.SUCCESS + '\n$finish\n'
        w.console(c, text)
        for suffix in ('\nVECTOR_FAIL', '\nINDEXED_ORIGINAL_FAIL', '\nBOARD_REPLAY_TRAP', '\nABORTED'):
            with self.assertRaises(ValueError): w.console(c, text + suffix)
        with self.assertRaises(ValueError): w.console(c, text.replace(w.marker(c), ''))
        with self.assertRaises(ValueError): w.console(c, text + '\nINDEXED_ORIGINAL_PASS')

    def test_cancellation_inside_expensive_checker(self):
        abort = threading.Event()
        class Parent:
            def __init__(self): pass
            def _run_test(self, test, image): return SimpleNamespace(status='PASS', reason='')
        runner = w.checked_runner(Parent, {'x': {}}, {}, REF, abort, lambda _: None)()
        with patch.object(w, 'artifacts', side_effect=lambda *args: abort.set()):
            result = runner._run_test(SimpleNamespace(name='x'), None)
        self.assertEqual(result.status, 'CANCELLED'); self.assertTrue(abort.is_set())

    def test_failure_cancels_queue(self):
        abort = threading.Event()
        class Parent:
            def __init__(self): pass
            def _run_test(self, test, image): return SimpleNamespace(status='FAIL', reason='real failure')
        runner = w.checked_runner(Parent, {}, {}, REF, abort, lambda _: None)()
        self.assertEqual(runner._run_test(SimpleNamespace(name='x'), None).status, 'FAIL')
        self.assertTrue(abort.is_set())

    def test_raw_runner_interrupted_rejected(self):
        with self.assertRaises(ValueError):
            w.common.check_stage([], {'status': 'INTERRUPTED', 'status_counts': {'PASS': 1}},
                                 [{'id': 'x'}], threading.Event())

    def test_image_elf_pin_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'image'; path.write_text('first')
            pins = {str(path): w.sha(path)}
            w.common.base.verify_pins(pins)
            path.write_text('second')
            with self.assertRaises(ValueError): w.common.base.verify_pins(pins)

    def test_resource_comm_or_argv(self):
        self.assertTrue(w.common.is_simv('renamed', ['/path/simv']))
        self.assertTrue(w.common.is_simv('simv', ['/other']))
        with self.assertRaises(ValueError): w.common.resource_math([], 31 * 1024**3, w.HERE, 2, 0)
        with self.assertRaises(ValueError): w.common.resource_math([], 64 * 1024**3, w.HERE, 2, 23)

    def test_frozen_profile_signal_tokens(self):
        root = Path('/home/wangwy/fpga_runs/current_board_memory_candidate05/frozen/sources/hardware/src')
        tcl = (w.HERE / 'capture.tcl').read_text()
        groups = re.findall(r'foreach p \{([^}]+)\} \{\s*dump -add ([^ ]+) ', tcl)
        mapping = {'$ara.i_dispatcher.$p': 'ara_dispatcher.sv', '$ara.i_vlsu.i_addrgen.$p': 'vlsu/addrgen.sv',
                   '$ara.i_vlsu.i_vldu.$p': 'vlsu/vldu.sv', '$ara.i_sequencer.$p': 'ara_sequencer.sv',
                   '$lane.$p': 'lane/lane.sv', '$lane.i_operand_requester.$p': 'lane/operand_requester.sv'}
        self.assertEqual(len(groups), 6)
        for tokens, prefix in groups:
            source = (root / mapping[prefix]).read_text()
            for token in tokens.split():
                self.assertTrue(re.search(r'\b' + token + r'\b', source), prefix + ':' + token)
        self.assertIn('run -absolute 1000000ns', tcl)
        self.assertNotIn('dump -add /', tcl)

    def test_real_existing_nf2_memory_decoder(self):
        path = w.OWNER.parent / 'masked_translation/segment_review/sv39/vcs_preflight01/run/tests/nf2_segment4/commit_trace.csv'
        regs = {i: 0 for i in range(32)}; accesses = 0
        with path.open() as stream:
            for n, r in enumerate(csv.DictReader(stream)):
                if r['event'] != 'retire': continue
                if not int(r['trap']):
                    for write in (True, False):
                        if ck.memory_access(r, regs, write): accesses += 1
                    rd = int(r['rd'])
                    if rd: regs[rd] = int(r['rd_wdata'], 16)
                if n > 30000: break
        self.assertGreater(accesses, 1000)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(HostTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    w.save(args.report, dict(status='HOST_PASS_NOT_DUT' if result.wasSuccessful() else 'HOST_FAIL',
        tests=result.testsRun, failures=[(str(t), s) for t, s in result.failures],
        errors=[(str(t), s) for t, s in result.errors], VCS_launched=False,
        pins={str(w.HERE / name): w.sha(w.HERE / name) for name in ('worker.py', 'checker.py', 'test_host.py', 'capture.tcl')}))
    raise SystemExit(not result.wasSuccessful())
