import copy
import unittest
from types import SimpleNamespace

import build_gap111_preflight as p


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.symbols = dict(g111_leaf=0x80010000, g111_page=0x80004000,
                            g111_entry=0x80004fc0, g111_probe=0x80004fc0,
                            g111_second=0x80005000, g111_ecall=0x80005028)

    def test_same_PTE_line(self):
        r = p.geometry(self.symbols)
        self.assertEqual(r['second_PTE'], r['data_probe'])
        self.assertNotEqual(r['first_PTE'] // 32, r['second_PTE'] // 32)
        self.assertFalse(r['runtime_overlap_proven'])

    def test_wrong_linked_page(self):
        self.symbols['g111_second'] += 4
        with self.assertRaises(ValueError): p.geometry(self.symbols)

    def test_wrong_probe_owner(self):
        self.symbols['g111_probe'] -= 4
        with self.assertRaises(ValueError): p.geometry(self.symbols)

    def test_independent_gold(self):
        result = p.expected(self.symbols)
        pte = ((0x80005000 >> 12) << 10) | 0xcb
        self.assertEqual(result, [pte, pte ^ 0x123, pte + 17, pte, 0, 0, 0x80010020, 2])

    def test_unaligned_table(self):
        self.symbols['g111_leaf'] += 8
        with self.assertRaises(ValueError): p.geometry(self.symbols)

    def test_no_vector_or_wrong_terminal(self):
        c = SimpleNamespace(vector_writes={'v1': 0}, memory_accesses=(), instruction=0, gpr_writes={}, pc=0)
        with self.assertRaisesRegex(ValueError, 'vector'): p.validate([c], self.symbols)
        c.vector_writes = {}
        self.symbols['tohost'] = 0x80001000
        with self.assertRaisesRegex(ValueError, 'terminal'): p.validate([c], self.symbols)

    def test_actual_740_targets_and_already_hit_rejected(self):
        import json
        b = json.loads((p.BASE / 'combined-bits.json').read_bytes())
        shape = p.read_xml(p.BUILD / 'sim/simv.vdb/snps/coverage/db/shape/fsm.verilog.shape.xml')
        targets = p.targets(b, shape)
        self.assertEqual(len(targets), 14)
        self.assertEqual({r['compiled']['raw_index'] for r in targets}, {6, 7, 16, 21, 23, 24, 27})
        bad = copy.deepcopy(b)
        row = bad['metrics']['fsm'][targets[0]['scope']]
        row['bits'] = hex(int(row['bits'], 16) | (1 << (27 - 6)))[2:]
        with self.assertRaisesRegex(ValueError, 'already'): p.targets(bad, shape)

    def test_actual_spike_ecall_is_trap_not_retirement(self):
        out = p.OUT / 'gap111-pte-line-preflight-740-agent-20261007-01'
        symbols = {k: p.shared._elf_symbol(out / 'input.elf', p.shared.LLVM / 'llvm-readelf', k)
                   for k in p.SYMBOLS}
        commits = p.shared.parse_spike_commits(out / 'spike.trace')
        validation = p.validate(commits, symbols)
        self.assertEqual(validation['checks'], 26)
        self.assertEqual(validation['expected_traps'], 1)
        self.assertNotIn(0x40004028, [c.pc for c in commits])


if __name__ == '__main__':
    unittest.main()
