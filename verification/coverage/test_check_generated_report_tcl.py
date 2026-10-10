import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import check_generated_report_tcl as tool


class GeneratedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'selection.tcl'

    def check(self, text, names=('fma_helper',)):
        self.path.write_text(text)
        return tool.evaluate(self.path, {str(self.path): hashlib.sha256(self.path.read_bytes()).hexdigest()}, names)

    def test_actual_text_and_literal_arguments(self):
        self.check('set fma_helper {a path [not-command] ; literal}\nset x {}\nlappend x {logic [0:1][63:0]mant}\n')

    def test_json_writer_failure(self):
        with self.assertRaisesRegex(ValueError, 'JSON-serialized'):
            self.check(json.dumps('set fma_helper {tool}\n'))

    def test_literal_backslash_newline_is_not_two_commands(self):
        with self.assertRaises(ValueError):
            self.check(r'set fma_helper {}\nset x {}\n')

    def test_local_not_global_and_unsealed_source_rejected(self):
        for text in ('proc setup {} {set fma_helper local}\nsetup\n', 'source {/not/approved.tcl}\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.check(text)

    def test_syntax_and_side_effect_rejected(self):
        for text in ('set fma_helper {unterminated', 'exec echo unsafe\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.check(text)

    def test_real_sealed745_selection(self):
        root = Path(__file__).resolve().parents[1] / 'out/qualified-native-combo-diagnostic-full745-agent-20261007-01'
        config = json.loads((root / 'config.json').read_bytes())
        path = root / 'selection.tcl'
        tool.evaluate(path, {str(path): config['pins'][str(path)]},
                      ('fx_groups', 'report745_roots', 'diagnostic_instances'))


if __name__ == '__main__':
    unittest.main()
