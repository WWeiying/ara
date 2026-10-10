"""Check frozen parent parameter wiring; not native exclusion approval."""
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FF1ParentWidthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pins = json.loads((ROOT / 'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json').read_bytes())
        cls.sources = {}
        for name in ('fpnew_pkg.sv', 'fpnew_top.sv', 'fpnew_opgroup_block.sv',
                     'fpnew_opgroup_multifmt_slice.sv', 'fpnew_divsqrt_th_64_multi.sv'):
            path = ROOT / 'hardware/deps/fpnew/src' / name
            if hashlib.sha256(path.read_bytes()).hexdigest() != pins[str(path)]:
                raise ValueError('Frozen parent source drift: ' + name)
            cls.sources[name] = re.sub(r'\s+', ' ', path.read_text())
        path = ROOT / 'hardware/src/lane/vmfpu.sv'
        if hashlib.sha256(path.read_bytes()).hexdigest() != pins[str(path)]:
            raise ValueError('Frozen VMFPU source drift')
        cls.sources['vmfpu.sv'] = re.sub(r'\s+', ' ', path.read_text())

    def test_vector_parent_width_is_fixed(self):
        text = self.sources['vmfpu.sv']
        self.assertIn("localparam fpu_features_t FPUFeatures = '{ Width : 64, "
                      "EnableVectors: 1'b1, EnableNanBox : 1'b1,", text)
        self.assertIn('.Features (FPUFeatures )', text)

    def test_default_half_single_double_chain(self):
        pins = json.loads((ROOT / 'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json').read_bytes())
        names = ('hardware/tb/ara_testharness.sv', 'hardware/src/ara_soc.sv',
                 'hardware/src/ara_system.sv', 'hardware/src/ara.sv',
                 'hardware/src/lane/lane.sv', 'hardware/src/lane/vector_fus_stage.sv',
                 'hardware/include/ara_pkg.sv')
        sources = {}
        for name in names:
            path = ROOT / name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), pins[str(path)])
            sources[name] = re.sub(r'\s+', ' ', path.read_text())
        harness = sources[names[0]].split('ara_soc #(', 1)[1].split(') i_ara_soc', 1)[0]
        self.assertNotIn('FPUSupport', harness)
        self.assertIn("FPUSupportHalfSingleDouble = 6'b111000", sources[names[-1]])
        for name in names[1:-1]:
            self.assertIn('FPUSupport', sources[name])
            self.assertIn('.FPUSupport', sources[name])
        self.assertRegex(sources['hardware/src/ara_soc.sv'],
                         r'FPUSupport\s*=\s*FPUSupportHalfSingleDouble')
        for signal, bit in (('RVVD', 5), ('RVVF', 4), ('RVVH', 3)):
            self.assertIn('function automatic logic %s(fpu_support_e e); return e[%d];' %
                          (signal, bit), sources[names[-1]])

    def test_parent_width_and_format_forwarding(self):
        top = self.sources['fpnew_top.sv']
        block = self.sources['fpnew_opgroup_block.sv']
        self.assertIn('WIDTH = Features.Width', top)
        self.assertIn('.Width ( WIDTH )', top)
        self.assertIn('.FpFmtMask ( Features.FpFmtMask )', top)
        self.assertIn('.Width ( Width )', block)
        self.assertIn('.FpFmtConfig ( FpFmtMask )', block)

    def test_multiformat_lane_width_selection(self):
        text = self.sources['fpnew_opgroup_multifmt_slice.sv']
        self.assertIn('fpnew_pkg::get_lane_formats(Width, FpFmtConfig, LANE)', text)
        self.assertIn('MAX_WIDTH = fpnew_pkg::max_fp_width(ACTIVE_FORMATS)', text)
        self.assertIn('LANE_WIDTH = (OpGroup == fpnew_pkg::CONV) ? CONV_WIDTH : '
                      '(OpGroup == fpnew_pkg::DOTP) ? DOTP_WIDTH : MAX_WIDTH;', text)
        self.assertIn('LANE_FORMATS = (OpGroup == fpnew_pkg::CONV) ? CONV_FORMATS : '
                      '(OpGroup == fpnew_pkg::DOTP) ? DOTP_FORMATS : ACTIVE_FORMATS;', text)
        self.assertIn('.FpFmtConfig ( LANE_FORMATS )', text)
        wrapper = self.sources['fpnew_divsqrt_th_64_multi.sv']
        self.assertIn('WIDTH = fpnew_pkg::max_fp_width(FpFmtConfig)', wrapper)

    def test_format_lane_formula(self):
        text = self.sources['fpnew_pkg.sv']
        self.assertIn('res[fmt] = cfg[fmt] & (width / fp_width(fp_format_e\'(fmt)) > lane_no)', text)
        # Conditional result: the parent must independently enable these formats.
        widths = [max(w for w in (64, 32, 16) if 64 // w > lane) for lane in range(4)]
        self.assertEqual(widths, [64, 32, 16, 16])

    def test_population_has_exact_lane_operand_instances(self):
        bitmap = json.loads((ROOT / 'verification/out/gap94-offline-admitted-701-20261006-01/combined-bits.json').read_bytes())
        scopes = [s for s in bitmap['metrics']['branch']
                  if '.i_ara.' in s and s.endswith(('x_frac0_expnt', 'x_frac1_expnt'))]
        self.assertEqual(len(scopes), 32)
        pairs = []
        for scope in scopes:
            outer = re.search(r'\.gen_lanes\[(\d+)\]\.i_lane\.', scope)
            inner = re.search(r'\.gen_num_lanes\[(\d+)\]\.', scope)
            self.assertIsNotNone(outer)
            self.assertIsNotNone(inner)
            pairs.append((int(outer[1]), int(inner[1]), scope.rsplit('.', 1)[1]))
        self.assertEqual(set(pairs), {(outer, inner, operand)
                         for outer in range(4) for inner in range(4)
                         for operand in ('x_frac0_expnt', 'x_frac1_expnt')})


if __name__ == '__main__':
    unittest.main()
