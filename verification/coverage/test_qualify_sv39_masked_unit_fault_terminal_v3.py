"""Actual frozen parser regression plus owner/transaction negative tests."""
from copy import deepcopy
import unittest
import qualify_sv39_masked_unit_fault_terminal_v3 as m


class ActualParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.starts,_,cls.rejected=m.v2.vc._parse_architecture_mapping(m.v2.RUN/'commit_trace.csv')
        cls.rows=m.v2.old.common.read_csv((m.v2.RUN/'commit_trace.csv').read_bytes(),m.v2.old.common.COMMIT_FIELDS)
        cls.symbols={'smuf_masked_load':0x80002268}

    def test_real_parser_list_tuple_contract(self):
        self.assertIs(type(self.starts),list)
        self.assertTrue(all(type(x) is tuple for x in self.starts))
        self.assertNotIn(243,self.starts)
        self.assertEqual(self.rejected,{243})
        self.assertTrue(m.architecture_owner(self.starts,self.rows,self.symbols))

    def test_duplicate_owner(self):
        with self.assertRaises(ValueError):m.architecture_owner(self.starts+[(243,230407)],self.rows,self.symbols)

    def test_wrong_opcode(self):
        starts=[(s,i^1 if s==243 else i) for s,i in self.starts]
        with self.assertRaises(ValueError):m.architecture_owner(starts,self.rows,self.symbols)

    def test_wrong_pc(self):
        with self.assertRaises(ValueError):m.architecture_owner(self.starts,self.rows,{'smuf_masked_load':0})

    def test_wrong_transaction(self):
        rows=deepcopy(self.rows)
        for r in rows:
            if r['event']=='arch_start' and r['order']=='243':r['trans_id']='7'
        with self.assertRaises(ValueError):m.architecture_owner(self.starts,rows,self.symbols)

    def test_wrong_exception(self):
        rows=deepcopy(self.rows)
        for r in rows:
            if r['event']=='cvx_resp' and r['cycle']=='36469':r['trap']='0'
        with self.assertRaises(ValueError):m.architecture_owner(self.starts,rows,self.symbols)

    def test_monitor_pc_is_not_fault_pc(self):
        rows=deepcopy(self.rows)
        for r in rows:
            if r['event']=='arch_start' and r['order']=='243':r['pc']='0000000080002268'
        with self.assertRaises(ValueError):m.architecture_owner(self.starts,rows,self.symbols)

    def test_private_replacement_global_unchanged(self):
        original=m.v2.compare_with_proof
        f=m.comparator()
        self.assertIsNot(f,original)
        self.assertIs(m.v2.compare_with_proof,original)
        self.assertIs(f.__globals__['architecture_owner'],m.architecture_owner)


if __name__=='__main__':unittest.main()
