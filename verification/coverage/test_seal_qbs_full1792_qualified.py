import copy
from pathlib import Path
import tempfile
import unittest

import seal_qbs_full1792_qualified as p


class Seal(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.record=p.evidence()

    def test_actual1792_with_annotation_and_full17920checks(self):
        p.gate(self.record['qualification'])
        self.assertEqual(len(self.record['actual_annotated_native_records']),1792)
        self.assertEqual(self.record['state_checks'],17920)
        self.assertFalse(self.record['final_application'])

    def test_missing_final_and_changed_population_rejected(self):
        for field,value in (('five_stages_pass',False),('target_count',1791),('protected_count',41213),
                            ('application',True),('not_arbitrary_X_or_delta_proof',False)):
            r=copy.deepcopy(self.record['qualification']);r[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):p.gate(r)
        r=copy.deepcopy(self.record['qualification']);r['actual_native_records'].pop()
        with self.assertRaises(ValueError):p.gate(r)

    def test_source_boundary_no_fourstate_promotion(self):
        r=copy.deepcopy(self.record['qualification']);r['source_control_boundary']['boolean_checks_are_four_state_proof']=True
        with self.assertRaises(ValueError):p.gate(r)

    def test_pin_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'pin';path.write_bytes(b'original');ledger={str(path):p.f.sha(path)}
            p.f.check_pins(ledger);path.write_bytes(b'changed')
            with self.assertRaises(ValueError):p.f.check_pins(ledger)


if __name__=='__main__':unittest.main()
