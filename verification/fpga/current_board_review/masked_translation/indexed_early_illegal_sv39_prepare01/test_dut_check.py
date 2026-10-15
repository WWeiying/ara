#!/usr/bin/env python3
"""Focused adapter tests; synthetic rows are never DUT evidence."""
import json
from pathlib import Path
import tempfile
import unittest
import dut_check as d
import vcs
HERE=Path(__file__).resolve().parent
S=json.loads((HERE/'reference_indexed01/soc.symbols.json').read_text())


def row(pc,insn=0x13,rd=0,value=0,order=0):
    r={k:'0' for k in d.FIELDS};r.update(cycle=str(order),event='retire',order=str(order),
        pc=f'{pc:x}',insn=f'{insn:x}',rd=str(rd),rd_wdata=f'{value:x}')
    return r


class Tests(unittest.TestCase):
    def test_all_966_operands_and_restores(self):
        for store in (0,1):
            c=d.Checker(S,store);c.saved={csr:0 for csr in d.RESTORE}
            for i,v in enumerate(c.gold+[0]*14):
                c.regs[10]=c.regs[11]=v;c.row(row(S['check'],order=i))
            self.assertEqual(c.calls,966)
    def test_tail_or_guard_equal_but_wrong(self):
        for n in (30,100,350,650,850,899):
            c=d.Checker(S,0);c.calls=n;c.regs[10]=c.regs[11]=c.gold[n]^1
            with self.assertRaises(ValueError):c.row(row(S['check']))
    def test_mismatch(self):
        c=d.Checker(S,0);c.regs[10]=127;c.regs[11]=128
        with self.assertRaises(ValueError):c.row(row(S['check']))
    def test_missing_restore_save(self):
        c=d.Checker(S,0);c.calls=952
        with self.assertRaises(ValueError):c.row(row(S['check']))
    def test_bad_vstart(self):
        c=d.Checker(S,0);c.capture={}
        with self.assertRaises(ValueError):c.row(row(S['mt_trap_vstart_read'],0x00802373,6,1))
    def test_wrong_target_opcode(self):
        with self.assertRaises(ValueError):d.Checker(S,0).row(row(S['mt_target']))
    def test_first_error(self):
        for name in ('replay_mismatch','mt_bad_trap','trap_entry'):
            with self.assertRaises(ValueError):d.Checker(S,0).row(row(S[name]))
    def test_mepc_before_retry(self):
        c=d.Checker(S,0);c.retry=True
        with self.assertRaises(ValueError):c.row(row(S['mt_handler']+4,0x34131073))
    def test_partial_terminal(self):
        with self.assertRaises(ValueError):d.Checker(S,0).finish()
    def test_exit_nonzero(self):
        c=d.Checker(S,0);c.regs[5]=0xd0000000;c.regs[6]=1
        r=row(S['main'],0x0062b023);r.update(mem_addr='d0000000',mem_wmask='ff',mem_wdata='1')
        with self.assertRaises(ValueError):c.row(r)
    def test_durable_real_filesystem(self):
        for result in ((0,1.0,False,False),(7,1.0,False,True),(-15,1.0,True,False)):
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)
                actual=vcs.monitor_wrapper(lambda *args:result)(['simv'],p,p/'console.log',10)
                self.assertEqual(actual,result);receipt=json.loads((p/'child_exit.json').read_text())
                self.assertEqual(receipt['returncode'],result[0]);self.assertFalse(receipt['architectural_acceptance'])
                with self.assertRaises(FileExistsError):vcs.save(p/'child_exit.json',{})


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    vcs.save(HERE/'host_dut_check01.json',dict(passed=result.wasSuccessful(),tests=result.testsRun,
        checker_sha256=vcs.sha(Path(d.__file__)),worker_sha256=vcs.sha(Path(vcs.__file__)),
        test_sha256=vcs.sha(Path(__file__)),scope='Focused synthetic host checks only'))
    raise SystemExit(not result.wasSuccessful())

