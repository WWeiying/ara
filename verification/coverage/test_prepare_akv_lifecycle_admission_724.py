import json
import unittest

import prepare_akv_lifecycle_admission_724 as helper


class GateTests(unittest.TestCase):
    def evidence(self):
        path=helper.life.OUT/"akv-lifecycle-strict-candidate-723-20261006-02"
        return tuple(json.loads((path/name).read_text()) for name in
                     ("status.json","target-reconciliation723.json","gained-compiled-points.json"))

    def test_actual_compiled_positive_candidate(self):helper.admission_gate(*self.evidence())

    def test_zero_gain(self):
        state,targets,points=self.evidence();state["raw_delta"]={m:0 for m in state["raw_delta"]}
        with self.assertRaises(ValueError):helper.admission_gate(state,targets,points)

    def test_wrong_baseline(self):
        state,targets,points=self.evidence();state["baseline_tests"]=722
        with self.assertRaises(ValueError):helper.admission_gate(state,targets,points)

    def test_unqualified_scalar(self):
        state,targets,points=self.evidence();state["full_scalar_independent_qualified"]=False
        with self.assertRaises(ValueError):helper.admission_gate(state,targets,points)

    def test_false_Spike_relabel(self):
        state,targets,points=self.evidence();state["native_Spike_comparison"]=True
        with self.assertRaises(ValueError):helper.admission_gate(state,targets,points)

    def test_wrong_qualification_seal(self):
        state,targets,points=self.evidence();state["qualification_seal"]="0"*64
        with self.assertRaises(ValueError):helper.admission_gate(state,targets,points)

    def test_missing_target(self):
        state,targets,points=self.evidence()
        with self.assertRaises(ValueError):helper.admission_gate(state,targets[:-1],points)

    def test_previous_target_hit(self):
        state,targets,points=self.evidence();targets[0]["baseline723_hit"]=True
        with self.assertRaises(ValueError):helper.admission_gate(state,targets,points)

    def test_boolean_delta(self):
        state,targets,points=self.evidence();state["raw_delta"]["cond"]=True
        with self.assertRaises(ValueError):helper.admission_gate(state,targets,points)

    def test_missing_gained_point(self):
        state,targets,points=self.evidence()
        with self.assertRaises(ValueError):helper.admission_gate(state,targets,points[:-1])

    def test_duplicate_gained_point(self):
        state,targets,points=self.evidence()
        metric=points[0]["metric"];i=next(i for i,r in enumerate(points[1:],1) if r["metric"] == metric)
        points[i]=points[0]
        with self.assertRaises(ValueError):helper.admission_gate(state,targets,points)

    def test_no_implicit_parent_authorization(self):
        with self.assertRaises(ValueError):helper.admit(None,None,None,None)


if __name__ == "__main__":unittest.main()
