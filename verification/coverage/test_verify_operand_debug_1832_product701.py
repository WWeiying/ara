import copy
import unittest

import verify_operand_debug_1832_product701 as v


class ProductContractTests(unittest.TestCase):
    def setUp(self):
        self.actual = {"ara_tb": dict(Name="ara_tb", Depth="0", Branch="81.92%")}
        self.actual.update({"ara_tb.n%d" % i: dict(Name="n%d" % i, Depth="1", Branch="NA") for i in range(2987)})
        self.reference = copy.deepcopy(self.actual)
        self.reference[v.ROOT] = dict(Name=v.ROOT, Depth="0", Branch="4.66%")
        self.source = dict(module=v.ROOT, definition_checksum="2787408814", file_id="152",
                           source_path=str(v.SOURCE), resolved_path=str(v.SOURCE), definition_lines=["42", "331"])
        self.definition = dict(id="-203", name=v.ROOT, type="module", chksum="2787408814")
        self.instances = [dict(id="-2758", name=v.ROOT, pid="-1")]

    def test_exact_single_vendor_absence(self):
        v.compare_product(self.actual, self.reference)
        v.validate_owner(self.source, self.definition, self.instances, ["ara_tb", v.ROOT])

    def test_product_omission_rejected(self):
        del self.actual["ara_tb.n0"]
        with self.assertRaises(ValueError):
            v.compare_product(self.actual, self.reference)

    def test_other_root_absence_rejected(self):
        self.reference["another_vendor"] = dict(Name="another_vendor", Depth="0", Branch="NA")
        with self.assertRaises(ValueError):
            v.compare_product(self.actual, self.reference)

    def test_extra_row_rejected(self):
        self.actual["ara_tb.extra"] = dict(Name="extra", Depth="1", Branch="NA")
        with self.assertRaises(ValueError):
            v.compare_product(self.actual, self.reference)

    def test_vendor_descendant_cannot_be_dropped_or_retained(self):
        self.reference[v.ROOT + ".child"] = dict(Name="child", Depth="1", Branch="NA")
        with self.assertRaises(ValueError):
            v.compare_product(self.actual, self.reference)
        self.actual[v.ROOT + ".child"] = self.reference[v.ROOT + ".child"]
        with self.assertRaises(ValueError):
            v.compare_product(self.actual, self.reference)

    def test_name_depth_metrics_strict(self):
        for field, value in (("Name", "changed"), ("Depth", "2"), ("Branch", "0.00%")):
            changed = copy.deepcopy(self.actual)
            changed["ara_tb.n0"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                v.compare_product(changed, self.reference)

    def test_vendor_row_must_be_exact_root(self):
        self.reference[v.ROOT]["Depth"] = "1"
        with self.assertRaises(ValueError):
            v.compare_product(self.actual, self.reference)

    def test_source_module_and_top_instance_strict(self):
        for field in self.source:
            source = copy.deepcopy(self.source)
            source[field] = "wrong"
            with self.subTest(field=field), self.assertRaises(ValueError):
                v.validate_owner(source, self.definition, self.instances, ["ara_tb", v.ROOT])
        definition = dict(self.definition, chksum="0")
        with self.assertRaises(ValueError):
            v.validate_owner(self.source, definition, self.instances, ["ara_tb", v.ROOT])
        with self.assertRaises(ValueError):
            v.validate_owner(self.source, self.definition, [dict(self.instances[0], pid="-99")], ["ara_tb", v.ROOT])

    def test_compiled_subtree_rejected(self):
        with self.assertRaises(ValueError):
            v.validate_owner(self.source, self.definition, self.instances, ["ara_tb", v.ROOT, v.ROOT + ".child"])


if __name__ == "__main__":
    unittest.main()
