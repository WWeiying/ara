"""Own fractional actual-helper owner tests; no CSV, reference or DUT execution."""
from collections import Counter
import unittest
import checker as c


class OwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = c.base.specification()
        cls.gold = c.base.model()

    def fixture(self, vl, start=0, op=19):
        row = dict(op=op, vl=vl, vstart=start, mode=0)
        helper = self.spec['backend']['helpers'][f'op_{op}']
        ledger = []
        for j in (1, 2, 3, 4, 8, 11):
            insn = helper[j]['insn']
            target = j == 8
            ledger.append(dict(insn=insn, pc=helper[j]['pc'], call=0, helper_index=j,
                kind='target' if target else 'memory',
                required=c.target_required(insn, row, self.spec) if target else True))
        observer = object.__new__(c.OwnerObserver)
        observer.source_spec = self.spec
        observer.arch = [x['insn'] for x in ledger]
        observer.retvec = observer.arch[:]
        observer.owner_alloc = Counter({i: 1 for i, x in enumerate(ledger) if x['required']})
        observer.owner_done = observer.owner_alloc.copy()
        return observer, ledger, dict(rows=[row], masks=[[0]])

    def delete(self, vl, index, op=19):
        observer, ledger, gold = self.fixture(vl, op=op)
        observer.owner_alloc[index] = observer.owner_done[index] = 0
        return observer.owner_coverage(ledger, gold)

    def test_empty_vl1_vl2_elision(self):
        for vl in (1, 2):
            with self.subTest(vl=vl):
                result = self.delete(vl, 4)
                self.assertEqual(result['minimum_required_owners'], 5)

    def test_vl3_completed(self):
        observer, ledger, gold = self.fixture(3)
        self.assertEqual(observer.owner_coverage(ledger, gold)['minimum_required_owners'], 6)

    def test_vl3_missing_target_pair(self):
        with self.assertRaisesRegex(ValueError, 'Missing necessary'):
            self.delete(3, 4)

    def test_each_helper_missing_pair(self):
        for index in (0, 1, 2, 3, 5):
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'Missing necessary'):
                self.delete(1, index)

    def test_slidedown_not_waived(self):
        with self.assertRaisesRegex(ValueError, 'Missing necessary'):
            self.delete(1, 4, op=20)

    def test_op24_not_waived(self):
        with self.assertRaisesRegex(ValueError, 'Missing necessary'):
            self.delete(1, 4, op=24)

    def test_wrong_encoding_rejected(self):
        row = dict(op=19, vl=1, vstart=0)
        with self.assertRaisesRegex(ValueError, 'encoding'):
            c.target_required(0x38813c57 ^ (1 << 15), row, self.spec)

    def test_false_required_flag_rejected(self):
        observer, ledger, gold = self.fixture(3)
        ledger[4]['required'] = False
        with self.assertRaisesRegex(ValueError, 'required flag'):
            observer.owner_coverage(ledger, gold)

    def test_alloc_done_mismatch(self):
        observer, ledger, gold = self.fixture(1)
        observer.owner_alloc[4] = 1
        with self.assertRaisesRegex(ValueError, 'alloc/done'):
            observer.owner_coverage(ledger, gold)

    def test_full_static_scope(self):
        changed = []
        needed = 0
        for i, row in enumerate(self.gold):
            insn = self.spec['backend']['helpers'][f'op_{row["op"]}'][8]['insn']
            actual = c.target_required(insn, row, self.spec)
            needed += actual
            if actual != (row['vstart'] < row['vl']):
                changed.append(i)
        self.assertEqual(changed, [base + j for base in (1200, 2565, 3930) for j in range(6)])
        self.assertEqual(needed, 2592)
        self.assertEqual(sum(r['op'] == 24 and r['vstart'] < r['vl'] for r in self.gold), 117)

    def test_original_vstart_elision_preserved(self):
        observer, ledger, gold = self.fixture(3, start=3)
        self.assertEqual(observer.owner_coverage(ledger, gold)['required_target_owners'], 0)

    def test_actual_strict_consume_binding(self):
        state = c.Strict(self.spec)
        state.main_entered = state.body_entered = True
        state.retired = 1
        state.csr_count = 5
        state.helper, state.index = 'op_19', 8
        state.active = dict(ordinal=1200, original_ordinal=1201)
        state.regs[16], state.regs[28] = 0, 7
        pc = self.spec['backend']['helpers']['op_19'][8]['pc']
        state.consume(dict(cycle='1', event='retire', trap='0', order='1', pc=hex(pc),
            insn='38813c57', rd='0', rd_wdata='0', mem_addr='0', mem_rmask='0',
            mem_wmask='0', mem_wdata='0'))
        self.assertEqual(len(state.offloads), 1)
        self.assertFalse(state.offloads[0]['required'])
        self.assertEqual(state.counts[8], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)

