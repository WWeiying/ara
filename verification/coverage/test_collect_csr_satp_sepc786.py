import copy
from dataclasses import replace
import unittest
import collect_csr_satp_sepc786 as p


class ArchitectureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre = p.life.read_bound(p.runner.PRE / 'preflight-manifest.json', p.runner.PRE_SEAL)
        cls.reference = p.runner.reference(cls.pre)
        cls.elf = p.runner.ELF.read_bytes(); cls.rows = []
        regs = {i: 0 for i in range(32)}
        for i, c in enumerate(cls.reference):
            writes = {r: v for r, v in c.gpr_writes.items() if r}
            rd = next(iter(writes), 0)
            row = dict(event='retire', order=i, cycle=i + 10, pc=c.pc, insn=c.instruction,
                trap=0, rd=rd, rd_wdata=writes.get(rd, 0), mem_addr=0, mem_rmask=0, mem_wmask=0, mem_wdata=0)
            d = p.primitive.memory_decode(c.instruction)
            if d:
                addr = (regs[d['base']] + d['offset']) & p.memory.MASK64
                row['mem_addr'] = addr
                row['mem_wmask' if d['kind'] == 'write' else 'mem_rmask'] = ((1 << d['size']) - 1) << (addr & 7)
                if d['kind'] == 'write': row['mem_wdata'] = regs[d['register']] & ((1 << (8 * d['size'])) - 1)
            cls.rows.append(row); regs.update(writes); regs[0] = 0

    def audit(self, rows=None, elf=None):
        return p.architecture(self.rows if rows is None else rows, self.reference, self.pre['symbols'], self.elf if elf is None else elf)

    def test_real_reference_full_positive(self):
        audit = self.audit()
        self.assertEqual((audit['instructions'], audit['memory_accesses'], audit['checks']), (673, 168, 44))
        self.assertEqual(len(audit['expected_CSR']), 30)

    def test_bad_scalar_value(self):
        rows = copy.deepcopy(self.rows); next(r for r in rows if r['rd'])['rd_wdata'] ^= 1
        with self.assertRaisesRegex(ValueError, 'GPR'): self.audit(rows)

    def test_bad_store_mask(self):
        rows = copy.deepcopy(self.rows); next(r for r in rows if r['mem_wmask'])['mem_wmask'] ^= 1
        with self.assertRaisesRegex(ValueError, 'store'): self.audit(rows)

    def test_bad_load_address(self):
        rows = copy.deepcopy(self.rows); next(r for r in rows if r['mem_rmask'])['mem_addr'] += 8
        with self.assertRaisesRegex(ValueError, 'address'): self.audit(rows)

    def test_incomplete_scalar(self):
        with self.assertRaisesRegex(ValueError, 'retirement'): self.audit(self.rows[:-1])

    def test_csr_readback_wrong_old_value(self):
        ref = copy.deepcopy(self.reference)
        c = next(c for c in ref if c.instruction >> 20 == 0x180 and c.instruction & 127 == 0x73
                 and c.instruction >> 7 & 31)
        c.gpr_writes[(c.instruction >> 7) & 31] ^= 1
        with self.assertRaisesRegex(ValueError, 'old-value'):
            p.csr_expected(ref, self.rows, p.runner.source_contract()[0]['ops'])

    def test_elf_guard_corruption(self):
        data = bytearray(self.elf)
        image = p.struct.pack('<QQ', *p.oracle.GUARDS)
        at = data.find(image); self.assertGreater(at, 0); data[at] ^= 1
        with self.assertRaisesRegex(ValueError, 'guard'): self.audit(elf=bytes(data))


