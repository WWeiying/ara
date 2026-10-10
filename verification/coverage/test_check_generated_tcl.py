import json
from pathlib import Path
import tempfile
import unittest
import check_generated_tcl as gate


class GeneratedTclTests(unittest.TestCase):
    def check(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'selection.tcl'
            path.write_text(text)
            before = path.read_bytes()
            result = gate.check(path)
            self.assertEqual(path.read_bytes(), before)
            return result

    def test_plain_text_not_executed_or_qualified(self):
        result = self.check('set value {hello}\nerror {must not execute}\n')
        self.assertFalse(result['executed'])
        self.assertFalse(result['native_qualified'])

    def test_json_serialization_rejected(self):
        with self.assertRaisesRegex(ValueError, 'JSON string'):
            self.check(json.dumps('set value {hello}\n'))

    def test_incomplete_or_invalid_payload_rejected(self):
        for text in ('set value {hello', '', 'set a 1\x00'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.check(text)

    def test_literal_escaped_newline_in_real_script_allowed(self):
        self.assertFalse(self.check('set value "first\\nsecond"\n')['executed'])


if __name__ == '__main__':
    unittest.main()
