"""Host-only integrity tests. Synthetic C fixtures are not target measurements.

Run with python3 -B -m unittest discover -s <q6_decode> -p test_input_integrity.py.
Set Q6_INTEGRITY_BUILD to the new build directory for the sealed artifact audit.
No test modifies predecessor files, receipts, data or logs.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


builder = module('q6_integrity_build_tests', 'build_integrity_successor.py')
csr_tests = module('q6_integrity_inherited_tests', 'test_csr_successor.py')
base = builder.base

# Preserve every predecessor CSR parser, receipt, source and first-failure test.
SuccessorParserTests = csr_tests.SuccessorParserTests
BuildManifestTests = csr_tests.BuildManifestTests
BuilderAndSourceTests = csr_tests.BuilderAndSourceTests
OriginalFailureEvidenceTests = csr_tests.OriginalFailureEvidenceTests


class HashTests(unittest.TestCase):
    def test_known_answers(self):
        for data, expected in ((b'', 'cbf29ce484222325'), (b'a', 'af63dc4c8601ec8c'),
                               (b'foobar', '85944171f73967e8'),
                               (b'hello', 'a430d84680aabd0b'),
                               (bytes(range(256)), '4242dc5249c33625')):
            with self.subTest(data=data[:8]):
                self.assertEqual(builder.fnv1a64(data), expected)

    def test_parent_identity_checked_before_execution(self):
        with mock.patch.object(Path, 'read_bytes', return_value=b'untrusted'), \
             mock.patch.object(importlib.util, 'spec_from_file_location') as load:
            with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                builder.load_parent()
            load.assert_not_called()

    def test_private_modules_keep_original_roots_and_classes(self):
        self.assertEqual(base.HERE, HERE)
        self.assertEqual(base.ROOT, HERE.parents[3])
        self.assertIs(builder.Builder.__mro__[1], builder.parent.Builder)
        self.assertIs(builder.parent.Builder.__mro__[1], base.Builder)
        self.assertEqual(base.digest(HERE / 'main.c'),
                         '56443c323cb4f148222514bda807588619d9ccaa314d2dfd44aac022497a0058')
        self.assertEqual(base.digest(HERE / 'main_csr_successor.c'),
                         'd1cb1b263e69be4b080555066c2eb150352f0b44b5b23e7ac5fbe7c3732fd645')
        self.assertEqual(base.digest(HERE / 'check_successor.py'), builder.CHECKER_SHA256)

    def test_frozen_payload_size_sha_and_bytes_checked_before_hash(self):
        files, frozen = {}, dict(artifacts={})
        for tag, (name, size, _) in builder.PAYLOADS.items():
            data = bytes(size)
            ref, new = builder.FROZEN / 'data' / name, Path('/fixture/data') / name
            files[ref] = files[new] = data
            frozen['artifacts'][str(ref)] = builder.hashlib.sha256(data).hexdigest()
        with mock.patch.object(Path, 'read_bytes', autospec=True, side_effect=lambda p: files[p]):
            records = builder.payload_records(Path('/fixture'), frozen)
            for tag, (name, size, symbol) in builder.PAYLOADS.items():
                self.assertEqual(records[tag], dict(path='/fixture/data/' + name, bytes=size,
                    symbol=symbol, expected_hash=builder.fnv1a64(bytes(size))))
                ref = builder.FROZEN / 'data' / name
                new = Path('/fixture/data') / name
                original = files[ref]
                for changed in (original[:-1], b'\x01' + original[1:]):
                    files[ref] = changed
                    with self.assertRaisesRegex(ValueError, 'Frozen payload identity'):
                        builder.payload_records(Path('/fixture'), frozen)
                files[ref] = original
                files[new] = b'\x01' + original[1:]
                with self.assertRaisesRegex(ValueError, 'Fresh payload differs'):
                    builder.payload_records(Path('/fixture'), frozen)
                files[new] = original


class RoutingTests(unittest.TestCase):
    def instance(self):
        # No subprocess or frozen-evidence I/O for isolated dispatch tests.
        instance = builder.Builder.__new__(builder.Builder)
        base.Builder.__init__(instance, Path('/unused'))
        instance.main_compile = None
        return instance

    def test_only_exact_main_renamed_and_csr_routing_inherited(self):
        instance = self.instance()
        flags = ['-O3', '-Wall']
        sources = [HERE / 'main.c', HERE / 'host_ref.c', Path('/sdk/qbs_runtime.c'),
                   Path('/sdk/qbs_native_riscv.c'), Path('/llama/quants.c'),
                   Path('/other/main.c'), Path('/sdk/crt0.S'), HERE / 'input_integrity.c']
        with mock.patch.object(base.Builder, 'compile', autospec=True) as compile:
            for i, source in enumerate(sources):
                obj = Path(f'/unused/object{i}.o')
                instance.compile('gcc', flags, source, obj)
                routed = HERE / 'main_csr_successor.c' if i == 0 else source
                expected_flags = [*flags, builder.RENAME_MAIN] if i == 0 else flags
                compile.assert_called_with(instance, 'gcc', expected_flags, routed, obj)
        self.assertEqual(flags, ['-O3', '-Wall'])
        self.assertEqual(instance.main_compile, ('gcc', flags, Path('/unused/object0.o')))
        with self.assertRaisesRegex(ValueError, 'Duplicate/renamed'):
            instance.compile('gcc', flags, HERE / 'main.c', Path('/unused/main.o'))

    def test_link_hook_compiles_wrapper_and_records_real_link(self):
        instance = self.instance()
        instance.main_compile = ('gcc', ['-O3'], Path('/unused/main.o'))
        instance.frozen = {}
        argv = ['gcc', '/unused/main.o', '-lm', '-o', '/unused/q6_decode.elf']
        payloads = {tag: dict(expected_hash='0123456789abcdef') for tag in builder.PAYLOADS}
        with mock.patch.object(builder, 'payload_records', return_value=payloads), \
             mock.patch.object(Path, 'exists', return_value=False), \
             mock.patch.object(Path, 'write_text') as write, \
             mock.patch.object(instance, 'pin') as pin, \
             mock.patch.object(instance, 'compile') as compile, \
             mock.patch.object(base.Builder, 'run', autospec=True, return_value=b'') as run:
            instance.run('link', argv)
            write.assert_called_once_with(builder.config_text(payloads))
            pin.assert_called_once_with(Path('/unused/integrity_config.h'))
            compile.assert_called_once_with('gcc', ['-O3'], HERE / 'input_integrity.c',
                                            Path('/unused/wrapper.o'))
            run.assert_called_once_with(instance, 'link', [
                'gcc', '/unused/main.o', '/unused/wrapper.o', '-lm', '-o',
                '/unused/q6_decode.elf'], None)
        self.assertNotIn('/unused/wrapper.o', argv)

    def test_output_reuse_and_other_destinations_rejected(self):
        for output in (Path('/tmp/not-authorized'), builder.FROZEN):
            with self.subTest(output=output), \
                 mock.patch.object(base, 'build') as build, \
                 self.assertRaisesRegex(ValueError, 'Output must be'):
                builder.build(type('Args', (), dict(output=output))())
            build.assert_not_called()

    def test_base_class_restored_on_build_failure(self):
        original = base.Builder
        def fail(args):
            self.assertIs(base.Builder, builder.Builder)
            raise ValueError('injected')
        with mock.patch.object(Path, 'exists', return_value=False), \
             mock.patch.object(base, 'build', side_effect=fail):
            with self.assertRaisesRegex(ValueError, 'injected'):
                builder.build(type('Args', (), dict(output=builder.OUTPUT))())
        self.assertIs(base.Builder, original)

    def test_frozen_revision_selected_with_real_git_command(self):
        instance = self.instance()
        instance.frozen = {'sdk_commit': 'abc123', 'llama_commit': 'def456'}
        for name, commit in (('sdk', 'abc123'), ('llama', 'def456')):
            with mock.patch.object(base.Builder, 'run', autospec=True,
                                   return_value=(commit + '\n').encode()) as run:
                instance.run(name + '-head', ['git', '-C', '/repo', 'rev-parse', 'HEAD'])
                run.assert_called_once_with(instance, name + '-head', [
                    'git', '-C', '/repo', 'rev-parse', commit], None)


class WrapperHostTests(unittest.TestCase):
    """Execute the exact C byte loop with only the RISC-V asm stubbed on host."""

    @classmethod
    def setUpClass(cls):
        output = os.environ.get('Q6_INTEGRITY_BUILD')
        cls.directory = tempfile.TemporaryDirectory(prefix='q6-integrity-host-', dir=output)
        cls.path = Path(cls.directory.name)
        payloads = {'activation': dict(expected_hash=builder.fnv1a64(bytes(8192))),
                    'weight': dict(expected_hash=builder.fnv1a64(bytes(107520)))}
        (cls.path / 'integrity_config.h').write_text(builder.config_text(payloads))
        common = builder.FROZEN / 'inputs/sdk/apps/common'
        pins = json.loads((builder.FROZEN / 'source-pins.json').read_text())
        for name in ('printf.c', 'printf.h'):
            if base.digest(common / name) != pins[str(common / name)]:
                raise ValueError('Frozen printf source drift')
        # Function-like volatile macro only swallows the asm operand list; the
        # volatile const byte pointer remains intact. No target source rewrite.
        driver = '''#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#define __asm__
#define volatile(...) ((void)0)
#define main integrity_main
#include "WRAPPER"
#undef main
#undef volatile
#undef __asm__
void _putchar(char character) { putchar(character); }
const float profile_input[2048] = {0};
const unsigned char profile_weights[107520] = {0};
static unsigned calls;
int q6_profile_body(void) {
  ++calls;
  if (getenv("MUTATE_PAYLOAD")) {
    volatile unsigned char *data = (volatile unsigned char *)(
        !strcmp(getenv("MUTATE_PAYLOAD"), "activation") ?
        (const void *)profile_input : (const void *)profile_weights);
    const size_t offset = strtoul(getenv("MUTATE_OFFSET"), NULL, 10);
    const uintptr_t page = (uintptr_t)sysconf(_SC_PAGESIZE);
    if (mprotect((void *)((uintptr_t)(data + offset) & ~(page - 1)),
                 page, PROT_READ | PROT_WRITE)) exit(98);
    data[offset] ^= 1;
    if (!strcmp(getenv("MUTATE_PAYLOAD"), "both")) {
      data = (volatile unsigned char *)profile_input;
      if (mprotect((void *)((uintptr_t)data & ~(page - 1)),
                   page, PROT_READ | PROT_WRITE)) exit(98);
      data[0] ^= 1;
    }
  }
  puts("SYNTHETIC_BODY_RETURN");
  return getenv("BODY_STATUS") ? atoi(getenv("BODY_STATUS")) : 0;
}
int main(int argc, char **argv) {
  if (argc == 2 && !strcmp(argv[1], "hash-all-bytes")) {
    unsigned char data[256];
    for (unsigned i = 0; i < 256; ++i) data[i] = (unsigned char)i;
    printf("%016lx\\n", (unsigned long)fnv1a64(data, sizeof(data)));
    return 0;
  }
  if (argc == 3 && !strcmp(argv[1], "hash")) {
    printf("%016lx\\n", (unsigned long)fnv1a64(
        (volatile const unsigned char *)argv[2], strlen(argv[2])));
    return 0;
  }
  const int result = integrity_main();
  return calls == 1 ? result : 99;
}
'''.replace('WRAPPER', str(HERE / 'input_integrity.c'))
        (cls.path / 'driver.c').write_text(driver)
        cls.exe = cls.path / 'wrapper-host'
        subprocess.run(['/usr/bin/gcc', '-std=c11', '-O3', '-Wall', '-Wextra', '-Werror',
                        '-I' + str(cls.path), '-I' + str(common), cls.path / 'driver.c',
                        common / 'printf.c', '-o', cls.exe],
                       check=True, capture_output=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def run_host(self, *args, **env):
        return subprocess.run([self.exe, *args], env={**os.environ, 'BODY_STATUS': '0', **env},
                              capture_output=True, text=True, timeout=10)

    def test_c_known_answers(self):
        for value in ('', 'a', 'foobar', 'hello'):
            result = self.run_host('hash', value)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), builder.fnv1a64(value.encode()))
        self.assertEqual(self.run_host('hash-all-bytes').stdout.strip(), '4242dc5249c33625')

    def test_exact_rows_only_after_body_returns(self):
        result = self.run_host()
        self.assertEqual(result.returncode, 0)
        expected = ['SYNTHETIC_BODY_RETURN']
        for tag, size in (('activation', 8192), ('weight', 107520)):
            value = builder.fnv1a64(bytes(size))
            expected.append(f'CHAIN_Q6_INPUT_INTEGRITY tag={tag} bytes={size} '
                            f'expected={value} actual={value}')
        expected.append('CHAIN_Q6_INPUT_INTEGRITY_DONE errors=0')
        self.assertEqual(result.stdout.splitlines(), expected)

    def test_body_failure_propagates_after_full_integrity_check(self):
        for status in ('1', '7', '-1'):
            result = self.run_host(BODY_STATUS=status)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout.count('CHAIN_Q6_INPUT_INTEGRITY tag='), 2)
            self.assertTrue(result.stdout.endswith('CHAIN_Q6_INPUT_INTEGRITY_DONE errors=0\n'))

    def test_payload_corruption_at_boundaries_and_interior_rejected(self):
        for tag, size in (('activation', 8192), ('weight', 107520)):
            for offset in (0, 31, 64, 4095, size // 2, size - 1):
                with self.subTest(tag=tag, offset=offset):
                    result = self.run_host(MUTATE_PAYLOAD=tag, MUTATE_OFFSET=str(offset))
                    self.assertEqual(result.returncode, 1)
                    data = bytearray(size)
                    data[offset] = 1
                    row = next(line for line in result.stdout.splitlines()
                               if line.startswith('CHAIN_Q6_INPUT_INTEGRITY tag=' + tag))
                    self.assertTrue(row.endswith('expected=' + builder.fnv1a64(bytes(size)) +
                                                 ' actual=' + builder.fnv1a64(data)))
                    self.assertTrue(result.stdout.endswith('CHAIN_Q6_INPUT_INTEGRITY_DONE errors=1\n'))

    def test_both_bad_and_body_plus_hash_failure_propagate(self):
        for status in ('0', '7'):
            result = self.run_host(MUTATE_PAYLOAD='both', MUTATE_OFFSET='0', BODY_STATUS=status)
            self.assertEqual(result.returncode, 1)
            self.assertTrue(result.stdout.endswith('CHAIN_Q6_INPUT_INTEGRITY_DONE errors=2\n'))

    def test_static_fence_and_full_byte_reads_outside_body(self):
        source = (HERE / 'input_integrity.c').read_text()
        self.assertEqual(source.count('q6_profile_body();'), 1)
        self.assertLess(source.index('q6_profile_body();'), source.index('"fence rw, rw"'))
        self.assertLess(source.index('"fence rw, rw"'), source.index('unsigned errors ='))
        self.assertIn('volatile const unsigned char *data', source)
        self.assertIn('hash ^= data[i];', source)
        self.assertNotRegex(source, r'\b(?:rdcycle|q6_decode_trial|quantize_row_q8_K)\b')


@unittest.skipUnless(os.environ.get('Q6_INTEGRITY_BUILD'), 'Set Q6_INTEGRITY_BUILD for real artifacts')
class ArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = Path(os.environ['Q6_INTEGRITY_BUILD']).resolve()
        cls.receipt = builder.check_integrity_build(cls.output / 'build.json')
        cls.frozen = builder.frozen_build()

    def test_manifest_pins_dependencies_and_actual_commands(self):
        receipt = self.receipt
        manifest = receipt['input_integrity']
        pins = json.loads(Path(receipt['source_pins']).read_text())
        self.assertEqual(manifest['method'], 'fnv1a64-after-both-timed-calls-v1')
        self.assertEqual(manifest['entrypoint'], 'main -> q6_profile_body')
        self.assertIs(manifest['memory_checked_after_both_calls'], True)
        self.assertEqual(set(manifest['payloads']), {'activation', 'weight'})
        for key in ('source', 'object', 'config'):
            path = manifest['wrapper'][key]
            self.assertEqual(pins[path], manifest['wrapper'][key + '_sha256'])
        dependencies = (self.output / 'wrapper.d').read_text().replace('\\\n', '')
        self.assertIn(manifest['wrapper']['source'], dependencies)
        self.assertIn(manifest['wrapper']['config'], dependencies)
        for filename in ('input_integrity.c', 'build_integrity_successor.py', 'test_input_integrity.py'):
            self.assertEqual(pins[str(HERE / filename)], base.digest(HERE / filename))

    def test_metadata_and_frozen_inputs_unchanged(self):
        frozen = builder.frozen_build()
        for key in ('csr_contract', 'successor_reason', 'parent_builder', 'measurement_source',
                    'checker_api', 'sdk_commit', 'llama_commit', 'timing', 'capture_scope'):
            self.assertEqual(self.receipt[key], frozen[key])
        for file in (builder.FROZEN / 'data').iterdir():
            self.assertEqual((self.output / 'data' / file.name).read_bytes(), file.read_bytes())
        for file in ('sdk.tar', 'llama.tar'):
            self.assertEqual(base.digest(self.output / file), base.digest(builder.FROZEN / file))
        self.assertEqual(self.receipt['reused_objects'], 0)
        self.assertEqual(self.receipt['rebuilt_runtime_objects'], frozen['rebuilt_runtime_objects'] + 1)

    def test_original_checker_still_accepts_build(self):
        self.assertEqual(builder.checker.check_build(self.output / 'build.json'), self.receipt)

    def test_manifest_tampering_rejected_without_evidence_edits(self):
        original = self.receipt
        candidates = []
        for key, value in (('method', 'other'), ('entrypoint', 'other'),
                           ('memory_checked_after_both_calls', False)):
            receipt = copy.deepcopy(original)
            receipt['input_integrity'][key] = value
            candidates.append(receipt)
        for tag in builder.PAYLOADS:
            for key, value in (('bytes', 1), ('expected_hash', '0000000000000000'),
                               ('path', '/wrong'), ('symbol', 'wrong')):
                receipt = copy.deepcopy(original)
                receipt['input_integrity']['payloads'][tag][key] = value
                candidates.append(receipt)
        for key in original['input_integrity']['wrapper']:
            receipt = copy.deepcopy(original)
            receipt['input_integrity']['wrapper'][key] = 'drift'
            candidates.append(receipt)
        for receipt in candidates:
            with mock.patch.object(builder, 'frozen_build', return_value=self.frozen), \
                 mock.patch.object(builder.checker, 'check_build', return_value=receipt), \
                 self.assertRaisesRegex(ValueError, 'manifest mismatch'):
                builder.check_integrity_build(self.output / 'build.json')

    def audit_document(self, path, document):
        real_read = Path.read_text
        def read(candidate, *args, **kwargs):
            return json.dumps(document) if candidate == path else real_read(candidate, *args, **kwargs)
        with mock.patch.object(builder, 'frozen_build', return_value=self.frozen), \
             mock.patch.object(builder.checker, 'check_build', return_value=self.receipt), \
             mock.patch.object(Path, 'read_text', autospec=True, side_effect=read):
            return builder.check_integrity_build(self.output / 'build.json')

    def test_missing_wrapper_header_object_payload_pins_rejected(self):
        receipt = self.receipt
        pins_path = Path(receipt['source_pins'])
        pins = json.loads(pins_path.read_text())
        wrapper = receipt['input_integrity']['wrapper']
        names = [wrapper[key] for key in ('source', 'object', 'config')]
        names += [record['path'] for record in receipt['input_integrity']['payloads'].values()]
        for name in names:
            for value in (None, 'drift'):
                changed = dict(pins)
                if value is None:
                    del changed[name]
                else:
                    changed[name] = value
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    self.audit_document(pins_path, changed)

    def test_missing_or_forged_compile_link_commands_rejected(self):
        path = self.output / 'commands.json'
        commands = json.loads(path.read_text())
        for label in ('compile-main', 'compile-wrapper', 'link'):
            with self.subTest(missing=label), self.assertRaises(ValueError):
                self.audit_document(path, [c for c in commands if c['label'] != label])
        for label, old, new in (
            ('compile-main', builder.RENAME_MAIN, '-Dunrelated'),
            ('compile-wrapper', '-O3', builder.RENAME_MAIN),
            ('link', str(self.output / 'wrapper.o'), str(self.output / 'not-wrapper.o')),
        ):
            changed = copy.deepcopy(commands)
            record = next(c for c in changed if c['label'] == label)
            record['argv'] = [new if arg == old else arg for arg in record['argv']]
            with self.subTest(label=label), self.assertRaises(ValueError):
                self.audit_document(path, changed)

    def test_disassembly_proves_post_body_fence_and_byte_loop(self):
        text = (self.output / 'disassembly.log').read_text()
        main = text.split('<main>:', 1)[1].split('\n\n', 1)[0]
        self.assertIn('<q6_profile_body>', main)
        self.assertEqual(len(re.findall(r'\bfence\b', main)), 1)
        self.assertLess(main.index('<q6_profile_body>'), main.index('fence'))
        self.assertNotRegex(main[:main.index('<q6_profile_body>')], r'\blbu\b')
        self.assertRegex(main[main.index('fence'):], r'\blbu\b')
        self.assertNotRegex(main, r'\b(?:vle|vse|rdcycle)')


if __name__ == '__main__':
    unittest.main()
