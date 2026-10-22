import copy
import json
from pathlib import Path
from unittest.mock import patch
import unittest

import qualify_csr_frozen_counter_terminal as q


class CSRQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre = q.life.read_bound(q.runner.PRE / 'preflight-manifest.json', q.runner.PRE_SEAL)
        cls.symbols = cls.pre['symbols']
        cls.reference = q.primitives.reference_prefix(q.spike_trace.parse_spike_commits(
                            q.runner.PRE / 'spike.trace'), cls.symbols['tohost'])
        cls.rows = q.primitives.parse_rows(q.RUN / 'commit_trace.csv')
        cls.guard = q.elf_file_bytes(q.runner.ELF.read_bytes(), cls.symbols['counter_guards'], 16)
        cls.record = q.life.read_bound(q.RUN / 'manifest.json', q.RUN_SEAL)
        cls.scalar = q.spike_trace.compare_commit_prefix(q.runner.PRE / 'spike.trace', q.RUN / 'commit_trace.csv',
                      0x80000000, terminal_tohost_address=cls.symbols['tohost'], rvfi_store_data_layout='unshifted')

    def test_actual_scalar(self):
        q.scalar_gate(self.scalar)

    def test_actual_counter_gold(self):
        result = q.architecture(self.rows, self.reference, self.symbols, self.guard)
        self.assertEqual(result['oracle']['checks'], 54)
        self.assertEqual(result['oracle']['observed_bytes'], 416)
        self.assertEqual(result['memory_accesses'], 203)
        self.assertFalse(result['independent_counter_CSR']['platform_dynamic_counter_values_compared'])

    def reject_rows(self, mutate):
        rows = copy.deepcopy(self.rows)
        mutate(rows)
        with self.assertRaises(ValueError):
            q.architecture(rows, self.reference, self.symbols, self.guard)

    def test_partial(self):
        self.reject_rows(lambda rows: rows.pop())

    def test_trap(self):
        self.reject_rows(lambda rows: rows[10].__setitem__('trap', 1))

    def test_wrong_pc(self):
        self.reject_rows(lambda rows: rows[10].__setitem__('pc', rows[10]['pc'] + 4))

    def test_wrong_opcode(self):
        self.reject_rows(lambda rows: rows[10].__setitem__('insn', 1))

    def test_wrong_gpr(self):
        self.reject_rows(lambda rows: next(r for r in rows if r['rd']).__setitem__('rd_wdata', 0xdead))

    def test_wrong_csr_return(self):
        self.reject_rows(lambda rows: next(r for r in rows if r['insn'] >> 20 == 0xb00 and r['rd'])
                         .__setitem__('rd_wdata', 0xdead))

    def test_wrong_store(self):
        self.reject_rows(lambda rows: next(r for r in rows if r['mem_wmask']).__setitem__('mem_wdata', 0xdead))

    def test_wrong_load_mask(self):
        self.reject_rows(lambda rows: next(r for r in rows if r['mem_rmask']).__setitem__('mem_rmask', 0))

    def test_wrong_address(self):
        self.reject_rows(lambda rows: next(r for r in rows if r['mem_wmask']).__setitem__('mem_addr', 0))

    def test_backend_event(self):
        self.reject_rows(lambda rows: rows[10].__setitem__('event', 'uop_alloc'))

    def test_elf_guard_changed(self):
        with self.assertRaises(ValueError):
            q.architecture(self.rows, self.reference, self.symbols, b'\0' * 16)

    def test_counter_independent_wrong_return(self):
        cs = copy.deepcopy(self.reference)
        c = next(c for c in cs if c.instruction >> 20 == 0xb00 and c.gpr_writes)
        reg = next(iter(c.gpr_writes))
        c.gpr_writes[reg] ^= 1
        with self.assertRaises(ValueError):
            q.counter_csr_audit(cs)

    def test_counter_unfrozen(self):
        cs = copy.deepcopy(self.reference)
        index = next(i for i, c in enumerate(cs) if c.instruction >> 20 == 0x320)
        cs[index] = copy.copy(cs[index])
        # Same CSR write, x0 instead of the register carrying5.
        object.__setattr__(cs[index], 'instruction', cs[index].instruction & ~(31 << 15))
        with self.assertRaises(ValueError):
            q.counter_csr_audit(cs)

    def test_scalar_bool_count(self):
        result = copy.deepcopy(self.scalar)
        result['ara_trap_events'] = False
        with self.assertRaises(ValueError):
            q.scalar_gate(result)

    def test_scalar_skip(self):
        result = copy.deepcopy(self.scalar)
        result['skipped_unobservable_register_values'] = 1
        with self.assertRaises(ValueError):
            q.scalar_gate(result)

    def test_scalar_prefix(self):
        result = copy.deepcopy(self.scalar)
        result['status'] = 'PREFIX_MATCH'
        with self.assertRaises(ValueError):
            q.scalar_gate(result)

    def test_actual_terminal(self):
        q.terminal_gate(json.loads((q.RUN / 'simulation-status.json').read_bytes()),
                        json.loads((q.RUN / 'started.json').read_bytes()), self.record)

    def test_timeout_rejected(self):
        state = json.loads((q.RUN / 'simulation-status.json').read_bytes())
        state['timeout'] = True
        with self.assertRaises(ValueError):
            q.terminal_gate(state, json.loads((q.RUN / 'started.json').read_bytes()), self.record)

    def test_wrong_startup_budget(self):
        started = json.loads((q.RUN / 'started.json').read_bytes())
        started['budget_s'] = 300
        with self.assertRaises(ValueError):
            q.terminal_gate(json.loads((q.RUN / 'simulation-status.json').read_bytes()), started, self.record)

    def test_actual_zero_vector(self):
        q.primitives.zero.vector_zero(q.RUN / 'vector_trace.csv')
        result = q.vector_commit.compare_vector_commits(q.runner.PRE / 'spike.trace', q.RUN / 'commit_trace.csv',
                                                        q.RUN / 'vector_trace.csv', 0x80000000)
        q.primitives.vector_gate(result)
        self.assertEqual(result['status'], 'UNOBSERVABLE')

    def test_actual_log(self):
        self.assertTrue(all(v == 0 for v in q.primitives.log_gate((q.RUN / 'run.vcs.log').read_text()).values()))

    def test_uvm_error(self):
        with self.assertRaises(ValueError):
            q.primitives.log_gate((q.RUN / 'run.vcs.log').read_text() + '\nUVM_ERROR @42 bad\n')

    def test_nonzero_stall(self):
        with self.assertRaises(ValueError):
            q.primitives.log_gate((q.RUN / 'run.vcs.log').read_text().replace('req_stalled=0', 'req_stalled=1'))

    def test_duplicate_contract(self):
        text = (q.RUN / 'run.vcs.log').read_text()
        line = next(l for l in text.splitlines() if '[ARA_CONTRACT]' in l)
        with self.assertRaises(ValueError):
            q.primitives.log_gate(text + '\n' + line)

    def test_baseline_wrong_population(self):
        with self.assertRaises(ValueError):
            q.baseline_gate({'output_pins': {}}, dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',
                        aggregate_passed=737, coverage_admitted=True), {'tests': []})


if __name__ == '__main__':
    unittest.main()
