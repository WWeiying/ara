import os
from pathlib import Path
import struct
import subprocess
import tkinter
import unittest

import build_qbs_k2_row_pending781 as case


class FixtureTests(unittest.TestCase):
    def test_decode_every_q2_value(self):
        w,_,_,_=case.fixture()
        for row in range(8):
            for k in range(2):
                b=w[74+84*(2*row+k):74+84*(2*row+k+1)]
                for i in range(256):
                    half=i//128;group=(i%128)//16;lane=i%16
                    self.assertEqual((b[16+half*32+(group&1)*16+lane]>>(2*(group//2)))&3,case.q(row,k,i))
                self.assertEqual(b[80:],bytes.fromhex('003c003c'))

    def test_activation_aux_and_alignment(self):
        _,a,_,_=case.fixture()
        for ctx in range(4):
            for k in range(2):
                start=64+292*(2*ctx+k)
                self.assertEqual(struct.unpack_from('<I',a,start)[0],0x3f800000)
                for g in range(16):
                    self.assertEqual(struct.unpack_from('<h',a,start+260+2*g)[0],
                        sum(case.a(ctx,k,i) for i in range(g*16,g*16+16)))
        self.assertEqual((64+1460)%16,4)
        self.assertEqual(74%16,10)

    def test_full_vrf_zero_tail_and_untouched(self):
        _,_,image,values=case.fixture();seed=case.seed_bytes()
        self.assertEqual(image[:1024],seed[:1024]);self.assertEqual(image[1536:],seed[1536:])
        for ctx in range(4):
            self.assertEqual(image[1024+128*ctx+32:1024+128*(ctx+1)],bytes(96))
            self.assertEqual(list(struct.unpack_from('<8f',image,1024+128*ctx)),values[8*ctx:8*(ctx+1)])

    def test_pending_witness_no_recompact(self):
        locations=[28+b-4 for b in range(16)]
        consumed=sum(1<<b for b,x in enumerate(locations) if x//32==0)
        self.assertEqual(consumed,0xff);self.assertEqual(0xffff^consumed,0xff00)
        self.assertEqual(locations[13],37);self.assertEqual(locations[13]%32,5)

    def test_probe_actual_tcl_brackets_and_failclosed(self):
        script=(case.ROOT/'verification/coverage/qbs_k2_row_pending781_probe.tcl').read_text()
        tcl=tkinter.Tcl();tcl.eval('set observed {}; proc show {args} {}; proc dump {args} {return 1}; proc run {args} {error HOST_STOP}; proc exit {args} {}')
        tcl.eval('rename puts original_puts; proc puts {args} {global observed; lappend observed [lindex $args end]}')
        tcl.eval(script)
        observed=tcl.eval('join $observed "\\n"')
        for name in ('activation_pending_q','write_req[0][2][2]','gen_write_merge[1].gen_bank_plane[2].gen_bank_row[2].selected_word'):
            self.assertIn(name,observed)
        self.assertIn('QBS_PENDING_PROBE_READY',observed)
        self.assertIn('QBS_PENDING_PROBE_REJECT HOST_STOP',observed)


@unittest.skipUnless(os.environ.get('QBS_PENDING_PREFLIGHT'),'Set actual preflight fixture')
class ActualPreflightTests(unittest.TestCase):
    def test_pins_and_host_mutations(self):
        out=Path(os.environ['QBS_PENDING_PREFLIGHT']).resolve();record=case.common.read(out/'preflight-manifest.json')
        case.common.verify(record['input_pins']);case.common.verify(record['output_pins'])
        self.assertEqual(record['host_negative_tests'],9)
        self.assertEqual(record['sites'][0]['word'],case.WORD)
        for kind in ('weight','activation','vrf','dest','tail','guard','csr','descriptor','sourceguard'):
            result=subprocess.run([out/'host',kind],capture_output=True,timeout=10)
            self.assertEqual(result.returncode,1,kind);self.assertIn(b'FAILED:',result.stdout)


if __name__=='__main__':unittest.main()
