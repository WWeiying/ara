import unittest

from repair_oob_random_cases import repair


def block(index="v17", scalar="t0", ordinal=0):
    return f"""# ARA_DSA_DEFINED_SCALAR_SOURCE_{ordinal:03d}
addi x13, x13, -16
sd x5, 0(x13)
csrr x5, vstart
sd x5, 8(x13)
csrw vstart, zero
la x5, __ara_defined_scalar_source
vl1re8.v {index}, (x5)
ld x5, 8(x13)
csrw vstart, x5
ld x5, 0(x13)
addi x13, x13, 16
vmv.x.s {scalar}, {index}
vslide1down.vx {index}, {index}, {scalar}
"""


def source():
    result = "main: vsetvli t0, zero, e16, mf4, tu, mu #start riscv_vector_load_store_instr_stream_2\n"
    result += "".join(f"li t0, {i * 2}\nvslide1down.vx v17, v17, t0\n" for i in range(10))
    result += "".join(block(ordinal=i) for i in range(6))
    result += """li t0, 0xa
vsetvli sp, t0, e16, mf4, tu, mu
la s5, region_0+2876
li s2, 0x0
csrrw s2, vstart, s2
vluxseg4ei16.v v12, (s5), v17
"""
    result += block("v7", "a1", 6)  # Not part of any index initializer.
    result += "load_fault_handler:\nmret\nregion_0:\n"
    result += ".word " + ", ".join(["0"] * 1024) + "\n__ara_region_0_end:\n"
    return result


class RepairTests(unittest.TestCase):
    def test_only_instrumentation_is_removed(self):
        original = source()
        derived, reports = repair(original)
        expected = original
        for i in range(6):
            expected = expected.replace(block(ordinal=i).split("vmv.x.s")[0], "", 1)
        self.assertEqual(derived, expected)
        self.assertIn(block("v7", "a1", 6), derived)
        self.assertEqual(reports[0]["offsets"], list(range(0, 20, 2)))
        self.assertEqual(reports[0]["max_access_end_exclusive"], 2902)
        self.assertEqual(len(reports[0]["removed_blocks"]), 6)

    def test_rotation_proof_for_arbitrary_initial_state(self):
        # The first K final elements depend only on K inserted literals, not on
        # any initial values read/rotated into the unused suffix.
        for n, k in ((32, 24), (16, 10), (16, 15)):
            for initial in (list(range(n)), [-1] * n, [0xDEADBEEF] * n):
                elements = initial[:]
                offsets = list(range(0, 2 * k, 2))
                for offset in offsets:
                    elements = elements[1:] + [offset]
                for _ in range(n - k):
                    elements = elements[1:] + elements[:1]
                self.assertEqual(elements[:k], offsets)

    def test_segment_footprint_not_just_last_element(self):
        with self.assertRaisesRegex(ValueError, "segment footprint"):
            repair(source().replace("region_0+2876", "region_0+4072"))

    def test_bad_offset_alignment(self):
        with self.assertRaisesRegex(ValueError, "unaligned"):
            repair(source().replace("li t0, 18\n", "li t0, 19\n"))

    def test_missing_rotation(self):
        with self.assertRaisesRegex(ValueError, "exactly VLMAX"):
            repair(source().replace(block(ordinal=5), ""))

    def test_changed_instrumentation(self):
        with self.assertRaisesRegex(ValueError, "instrumentation changed"):
            repair(source().replace("vl1re8.v v17, (x5)", "vl1re8.v v18, (x5)", 1))

    def test_vl_mismatch(self):
        with self.assertRaisesRegex(ValueError, "final VL"):
            repair(source().replace("li t0, 0xa", "li t0, 0xb"))

    def test_emul_mismatch(self):
        with self.assertRaisesRegex(ValueError, "EMUL mismatch"):
            repair(source().replace("vsetvli sp, t0, e16, mf4", "vsetvli sp, t0, e32, mf4"))

    def test_clobbers_branches_and_unreviewed_ops_rejected(self):
        for op in ("vsub.vx v17, v1, a1", "li s5, 1", "li x21, 1", "j skip",
                   "vmv2r.v v16, v20", "csrrw t1, vtype, t0", "skip: nop"):
            with self.subTest(op=op), self.assertRaises(ValueError):
                repair(source().replace("li s2, 0x0", op + "\nli s2, 0x0"))

    def test_unknown_region_data_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported region"):
            repair(source().replace("region_0:\n", "region_0:\n.incbin \"unknown\"\n"))

    def test_non_indexed_scalar_source_cannot_be_repaired(self):
        with self.assertRaisesRegex(ValueError, "no proven"):
            repair(block())


if __name__ == "__main__":
    unittest.main()
