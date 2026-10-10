"""Exact720 ancestry / independent OR gates; never invokes formal admission."""
import copy
import json
import unittest
from unittest.mock import patch

import prepare_akv_column_boundary_admission_720 as a


class PopulationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def read(path):return json.loads(path.read_text())
        cls.before=read(a.BASE/"combined-bits.json")
        cls.historical=read(a.prior.old.r.BASE/"combined-bits.json")
        cls.single=read(a.prior.old.r.CANDIDATE/"sample-bits.json")
        manifest=read(a.BASE/"admission-manifest.json")
        cls.gap103=read(a.Path(manifest["candidate"])/"single-raw-bits.json")

    def test_actual720_OR_and_fresh_delta(self):
        union,delta=a.population(self.before,self.historical,self.gap103,self.single)
        self.assertEqual(union["tests"][:-1],self.before["tests"])
        self.assertEqual(len(union["tests"]),721)
        self.assertEqual(delta["metrics"],dict(line=2,cond=3,branch=2,fsm=0))

    def test_reordered_prefix_rejected(self):
        before=copy.deepcopy(self.before);before["tests"][0],before["tests"][1]=before["tests"][1],before["tests"][0]
        with self.assertRaises(ValueError):a.population(before,self.historical,self.gap103,self.single)

    def test_duplicate_baseline_member_rejected(self):
        before=copy.deepcopy(self.before);before["tests"][-1]=before["tests"][0]
        with self.assertRaises(ValueError):a.population(before,self.historical,self.gap103,self.single)

    def test_wrong_gap103_singleton_rejected(self):
        gap=copy.deepcopy(self.gap103);gap["tests"]=["foreign.vdb"]
        with self.assertRaises(ValueError):a.population(self.before,self.historical,gap,self.single)

    def test719_cannot_be_reused_as720(self):
        with self.assertRaises(ValueError):a.population(self.historical,self.historical,self.gap103,self.single)

    def test_changed_baseline_bitmap_rejected(self):
        before=copy.deepcopy(self.before)
        rec=next(r for r in before["metrics"]["line"].values() if r["width"])
        rec["bits"]=hex(int(rec["bits"],16)^1)
        with self.assertRaises(ValueError):a.population(before,self.historical,self.gap103,self.single)

    def test_wrong_AKV_singleton_rejected(self):
        single=copy.deepcopy(self.single);single["tests"]=[self.before["tests"][-1]]
        with self.assertRaises(ValueError):a.population(self.before,self.historical,self.gap103,single)

    def test_known_failed_population_rejected(self):
        historical=copy.deepcopy(self.historical);gap=copy.deepcopy(self.gap103)
        historical["tests"][0]="/tmp/akv-column-boundary-old-image-20261006-01/code.vdb"
        before=a.prior.old.r.c.common.bitmap.combine(historical,gap)
        with self.assertRaises(ValueError):a.population(before,historical,gap,self.single)

    def test_zero_gain_cannot_inflate_population(self):
        gap=copy.deepcopy(self.gap103)
        gap["metrics"]=a.prior.old.r.c.common.bitmap.combine(gap,self.single)["metrics"]
        before=a.prior.old.r.c.common.bitmap.combine(self.historical,gap)
        with self.assertRaisesRegex(ValueError,"No actual positive coverage gain"):
            a.population(before,self.historical,gap,self.single)


class EvidenceGateTest(unittest.TestCase):
    def test_actual_formal720_seal(self):
        manifest=a.life.read_bound(a.BASE/"admission-manifest.json",a.BASE_SEAL)
        self.assertEqual(manifest["baseline_seal"],a.prior.BASE_SEAL)

    def test_scalar_hard_gate_not_bypassed(self):
        with patch.object(a.prior,"check",side_effect=ValueError("missing scalar qualification")) as check:
            with self.assertRaisesRegex(ValueError,"missing scalar"):a.evaluate()
        check.assert_called_once_with(a.PREVIOUS,a.PREVIOUS_SEAL)

    def test_wrong_baseline_seal_rejected(self):
        with self.assertRaises(ValueError):a.life.read_bound(a.BASE/"admission-manifest.json",'0'*64)

    def test_existing_output_rejected(self):
        with self.assertRaises(ValueError):a.prepare(a.PREVIOUS)


if __name__ == "__main__":
    unittest.main()
