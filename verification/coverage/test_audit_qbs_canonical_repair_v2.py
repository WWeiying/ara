import copy
import csv
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import audit_qbs_canonical_repair_v2 as a

RUN = a.previous.ROOT / 'verification/out/failed-repair-acceptance-20261008-03/results/qbs_canonical'
WAVE = a.previous.ROOT / 'verification/out/qbs-canonical-repair-v2-audit-20261008-01/focused.vcd'


class TerminalRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob = a.previous.ORIGINAL_ELF.read_bytes()
        with (RUN / 'commit_trace.csv').open(newline='') as stream:
            cls.rows = list(csv.DictReader(stream))

    def tail(self):
        rows = [copy.deepcopy(r) for r in self.rows if r['event'] == 'retire'
                and a.EOC_PC <= int(r['pc'], 16) <= a.EOC_PC + 12]
        for i, r in enumerate(rows):
            r['order'] = str(i)
        return rows

    def test_actual_native_mmio_trace(self):
        result = a.mmio_terminal(self.rows, self.blob)
        self.assertEqual(result['first_store_cycle'], 147923)
        self.assertEqual(result['store_count'], 1)
        self.assertEqual(result['retirement_count'], 63877)
        self.assertEqual(result['exit_loop_retirements'], 5)

    def test_success_loop_tail_is_not_required_to_end_on_store(self):
        rows = self.tail()
        for size in (3, 4, 5):
            self.assertEqual(a.mmio_terminal(rows[:size], self.blob)['store_count'], 1)

    def test_no_exit_or_truncated_store_rejected(self):
        for rows in ([], self.tail()[:1], self.tail()[:2]):
            with self.assertRaises(ValueError):
                a.mmio_terminal(rows, self.blob)

    def test_bad_exit_mutations_rejected(self):
        changes = [(2, 'mem_wdata', '1'), (2, 'mem_addr', '80001000'),
                   (2, 'mem_wmask', '0f'), (2, 'trap', '1'), (2, 'rd', '1'),
                   (3, 'pc', '80001000'), (3, 'insn', '00000013'),
                   (4, 'mem_rmask', 'ff'), (4, 'mem_wmask', 'ff'),
                   (0, 'rd_wdata', 'd0000000'), (1, 'rd_wdata', 'd00000e4'),
                   (1, 'order', '9'), (3, 'cycle', '0')]
        for index, field, value in changes:
            rows = self.tail()
            rows[index][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                a.mmio_terminal(rows, self.blob)

    def test_wrong_linked_elf_rejected(self):
        elf = a.ELFFile(a.BytesIO(self.blob))
        segment = next(s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD'
                       and s['p_vaddr'] <= a.EOC_PC < s['p_vaddr'] + s['p_filesz'])
        bad = bytearray(self.blob)
        bad[segment['p_offset'] + a.EOC_PC - segment['p_vaddr']] ^= 1
        with self.assertRaisesRegex(ValueError, 'MMIO exit instructions'):
            a.mmio_terminal(self.rows, bad)

    def test_original_tohost_assumption_rejects_actual_success(self):
        info, _ = a.previous.fixture_contract(RUN / 'input.elf')
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'Exact terminal tohost store'):
                a.strict.native_architecture(RUN / 'commit_trace.csv', RUN / 'vector_trace.csv',
                                             info, self.blob, Path(temp))

    def test_full_existing_architecture_oracle_after_terminal_fix(self):
        info, _ = a.previous.fixture_contract(RUN / 'input.elf')
        with tempfile.TemporaryDirectory() as temp:
            result = a.native_architecture(RUN / 'commit_trace.csv', RUN / 'vector_trace.csv',
                                           info, self.blob, Path(temp))
        self.assertEqual(result['owner']['full_scalar_compared_words'], 4688)
        self.assertEqual(result['owner']['exact_destination_bytes'], 128)
        self.assertEqual(result['recovery']['destination_bytes'], 128)

    def test_recovery_and_custom_owner_gates_not_bypassed(self):
        info, _ = a.previous.fixture_contract(RUN / 'input.elf')
        for module, name in ((a, 'recovery_gate'), (a.strict, 'recovery_lifetimes'),
                             (a.strict.runner.p.audit, 'custom_write_lifetimes')):
            with self.subTest(gate=name), tempfile.TemporaryDirectory() as temp:
                with patch.object(module, name, side_effect=ValueError('injected ' + name)):
                    with self.assertRaisesRegex(ValueError, 'injected ' + name):
                        a.native_architecture(RUN / 'commit_trace.csv', RUN / 'vector_trace.csv',
                                              info, self.blob, Path(temp))

    def test_recovery_owner_and_data_mutations_rejected(self):
        from dataclasses import replace
        info, _ = a.previous.fixture_contract(RUN / 'input.elf')
        _, _, activities = a.strict._parse_vector_trace(RUN / 'vector_trace.csv')
        seqs, _ = a.recovery_gate(self.rows, activities, info, self.blob)
        self.assertEqual(seqs, {119, 120, 121})
        for mutation in ('missing', 'duplicate', 'wrong_pc', 'wrong_value', 'unknown_byte', 'wrong_owner'):
            rows, acts = copy.deepcopy(self.rows), copy.deepcopy(activities)
            if mutation == 'missing':
                rows = [r for r in rows if not (r['event'] == 'arch_start' and r['order'] == '119')]
            elif mutation == 'duplicate':
                rows.append(next(r for r in rows if r['event'] == 'arch_start' and r['order'] == '119'))
            elif mutation == 'wrong_pc':
                row = next(r for r in rows if r['event'] == 'retire' and
                           int(r['pc'], 16) == info['symbols']['canon_recovery_site'])
                row['pc'] = '80000000'
            elif mutation == 'wrong_owner':
                acts[119].instruction ^= 1
            else:
                write = acts[120].writes[0]
                acts[120].writes[0] = replace(write, **({'data': write.data ^ 1}
                    if mutation == 'wrong_value' else {'known_be': 0}))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                a.recovery_gate(rows, acts, info, self.blob)

    def test_gated_clock_full_capture(self):
        result = a.cycle_wave(WAVE, 147935, (RUN / 'console.log').read_text())
        self.assertEqual(result['sampled_edges'], 295)
        self.assertEqual(result['accepted_AR'], 4)
        self.assertEqual(result['accepted_RLAST'], 4)
        self.assertEqual(result['capture_end_100fs'], 1479505000)
        self.assertTrue(result['target_retry_translated'])

    def test_capture_end_mismatch_or_truncation_rejected(self):
        console = (RUN / 'console.log').read_text()
        with self.assertRaisesRegex(ValueError, 'simulator finish timestamp'):
            a.cycle_wave(WAVE, 147935, console.replace('Time: 147950500000 fs', 'Time: 147950600000 fs'))
        with self.assertRaisesRegex(ValueError, 'before architectural trace'):
            a.cycle_wave(WAVE, 150000, console)
        with tempfile.TemporaryDirectory() as temp:
            truncated = Path(temp) / 'truncated.vcd'
            data = WAVE.read_text()
            self.assertTrue(data.endswith('#1479505000\n'))
            truncated.write_text(data[:-len('#1479505000\n')])
            with self.assertRaisesRegex(ValueError, 'simulator finish timestamp'):
                a.cycle_wave(truncated, 147935, console)

    def test_protocol_fault_gate_not_bypassed(self):
        with patch.object(a.strict, 'cycle_gate', side_effect=ValueError('injected fault gate')):
            with self.assertRaisesRegex(ValueError, 'injected fault gate'):
                a.cycle_wave(WAVE, 147935, (RUN / 'console.log').read_text())

    def test_old_actual_failed_capture_rejected_without_conversion(self):
        old = a.previous.ROOT / 'verification/out/gap71-canonical-qbs-positive779-run-agent-20261008-03'
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            shutil.copyfile(a.previous.ORIGINAL_ELF, run / 'input.elf')
            for name in ('run.vcs.log', 'console.log', 'commit_trace.csv',
                         'vector_trace.csv', 'qbs-canonical-focused.vpd'):
                (run / name).symlink_to(old / name)
            with patch.object(a.subprocess, 'run') as convert:
                with self.assertRaisesRegex(ValueError, 'Simulator/self-check failure'):
                    a.audit(run)
                convert.assert_not_called()


if __name__ == '__main__':
    unittest.main()