class OwnerTests(ArchitectureTests):
    def edges(self):
        expected = self.audit()['expected_CSR']; edges = []
        for i, want in enumerate(expected):
            edge = dict(cycle=want['cycle'], commit=1, buffer_commit=1, address=want['csr'], ack=1,
                pc=want['pc'], tid=i % 8, wdata=want['operand'], rdata=want['old'], operation=want['operation'],
                issue=0, issue_address=-1, flush=0, ready=1, buffer_valid=1)
            issue = dict(cycle=want['cycle'] - 1, commit=0, buffer_commit=0, issue=1,
                issue_address=want['csr'], ready=0, buffer_valid=0, issue_tid=i % 8, issue_operand=want['operand'], flush=0)
            edges.extend([issue, edge])
        return expected, edges

    def test_all30_owned_positive(self):
        expected, edges = self.edges(); self.assertEqual(len(p.owner_gate(edges, expected)['committed']), 30)

    def test_first_issue_ready_zero_is_valid(self):
        expected, edges = self.edges()
        self.assertEqual((edges[0]['buffer_valid'], edges[0]['issue'], edges[0]['ready']), (0, 1, 0))
        self.assertEqual(len(p.owner_gate(edges, expected)['committed']), 30)

    def test_ready_is_checked_separately(self):
        expected, edges = self.edges(); edges[0]['ready'] = 1
        with self.assertRaisesRegex(ValueError, 'ready formula'): p.owner_gate(edges, expected)

    def test_occupied_new_issue_without_commit_rejected(self):
        expected, edges = self.edges(); extra = dict(edges[0], buffer_valid=1)
        edges.insert(1, extra)
        with self.assertRaisesRegex(ValueError, 'occupied owner'): p.owner_gate(edges, expected)

    def test_flush_cancels_uncommitted_issue_before_recovery(self):
        expected, edges = self.edges()
        speculative = dict(edges[0], cycle=0)
        flush = dict(cycle=1, commit=0, buffer_commit=0, buffer_valid=1, issue=0,
                     issue_address=-1, ready=0, flush=1)
        result = p.owner_gate([speculative, flush] + edges, expected)
        self.assertEqual(len(result['committed']), 30)
        self.assertEqual(len(result['canceled_uncommitted_issues']), 1)

    def test_canceled_owner_cannot_commit_without_reissue(self):
        expected, edges = self.edges()
        flush = dict(cycle=edges[0]['cycle'], commit=0, buffer_commit=0, buffer_valid=1,
                     issue=0, issue_address=-1, ready=0, flush=1)
        with self.assertRaisesRegex(ValueError, 'owner'):
            p.owner_gate([edges[0], flush] + edges[1:], expected)

    def test_same_edge_same_csr_commit_before_issue(self):
        expected, edges = self.edges()
        for i in range(len(expected) - 1):
            issue = edges[2 * (i + 1)]
            edges[2 * i + 1].update({k: issue[k] for k in ('issue', 'issue_address', 'issue_tid', 'issue_operand')})
            issue['issue'] = 0
            issue['buffer_valid'] = 1
        self.assertEqual(len(p.owner_gate(edges, expected)['committed']), 30)

    def test_wrong_tid(self):
        expected, edges = self.edges(); edges[1]['tid'] ^= 1
        with self.assertRaisesRegex(ValueError, 'TID'): p.owner_gate(edges, expected)

    def test_wrong_native_csr_word(self):
        expected, edges = self.edges(); edges[1]['wdata'] ^= 1
        with self.assertRaisesRegex(ValueError, 'word'): p.owner_gate(edges, expected)

    def test_wrong_old_readback(self):
        expected, edges = self.edges(); edges[1]['rdata'] ^= 1
        with self.assertRaisesRegex(ValueError, 'word'): p.owner_gate(edges, expected)

    def test_missing_ack(self):
        expected, edges = self.edges(); edges[1]['ack'] = 0
        with self.assertRaises(ValueError): p.owner_gate(edges, expected)

    def test_missing_owner(self):
        expected, edges = self.edges()
        with self.assertRaisesRegex(ValueError, 'owner'): p.owner_gate(edges[1:], expected)


class TerminalTests(unittest.TestCase):
    def test_boolean_returncode_rejected(self):
        with self.assertRaises(ValueError): p.terminal_gate(dict(status='SIMULATION_EXITED_NOT_ADMITTED', returncode=False), {}, {}, {})

    def test_vector_unobservable_schema(self):
        result = dict(status='UNOBSERVABLE', vector_destination_requests=0, prefix_vector_destination_requests=0,
            compared_instructions=0, compared_bytes=0, skipped_unknown_bytes=0, non_bit_exact_instructions=0,
            unobservable_instructions=0, incomplete_requests=[], unretired_requests=[], trapped_requests=[],
            verified_zero_write_traps=[], verified_identity_write_traps=[], verified_probed_load_faults=[],
            verified_trapped_destination_requests=[], first_mismatch=None, instructions=[], stopped_at_spike_index=None)
        p.primitive.vector_gate(result)
        result['non_bit_exact_instructions'] = []
        with self.assertRaises(ValueError): p.primitive.vector_gate(result)


if __name__ == '__main__': unittest.main()
