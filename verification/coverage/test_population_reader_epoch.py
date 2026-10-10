"""Unwired reader-interface tests; small fixtures only, no EDA or sealed writes."""
import copy
import hashlib
from pathlib import Path
import tempfile
from types import MappingProxyType
import unittest
from unittest.mock import patch

from population_reader_epoch import ConfigView, PopulationReaderEpoch
from verification_epoch import AliasBinding, EpochError


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.config = self.root / 'config.json'
        self.config.write_bytes(b'{"schema":"sample","groups":{"x":[1,true]},"pins":{}}')
        self.tool = self.root / 'tool'
        self.tool.write_bytes(b'large-streamed-tool')
        self.link = self.root / 'alias'
        self.link.symlink_to('tool')
        self.pins = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in (self.config, self.tool, self.link)}
        self.aliases = {str(self.link): AliasBinding('tool', str(self.tool), self.pins[str(self.tool)])}

    def reader(self, **kwargs):
        return PopulationReaderEpoch(self.pins, self.aliases, json_paths=[str(self.config)], **kwargs)

    def test_context_reader_and_validator_share_one_config(self):
        reader = self.reader()
        seen = []

        def validate(config, output, context):
            self.assertEqual(output, self.root)
            self.assertIs(context, reader)
            self.assertIs(config, context.load_sealed(self.config, self.pins[str(self.config)]))
            context.check_pins(self.pins)
            seen.append(config)

        context, first = reader.read_config(self.root, self.pins[str(self.config)], validate)
        _, second = context.read_config(self.root, self.pins[str(self.config)], validate)
        self.assertIs(first, second)
        self.assertEqual(dict(reader.finish()), dict(reads=2, hashes=2,
            hashed_bytes=self.config.stat().st_size + self.tool.stat().st_size,
            parses=1, json_input_bytes=self.config.stat().st_size,
            retained_raw_bytes=0, verified_paths=3))

    def test_stream_only_no_whole_file_read(self):
        reader = self.reader()
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Whole-file reread')):
            reader.check_pins(self.pins)
            reader.load_sealed(self.config, self.pins[str(self.config)])
        reader.finish()

    def test_immutable_fields_and_shallow_facade(self):
        reader = self.reader()
        config = reader.load_sealed(self.config, self.pins[str(self.config)])
        view = ConfigView(config, {'schema': 'legacy-facade'})
        self.assertIs(view['groups'], config['groups'])
        self.assertIs(copy.deepcopy(view), view)
        self.assertEqual(view['schema'], 'legacy-facade')
        self.assertEqual(config['schema'], 'sample')
        self.assertNotEqual(view, ConfigView(config, {'schema': 'different'}))
        with self.assertRaises(TypeError):
            config['groups']['x'][0] = 99
        with self.assertRaises(EpochError):
            ConfigView(config, {'groups': {}})
        with self.assertRaises(EpochError):
            ConfigView(config, {'groups': MappingProxyType({'x': []})})
        with self.assertRaises(AttributeError):
            view._config = MappingProxyType({})

    def test_exact_seal_conflict_after_capture(self):
        reader = self.reader()
        reader.load_sealed(self.config, self.pins[str(self.config)])
        with self.assertRaises(EpochError):
            reader.load_sealed(self.config, '0' * 64)
        with self.assertRaises(EpochError):
            reader.finish()

    def test_wrong_captured_content_rejected(self):
        self.tool.write_bytes(b'changed')
        with self.assertRaises(EpochError):
            self.reader().sha(self.tool)

    def test_alias_all_paths_required_not_just_endpoint(self):
        reader = self.reader()
        reader.sha(self.tool)
        reader.load_sealed(self.config, self.pins[str(self.config)])
        with self.assertRaises(EpochError):
            reader.finish()

    def test_conflicting_alias_authority_rejected(self):
        self.pins[str(self.link)] = '0' * 64
        with self.assertRaises(EpochError):
            self.reader()

    def test_alias_retargeted_rejected(self):
        reader = self.reader()
        reader.sha(self.link)
        self.link.unlink()
        self.link.symlink_to('./tool')
        with self.assertRaises(EpochError):
            reader.sha(self.link)

    def test_destination_pin_conflict_rejected(self):
        with self.assertRaises(EpochError):
            self.reader().pin({str(self.tool): '0' * 64}, self.tool)

    def test_missing_and_extra_inventory_rejected(self):
        for pins in ({str(self.tool): self.pins[str(self.tool)]},
                     dict(self.pins, unknown='0' * 64)):
            with self.subTest(pins=pins), self.assertRaises(EpochError):
                self.reader().check_pins(pins)

    def test_undeclared_json_cannot_promote_hash_capture(self):
        reader = PopulationReaderEpoch(self.pins, self.aliases)
        reader.sha(self.config)
        with self.assertRaises(EpochError):
            reader.load_sealed(self.config, self.pins[str(self.config)])

    def test_per_file_and_total_json_budget(self):
        for kwargs in ({'max_json_bytes': 1}, {'max_total_json_bytes': 1},
                       {'max_json_bytes': True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(EpochError):
                self.reader(**kwargs).load_sealed(self.config, self.pins[str(self.config)])

    def test_bad_json_and_nonfinite_rejected(self):
        for data in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e999}', b'{'):
            self.config.write_bytes(data)
            self.pins[str(self.config)] = hashlib.sha256(data).hexdigest()
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.reader().load_sealed(self.config, self.pins[str(self.config)])

    def test_validator_failure_poisoned_not_skipped(self):
        reader = self.reader()

        def reject(*args):
            raise EpochError('Native validation failed')

        with self.assertRaises(EpochError):
            reader.read_config(self.root, self.pins[str(self.config)], reject)
        with self.assertRaises(EpochError):
            reader.check_pins(self.pins)

    def test_false_validator_verdict_rejected(self):
        reader = self.reader()
        with self.assertRaises(EpochError):
            reader.read_config(self.root, self.pins[str(self.config)], lambda *args: False)
        with self.assertRaises(EpochError):
            reader.finish()

    def test_fresh_postrun_epoch_rechecks_content(self):
        reader = self.reader()
        reader.check_pins(self.pins)
        reader.finish()
        reader.close()
        self.tool.write_bytes(b'changed-after-preflight')
        with self.assertRaises(EpochError):
            self.reader().check_pins(self.pins)

    def test_namespace_is_private_and_sha_known_only(self):
        reader = self.reader()
        namespace = reader.namespace()
        self.assertEqual(namespace['sha'](self.tool), self.pins[str(self.tool)])
        with self.assertRaises(EpochError):
            namespace['sha'](self.root / 'unknown')

    def test_relative_request_poisoned(self):
        reader = self.reader()
        with self.assertRaises(EpochError):
            reader.sha('relative')
        with self.assertRaises(EpochError):
            reader.check_pins(self.pins)

    def test_nonobject_config_poisoned(self):
        self.config.write_bytes(b'[]')
        self.pins[str(self.config)] = hashlib.sha256(self.config.read_bytes()).hexdigest()
        reader = self.reader()
        with self.assertRaises(EpochError):
            reader.read_config(self.root, self.pins[str(self.config)], lambda *args: None)
        with self.assertRaises(EpochError):
            reader.check_pins(self.pins)

    def test_json_declared_via_alias_still_one_parse(self):
        self.link.unlink()
        self.link.symlink_to('config.json')
        self.pins[str(self.link)] = self.pins[str(self.config)]
        self.aliases[str(self.link)] = AliasBinding('config.json', str(self.config), self.pins[str(self.config)])
        reader = PopulationReaderEpoch(self.pins, self.aliases, json_paths=[str(self.link)])
        first = reader.load_sealed(self.link, self.pins[str(self.link)])
        self.assertIs(first, reader.load_sealed(self.config, self.pins[str(self.config)]))
        reader.check_pins(self.pins)
        self.assertEqual(reader.finish()['parses'], 1)

    def test_top_level_array_immutable(self):
        self.config.write_bytes(b'[{"a":[1]}]')
        self.pins[str(self.config)] = hashlib.sha256(self.config.read_bytes()).hexdigest()
        value = self.reader().load_sealed(self.config, self.pins[str(self.config)])
        self.assertIsInstance(value, tuple)
        self.assertIsInstance(value[0], MappingProxyType)


if __name__ == '__main__':
    unittest.main()
