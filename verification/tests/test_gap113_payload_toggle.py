import copy
import json
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
import build_gap113_payload_toggle as tool


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=tempfile.TemporaryDirectory();cls.host=Path(cls.directory.name)/'host'
        subprocess.run(['cc','-O2','-Wall','-Wextra','-Werror','-DGAP110_HOST=1',
                        tool.APP/'main.c','-o',cls.host],check=True,capture_output=True)
        cls.evidence=json.loads(tool.EVIDENCE.read_bytes())

    @classmethod
    def tearDownClass(cls):cls.directory.cleanup()

    def test_actual_full_host_checks(self):
        r=subprocess.run([self.host],capture_output=True,check=True)
        self.assertIn(b'PASSED: qbs_gap113_payload_toggle inherited_checks=44 errors=0',r.stdout)
        self.assertIn(b'vrf_words=2048 initial_words=2048 source_bytes=7328 csr_words=24',r.stdout)

    def test_actual_templates_independent_gold(self):
        expected=b''
        for phase in (0,1):
            w,a,g=tool.fixtures(phase);expected+=w+a+struct.pack('<%dI'%len(g),*g)
        self.assertEqual(subprocess.check_output([self.host,'--dump']),expected)

    def test_all_42_reused_negative_mutations(self):
        from build_gap110_q3_r4 import MUTATIONS
        for phase in (0,1):
            for mutation in MUTATIONS:
                with self.subTest(phase=phase,mutation=mutation):
                    r=subprocess.run([self.host,mutation,str(phase)],capture_output=True)
                    self.assertEqual(r.returncode,1);self.assertIn(b'FAILED: qbs_gap113_payload_toggle',r.stdout)

    def test_legal_permutation_complement_and_bsum(self):
        w,a,g=tool.fixtures(0);_,b,_=tool.fixtures(1)
        for c in range(8):
            values=[a[68+32+8*i+c] for i in range(256)]
            self.assertEqual(set(values),set(range(256)))
            for i,v in enumerate(values):self.assertEqual(v^b[68+32+8*i+c],255)
            for group in range(16):
                signed=[v if v<128 else v-256 for v in values[16*group:16*group+16]]
                self.assertEqual(struct.unpack_from('<h',a,68+2080+16*group+2*c)[0],sum(signed))
        broken=bytearray(a[68:68+2336]);broken[2080]^=1
        with self.assertRaises(ValueError):tool.native.unpack_oracle(w[64:944],broken,7)

    def test_exact83_serialized_zeros_no_direction_claim(self):
        t=tool.target(self.evidence);self.assertEqual(len(t['serialized_zero_coordinates']),83)
        self.assertFalse(t['direction_binding_verified'])

    def test_wrong_scope_or_checksum_rejected(self):
        d=copy.deepcopy(self.evidence);del d['metrics'][tool.SCOPE]
        with self.assertRaises(KeyError):tool.target(d)
        d=copy.deepcopy(self.evidence);d['metrics'][tool.SCOPE]['checksum']='123'
        with self.assertRaises(ValueError):tool.target(d)

    def test_non740_or_hit_target_rejected(self):
        d=copy.deepcopy(self.evidence);d['tests']=d['tests'][:-1]
        with self.assertRaises(ValueError):tool.target(d)
        d=copy.deepcopy(self.evidence);row=d['metrics'][tool.SCOPE];row['bits']=hex((1<<row['width'])-1)
        with self.assertRaises(ValueError):tool.target(d)

    def test_phase_or_unsafe_native_scale_rejected(self):
        with self.assertRaises(ValueError):tool.fixtures(True)
        w,a,_=tool.fixtures(0);broken=bytearray(w[64:944]);broken[109]=0
        with self.assertRaises(ValueError):tool.native.unpack_oracle(broken,a[68:68+2336],7)


if __name__=='__main__':unittest.main()
