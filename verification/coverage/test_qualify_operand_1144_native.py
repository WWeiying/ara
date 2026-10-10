import copy
import json
from pathlib import Path
import unittest

import qualify_operand_1144_native as qualification


class QualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pins = {}
        p = qualification.preflight
        cls.review = qualification.module(p.REVIEW / "review.py", pins, "unit_operand_review")
        cls.point = json.loads((p.REVIEW / "accepted-coordinates.json").read_text())["points"][0]
        legacy = qualification.module(p.HERE / "reviewed_20261004/audit_readonly.py", pins, "unit_operand_design")
        design = legacy.Design(p.BUILD / "sim/simv.vdb")
        cls.definition = design.definition(cls.point["scope"], "branch")
        cls.text = (p.ROOT / "hardware/src/lane/operand_queue.sv").read_text()
        cls.parameters, _ = cls.review.queue_parameters(
            (p.ROOT / "hardware/src/lane/operand_queues_stage.sv").read_text(), cls.text,
            (p.ROOT / "hardware/include/ara_pkg.sv").read_text())

    def test_reconstruct_real_source_proof(self):
        result = qualification.prove_point(self.point, self.definition, self.parameters, self.text, self.review)
        self.assertEqual(result["proof"], self.point["proof"])

    def test_enabled_guard_cannot_use_old_false_proof(self):
        point, parameters = copy.deepcopy(self.point), copy.deepcopy(self.parameters)
        queue = point["scope"].rsplit("i_operand_queue_", 1)[1]
        parameters[queue]["FPUSupport"] = 63
        point["parameters"] = parameters[queue]
        with self.assertRaises(ValueError):
            qualification.prove_point(point, self.definition, parameters, self.text, self.review)

    def test_wrong_guard_span_or_index_reject(self):
        for field, value in (("source_guard", {"start": [1, 1], "end": [1, 1], "text": "wrong"}),
                             ("expression_index", 0)):
            point = copy.deepcopy(self.point)
            point["proof"][0][field] = value
            with self.assertRaises(ValueError):
                qualification.prove_point(point, self.definition, self.parameters, self.text, self.review)

    def test_native_header_expression_and_population_binding(self):
        proven = qualification.prove_point(self.point, self.definition, self.parameters, self.text, self.review)
        key = proven["scope"], proven["point"]
        row = dict(checksum=proven["checksum"], nativepointchecksum=proven["spec_checksum"], expression=proven["expression"])
        self.assertEqual(len(qualification.native_binding({key: row}, [proven])), 1)
        for field, value in (("checksum", ["1", "2"]), ("nativepointchecksum", "1"), ("expression", "wrong")):
            with self.assertRaises(ValueError):
                qualification.native_binding({key: dict(row, **{field: value})}, [proven])
        with self.assertRaises(ValueError):
            qualification.native_binding({}, [proven])


if __name__ == "__main__":
    unittest.main()
