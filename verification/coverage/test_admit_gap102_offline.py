"""Offline admission negative fixtures; no real candidate evaluation or admission."""
from copy import deepcopy
import json
from unittest.mock import patch
import unittest

import admit_gap102_offline as a


class AdmissionTests(unittest.TestCase):
    def baseline(self):
        return {"tests":["historical-%d"%i for i in range(717)]}

    def test_population_prefix(self):
        before=self.baseline(); single={"tests":[str(a.collector.RUN/"code.vdb")]}
        union={"tests":before["tests"]+single["tests"]}
        with patch.object(a.bitmap,"combine",return_value=union),patch.object(a.bitmap,"delta",return_value={"metrics":{"branch":1}}):
            self.assertEqual(a.population(before,single,union)[0],union)

    def test_wrong_duplicate_and_failed_population(self):
        before=self.baseline();single={"tests":[str(a.collector.RUN/"code.vdb")]}
        wrong=deepcopy(before);wrong["tests"][-1]=wrong["tests"][0]
        fail=deepcopy(before);fail["tests"][0]="gap101-illegal-segment-store-old-image-20261006-01/code.vdb"
        for base,new in ((wrong,single),(fail,single),(before,{"tests":["wrong/code.vdb"]})):
            with self.assertRaises(ValueError): a.population(base,new,{})

    def test_wrong_proposed_union(self):
        before=self.baseline();single={"tests":[str(a.collector.RUN/"code.vdb")]}
        union={"tests":before["tests"]+single["tests"]}
        with patch.object(a.bitmap,"combine",return_value=union),self.assertRaises(ValueError):
            a.population(before,single,{"tests":list(reversed(union["tests"]))})

    def test_review_exact_set(self):
        pins={str(a.CANDIDATE/n):"a"*64 for n in a.FILES}
        with patch.object(a,"bound",return_value=json.dumps(pins).encode()):
            self.assertEqual(a.review_pins("unused","external"),pins)
        for bad in ({},dict(pins,**{"foreign":"a"*64}),{k:None for k in pins}):
            with patch.object(a,"bound",return_value=json.dumps(bad).encode()),self.assertRaises(ValueError):
                a.review_pins("unused","external")

    def test_expected_pin_conflict(self):
        with self.assertRaises(ValueError): a.life.merge_pins({"source":"a"*64},{"source":"b"*64})

    def test_locked_collector_bytes(self):
        for path,expected in a.COLLECTOR_PINS.items():
            self.assertEqual(a.life.digest(path),expected)

    def test_rejected_candidate_before_comparisons(self):
        pins={str(a.CANDIDATE/n):"a"*64 for n in a.FILES}
        with patch.object(a,"review_pins",return_value=pins),patch.object(a,"bound",return_value=b'{}'),\
             patch.object(a.bitmap,"collect") as collect:
            with self.assertRaises(KeyError): a.evaluate("unused","external")
            collect.assert_not_called()

    def test_explicit_fail_not_admitted(self):
        pins={str(a.CANDIDATE/n):"a"*64 for n in a.FILES}
        failed=dict(status="GAP102_COLLECTOR_REJECTED_NOT_ADMITTED",baseline_tests=717)
        def content(path,seal):
            return json.dumps(failed if str(path).endswith("status.json") else {}).encode()
        with patch.object(a,"review_pins",return_value=pins),patch.object(a,"bound",side_effect=content),\
             patch.object(a.bitmap,"collect") as collect:
            with self.assertRaises(ValueError): a.evaluate("unused","external")
            collect.assert_not_called()

    def test_no_unsealed_verify(self):
        with patch.object(a,"evaluate") as evaluate,self.assertRaises(ValueError):
            a.main(["--output",str(a.OUT/"gap102-unit-not-created"),"--review-pins",str(a.OUT/"review-unit.json"),
                    "--review-seal","a"*64,"--verify"])
        evaluate.assert_not_called()


if __name__=="__main__": unittest.main()
