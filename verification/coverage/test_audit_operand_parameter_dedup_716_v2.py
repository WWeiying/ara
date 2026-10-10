import unittest
import audit_operand_parameter_dedup_716_v2 as m


class ParameterDedupTests(unittest.TestCase):
    def test_compiled_merged_variants(self):
        block = ",".join(k + "=0" for k in m.PARAMS) + ","
        self.assertEqual(m.parameters(" + ".join([block] * 3)), dict.fromkeys(m.PARAMS, 0))

    def test_one_nonzero_variant_rejected(self):
        block = ",".join(k + "=0" for k in m.PARAMS) + ","
        with self.assertRaisesRegex(ValueError, "variants zero"):
            m.parameters(" + ".join([block, block, block.replace("SupportIntExt2=0", "SupportIntExt2=1")]))

    def test_guard_true_vs_conv_entry(self):
        point = dict(native_vector=dict(vector="011"), expressions=[
            dict(exprstr="cmd.conv", index="1", id="336"),
            dict(exprstr="SupportIntExt2", index="2", id="339")])
        self.assertEqual(len(m.guards(point)), 1)
        point["native_vector"]["vector"] = "101"
        self.assertEqual(m.guards(point), [])

    def test_out_of_range_guard_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside vector"):
            m.guards(dict(native_vector=dict(vector="01"), expressions=[
                dict(exprstr="SupportReduct", index="4", id="396")]))


if __name__ == "__main__":
    unittest.main()
