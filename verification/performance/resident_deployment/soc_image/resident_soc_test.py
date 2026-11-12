import importlib.util
from pathlib import Path
import unittest

import build_image as s
from resident_capability_validator import WORD


class SuccessorTests(unittest.TestCase):
    def test_exact_derivation_and_old_contract_unchanged(self):
        self.assertEqual(s.sha(s.BASE), s.BASE_SHA)
        original = s.BASE.read_text()
        self.assertIn('resident_capability=0, ideal_dispatcher=0)', original)
        self.assertIn(s.OLD_CAP_BLOCK, original)
        changed = s.derive(original)
        self.assertNotIn(s.OLD_CAP_BLOCK, changed)
        self.assertIn('validate(source, b)', changed)
        for guard in ('Locked dependencies / repaired CPU commit-stage identity drift',
                      'All-on filelist selection drift', 'Shared FMA must use the sealed default-OFF macro',
                      'Missing frozen source/helper pin', 'Exact file inventory drift'):
            if guard in original:
                self.assertIn(guard, changed)
        with self.assertRaises(ValueError):
            s.derive(original.replace('resident_capability=0', 'resident_capability=1'))

    def test_only_configuration_change_is_resident_word(self):
        original = importlib.util.spec_from_file_location('old_sealed_soc', s.BASE)
        old = importlib.util.module_from_spec(original)
        original.loader.exec_module(old)
        new = s.worker()
        self.assertEqual([key for key in old.CONFIG if old.CONFIG[key] != new.CONFIG[key]],
                         ['resident_capability'])
        self.assertEqual(new.CONFIG['resident_capability'], WORD)
        self.assertEqual(new.MONITORS, old.MONITORS)
        self.assertEqual(set(new.OVERLAYS), set(old.OVERLAYS) | set(s.CAP_FILES) | set(s.EXTENSION_FILES))
        for name in new.OVERLAYS:
            self.assertNotIn('/deps/', name)
            self.assertNotIn('/tb/', name)
        code = new.DERIVED_FILES['soc_build.py']
        self.assertIn('RESIDENT_DEPLOYMENT_SOC_BUILT_NOT_EXECUTED', code)
        self.assertNotIn('ENABLEMENT_SOC_BUILT_NOT_EXECUTED', code)

    def test_output_boundary(self):
        new = s.worker()
        self.assertEqual(new.output(new.OUT/'enablement_soc_resident_deployment_test').parent, new.OUT)
        for name in ('enablement_soc_old', 'stage3_soc_test'):
            with self.assertRaises(ValueError):
                new.output(new.OUT/name)


if __name__ == '__main__':
    unittest.main()
