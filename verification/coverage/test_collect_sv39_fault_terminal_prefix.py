"""Actual saved reference prefix and strict terminal corruption tests."""
from dataclasses import replace
import unittest
import collect_sv39_fault_alternating771_terminal_prefix as q

class TerminalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pre=q.life.read_bound(q.old.PRE/'preflight.json',q.old.PRE_SHA)
        cls.s=pre['symbols'];cls.rows=q.old.p.build.parse_spike_commits(q.old.PRE/'spike.trace')
        cls.i=next(i for i,c in enumerate(cls.rows) if (cls.s['tohost'],1) in c.memory_accesses)
    def reject(self,rows):
        with self.assertRaises(ValueError):q.terminal_prefix(rows,self.s)
    def test_actual(self):
        prefix=q.terminal_prefix(self.rows,self.s)
        self.assertEqual(len(prefix),19767);self.assertEqual(len(self.rows)-self.i-1,1009)
    def test_missing(self):self.reject(self.rows[:self.i]+self.rows[self.i+1:])
    def test_wrong_value(self):
        rows=list(self.rows);rows[self.i]=replace(rows[self.i],memory_accesses=((self.s['tohost'],3),));self.reject(rows)
    def test_early_terminal(self):
        rows=list(self.rows);last=rows.pop(self.i);rows.insert(10,last);self.reject(rows)
    def test_duplicate(self):self.reject(self.rows+[self.rows[self.i]])
    def test_tail_memory(self):
        rows=list(self.rows);rows[-1]=replace(rows[-1],memory_accesses=((self.s['fault_page'],1),));self.reject(rows)
    def test_tail_register(self):
        rows=list(self.rows);rows[-1]=replace(rows[-1],gpr_writes={1:1});self.reject(rows)
    def test_tail_CSR(self):
        rows=list(self.rows);rows[-1]=replace(rows[-1],csr_writes={0x180:0});self.reject(rows)
    def test_tail_vector(self):
        rows=list(self.rows);rows[-1]=replace(rows[-1],vector_writes={8:0});self.reject(rows)
    def test_wrong_spin_pc(self):
        rows=list(self.rows);rows[-1]=replace(rows[-1],pc=rows[-1].pc+2);self.reject(rows)
    def test_wrong_spin_opcode(self):
        rows=list(self.rows);rows[-1]=replace(rows[-1],instruction=0x13);self.reject(rows)

if __name__=='__main__':unittest.main()
