import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from lzc_padding_candidates import classify, expected_expression, shape_bindings
from lzc_padding_proof import SOURCE_SHA256


class LzcPaddingCandidatesTest(unittest.TestCase):
    def setUp(self):
        expr = expected_expression(1, 1)
        self.point = dict(module="lzc", metric="cond", scope="dut.i_operand_queue_mfpu_a.lzc",
                          raw_index=0, metric_checksum="3513283519", source_sha256=SOURCE_SHA256,
                          native_id="1", file_id="244",
                          line="93", expression=expr, vector="01", row=1,
                          attributes=dict(optype="13", width="1", exprstr=expr),
                          spec=dict(generate_info="level=1,l=1", lines="93"),
                          truth_table=dict(ncols="2", nrows="3", vecs="000110"))
        self.bitmap = dict(metrics=dict(cond={self.point["scope"]:
                                             dict(width=3, checksum="3513283519", bits="0")}))
        self.bindings = {self.point["scope"]: {0: copy.deepcopy(self.point)}}

    def classify(self, points):
        return classify(points, self.bitmap, self.bindings)

    def test_padding_candidate(self):
        self.assertEqual(self.classify([self.point])["candidate_count"], 1)

    def test_reachable_retained(self):
        point = copy.deepcopy(self.point)
        point.update(vector="10", row=2)
        self.bindings[point["scope"]][0] = copy.deepcopy(point)
        self.assertEqual(self.classify([point])["retained_count"], 1)

    def test_contradictory_hit_rejected(self):
        self.bitmap["metrics"]["cond"][self.point["scope"]]["bits"] = "4"
        with self.assertRaisesRegex(ValueError, "contradicts"):
            self.classify([self.point])

    def test_unbound_source_retained(self):
        self.point["source_sha256"] = "different"
        self.assertEqual(self.classify([self.point])["candidate_count"], 0)

    def test_native_vector_mismatch_rejected(self):
        self.point["row"] = 0
        self.bindings[self.point["scope"]][0]["row"] = 0
        with self.assertRaisesRegex(ValueError, "row/vector"):
            self.classify([self.point])

    def test_duplicate_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.classify([self.point, self.point])

    def test_wrong_native_identity_rejected(self):
        self.point["native_id"] = "99"
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            self.classify([self.point])

    def test_wrong_coordinate_rejected(self):
        self.bindings[self.point["scope"]][1] = copy.deepcopy(self.point)
        self.bindings[self.point["scope"]][1].update(raw_index=1, native_id="2")
        self.point["raw_index"] = 1
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            self.classify([self.point])

    def test_real_xml_binding_and_hash_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "design").mkdir()
            (root / "shape").mkdir()
            design = ET.Element("design")
            for module_id, module_name, instance_id, parent, name in (
                ("1", "top", "10", None, "dut"),
                ("2", "operand_queue", "20", "10", "i_operand_queue_mfpu_a"),
                ("3", "lzc", "30", "20", "lzc"),
            ):
                module = ET.SubElement(design, "srcdef", id=module_id, name=module_name)
                attrs = dict(id=instance_id, name=name)
                if parent is not None:
                    attrs["pid"] = parent
                ET.SubElement(module, "srcinst", **attrs)
            shape = ET.Element("shape")
            definition = ET.SubElement(shape, "conddef", id="3", chksum="3513283519")
            spec = ET.SubElement(definition, "condspec", file="244", lines="93", generate_info="level=1,l=1")
            expression = ET.SubElement(spec, "expr_monitored", condregid="1", optype="13",
                                       width="1", exprstr=expected_expression(1, 1), chksum="123")
            ET.SubElement(expression, "truth_table", ncols="2", nrows="3", vecs="000110")
            paths = {"design/verilog.design.xml": design, "shape/cond.verilog.shape.xml": shape}
            self.bitmap["design"] = {}
            for name, node in paths.items():
                data = ET.tostring(node)
                (root / name).write_bytes(data)
                self.bitmap["design"][name] = hashlib.sha256(data).hexdigest()
            bound = shape_bindings([self.point], self.bitmap, root)
            self.assertEqual(bound[self.point["scope"]][1]["vector"], "01")
            self.assertEqual(bound[self.point["scope"]][1]["native_id"], "1")
            self.assertEqual(bound[self.point["scope"]][1]["attributes"]["chksum"], "123")
            self.bitmap["metrics"]["cond"][self.point["scope"]]["width"] = 4
            with self.assertRaisesRegex(Exception, "width"):
                shape_bindings([self.point], self.bitmap, root)
            (root / "shape/cond.verilog.shape.xml").write_bytes(b"drift")
            with self.assertRaisesRegex(ValueError, "changed"):
                shape_bindings([self.point], self.bitmap, root)


if __name__ == "__main__":
    unittest.main()
