"""Finite layout/gold and real host corruption tests; never launch VCS."""
import json
import os
from pathlib import Path
import struct
import subprocess
import tkinter
import unittest

import build_qbs_pending_two_phase783 as b


class FixtureTests(unittest.TestCase):
    def test_phase0_exact_proved_fixture(self):
        self.assertEqual(b.fixture()[0],b.old.fixture())

    def test_q6_all_coefficients_and_signed_scales(self):
        w=b.fixture()[1][0]
        for row in range(8):
            for k in range(2):
                values,scales=b.decode_q6(w[74+(2*row+k)*210:74+(2*row+k+1)*210])
                self.assertEqual(values,[b.q6_value(row,k,i) for i in range(256)])
                self.assertEqual(scales,[b.q6_scale(row,k,g) for g in range(16)])

    def test_q6_corruption_changes_decode(self):
        w=bytearray(b.fixture()[1][0][74:284]);expected=b.decode_q6(w)
        w[0]^=1;self.assertNotEqual(b.decode_q6(w),expected)
        w[208]^=1
        with self.assertRaises(ValueError):b.decode_q6(w)

    def test_all_tail_bytes_preserved_phase1(self):
        _,_,gold,values=b.fixture()[1];seed=b.old.seed_bytes()
        active=set()
        for ctx in range(8):
            for row in range(8):
                offset=1024+128*ctx+4*row
                self.assertEqual(struct.unpack_from('<f',gold,offset)[0],values[8*ctx+row])
                active.update(range(offset,offset+4))
        self.assertEqual(bytes(v for i,v in enumerate(gold) if i not in active),
                         bytes(v for i,v in enumerate(seed) if i not in active))

    def test_container_guards(self):
        for phase,(w,a,_,_) in enumerate(b.fixture()):
            wb,ab=(1344,2336) if not phase else (3360,4672);ao=64 if not phase else 76
            self.assertEqual(w[:74],bytes([0xa5])*74)
            self.assertEqual(w[74+wb:],bytes([0xa5])*(len(w)-74-wb))
            self.assertEqual(a[:ao],bytes([0x5a])*ao)
            self.assertEqual(a[ao+ab:],bytes([0x5a])*(len(a)-ao-ab))

    def test_frozen_source_profiles(self):
        self.assertEqual(len(b.source_contract()),9)

    def test_probe_real_tcl_syntax_and_banks(self):
        t=tkinter.Tcl();t.eval('set captured {}; set ready 0')
        t.eval('proc dump {args} {global captured; if {[lindex $args 0] eq "-add"} {lappend captured [lindex $args 1]}; return 1}')
        t.eval('proc show {args} {}; proc run {args} {error HOST_STOP}; proc exit {args} {}')
        t.eval('rename puts realputs; proc puts {args} {global ready; if {[lindex $args end] eq "QBS_TWO_PHASE_PROBE_READY"} {set ready 1}}')
        t.eval(b.PROBE.read_text())
        self.assertEqual(t.eval('set ready'),'1')
        objects=t.splitlist(t.eval('set captured'))
        self.assertEqual(len(objects),len(set(objects)))
        for bank in (0,1):
            self.assertTrue(any('bank%d.activation_pending_q'%bank in x for x in objects))
            self.assertTrue(any('bank%d.i_payload_buffer.gen_write_merge[0].gen_bank_plane[2].gen_bank_row[2].gen_byte_merge[5].hit'%bank in x for x in objects))


class ActualPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value=os.environ.get('QBS_TWO_PHASE_PREFLIGHT')
        if not value:raise unittest.SkipTest('Set QBS_TWO_PHASE_PREFLIGHT for actual immutable preflight')
        cls.out=Path(value).resolve();cls.manifest=json.loads((cls.out/'preflight-manifest.json').read_text())

    def test_actual_all_pins(self):
        b.common.verify(self.manifest['input_pins']);b.common.verify(self.manifest['output_pins'])

    def test_actual_host_positive_and_all_negatives(self):
        p=subprocess.run([self.out/'host'],capture_output=True,timeout=10)
        self.assertEqual(p.returncode,0);self.assertIn(b'checks=14 errors=0',p.stdout)
        for phase in range(2):
            for kind in b.MUTATIONS:
                with self.subTest(phase=phase,kind=kind):
                    p=subprocess.run([self.out/'host',kind,str(phase)],capture_output=True,timeout=10)
                    self.assertEqual(p.returncode,1);self.assertIn(b'FAILED:',p.stdout)

    def test_actual_contract(self):
        m=self.manifest
        self.assertEqual([r['word'] for r in m['sites']],list(b.WORDS))
        self.assertEqual(m['full_vrf_checkpoint_bytes'],[4096,4096])
        self.assertEqual(m['host_negative_tests'],18)
        self.assertFalse(m['vcs_launched']);self.assertFalse(m['custom_spike_pass'])
        self.assertEqual(b.common.sha(Path(m['binary'])),m['binary_sha256'])


if __name__=='__main__':unittest.main()
