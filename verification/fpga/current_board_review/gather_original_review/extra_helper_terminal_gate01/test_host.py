#!/usr/bin/env python3
"""Small synthetic architectural/protocol traces, not firmware or DUT runs."""
import copy
import csv
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
import audit as a

TRACE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/verification/ara_verify/trace.py')
TRACE_SHA = 'b5751d25426ba78893c52359519d3b6f1df6bc9c77eb341c91cdca1ff75b506a'


def retire(instr, **fields):
    row = dict(cycle='0', event='retire', order='0', port='0', trans_id='0',
               pc=f"{instr['pc']:x}", insn=instr['insn'], trap='0', rd='0', rd_wdata='0',
               mem_addr='0', mem_rmask='0', mem_wmask='0', mem_wdata='0')
    row.update(fields)
    return row


def fixture(spec):
    result = [retire(spec['instructions'][spec['text_start']])]
    for entry in spec['bootstrap'][:2]:
        result.append(retire(entry, rd=str(entry['rd']), rd_wdata=f"{entry['value']:x}"))
    result.extend(retire(r) for r in spec['capacity'])
    entry = spec['bootstrap'][2]
    result.append(retire(entry, rd=str(entry['rd']), rd_wdata=f"{entry['value']:x}"))
    for _ in range(112):
        result.extend(retire(r) for r in spec['routine'])
        # A real scalar PC outside all helper windows stands for intervening C.
        result.append(retire(spec['instructions'][spec['text_start']]))
    result.append(retire(spec['exit_store'], mem_addr='d0000000', mem_wmask='ff'))
    result.append(retire(spec['park']))
    return result


def protocol(retirements):
    rows, order = [], 0
    for item in retirements:
        row = dict(item)
        if row['event'] == 'retire' and a.vector_instruction(int(row['insn'], 16)):
            for event in ('cvx_req', 'cvx_resp'):
                rows.append(dict(row, pc='0', event=event, order='0', trap='0'))
        if row['event'] == 'retire':
            row['order'] = str(order)
            order += 1
        rows.append(row)
    for cycle, row in enumerate(rows):
        row['cycle'] = str(cycle)
    return rows


