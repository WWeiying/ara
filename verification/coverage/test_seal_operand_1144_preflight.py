import copy
import gzip
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

import seal_operand_1144_preflight as audit


class OperandPreflightTests(unittest.TestCase):
    def setUp(self):
        self.module = ET.fromstring('<srcdef id="-18" name="operand_queue" chksum="1532764271"/>')
        self.shape = ET.Element("root")
        self.definition = ET.SubElement(self.shape, "branch_def", id="-18", chksum=audit.METRIC)
        spec = ET.SubElement(self.definition, "branch_spec", id="4", chksum="99")
        for i in range(101):
            ET.SubElement(spec, "branch_vector", id=str(i), vector="01")
        self.point = dict(scope="queue", point="Branch 4 (100)", raw_index=0, vector="01",
                          spec_checksum="99", module_checksum=audit.MODULE, metric_checksum=audit.METRIC,
                          decision="ELIGIBLE_STATIC_NOT_APPLIED",
                          proof=[dict(expression_index=1, constant_value=0, demanded_value="1")])

    def test_null_checksum_requires_unique_definition(self):
        self.assertIs(audit.bind_definition(self.module, self.shape, None), self.definition)
        self.shape.append(copy.deepcopy(self.definition))
        with self.assertRaises(ValueError):
            audit.bind_definition(self.module, self.shape, None)

    def test_wrong_checksum_or_genblk_cannot_bind(self):
        with self.assertRaises(ValueError):
            audit.bind_definition(self.module, self.shape, "4188317026")
        self.module.set("id", "-30")
        with self.assertRaises(ValueError):
            audit.bind_definition(self.module, self.shape, None)

    def test_source_identity_and_width_required(self):
        self.module.set("chksum", "1")
        with self.assertRaises(ValueError):
            audit.bind_definition(self.module, self.shape, None)
        self.module.set("chksum", audit.MODULE)
        self.definition.find("branch_spec").remove(self.definition.find("branch_spec/branch_vector"))
        with self.assertRaises(ValueError):
            audit.bind_definition(self.module, self.shape, None)

    def test_coordinate_and_constant_proof(self):
        inv = audit.inventory(self.definition)
        audit.validate_point(self.point, inv)
        for field, value in (("raw_index", 100), ("spec_checksum", "1"), ("vector", "10")):
            bad = dict(self.point, **{field: value})
            with self.assertRaises(ValueError):
                audit.validate_point(bad, inv)
        bad = copy.deepcopy(self.point)
        bad["proof"][0]["expression_index"] = 0
        with self.assertRaises(ValueError):
            audit.validate_point(bad, inv)

    def test_raw_null_metadata_and_gzip(self):
        raw = ('<root><instance_data name="queue" value="%s"/></root>' % ("0"*101)).encode()
        self.assertEqual(audit.raw_scopes(gzip.compress(raw), {"queue"}), {"queue": 0})

    def test_raw_missing_duplicate_bad_width_checksum_reject(self):
        node = '<instance_data name="queue" value="%s"/>' % ("0"*101)
        bad_rows = ["", node+node, node.replace("0"*101, "0"*100),
                    node.replace("/>", ' chksum="2"/>'), node.replace("0"*101, "X"*101)]
        for rows in bad_rows:
            with self.assertRaises(ValueError):
                audit.raw_scopes(("<root>"+rows+"</root>").encode(), {"queue"})

    def test_contradictory_hit_reject(self):
        audit.check_zero([self.point], {"queue": 0})
        with self.assertRaises(ValueError):
            audit.check_zero([self.point], {"queue": 1 << 100})

    def test_changed_or_conflicting_pin_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(b"old")
            pins = {}
            audit.read_bound(path, pins)
            expected = pins[str(path)]
            path.write_bytes(b"new")
            with self.assertRaises(ValueError):
                audit.read_bound(path, {}, expected)
            with self.assertRaises(ValueError):
                audit.read_bound(path, pins)

    def test_capture_membership_is_exact_and_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                audit.tree_members(root)
            (root / "data").write_bytes(b"x")
            self.assertEqual(audit.tree_members(root), ["data"])
            (root / "alias").symlink_to(root / "data")
            with self.assertRaises(ValueError):
                audit.tree_members(root)


if __name__ == "__main__":
    unittest.main()
