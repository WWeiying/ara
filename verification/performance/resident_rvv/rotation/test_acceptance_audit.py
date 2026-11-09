import csv
from pathlib import Path
import tempfile
import unittest
import acceptance_audit as audit


class SchemaTests(unittest.TestCase):
    def check_header(self, fields):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "vector.csv"
            with path.open("w", newline="") as stream:
                csv.writer(stream).writerow(fields)
            return audit.strict_header(path)

    def test_exact_schema(self):
        self.assertEqual(self.check_header(audit.FIELDS), audit.FIELDS)

    def test_duplicate_instruction_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.check_header(audit.FIELDS + ["insn"])

    def test_missing_configuration_rejected(self):
        with self.assertRaisesRegex(ValueError, "schema"):
            self.check_header(audit.FIELDS[:-1])


if __name__ == "__main__":
    unittest.main()
