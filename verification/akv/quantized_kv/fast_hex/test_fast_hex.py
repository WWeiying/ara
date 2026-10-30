"""Host-only stdout/renderer/factory tests; no cross compiler or simulator."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import build
import render


class RenderTests(unittest.TestCase):
    def test_exact_inverse_and_window(self):
        original = render.ORIGINAL.read_bytes()
        successor = render.render(original)
        self.assertEqual(render.inverse(successor), original)
        self.assertEqual(render.timed_region(original), render.timed_region(successor))
        self.assertEqual(successor.count(render.NEW_CALL), 1)
        self.assertNotIn(render.OLD_CALL, successor)
        proof = render.provenance(original, successor)
        self.assertEqual(proof['inverse_sha256'], render.ORIGINAL_SHA256)
        self.assertEqual(proof['output_hex_characters'], 6 * 768 * 8)
        self.assertEqual(proof['trial_order'], [0, 1, 2, 2, 1, 0])
        self.assertFalse(proof['machine_code_identity_claimed'])

    def test_reject_source_or_inverse_drift(self):
        original = render.ORIGINAL.read_bytes()
        for bad in (original + b'\n', original.replace(b'THREEWAY_TRIALS = 6', b'THREEWAY_TRIALS = 4'),
                    original.replace(render.OLD_CALL, render.OLD_CALL * 2)):
            with self.assertRaises(ValueError):
                render.render(bad)
        successor = render.render(original)
        for bad in (successor + b'\n', successor.replace(b'fc!=baseline_fcsr', b'0'),
                    successor.replace(render.NEW_CALL, render.NEW_CALL * 2),
                    successor.replace(render.HEADER_LINE, b''),
                    successor.replace(b'const uint64_t start=', b'const uint64_t changed=')):
            with self.assertRaises(ValueError):
                render.inverse(bad)

    def test_original_include_resolution(self):
        root = HERE.parents[3]
        source = render.render(render.ORIGINAL.read_bytes())
        for _old, qualified in render.INCLUDES:
            relative = qualified.split(b'"')[1].decode()
            self.assertEqual((root / relative).resolve(), HERE.parent / Path(relative).name)
            self.assertTrue((root / relative).is_file())
            self.assertIn(qualified, source)
        self.assertTrue((root / render.HEADER_LINE.split(b'"')[1].decode()).is_file())

    def test_factory_instances_are_private(self):
        a = build.load_factory(Path('/unbuilt/a.c'))
        b = build.load_factory(Path('/unbuilt/b.c'))
        self.assertIsNot(a, b)
        self.assertEqual(a.MAIN, Path('/unbuilt/a.c'))
        self.assertEqual(b.MAIN, Path('/unbuilt/b.c'))
        self.assertEqual(a.predecessor.MAIN.name, 'attention_strided_main.c')
        self.assertEqual(render.digest(build.FACTORY.read_bytes()), build.FACTORY_SHA256)

    def test_reused_input_policy(self):
        base = Path('/base')
        link = ['cc', '/base/main.o', '/base/runtime.o', '/base/lib.a', '-o', '/new/program.elf']
        self.assertEqual(build.reused_inputs(link, base), [Path('/base/runtime.o'), Path('/base/lib.a')])
        for bad in (link + ['/base/main.o'], [x for x in link if x != '/base/main.o']):
            with self.assertRaises(ValueError):
                build.reused_inputs(bad, base)

    def test_report_refresh_and_checker_compatibility(self):
        factory = build.load_factory(Path('/unbuilt/main.c'))
        # Validate the published interface with the actual unchanged checker,
        # using dummy artifacts only. This does not claim a native ELF build.
        spec = importlib.util.spec_from_file_location('_fast_hex_test_checker',
                                                    HERE.parent / 'run_threeway_attention.py')
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            elf, obj, reused = out / 'threeway_attention.elf', out / 'main.o', out / 'runtime.o'
            elf.write_bytes(b'host-test-only-not-an-ELF')
            obj.write_bytes(b'new-main')
            reused.write_bytes(b'reused')
            source = out / 'generated.c'
            source.write_bytes(render.render(render.ORIGINAL.read_bytes()))
            factory.s.atomic_json(out / 'source-pins.json', factory.s.hashes([reused, source]))
            report = dict(state='THREEWAY_ENTRY_BUILT_NOT_EXECUTED', execution='NOT_RUN',
                          post_pins_match=True, threeway_entry=True, trial_order=[0, 1, 2, 2, 1, 0],
                          trials=6, expected_commands=16, outputs_per_trial=768, heads=6,
                          head_dim=128, visible_tokens=128, kv_head=0, exact_scale_bits='3db504f3',
                          rvv_value_decode=True, rvv_baseline_decode=True, mapping_timed=True,
                          admission_timed=True, gather_timed=True, workspace_bytes=13120,
                          kind='q8_0', key_token_stride=272, value_token_stride=272,
                          elf=str(elf), elf_sha256=factory.s.digest(elf))
            factory.s.atomic_json(out / 'build.json', report)
            new = build.finish_report(factory, out, report, factory.s.hashes([source]),
                                      render.provenance(render.ORIGINAL.read_bytes(), source.read_bytes()),
                                      factory.s.hashes([reused]))
            self.assertEqual(new['source_variant'], build.VARIANT)
            self.assertEqual(new['elf_sha256'], report['elf_sha256'])
            self.assertEqual(new['artifact_sha256'][str(out / 'source-pins.json')],
                             new['source_pins_sha256'])
            self.assertNotIn(str(out / 'build.json'), new['artifact_sha256'])
            accepted, _pins = checker.checked_build(out)
            self.assertEqual(accepted, new)
            source.write_bytes(source.read_bytes() + b'\n')
            with self.assertRaises(ValueError):
                checker.checked_build(out)


class HostStdoutTests(unittest.TestCase):
    def test_exact_stdout_boundaries_exhaustive_and_random(self):
        compiler = shutil.which('gcc')
        self.assertIsNotNone(compiler, 'GNU host compiler required; do not silently skip')
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / 'hex-test'
            subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-pedantic', str(HERE / 'test_hex.c'), '-o', str(exe)],
                           check=True, capture_output=True, timeout=60)
            def output(mode):
                return subprocess.run([str(exe), mode], check=True, capture_output=True,
                                      timeout=30).stdout
            reference, candidate = output('reference'), output('candidate')
            self.assertEqual(candidate, reference)
            self.assertEqual(len(candidate), (18 + 3 * 65536) * 8)
            self.assertLessEqual(set(candidate), set(b'0123456789abcdef'))
            self.assertEqual(candidate[:32], b'00000000000000010000000f00000010')
            self.assertEqual(hashlib.sha256(candidate).digest(), hashlib.sha256(reference).digest())


if __name__ == '__main__':
    unittest.main()
