import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('power_successor', Path(__file__).with_name('gate_rvv_short_power_v1.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class Tests(unittest.TestCase):
    def test_original_failure_not_overridden(self):
        with patch.object(p, 'original_inputs', side_effect=ValueError('original image gate')):
            with self.assertRaisesRegex(ValueError, 'original image gate'):
                p.checked_inputs(Path('/unused'), 'rvv', 'm1')

    def test_startup_evidence_and_mutations(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder)
            file = image / 'environment-validation.json'
            good = dict(state='OPPOSITE_VRF_SEEDS_EXACT_REDUCTIONS_PASS', seeds=[0, 1],
                        runtime_force=False, controls_initialized=False)
            for field, value in [('seeds', [0, 0]), ('runtime_force', True),
                                 ('controls_initialized', True), ('state', 'PASS'), (None, None)]:
                data = dict(good)
                if field:
                    data[field] = value
                file.write_text(json.dumps(data))
                original = (dict(image=str(image)), {}, image / 'design.ddc', {}, {})
                with patch.object(p, 'original_inputs', return_value=original):
                    if field:
                        with self.assertRaises(ValueError):
                            p.checked_inputs(image, 'rvv', 'm1')
                    else:
                        _, _, _, pins, roles = p.checked_inputs(image, 'rvv', 'm1')
                        self.assertEqual(pins[str(file)], p.dc.sha(file))
                        self.assertIn('512 VRF data words', roles['initialization'])


if __name__ == '__main__':
    unittest.main()
