"""Focused exact718-prefix and fresh-delta admission rejection fixtures."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import admit_gap102b_offline as m


def fixtures():
    scope = "ara_tb.dut.i_ara_soc.i_system"
    before = dict(design={"shape":"a"},tests=["old%d"%i for i in range(718)],input_hashes={},
        metrics={k:{scope:dict(width=2,checksum="1",bits="0x0")}
                 for k in ("line","cond","branch","fsm")})
    single = deepcopy(before); single["tests"] = [str(m.c.RUN/"code.vdb")]
    for metric in ("line","branch"):
        single["metrics"][metric][scope]["bits"] = "0x1"
    return before,single


class AdmissionTests(unittest.TestCase):
    def test_exact_population(self):
        before,single = fixtures(); union,delta = m.population(before,single)
        self.assertEqual(union["tests"],before["tests"]+single["tests"])
        self.assertEqual(len(union["tests"]),719)
        self.assertEqual(delta["metrics"],dict(line=1,cond=0,branch=1,fsm=0))

    def test_recomputes_718_delta_not_717(self):
        before,single = fixtures()
        next(iter(before["metrics"]["line"].values()))["bits"] = "0x1"
        _,delta = m.population(before,single)
        self.assertEqual(delta["metrics"],dict(line=0,cond=0,branch=1,fsm=0))

    def test_no_new_gain_rejected(self):
        before,single = fixtures(); before["metrics"] = deepcopy(single["metrics"])
        with self.assertRaisesRegex(ValueError,"fresh718"): m.population(before,single)

    def test_duplicate_rejected(self):
        before,single = fixtures(); before["tests"][0] = single["tests"][0]
        with self.assertRaisesRegex(ValueError,"Duplicate"): m.population(before,single)

    def test_wrong_baseline_count_rejected(self):
        before,single = fixtures(); before["tests"].pop()
        with self.assertRaisesRegex(ValueError,"exact718"): m.population(before,single)

    def test_failures_excluded(self):
        before,single = fixtures()
        before["tests"][0] = "/tmp/gap101-illegal-segment-store-old-image-20261006-01/code.vdb"
        with self.assertRaisesRegex(ValueError,"FAIL mixed"): m.population(before,single)

    def test_shape_drift_rejected(self):
        before,single = fixtures()
        next(iter(single["metrics"]["branch"].values()))["checksum"] = "2"
        with self.assertRaisesRegex(ValueError,"shape"): m.population(before,single)

    def baseline(self):
        manifest = dict(schema="OPIVX_VSBC_HISTORICAL718_ADMISSION_V1",output=str(m.BASE),
                        baseline=str(m.c.BASE))
        state = dict(status="PASS_RAW_UNION_HISTORICAL_ONLY",baseline=717,aggregate_passed=718,new_passed=1)
        historical = dict(tests=["old%d"%i for i in range(717)])
        before = dict(tests=historical["tests"]+[str(m.OUT/"opivx-vsbc-vd0-old-image-717-20261006-01/code.vdb")])
        return manifest,state,before,historical

    def test_exact_vsbc_baseline(self): m.baseline_contract(*self.baseline())

    def test_717_reorder_rejected(self):
        manifest,state,before,historical = self.baseline()
        before["tests"][0],before["tests"][1] = before["tests"][1],before["tests"][0]
        with self.assertRaisesRegex(ValueError,"prefix"): m.baseline_contract(manifest,state,before,historical)

    def test_other_718_not_substituted(self):
        for section,key,value in ((0,"schema","GAP102_HISTORICAL718_ADMISSION_V1"),
                (1,"aggregate_passed",717),(2,"tests",["other"]*718)):
            objects = list(self.baseline()); objects[section][key] = value
            with self.assertRaises(ValueError): m.baseline_contract(*objects)

    def test_pin_conflict_not_overwritten(self):
        with self.assertRaisesRegex(ValueError,"Conflicting"):
            m.life.merge_pins({"/tmp/source":"a"*64},{"/tmp/source":"b"*64})

    def test_bound_mutation_and_alias_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve()/"evidence.json"
            path.write_text(json.dumps({"value":1})); digest = m.life.digest(path)
            m.bound(path,digest)
            alias = path.with_name("alias.json"); alias.symlink_to(path)
            with self.assertRaisesRegex(ValueError,"Aliased"): m.bound(alias,digest)
            path.write_text(json.dumps({"value":2}))
            with self.assertRaisesRegex(ValueError,"hash differs"): m.bound(path,digest)


if __name__ == "__main__": unittest.main()
