import copy
import csv
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import qualify_ptw_sfence_boundary_terminal as q


SUMMARY = '[ARA_CONTRACT] requests=0 responses=0 exceptions=0 mmu_request_cycles=0 protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0'
LOG = 'Core Test *** SUCCESS ***\n' + SUMMARY + '\nUVM_ERROR : 0\nUVM_FATAL : 0\n'


class Gates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pre = q.life.read_bound(q.runner.PRE / 'preflight-manifest.json', q.runner.PRE_SEAL)
        cls.symbols = pre['symbols']
        cls.reference = q.reference_prefix(q.spike_trace.parse_spike_commits(Path(pre['input_spike_trace'])),
                                           cls.symbols['tohost'])
        cls.rows = []
        for c in cls.reference:
            row = {k: 0 for k in q.common.COMMIT_FIELDS}
            row.update(event='retire', order=len(cls.rows), cycle=len(cls.rows), pc=c.pc, insn=c.instruction)
            gpr = {r: v for r, v in c.gpr_writes.items() if r}
            if gpr:
                if len(gpr) != 1:
                    raise ValueError('Unexpected multi-GPR reference')
                row['rd'], row['rd_wdata'] = next(iter(gpr.items()))
            d = q.memory_decode(c.instruction)
            if d:
                if len(c.memory_accesses) != 1:
                    raise ValueError('Unknown reference memory shape')
                addr, value = c.memory_accesses[0]
                row['mem_addr'] = addr
                row['mem_rmask' if value is None else 'mem_wmask'] = ((1 << d['size']) - 1) << (addr & 7)
                if value is not None:
                    row['mem_wdata'] = value
            cls.rows.append(row)
            if c.pc in (0x4000401c, 0x4002401c):
                trap = {k: 0 for k in q.common.COMMIT_FIELDS}
                trap.update(event='retire', order=len(cls.rows), cycle=len(cls.rows), pc=c.pc + 4, insn=0x73, trap=1)
                cls.rows.append(trap)

    def test_real_reference_synthetic_native_complete(self):
        result = q.architecture(self.rows, self.reference, self.symbols)
        self.assertEqual(result['oracle']['checks'], 35)
        self.assertEqual(result['skipped_memory_events'], 0)
        self.assertGreater(result['memory_counts']['compressed_write'], 0)
        self.assertGreater(len(result['CSR_records']), 0)

    def mutated_rows(self):
        return copy.deepcopy(self.rows)

    def reject(self, rows):
        with self.assertRaises(ValueError): q.architecture(rows, self.reference, self.symbols)

    def test_wrong_GPR(self):
        rows = self.mutated_rows()
        next(r for r in rows if r['rd'])['rd_wdata'] ^= 1
        self.reject(rows)

    def test_wrong_CSR_return(self):
        rows = self.mutated_rows()
        next(r for r in rows if r['insn'] & 127 == 0x73 and r['insn'] >> 12 & 7 and r['rd'])['rd_wdata'] ^= 1
        self.reject(rows)

    def test_wrong_branch_opcode(self):
        rows = self.mutated_rows()
        next(r for r in rows if r['insn'] & 127 == 0x63)['insn'] ^= 0x1000
        self.reject(rows)

    def test_wrong_memory_address(self):
        rows = self.mutated_rows()
        next(r for r in rows if r['mem_rmask'])['mem_addr'] += 8
        self.reject(rows)

    def test_wrong_mask_equal_population(self):
        rows = self.mutated_rows()
        row = next(r for r in rows if r['mem_wmask'] == 15)
        row['mem_wmask'] = 0xf0
        self.reject(rows)

    def test_wrong_compressed_store(self):
        rows = self.mutated_rows()
        row = next(r for r in rows if r['insn'] & 3 != 3 and r['mem_wmask'])
        row['mem_wdata'] ^= 1
        self.reject(rows)

    def test_wrong_load_sign(self):
        rows = self.mutated_rows()
        row = next(r for r in rows if r['mem_rmask'] and r['rd'])
        row['rd_wdata'] ^= 1 << 63
        self.reject(rows)

    def test_extra_memory_effect(self):
        rows = self.mutated_rows()
        next(r for r in rows if not r['trap'] and q.memory_decode(r['insn']) is None)['mem_wmask'] = 1
        self.reject(rows)

    def test_wrong_trap_PC(self):
        rows = self.mutated_rows()
        next(r for r in rows if r['trap'])['pc'] += 4
        self.reject(rows)

    def test_missing_trap(self):
        self.reject([r for r in self.rows if not r['trap']])

    def test_wrong_handler_cause(self):
        rows = self.mutated_rows()
        next(r for r in rows if r['insn'] >> 20 == 0x342 and r['rd'])['rd_wdata'] = 13
        self.reject(rows)

    def test_unknown_memory_decode(self):
        with self.assertRaises(ValueError): q.memory_decode(0x00007003)
        with self.assertRaises(ValueError): q.memory_decode(0x00004023)

    def test_partial_rows(self):
        self.reject(self.rows[:-1])

    def test_zero_contract(self):
        self.assertEqual(q.log_gate(LOG)['requests'], 0)

    def test_UVM_message(self):
        for line in ('UVM_ERROR @ 20: actual failure', 'UVM_FATAL fatal', 'UVM_ERROR : 2'):
            with self.assertRaises(ValueError): q.log_gate(LOG + line + '\n')

    def test_nonzero_stall(self):
        with self.assertRaises(ValueError): q.log_gate(LOG.replace('req_stalled=0', 'req_stalled=1'))

    def test_missing_duplicate_summary(self):
        for log in (LOG.replace(SUMMARY, ''), LOG + SUMMARY + '\n', LOG.replace(' resp_stalled=0', '')):
            with self.assertRaises(ValueError): q.log_gate(log)

    def test_success_single(self):
        with self.assertRaises(ValueError): q.log_gate(LOG + 'Core Test *** SUCCESS ***\n')

    def test_exit_not_enough(self):
        state = dict(status='SIMULATION_EXITED_NOT_ADMITTED', returncode=0, case=q.runner.NAME, timeout=True,
            coverage_admitted=False, admission_performed=False, dut_self_check_verified=False,
            terminal_oracle_verified=False)
        with self.assertRaises(ValueError): q.terminal_gate(state, {}, {})

    def test_incomplete_reference(self):
        c = SimpleNamespace(pc=0x80000000, memory_accesses=())
        with self.assertRaises(ValueError): q.reference_prefix([c], 0x80001000)

    def scalar_fixture(self):
        return dict(status='TERMINAL_TOHOST_MATCH', entry='0x0000000080000000', rvfi_store_data_layout='unshifted',
            matched_instructions=len(self.reference),
            matched_scalar_writes=sum(len({r: v for r, v in c.gpr_writes.items() if r}) for c in self.reference),
            matched_floating_writes=0, matched_scalar_memory_accesses=sum(bool(c.memory_accesses) and
                q.spike_trace._scalar_memory_access(c.instruction) is not None for c in self.reference),
            ara_committed_instructions=len(self.reference), ara_retired_instructions=len(self.reference) + 2,
            ara_trap_events=2, skipped_unobservable_register_values=0, stopped_at_unobservable=None,
            mismatch=None, terminal_ecall=None, aligned_vector_faults=[],
            terminal_tohost=dict(address='0x0000000080001000', write_value='0x1'))

    def test_full_scalar_gate(self):
        q.scalar_gate(self.scalar_fixture(), self.reference)

    def test_prefix_skip_or_type_rejected(self):
        for field, value in [('status', 'PREFIX'), ('skipped_unobservable_register_values', 1),
                             ('ara_trap_events', True), ('matched_scalar_memory_accesses', True),
                             ('aligned_vector_faults', [{}])]:
            result = self.scalar_fixture()
            result[field] = value
            with self.assertRaises(ValueError): q.scalar_gate(result, self.reference)

    def test_real_zero_vector_parser_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            commit, vector = Path(tmp) / 'commit.csv', Path(tmp) / 'vector.csv'
            hexes = {'pc', 'insn', 'rd_wdata', 'mem_addr', 'mem_rmask', 'mem_wmask', 'mem_wdata'}
            with commit.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=q.common.COMMIT_FIELDS)
                writer.writeheader()
                writer.writerows({k: hex(v) if k in hexes else v for k, v in r.items()} for r in self.rows)
            with vector.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=q.common.VECTOR_FIELDS)
                writer.writeheader()
                row = {k: 0 for k in q.common.VECTOR_FIELDS}
                row.update(event='config', nr_lanes=4, vlen_bits=1024)
                writer.writerow(row)
            q.zero.vector_zero(vector)
            pre = q.life.read_bound(q.runner.PRE / 'preflight-manifest.json', q.runner.PRE_SEAL)
            result = q.vector_commit.compare_vector_commits(Path(pre['input_spike_trace']), commit, vector, 0x80000000)
            q.vector_gate(result)
            self.assertEqual(result['status'], 'UNOBSERVABLE')
            result['unretired_requests'] = [1]
            with self.assertRaises(ValueError): q.vector_gate(result)


if __name__ == '__main__':
    unittest.main()
