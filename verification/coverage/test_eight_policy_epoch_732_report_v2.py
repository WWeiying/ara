from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import eight_policy_epoch_732_report_v2 as v2


class RoleTests(unittest.TestCase):
    def test_large_unused_json_loses_only_read_authority(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            required = root / 'config.json'
            other = root / 'historical.json'
            small = root / 'small.json'
            required.write_text('{}')
            other.write_text('{"unused":true}')
            small.write_text('0')
            pins = {str(p): 'a' * 64 for p in (required, other, small)}
            value = dict(output=str(root), fixed_seal='b' * 64, pins=pins,
                         byte_paths=list(pins), json_paths=list(pins))
            with patch.object(v2, 'SMALL_JSON', 1), \
                 patch.object(v2.prior.Builder, 'load_sealed', side_effect=[
                     dict(eight_output=str(root), eight_seal='c' * 64), dict(six_output=str(root))]):
                result = v2.restrict_roles(value)
            self.assertEqual(result['pins'], pins)
            self.assertNotIn(str(other), result['byte_paths'])
            self.assertIn(str(required), result['byte_paths'])
            self.assertIn(str(small), result['json_paths'])
            self.assertEqual(result['hash_only_large_json'], [str(other)])

    def test_private_functions_no_original_globals_mutated(self):
        self.assertIs(v2.check.__code__, v2.prior.check.__code__)
        self.assertIs(v2.run_reviewed.__code__, v2.prior.run_reviewed.__code__)
        self.assertEqual(v2.prior.PLAN, 'epoch-readiness-plan.json')
        self.assertEqual(v2.check.__globals__['PLAN'], 'epoch-readiness-v2-plan.json')
        self.assertIn(v2.prior.SCRIPT, v2.dependencies())
        self.assertIn(v2.SCRIPT, v2.dependencies())


if __name__ == '__main__':
    unittest.main()
