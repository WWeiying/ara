import hashlib
from pathlib import Path
import tempfile
import unittest

import eight_policy_epoch_732_report_v4 as v4


class BindingTests(unittest.TestCase):
    def test_private_snapshot_constant_captured_original_unchanged(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name).resolve() / 'config.json'
            path.write_bytes(b'{}')
            pins = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()}
            original = v4.prior.wiring.population.snapshot.BUILD
            owner = v4.PrivateWiring(pins, list(pins), list(pins))
            functions = [vars(cls).get('source_binding') for cls in type(owner.context).__mro__]
            source = next(f for f in functions if f is not None and
                f.__code__ is v4.prior.wiring.population.Context.source_binding.__code__)
            self.assertIsInstance(source.__globals__['snapshot'].BUILD, owner.Path)
            self.assertIs(v4.prior.wiring.population.snapshot.BUILD, original)
            self.assertIs(owner.context.check_config.__func__.__code__,
                          v4.prior.wiring.population.Context.check_config.__code__)
            owner.phase.close()

    def test_original_frozen_paths_unchanged(self):
        original = v4.prior.wiring.population.frozen.QUALIFIED707
        self.assertIs(type(original), Path().__class__)
        self.assertEqual(v4.prior.PLAN, 'epoch-readiness-v3-plan.json')
        self.assertEqual(v4.check.__globals__['PLAN'], 'epoch-readiness-v4-plan.json')


if __name__ == '__main__':
    unittest.main()
