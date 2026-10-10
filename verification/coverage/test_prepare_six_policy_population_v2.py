from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

import prepare_six_policy_population_v2 as subject


class ToolLinkTests(unittest.TestCase):
    def test_real_cc_exact_bytes_and_target(self):
        result = subject.tool_link_identity(subject.CC)
        self.assertEqual(result, dict(link_target='gcc', resolved='/usr/bin/gcc', sha256=subject.CC_SHA))

    def test_cc_expected_hash_mandatory(self):
        context = subject.Context(subject.frozen.OUT / 'fixture', '0' * 64, 723)
        for expected in (None, '0' * 64):
            with self.assertRaisesRegex(ValueError, 'exact sealed'):
                context.pin({}, subject.CC, expected)
        pins = {}
        context.pin(pins, subject.CC, subject.CC_SHA)
        self.assertEqual(pins[subject.CC], pins['/usr/bin/gcc'])

    def test_link_target_and_resolved_hash_drift_rejected(self):
        with patch.object(Path, 'readlink', return_value=Path('/usr/bin/gcc')):
            with self.assertRaisesRegex(ValueError, 'Exact cc'):
                subject.tool_link_identity(subject.CC)
        with patch.object(subject.frozen, 'sha', return_value='0' * 64):
            with self.assertRaisesRegex(ValueError, 'bytes differ'):
                subject.tool_link_identity(subject.CC)

    def test_unknown_alias_rejected_and_frozen_namespace_unchanged(self):
        original = dict(subject.frozen.INHERITED_TOOL_LINKS)
        with self.assertRaises(ValueError):
            subject.tool_link_identity('/usr/bin/c++')
        context = subject.Context(subject.frozen.OUT / 'fixture', '0' * 64, 723)
        self.assertEqual(set(context.namespace()['INHERITED_TOOL_LINKS']) - set(original), {subject.CC})
        self.assertEqual(subject.frozen.INHERITED_TOOL_LINKS, original)

    def test_cc_pin_conflict_rejected(self):
        context = subject.Context(subject.frozen.OUT / 'fixture', '0' * 64, 723)
        with self.assertRaisesRegex(ValueError, 'pin conflict'):
            context.pin({subject.CC: '0' * 64}, subject.CC, subject.CC_SHA)

    def test_missing_or_wrong_cc_in_sealed_ledger_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            context = subject.Context(subject.frozen.OUT / 'fixture', '0' * 64, 723)
            context.admission = Path(directory)
            ledger = context.admission / 'evidence-pins.json'
            for entry in ({}, {subject.CC: '0' * 64}):
                ledger.write_text(json.dumps(entry))
                manifest = {'output_pins': {str(ledger): subject.frozen.sha(ledger)}}
                with patch.object(subject.prior.Context, 'source_binding', return_value={}), \
                     patch.object(subject.frozen, 'load_sealed', return_value=manifest):
                    with self.assertRaisesRegex(ValueError, 'formal admission ledger'):
                        context.source_binding({})


if __name__ == '__main__':
    unittest.main()
