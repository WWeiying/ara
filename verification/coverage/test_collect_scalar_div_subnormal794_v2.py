import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import patch
import collect_scalar_div_subnormal794_v2 as c


class FullSuccessor(unittest.TestCase):
    def test_actual_authority_and_frozen_predecessor(self):
        pins=c.authority()
        self.assertEqual(pins[str(Path(c.original.__file__).resolve())],c.wave.OLD_SHA)
        self.assertEqual(pins[str(c.WAVE_EVIDENCE)],c.WAVE_SHA)

    def test_missing_or_drifted_wave_authority_rejected(self):
        with patch.object(c,'WAVE_SHA','0'*64):
            with self.assertRaises(ValueError):c.authority()

    def test_wrong_predecessor_rejected(self):
        with patch.object(c,'BASE_SHA','0'*64):
            with self.assertRaises(ValueError):c.authority()

    def test_complete_call_chain_private_replacements_only(self):
        def fake(run,out,seal):
            self.assertIs(wave_audit,c.wave.wave_audit)
            self.assertIsNot(life,c.life)
            self.assertIsNot(toggle,c.original.toggle)
            self.assertEqual(seal,'seal')
        with patch.object(c.original,'collect',fake),patch.object(c,'authority',return_value={}):
            c.collect(Path('/run'),Path('/not-existing-div-qualification-v2-test'),'seal')

    def test_existing_output_rejected(self):
        with tempfile.TemporaryDirectory() as out:
            with self.assertRaises(ValueError):c.collect(Path('/run'),Path(out),'seal')

    def test_full_toggle_shape_required(self):
        with self.assertRaises(ValueError):c.exact_toggle_union([],[])

    def test_publication_binds_successor_without_overwrite(self):
        with tempfile.TemporaryDirectory() as out:
            path=Path(out)/'qualification.json'
            value=dict(baseline=794,baseline_seal=c.BASE_SHA,input_pins={})
            with patch.object(c.life,'check'):
                c.publisher({'/test':'a'*64})(path,value)
                with self.assertRaises(FileExistsError):c.publisher({'/test':'a'*64})(path,value)
            self.assertEqual(json.loads(path.read_text())['input_pins'],{'/test':'a'*64})
            self.assertIn('flush clear has priority',json.loads(path.read_text())['qualification_authority']['cancellation_semantics'])
            self.assertNotIn('qualification_authority',value)

    def test_wrong_publication_baseline_rejected(self):
        with self.assertRaises(ValueError):c.publisher({})(Path('/qualification.json'),
            dict(baseline=793,baseline_seal=c.BASE_SHA,input_pins={}))


if __name__=='__main__':unittest.main()
