from pathlib import Path
import unittest

import c910_srt_datapath_native_v4 as v4


class NativeNetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = v4.base.life.OUT / 'c910-srt-native1264-load-agent-20261007-03'
        cls.config = v4.base.json.loads((cls.out / 'config.json').read_bytes())
        cls.actual = (cls.out / 'first.el').read_text()
        cls.candidate = (cls.out / 'candidate.el').read_text()

    def test_actual1264_export_exact_matches_candidate(self):
        records = v4.parse_el(self.actual, self.config)
        self.assertEqual(len(records), 1264)
        self.assertEqual(records, v4.parse_el(self.candidate, self.config))
        self.assertEqual(self.actual.count('"net '), 151 * 8)
        self.assertEqual(self.actual.count('"reg '), 7 * 8)

    def test_predecessor_reproduces_actual_net_rejection(self):
        with self.assertRaisesRegex(ValueError, 'Unknown exclusion syntax'):
            v4.original_parse(self.actual, self.config)

    def test_net_cannot_retype_reg(self):
        with self.assertRaises(ValueError):
            v4.parse_el(self.actual.replace('"reg cur_rem', '"net cur_rem'), self.config)

    def test_net_bounds_signature_scope_checksum_exact(self):
        for text in (self.actual.replace('net srt_remainder_nxt[60:0]',
                                        'net srt_remainder_nxt[59:0]'),
                     self.actual.replace('net srt_remainder_nxt[60:0]',
                                         'net cur_rem[60:0]'),
                     self.actual.replace('3969040510', '0'),
                     self.actual.replace('.gen_lanes[0].', '.gen_lanes[4].')):
            with self.assertRaises(ValueError):
                v4.parse_el(text, self.config)

    def test_unknown_protected_duplicate_or_missing_rejected(self):
        lines = self.actual.splitlines()
        for text in (self.actual + '\nToggle bound_sel "net bound_sel[6:0]"\n',
                     self.actual + '\n' + lines[-1],
                     '\n'.join(lines[:-1]), self.actual.replace('"net ', '"unknown ')):
            with self.assertRaises(ValueError):
                v4.parse_el(text, self.config)

    def test_frozen_dependencies_and_lifecycle_unchanged(self):
        v4.base.life.check(v4.PINS)
        text = v4.base.TCL.read_text()
        self.assertIn('c910_srt_datapath_native_v3.tcl', text)
        self.assertEqual(v4.base.TEST, Path(__file__).resolve())


if __name__ == '__main__':
    unittest.main()
