import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import report_population780_plus260 as m


class BatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = (m.OUT / 'current-population780-compact-prepared-agent-20261008-01/combined.el').read_text()
        cls.additions = [((directory / 'second.el').read_text(), count)
                         for name, directory, sha, config_sha, status, count in m.FAMILIES]

    def test_actual_sealed_local_qualifications_and_complete_complements(self):
        reader = m.stable.Reader()
        additions = []
        for family in m.FAMILIES:
            native, count, pins = m.qualification(reader, family)
            self.assertEqual(len(pins) > 90, True)
            additions.append((native, count))
        self.assertEqual(additions, self.additions)
        self.assertEqual(m.stable.semantic_seal(m.stable.semantic(m.union_gate(self.base, additions))),
                         m.UNION_SHA)

    def test_actual_union_adds260_without_changing_other_metrics(self):
        old = m.stable.semantic(self.base)
        new = m.stable.semantic(m.union_gate(self.base, self.additions))
        self.assertEqual(old[0], new[0])
        before, after = m.physical(old), m.physical(new)
        self.assertTrue(all(after[k] & mask == mask for k, mask in before.items()))
        self.assertEqual(sum(bin(v).count('1') for v in after.values()) -
                         sum(bin(v).count('1') for v in before.values()), 260)

    def test_overlap_and_foreign_union_rejected(self):
        for base, additions in [
            (self.base + '\n' + self.additions[0][0], self.additions),
            (self.base, [self.additions[0], self.additions[0]]),
            (self.base, [(self.additions[0][0], 130), self.additions[1]]),
            (self.base, [(self.additions[0][0].replace('[0]', '[1]'), 132), self.additions[1]]),
        ]:
            with self.subTest(additions=additions[0][1]):
                with self.assertRaises(ValueError):
                    m.union_gate(base, additions)

    def test_whole_field_and_missing_direction_rejected_by_local_authority(self):
        name, directory, sha, config_sha, status, count = m.FAMILIES[0]
        blob = (directory / 'second.el').read_text()
        for bad in (blob.replace(' [0] ', ' '), blob.replace('Toggle ', 'Toggle 0to1 ')):
            with self.assertRaises(ValueError):
                m.btb.native_records(bad)

    def test_wrong_receipt_seal_and_status_rejected(self):
        family = list(m.FAMILIES[0])
        family[2] = '0' * 64
        with self.assertRaises(ValueError):
            m.qualification(m.stable.Reader(), family)
        reader = m.stable.Reader()
        original_read = reader.read
        def read(path, sha, parse=False):
            value = original_read(path, sha, parse)
            if path.name == 'capture-result.json':
                value = dict(value, population_application=True)
            return value
        with patch.object(reader, 'read', side_effect=read):
            with self.assertRaises(ValueError):
                m.qualification(reader, m.FAMILIES[0])

    def test_qbs_strict_validator_return_value_not_required(self):
        reader = m.stable.Reader()
        validator = m.qbs.parse_el
        def validate_only(blob, config):
            validator(blob, config)
        with patch.object(m.qbs, 'parse_el', side_effect=validate_only) as parse:
            native, count, pins = m.qualification(reader, m.FAMILIES[1])
        self.assertEqual(parse.call_count, 2)
        self.assertEqual(count, 128)
        self.assertEqual(native, self.additions[1][0])
        config = reader.read(m.FAMILIES[1][1] / 'config.json', m.FAMILIES[1][3], True)
        for bad in (native.replace('0to1', '1to0'), native.replace('[2]', '[3]')):
            with self.assertRaises(ValueError):
                validate_only(bad, config)

    def test_explicit_base_before_any_ancestry_read(self):
        with patch.object(m.prior, 'approved') as old:
            for path, sha in [(m.BASE, '0' * 64), (m.BASE.parent.parent / 'foreign/admission-manifest.json', m.BASE_SHA)]:
                with self.assertRaises(ValueError):
                    m.approved(m.stable.Reader(), path, sha)
            old.assert_not_called()

    def test_prepare_declares_additions_and_keeps_original_lifecycle(self):
        captured = {}
        def construct(code, namespace):
            self.assertIs(code, m.prior.prepare.__code__)
            captured.update(namespace)
            def prepare(out, manifest, seal, unit):
                namespace['life'].save(out / 'config.json', dict(new_exclusions_added=False))
                namespace['life'].save(out / 'prepare-receipt.json', dict(status='old'))
                return manifest, seal, unit
            return prepare
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            with patch.object(m, 'FunctionType', side_effect=construct), patch.object(m.life, 'save') as save:
                self.assertEqual(m.prepare(out, 'ara-test.service'), (m.BASE, m.BASE_SHA, 'ara-test.service'))
                configs = [call.args[1] for call in save.call_args_list]
                self.assertIs(configs[0]['new_exclusions_added'], True)
                self.assertEqual(configs[0]['additional_direction_count'], 260)
                self.assertEqual(configs[1]['status'], 'FORMAL780_PLUS260_PREPARED_NOT_LAUNCHED')
        self.assertIs(captured['approved'], m.approved)
        self.assertIs(captured['dependencies'], m.dependencies)

    def test_private_check_view_only_adapts_legacy_flag(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            config = dict(schema=m.SCHEMA, new_exclusions_added=True, **m.metadata())
            m.life.save(out / 'config.json', config)
            seal = m.life.digest(out / 'config.json')
            captured = {}
            def construct(code, namespace):
                self.assertIs(code, m.prior.check.__code__)
                def check(path, requested):
                    reader = namespace['stable'].Reader()
                    value = reader.read(path / 'config.json', requested, True)
                    captured.update(value)
                    self.assertIs(value['new_exclusions_added'], False)
                    other = path / 'other.json'
                    m.life.save(other, dict(new_exclusions_added=True))
                    self.assertIs(reader.read(other, m.life.digest(other), True)['new_exclusions_added'], True)
                return check
            with patch.object(m, 'FunctionType', side_effect=construct):
                self.assertEqual(m.check(out, seal), config)
            self.assertEqual(m.life.digest(out / 'config.json'), seal)
            self.assertEqual(captured['local_qualifications'], config['local_qualifications'])
            for bad in (dict(config, new_exclusions_added=False), dict(config, additional_direction_count=258)):
                with patch.object(m.stable.Reader, 'read', return_value=bad):
                    with self.assertRaises(ValueError):
                        m.check(out, seal)

    def test_private_verify_and_run_retain_five_stage_implementation(self):
        def construct(code, namespace):
            if code is m.prior.verify.__code__:
                self.assertIs(namespace['check'], m.check)
                self.assertIs(namespace['stable'].el_gate, m.stable.el_gate)
                self.assertIs(namespace['stable'].summaries_gate, m.stable.summaries_gate)
            else:
                self.assertIs(code, m.stable.run.__code__)
                self.assertIs(namespace['check'], m.check)
                self.assertIs(namespace['verify'], m.verify)
                self.assertEqual(namespace['TCL'], m.stable.TCL)
            return lambda *args: args
        with patch.object(m, 'FunctionType', side_effect=construct):
            self.assertEqual(m.verify(Path('/unused'), 'sha'), (Path('/unused'), 'sha'))
            self.assertEqual(m.run(Path('/unused'), 'sha', 'review'), (Path('/unused'), 'sha', 'review'))

    def test_applied_extra_and_reset_exclusions_rejected(self):
        blob = m.union_gate(self.base, self.additions).encode('ascii')
        for stage in ('applied', 'reloaded'):
            m.stable.el_gate(blob, stage, m.UNION_SHA)
            with self.assertRaises(ValueError):
                m.stable.el_gate(self.base.encode('ascii'), stage, m.UNION_SHA)
        for stage in ('raw', 'reset', 'final'):
            m.stable.el_gate(b'', stage, m.UNION_SHA)
            with self.assertRaises(ValueError):
                m.stable.el_gate(blob, stage, m.UNION_SHA)


if __name__ == '__main__':
    unittest.main()
