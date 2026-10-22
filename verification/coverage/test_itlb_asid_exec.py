import subprocess
import unittest
from pathlib import Path
import build_itlb_asid_exec as pre


class Preflight(unittest.TestCase):
    def test_page_alignment_and_distinct_low_indices(self):
        for p in range(3):
            self.assertEqual(len({pre.address(p,e)>>12 for e in range(16)}),16)
            self.assertTrue(all(pre.address(p,e)&4095 == 64 for e in range(16)))
        self.assertEqual([pre.address(0,e) for e in range(16)],[pre.address(2,e) for e in range(16)])

    def test_exact_thunk_independent_decode(self):
        for e in range(16):
            w=pre.codeword(e,8);a,b=w&0xffffffff,w>>32
            self.assertEqual((a&127,(a>>7)&31,(a>>15)&31,a>>20),(0x13,10,0,256+e))
            self.assertEqual(b,0x00150513)
            self.assertEqual(pre.codeword(e,9)&0xffffffff,0x73)
            self.assertEqual(pre.codeword(e,511),pre.GUARD)

    def test_source_proof_actual_frozen(self):
        proof,pins=pre.source_contract()
        self.assertEqual(proof['entries'],16);self.assertEqual(proof['ASIDs'],[0x5555,0xaaaa,0x5555])
        self.assertGreaterEqual(len(pins),8)

    def test_pte_wx_g_u_are_protected(self):
        s={'itm_root':0x80004000,'itm_mid':0x80005000,'itm_leaf':0x80006000,'itm_code':0x80008000}
        for p in range(3):
            root,mid,leaf=pre.tables(s,p)
            self.assertEqual(root[2]&1023,0xcf)
            self.assertEqual(sum(v!=0 for v in leaf),16)
            for e in range(16):
                v=leaf[pre.shared.vpn(p,e)&511]
                self.assertEqual(v&1023,0x4b)
                self.assertEqual((v>>10)<<12,s['itm_code']+4096*e)

    def test_missing_phase_rejected(self):
        with self.assertRaisesRegex(ValueError,'Missing/extra'):
            pre.validate([],dict(trap_fail=1,itm_phase=2))

    def test_foreign_phase_rejected(self):
        c=pre.architecture.spike_trace.SpikeCommit(pc=0,instruction=0,gpr_writes={},fpr_writes={},
            vector_writes={},csr_writes={},memory_accesses=((2,2),))
        with self.assertRaisesRegex(ValueError,'CRT phase initialization'):
            pre.validate([c],dict(trap_fail=1,itm_phase=2))

    def test_probe_full_entry(self):
        script=Path(pre.__file__).with_name('itlb_asid_exec_probe.tcl').read_text()
        stub='proc dump {args} {return 1}\nproc show {args} {}\nproc run {} {}\n'
        result=subprocess.run(['tclsh'],input=stub+script,capture_output=True,text=True,check=True)
        lines=result.stdout.splitlines()
        self.assertEqual(lines.count('ITLB_EXEC_READY'),1)
        self.assertEqual(sum(x.startswith('ITLB_EXEC_OBJECT ') for x in lines),13)
        self.assertNotIn('force', '\n'.join(script.splitlines()[1:]))

    def test_probe_missing_object_rejected(self):
        script=Path(pre.__file__).with_name('itlb_asid_exec_probe.tcl').read_text()
        stub='proc dump {args} {return 0}\nproc show {args} {}\nproc run {} {}\n'
        r=subprocess.run(['tclsh'],input=stub+script,capture_output=True,text=True)
        self.assertEqual(r.returncode,1);self.assertIn('ITLB_EXEC_ERROR',r.stdout)
        self.assertNotIn('\nITLB_EXEC_READY\n',r.stdout)


if __name__ == '__main__':unittest.main()
