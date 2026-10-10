"""Isolated synthetic literal-path and membership tests; no EDA."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from population_reader_732_consumer import Context, path_binding, verify_membership
from verification_epoch import EpochError


class ConsumerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'bin').mkdir()
        (self.root / 'include').mkdir()
        self.file = self.root / 'include/input.json'
        self.file.write_bytes(b'{"data":[1,true]}')
        self.literal = str(self.root) + '/bin/../include/input.json'
        self.sha = hashlib.sha256(self.file.read_bytes()).hexdigest()
        self.pins = {self.literal: self.sha, str(self.file): self.sha}
        self.prefix = str(self.root) + '/bin/../include/'

    def context(self, **kwargs):
        return Context(self.pins, [self.literal], links={}, dotdot_prefix=self.prefix, **kwargs)

    def test_literal_and_endpoint_share_one_parse_all_obligations(self):
        context = self.context()
        first = context.load_sealed(self.literal, self.sha)
        self.assertIs(first, context.load_sealed(self.file, self.sha))
        self.assertEqual(context.finish()['reads'], 1)
        self.assertEqual(context.reader.statistics['parses'], 1)

    def test_literal_obligation_not_dropped(self):
        context = self.context()
        context.digest(self.file)
        with self.assertRaises(EpochError):
            context.finish()

    def test_wrong_endpoint_authority_rejected(self):
        self.pins[str(self.file)] = '0' * 64
        with self.assertRaises(EpochError):
            self.context()

    def test_arbitrary_dotdot_spelling_rejected(self):
        with self.assertRaises(EpochError):
            path_binding(str(self.root) + '/include/../include/input.json', {}, self.prefix)

    def test_multilevel_dotdot_walk_retains_literal(self):
        nested = self.root / 'a/b/c/d'
        nested.mkdir(parents=True)
        literal = str(nested) + '/../../../../include/input.json'
        prefix = str(nested) + '/../../../../include/'
        context = Context({literal: self.sha, str(self.file): self.sha}, [literal],
                          links={}, dotdot_prefix=prefix)
        context.load_sealed(literal, self.sha)
        context.digest(self.file)
        self.assertIn(literal, context.pins)
        self.assertEqual(context.finish()['reads'], 1)

    def test_unlisted_app_or_gcc_suffix_rejected_before_io(self):
        from population_reader_732_consumer import root_api
        paths = (str(root_api.ROOT / 'apps/qbs_gap109_k2_sticky') + '/../common/other.h',
                 '/usr/lib/gcc/x86_64-redhat-linux/11/../../../../lib64/libm.so')
        for path in paths:
            with self.subTest(path=path), self.assertRaises(EpochError):
                path_binding(path, {})

    def test_dotdot_directory_symlink_rejected_even_same_target(self):
        (self.root / 'bin').rmdir()
        (self.root / 'realbin').mkdir()
        (self.root / 'bin').symlink_to('realbin')
        with self.assertRaises(EpochError):
            path_binding(self.literal, {str(self.root / 'bin'): 'realbin'}, self.prefix)

    def test_literal_alias_same_endpoint_wrong_target_rejected(self):
        alias = self.root / 'alias'
        alias.symlink_to('./include/input.json')
        with self.assertRaises(EpochError):
            path_binding(str(alias), {str(alias): 'include/input.json'})

    def test_parent_alias_explicit_identity_all_paths(self):
        alias = self.root / 'directory'
        alias.symlink_to('include')
        literal = str(alias / 'input.json')
        context = Context({literal: self.sha, str(self.file): self.sha}, [literal],
                          links={str(alias): 'include'})
        context.load_sealed(literal, self.sha)
        context.digest(self.file)
        self.assertEqual(context.finish()['reads'], 1)
        alias.unlink()
        alias.symlink_to('./include')
        with self.assertRaises(EpochError):
            context.digest(literal)

    def test_destination_preserves_original_key_and_conflicts_reject(self):
        context = self.context()
        destination = {}
        context.pin(destination, self.literal, self.sha)
        self.assertEqual(destination, {self.literal: self.sha})
        with self.assertRaises(EpochError):
            context.pin({self.literal: '0' * 64}, self.literal)

    def members(self):
        tests = tuple('/fixture/test-%d.vdb' % i for i in range(732))
        current = dict(tests=tests, design={'shape': 'a'})
        previous = dict(tests=tests[:-1], design={'shape': 'a'})
        digest = lambda names: hashlib.sha256(('\n'.join(('/fixture/design.vdb', *names)) + '\n').encode()).hexdigest()
        return current, previous, digest

    def test_exact_prefix_and_independently_reconstructed_input_bytes(self):
        current, previous, digest = self.members()
        verify_membership(current, previous, digest(current['tests']), digest(previous['tests']), '/fixture/design.vdb')

    def test_duplicate_members_and_wrong_text_sha_rejected(self):
        current, previous, digest = self.members()
        with self.assertRaises(EpochError):
            verify_membership(current, previous, '0' * 64, digest(previous['tests']), '/fixture/design.vdb')
        current['tests'] = (*current['tests'][:-1], current['tests'][0])
        with self.assertRaises(EpochError):
            verify_membership(current, previous, digest(current['tests']), digest(previous['tests']), '/fixture/design.vdb')

    def test_reordered_prefix_and_design_drift_rejected(self):
        current, previous, digest = self.members()
        previous['tests'] = tuple(reversed(previous['tests']))
        with self.assertRaises(EpochError):
            verify_membership(current, previous, digest(current['tests']), digest(previous['tests']), '/fixture/design.vdb')
        current, previous, digest = self.members()
        previous['design']['shape'] = 'b'
        with self.assertRaises(EpochError):
            verify_membership(current, previous, digest(current['tests']), digest(previous['tests']), '/fixture/design.vdb')


if __name__ == '__main__':
    unittest.main()
