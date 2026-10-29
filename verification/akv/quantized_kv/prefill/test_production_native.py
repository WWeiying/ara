import copy
import json
from pathlib import Path
import tempfile
import unittest

from build_production_native import capture_inputs, digest, TENSORS
from run_production_native import require_production_build, ROOT


class ProductionNativeTest(unittest.TestCase):
    def test_binding_gate(self):
        report = dict(state='BUILT_NOT_EXECUTED', whole_call=True, rebuilt_objects=16,
            token_major=True, physical_kv_heads=8, reused_objects=0, commands_per_trial=4,
            outputs_per_trial=1024, value_decodes=[74,20,20,74], kind='q4_0',
            value_binding='shared_rvv_q8_0',
            canonical_prefill=str(ROOT/'software/akv/experimental/quantized_kv/prefill/execute.h'))
        for kind in ('q4_0', 'q8_0'):
            require_production_build(dict(report, kind=kind))
        for key, value in (('value_binding', 'scalar'), ('canonical_prefill', 'verification/execute.h'),
                           ('kind', 'f32'), ('whole_call', 1), ('reused_objects', 1)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                require_production_build(dict(report, **{key:value}))

    def test_capture_geometry_and_identity(self):
        base = ROOT/'verification/out/quant-prefill-capture-20261028-01'
        audited = json.loads((ROOT/'verification/out/quant-prefill-capture-audit-20261028-01/manifest.json').read_text())
        for kind in ('q4_0', 'q8_0'):
            capture = base/kind/'prefill/block'
            self.assertEqual(len(capture_inputs(capture, kind, audited)), 10)
            with tempfile.TemporaryDirectory() as temp:
                folder, pins = Path(temp), {}
                for name in TENSORS:
                    for suffix in ('.bin', '.json'):
                        p = folder/(name+suffix)
                        p.write_bytes((capture/p.name).read_bytes())
                        pins[str(p)] = digest(p)
                altered = folder/'attn_k_input-0.json'
                meta = json.loads(altered.read_text())
                meta['strides'][1] += 1
                altered.write_text(json.dumps(meta))
                with self.assertRaisesRegex(ValueError, 'audit mismatch'):
                    capture_inputs(folder, kind, pins)
                pins = copy.copy(pins)
                pins[str(altered)] = digest(altered)
                with self.assertRaisesRegex(ValueError, 'geometry'):
                    capture_inputs(folder, kind, pins)


if __name__ == '__main__':
    unittest.main()
