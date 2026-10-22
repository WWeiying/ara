"""Focused GAP82 conservation and exact-byte rejection tests; no EDA."""
import copy
from dataclasses import replace
from pathlib import Path
import struct
import tempfile
import unittest

import run_gap82_old_image as runner
from ara_verify.vector_commit import ArchActivity, VectorWrite


def rows():
    result = []
    for i in range(2):
        for event,cycle,word,order,pc in [
                ('arch_start',10,runner.WORD,20+i,0),
                ('cvx_req',30,runner.WORD,-1,0),
                ('cvx_resp',32,0,-1,0),
                ('retire',34,runner.WORD,100+i,1000+4*i)]:
            result.append(dict(event=event,cycle=str(cycle+100*i),insn=f'{word:08x}',
                               order=str(order),pc=f'{pc:x}',trans_id='0',trap='0'))
    return result


def activity():
    a = ArchActivity(instruction=runner.WORD,allocations=1,completions=1,
                     use_vd=True,vd=8,eew=2,vl=1,vstart=0)
    for context in range(4):
        for word in range(4):
            for lane in range(4):
                value = int.from_bytes(struct.pack('<f',float(256*(context+1)))+bytes(4),'little') if word == lane == 0 else 0
                a.writes.append(VectorWrite(row=len(a.writes)+2,cycle=20,arch_seq=20,vid=0,
                    lane=lane,source=4,instruction=runner.WORD,eew=2,addr=(8+context)*4+word,
                    be=255,data=value,known_be=255))
    return a


class RunnerTests(unittest.TestCase):
    def test_two_commands_reused_trans_id(self):
        starts,complete = runner.conservation(rows(),[1000,1004])
        self.assertEqual([s[0] for s in starts],[20,21])
        self.assertEqual(len(complete),2)

    def test_conservation_rejects_mutations(self):
        mutations = []
        r = rows(); del r[6]; mutations.append(r)
        r = rows(); r[7]['pc']='3e8'; mutations.append(r)
        r = rows(); r[4]['order']='20'; mutations.append(r)
        r = rows(); r[6]['trans_id']='1'; mutations.append(r)
        r = rows(); r[6]['trap']='1'; mutations.append(r)
        r = rows(); r[4]['cycle']='33'; mutations.append(r)
        r = rows(); r.insert(2,dict(r[1])); mutations.append(r)
        for r in mutations:
            with self.subTest(rows=r), self.assertRaises(ValueError):
                runner.conservation(r,[1000,1004])

    def test_exact_writeback(self):
        runner.activity_bytes(activity(),4,1024,10,32)

    def test_writeback_rejects_mutations(self):
        for field,value in [('completions',0),('vl',2),('vd',9),('instruction',0),('eew',3)]:
            a=activity(); setattr(a,field,value)
            with self.subTest(field=field),self.assertRaises(ValueError):
                runner.activity_bytes(a,4,1024,10,32)
        for field,value in [('data',1),('known_be',0),('cycle',40),('addr',31),('lane',4)]:
            a=activity(); a.writes[0]=replace(a.writes[0],**{field:value})
            with self.subTest(write=field),self.assertRaises(ValueError):
                runner.activity_bytes(a,4,1024,10,32)
        for duplicate in (True,False):
            a=activity()
            if duplicate: a.writes.append(copy.copy(a.writes[0]))
            else: a.writes.pop()
            with self.subTest(duplicate=duplicate),self.assertRaises(ValueError):
                runner.activity_bytes(a,4,1024,10,32)

    def test_software_strict_counts(self):
        text = '\n'.join(['GAP82 command=0 checks=17 errors=0','GAP82 command=1 checks=17 errors=0',
            'GAP82 inspected vrf_words=2048 initial_words=2048 source_bytes=6880 csr_words=24',
            'PASSED: qbs_gap82_m4_phase4_phase8 checks=41 errors=0','Core Test *** SUCCESS ***',
            '[ARA_CONTRACT] requests=2 responses=2 exceptions=0 mmu_request_cycles=0 protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0'])+'\n'
        with tempfile.TemporaryDirectory() as tmp:
            log=Path(tmp)/'run.log'; log.write_text(text)
            runner.software(log)
            for bad in [text.replace('checks=17','checks=18',1),
                        text.replace('checks=41','checks=44'),
                        text.replace('source_bytes=6880','source_bytes=3440'),
                        text+'GAP82 command=1 checks=17 errors=0\n',text+'FAILED: corruption\n']:
                log.write_text(bad)
                with self.subTest(log=bad),self.assertRaises(ValueError): runner.software(log)


if __name__ == '__main__':
    unittest.main()