class Gates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = a.specification()
        cls.good = fixture(cls.spec)
        a.require(a.sha(TRACE) == TRACE_SHA, 'Frozen generic validator drift')
        module = importlib.util.spec_from_file_location('frozen_trace_host_only', TRACE)
        cls.generic = importlib.util.module_from_spec(module)
        module.loader.exec_module(cls.generic)

    def check(self, rows):
        return a.audit_rows(protocol(rows), self.spec)

    def reject(self, rows, message):
        with self.assertRaisesRegex(ValueError, message):
            self.check(rows)

    def injected(self, item):
        rows = copy.deepcopy(self.good)
        rows.insert(-2, item)
        return rows

    def test_positive_exact112_closed_scope(self):
        report = self.check(self.good)
        self.assertEqual(report['helper_counts'], [112]*13)
        self.assertEqual(report['capacity_instruction_counts'], [1]*3)
        self.assertEqual(report['bootstrap_csr_counts'], [1]*3)
        self.assertEqual(report['vector_csr_retired'], 1236)

    def test_positive_generic_and_single_csv_scan(self):
        rows = protocol(self.good)
        with tempfile.TemporaryDirectory(dir=a.HERE) as tmp:
            path = Path(tmp)/'synthetic.csv'
            with path.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            generic = self.generic.validate_trace(path)
            result = a.scan_csv_once(path, self.spec)
            self.assertEqual(result['csv_sha256'], a.sha(path))
            self.assertEqual(generic['vector_retire_count'], 1236)
            self.assertEqual(result['rows'], generic['rows'])
            self.assertEqual(result['full_csv_passes'], 1)

    def test_vi31_interior_balanced_generic_accept_pc_gate_reject(self):
        instr = self.spec['helpers'][a.NAME+'_op_3'][8]
        self.assertEqual((instr['pc'], instr['insn']), (0x8000074a, '308fbc57'))
        rows = self.injected(retire(instr))
        with tempfile.TemporaryDirectory(dir=a.HERE) as tmp:
            path = Path(tmp)/'synthetic_extra.csv'
            trace = protocol(rows)
            with path.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(trace[0]))
                writer.writeheader()
                writer.writerows(trace)
            self.assertEqual(self.generic.validate_trace(path)['vector_retire_count'], 1237)
            with self.assertRaisesRegex(ValueError, 'Unused helper'):
                a.scan_csv_once(path, self.spec)

    def test_unused_op0_vector_internal(self):
        self.reject(self.injected(retire(self.spec['helpers'][a.NAME+'_op_0'][8])), 'Unused helper')

    def test_unused_op0_integer_internal(self):
        instr = self.spec['helpers'][a.NAME+'_op_0'][6]
        self.assertEqual(instr['insn'], '8e42')
        self.reject(self.injected(retire(instr)), 'Unused helper')

    def test_unused_op0_csr_internal(self):
        self.reject(self.injected(retire(self.spec['helpers'][a.NAME+'_op_0'][7])), 'Unused helper')

    def test_unused_entry(self):
        self.reject(self.injected(retire(self.spec['helpers'][a.NAME+'_op_3'][0])), 'Unused helper')

    def test_duplicate_op2_internal_in_window(self):
        rows = copy.deepcopy(self.good)
        at = next(i for i, r in enumerate(rows) if int(r['pc'], 16) == self.spec['routine'][6]['pc'])
        rows.insert(at+1, dict(rows[at]))
        self.reject(rows, 'Noncontiguous/duplicate')

    def test_extra_op2_internal_after_calls(self):
        self.reject(self.injected(retire(self.spec['routine'][6])), 'Interior entry')

    def test_extra_selected_csr(self):
        self.reject(self.injected(retire(self.spec['routine'][7])), 'Interior entry')

    def test_extra_bootstrap_csr(self):
        self.reject(self.injected(retire(self.spec['bootstrap'][0])), 'Extra bootstrap CSR')

    def test_duplicate_vlenb(self):
        instr = self.spec['bootstrap'][1]
        self.reject(self.injected(retire(instr, rd='14', rd_wdata='80')), 'Extra bootstrap CSR')

    def test_integer_between_helper_instructions(self):
        rows = copy.deepcopy(self.good)
        at = next(i for i, r in enumerate(rows) if int(r['pc'], 16) == self.spec['routine'][6]['pc'])
        rows.insert(at, retire(self.spec['instructions'][self.spec['text_start']]))
        self.reject(rows, 'Noncontiguous/duplicate')

    def test_missing_helper_integer(self):
        rows = copy.deepcopy(self.good)
        at = next(i for i, r in enumerate(rows) if int(r['pc'], 16) == self.spec['routine'][6]['pc'])
        del rows[at]
        self.reject(rows, 'Noncontiguous/duplicate')

    def test_missing_call(self):
        rows = copy.deepcopy(self.good)
        at = next(i for i, r in enumerate(rows) if int(r['pc'], 16) == self.spec['routine'][0]['pc'])
        del rows[at:at+13]
        self.reject(rows, 'Premature exit')

    def test_extra_call(self):
        rows = copy.deepcopy(self.good)
        rows[-2:-2] = [retire(r) for r in self.spec['routine']]
        self.reject(rows, 'Capacity/call count')

    def test_missing_capacity(self):
        rows = [r for r in self.good if int(r['pc'], 16) not in {p['pc'] for p in self.spec['capacity']}]
        self.reject(rows, 'Extra/late/wrong bootstrap')

    def test_duplicate_capacity(self):
        rows = copy.deepcopy(self.good)
        rows[-2:-2] = [retire(r) for r in self.spec['capacity']]
        self.reject(rows, 'Capacity/call count')

    def test_wrong_vlenb_return(self):
        rows = copy.deepcopy(self.good)
        next(r for r in rows if int(r['pc'], 16) == self.spec['bootstrap'][1]['pc'])['rd_wdata'] = '40'
        self.reject(rows, 'Extra/late/wrong bootstrap')

    def test_unknown_rvv_pc(self):
        row = retire(dict(pc=0x80010000, insn='308fbc57'))
        self.reject(self.injected(row), 'Unknown/non-boundary PC')

    def test_known_pc_wrong_code(self):
        row = retire(self.spec['instructions'][self.spec['text_start']], insn='308fbc57')
        self.reject(self.injected(row), 'ELF encoding mismatch')

    def test_middle_of_instruction_pc(self):
        row = retire(dict(pc=self.spec['routine'][0]['pc']+2, insn='003772d7'))
        self.reject(self.injected(row), 'Unknown/non-boundary PC')

    def test_trap_pc_even_without_trap_flag(self):
        row = retire(self.spec['instructions'][self.spec['trap_pcs'][0]])
        self.reject(self.injected(row), 'Forbidden trap path')

    def test_zero_padding_rejected(self):
        instr = next(r for r in self.spec['instructions'].values() if r['text'] == 'unimp')
        self.reject(self.injected(retire(instr)), 'Padding/illegal')

    def test_postexit_extra_rvv(self):
        self.reject([*self.good, retire(self.spec['routine'][8])], 'Post-exit')

    def test_postexit_park_side_effect(self):
        rows = copy.deepcopy(self.good)
        rows[-1]['rd'] = '1'
        self.reject(rows, 'Post-exit')

    def test_bad_exit(self):
        rows = copy.deepcopy(self.good)
        rows[-2]['mem_wdata'] = '1'
        self.reject(rows, 'Wrong CTRL exit')

    def test_incomplete_no_exit(self):
        self.reject(self.good[:-2], 'Incomplete helper/capacity/exit')

    def test_trap_flag(self):
        rows = copy.deepcopy(self.good)
        rows[0]['trap'] = '1'
        self.reject(rows, 'Trap/exception')

    def test_no_cvx_exception(self):
        rows = protocol(self.good)
        rows.insert(0, dict(rows[0], event='cvx_exception'))
        with self.assertRaisesRegex(ValueError, 'Event/cycle'):
            a.audit_rows(rows, self.spec)

    def test_transport_only_csr_replay_not_extra_retirement(self):
        rows = protocol(self.good)
        before = len(rows)-2
        for event in ('cvx_resp', 'cvx_req'):
            rows.insert(before, dict(rows[before], pc='0', event=event, insn='00802073', order='0'))
        for i, row in enumerate(rows):
            row['cycle'] = str(i)
        with tempfile.TemporaryDirectory(dir=a.HERE) as tmp:
            path = Path(tmp)/'synthetic_transport.csv'
            with path.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            self.assertEqual(self.generic.validate_trace(path)['cvx_replay_count'], 1)
            self.assertEqual(a.scan_csv_once(path, self.spec)['vector_csr_retired'], 1236)

    def test_classifier_matches_pinned_generic_all_elf_codes(self):
        for instr in self.spec['instructions'].values():
            code = int(instr['insn'], 16)
            self.assertEqual(a.vector_instruction(code), self.generic.is_vector_instruction(code))

    def test_missing_terminal_rejected_without_csv_read(self):
        with tempfile.TemporaryDirectory(dir=a.HERE) as tmp:
            with self.assertRaises(FileNotFoundError):
                a.terminal_binding(Path(tmp)/'complete.json', '0'*64)

    def test_notpass_terminal_rejected_without_csv_read(self):
        with tempfile.TemporaryDirectory(dir=a.HERE) as tmp:
            path = Path(tmp)/'complete.json'
            path.write_text(json.dumps(dict(status='NOT_PASS')))
            with self.assertRaisesRegex(ValueError, 'Original terminal not accepted'):
                a.terminal_binding(path, a.sha(path))


if __name__ == '__main__':
    output = Path(sys.argv[1]) if len(sys.argv) == 2 else a.HERE/'host01'
    a.require(output.resolve().is_relative_to(a.HERE) and not output.exists(), 'Fresh owned Host output only')
    output.mkdir()
    with (output/'tests.log').open('x') as log:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(Gates)
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    a.save_new(output/'report.json', dict(status='HOST_PASS' if result.wasSuccessful() else 'HOST_FAIL',
        synthetic_only=True, tests=result.testsRun, errors=len(result.errors), failures=len(result.failures),
        audit_sha256=a.sha(a.HERE/'audit.py'), tests_sha256=a.sha(Path(__file__)),
        generic_validator_sha256=a.sha(TRACE), log_sha256=a.sha(output/'tests.log')))
    print((output/'report.json').read_text())
    sys.exit(0 if result.wasSuccessful() else 1)
