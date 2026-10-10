from pathlib import Path
import unittest
from unittest.mock import patch
import prepare_narrow_source_group_gain_736 as p


class Tests(unittest.TestCase):
    def test_frozen_predecessor_and_exact3_source_changes(self):
        original=Path(p.prior.__file__).read_text()
        adapted=p.adapted_source(original)
        self.assertEqual(p.life.digest(Path(p.prior.__file__)),p.PRIOR_SHA)
        self.assertIn('Exact sealed formal736 required',adapted)
        self.assertIn('Exact unique736 required',adapted)
        self.assertIn("Path(PRIOR_FILE).with_name('test_prepare_narrow_source_group_gain.py')",adapted)
        self.assertEqual(p.load_adapter()['BASE'],p.prior.BASE)  # 735 remains the inherited prefix anchor.

    def test_wrong_baseline_or_seal_rejected_before_any_read(self):
        ns=p.load_adapter()
        with patch.object(p.life,'read_bound') as read:
            for baseline,seal in ((p.prior.BASE,p.prior.BASE_SEAL),(p.BASE,'foreign'),
                                 (p.prior.OUT/'foreign',p.BASE_SEAL)):
                with self.assertRaisesRegex(ValueError,'Exact sealed formal736'):
                    ns['inputs'](p.prior.QUAL,p.prior.QUAL_SEAL,baseline,seal)
            read.assert_not_called()

    def test_source_drift_or_duplicate_entry_rejected(self):
        original=Path(p.prior.__file__).read_text()
        for source in (original.replace('def inputs(', 'def foreign('),original+'\ndef inputs(qualpath,qualseal,baseline,baseseal):\n'):
            with self.assertRaises(ValueError):p.adapted_source(source)

    def test_original_module_globals_not_mutated(self):
        inputs=p.prior.inputs;p.load_adapter()
        self.assertIs(p.prior.inputs,inputs)
        self.assertEqual(p.prior.BASE.name,'readonly-csr-offline-admitted-735-parent-20261006-01')


if __name__=='__main__':unittest.main()
