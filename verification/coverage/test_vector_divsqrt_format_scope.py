"""Source-bound format reachability review, not a native exclusion approval."""
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FormatScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = ROOT / 'verification/out/repaired-aligned-build-20260930-01'
        cls.pins = json.loads((cls.build / 'build-source-pins.json').read_bytes())
        names = ['hardware/src/lane/vmfpu.sv', 'hardware/include/ara_pkg.sv',
                 'hardware/deps/fpnew/src/fpnew_top.sv',
                 'hardware/deps/fpnew/src/fpnew_opgroup_block.sv',
                 'hardware/deps/fpnew/src/fpnew_opgroup_multifmt_slice.sv',
                 'hardware/deps/fpnew/src/fpnew_divsqrt_th_64_multi.sv']
        cls.sources = {}
        for name in names:
            path = ROOT / name
            if hashlib.sha256(path.read_bytes()).hexdigest() != cls.pins[str(path)]:
                raise ValueError('Source drift: ' + name)
            cls.sources[Path(name).name] = path.read_text()

    def test_all_destination_assignments_exclude_alternate_format(self):
        text = self.sources['vmfpu.sv']
        assignments = re.findall(r'\bfp_dst_fmt\s*=\s*([^;]+);', text)
        self.assertEqual(assignments, ['FP64', 'FP8', 'FP16', 'FP16', 'FP32', 'FP64'])
        self.assertNotIn('FP16ALT', assignments)
        self.assertIn('.dst_fmt_i     (fp_dst_fmt     )', text)

    def test_intermediate_ports_pass_the_format_without_reencoding(self):
        self.assertIn('.dst_fmt_i,', self.sources['fpnew_top.sv'])
        self.assertIn('.dst_fmt_i,', self.sources['fpnew_opgroup_block.sv'])
        self.assertIn('.dst_fmt_i,', self.sources['fpnew_opgroup_multifmt_slice.sv'])

    def test_wrapper_pipeline_preserves_format(self):
        text = self.sources['fpnew_divsqrt_th_64_multi.sv']
        self.assertIn('assign inp_pipe_dst_fmt_q[0]  = dst_fmt_i;', text)
        self.assertIn("`FFL(inp_pipe_dst_fmt_q[i+1],  inp_pipe_dst_fmt_q[i],  reg_ena, fpnew_pkg::fp_format_e'(0))", text)
        self.assertIn('assign dst_fmt_q  = inp_pipe_dst_fmt_q[NUM_INP_REGS];', text)
        self.assertIn('fpnew_pkg::FP16ALT: divsqrt_fmt = 4\'b0001;', text)
        self.assertIn('fpnew_pkg::FP64:    divsqrt_fmt = 4\'b1000;', text)
        self.assertIn('fpnew_pkg::FP32:    divsqrt_fmt = 4\'b0100;', text)
        self.assertIn('fpnew_pkg::FP16:    divsqrt_fmt = 4\'b0010;', text)

    def test_configuration_is_the_frozen_default_build(self):
        command = json.loads((self.build / 'compile.command.json').read_bytes())['command']
        self.assertIn('config=default', command)
        self.assertIn('nr_lanes=4', command)
        self.assertIn('vlen=1024', command)
        self.assertIn("FPUSupportHalfSingleDouble = 6'b111000", self.sources['ara_pkg.sv'])


if __name__ == '__main__':
    unittest.main()
