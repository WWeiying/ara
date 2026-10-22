import copy
import unittest

from lzc_native_records import bind_records, parse_records

TEXT = '''CHECKSUM: "3250293308 3513283519"
INSTANCE: dut.lzc
ANNOTATION: "exact padding vector"
Condition 7 "2805863172" "(left | right) 1 -1" (2 "01")
'''


class NativeRecordsTest(unittest.TestCase):
    def setUp(self):
        self.candidate = dict(module_checksum="3250293308",
            point=dict(scope="dut.lzc", expression="(left | right)", vector="01",
                       metric_checksum="3513283519", native_id="7",
                       attributes=dict(chksum="2805863172", width="1")),
            structural_proof=dict(unreachable_child_vectors=["01", "11"]))

    def test_precise_record_binds(self):
        bind_records(parse_records(TEXT), [self.candidate])

    def test_empty_file_is_empty(self):
        self.assertEqual(parse_records(""), [])

    def test_whole_condition_or_instance_rejected(self):
        for text in (TEXT.rsplit(" (2", 1)[0] + "\n", 'CHECKSUM: "1 2"\nINSTANCE: dut.lzc\n'):
            with self.assertRaises(ValueError):
                parse_records(text)

    def test_duplicate_vector_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_records(TEXT + TEXT)

    def test_wrong_signature_or_extra_vector_rejected(self):
        records = parse_records(TEXT)
        for field in ("module_checksum", "metric_checksum", "native_id", "point_checksum", "width", "bit", "vector"):
            changed = copy.deepcopy(records)
            changed[0][field] = "wrong"
            with self.assertRaises(ValueError):
                bind_records(changed, [self.candidate])


if __name__ == "__main__":
    unittest.main()
