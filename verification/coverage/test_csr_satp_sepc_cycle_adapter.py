import copy
import unittest
from types import FunctionType, SimpleNamespace

import csr_satp_sepc_cycle_adapter as p


def changed_pc_parser(path):
    stream = iter(p.vcd(path)); tag, decl = next(stream); yield tag, decl
    for time, before, after in stream:
        before = dict(before); before[decl[p.original.CSR + '.pc_i']['code']] = '0'
        yield time, before, after


def changed_tid_parser(path):
    stream = iter(p.vcd(path)); tag, decl = next(stream); yield tag, decl
    for time, before, after in stream:
        before = dict(before)
        code = decl[p.original.CSR + '.commit_instr_i.trans_id']['code']
        bits = before.get(code, 'x')
        if set(bits) <= {'0', '1'}: before[code] = format(int(bits, 2) ^ 1, '03b')
        yield time, before, after


class EpochTests(unittest.TestCase):
    def stream(self, post=11, following=11, commit=False):
        names = {'ara_tb.clk': ('c', 1), 'ara_tb.rst_n': ('r', 1), p.original.MONITOR: ('m', 64),
                 p.original.CORE + '.csr_commit_commit_ex': ('v', 1), p.original.CSR + '.csr_addr_i': ('a', 12),
                 p.original.BUFFER + '.csr_valid_i': ('i', 1)}
        decl = {n: dict(code=c, width=w, type='wire') for n, (c, w) in names.items()}
        def state(clk, counter): return dict(c=str(clk), r='1', m=format(counter, '064b'), v=str(int(commit)), i='0', a=format(0x141, '012b'))
        return [('declarations', decl), (1, state(0, 10), state(1, post)),
                (2, state(1, post), state(0, post)), (3, state(0, following), dict(state(1, following + 1), v='0', a='0'))]

    def test_observed_post_counter_not_numeric_offset(self):
        out = list(p.rebind(self.stream()))
        self.assertEqual(int(out[1][1]['m'], 2), 11)
        self.assertEqual(int(out[3][1]['m'], 2), 12)

    def test_bad_nba_increment(self):
        with self.assertRaisesRegex(ValueError, 'NBA'): list(p.rebind(self.stream(post=12)))

    def test_exact_final_finish_without_nba(self):
        stream = self.stream()[:2]; stream[1][2]['m'] = stream[1][1]['m']
        self.assertEqual(len(list(p.rebind(stream, terminal_cycle=10))), 2)

    def test_finish_with_active_issue_rejected(self):
        stream = self.stream()[:2]; stream[1][2]['m'] = stream[1][1]['m']; stream[1][1]['i'] = '1'
        with self.assertRaisesRegex(ValueError, 'NBA'): list(p.rebind(stream, terminal_cycle=10))

    def test_finish_then_more_wave_rejected(self):
        stream = self.stream(); stream[1][2]['m'] = stream[1][1]['m']
        with self.assertRaisesRegex(ValueError, 'continues'): list(p.rebind(stream, terminal_cycle=10))

    def test_next_epoch_discontinuity(self):
        with self.assertRaisesRegex(ValueError, 'discontinuity'): list(p.rebind(self.stream(following=12)))

    def test_unknown_counter(self):
        stream = self.stream(); stream[1][2]['m'] = 'x'
        with self.assertRaisesRegex(ValueError, 'Unknown'): list(p.rebind(stream))

    def test_no_following_edge(self):
        with self.assertRaisesRegex(ValueError, 'subsequent'): list(p.rebind(self.stream(commit=True)[:2]))

    def test_rvfi_unregistered_source_rejected(self):
        root = p.life.ROOT
        sources = dict(monitor=(root/'hardware/tb/ara_commit_monitor.sv').read_text(),
            system=(root/'hardware/src/ara_system.sv').read_text(),
            rvfi=(root/'hardware/deps/cva6/core/cva6_rvfi.sv').read_text(),
            probes=(root/'hardware/deps/cva6/core/cva6_rvfi_probes.sv').read_text())
        sources['rvfi'] = sources['rvfi'].replace('rvfi_instr_o[i].valid <= valid;', 'rvfi_instr_o[i].valid = valid;')
        with self.assertRaisesRegex(ValueError, 'source anchor'): p.cycle_semantics(sources)


class ActualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pre = p.life.read_bound(p.original.runner.PRE/'preflight-manifest.json', p.original.runner.PRE_SEAL)
        rows = p.original.primitive.parse_rows(p.packed.RUN/'commit_trace.csv')
        cls.expected = p.original.csr_expected(p.original.runner.reference(pre), rows, p.original.runner.source_contract()[0]['ops'])
        cls.path = p.packed.HOLD/'csr-owner.vcd'

    def test_actual_all30_exact_original_gate(self):
        result = p.wave_audit(self.path, self.expected)
        self.assertEqual(len(result['committed']), 30)
        self.assertEqual(result['status'], 'ALL30_NATIVE_CSR_OWNER_WORD_TID_EXACT')

    def test_actual_all30_next_edge_counters(self):
        samples = p.measured_epochs(self.path, self.expected)
        self.assertEqual(len(samples), 30)
        for sample, expected in zip(samples, self.expected):
            self.assertEqual(sample['post_counter'], sample['next_edge_pre_counter'])
            self.assertEqual(sample['next_edge_pre_counter'], expected['cycle'])
            self.assertGreater(sample['next_edge_time'], sample['commit_edge_time'])

    def test_wrong_csv_cycle_rejected(self):
        expected = copy.deepcopy(self.expected); expected[0]['cycle'] += 1
        with self.assertRaisesRegex(ValueError, 'owner differs'): p.wave_audit(self.path, expected)

    def test_wrong_word_rejected(self):
        expected = copy.deepcopy(self.expected); expected[0]['operand'] ^= 1
        with self.assertRaisesRegex(ValueError, 'owner differs'): p.wave_audit(self.path, expected)

    def test_wrong_pc_rejected(self):
        audit = FunctionType(p.original.wave_audit.__code__, dict(p.original.wave_audit.__globals__, wave=SimpleNamespace(vcd=changed_pc_parser)))
        with self.assertRaisesRegex(ValueError, 'owner differs'): audit(self.path, self.expected)

    def test_wrong_tid_rejected(self):
        audit = FunctionType(p.original.wave_audit.__code__, dict(p.original.wave_audit.__globals__, wave=SimpleNamespace(vcd=changed_tid_parser)))
        with self.assertRaisesRegex(ValueError, 'owner differs'): audit(self.path, self.expected)


if __name__ == '__main__': unittest.main()
