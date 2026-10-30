"""Host-only tests of exact transformed code, not a second handwritten oracle."""
import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_untimed_verify_render', HERE / 'render.py')
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)


class TransformTests(unittest.TestCase):
    def setUp(self):
        self.original = render.ORIGINAL.read_bytes()
        self.generated = render.render(self.original)

    def test_hash_locked_roundtrip(self):
        self.assertEqual(render.digest(self.original), render.ORIGINAL_SHA256)
        self.assertEqual(render.inverse(self.generated), self.original)
        proof = render.provenance(self.original, self.generated)
        self.assertEqual(proof['trial_order'], [0, 1, 2, 2, 1, 0])
        self.assertEqual(proof['output_hex_characters'], 36864)
        self.assertFalse(proof['machine_code_identity_claimed'])
        self.assertEqual(proof['execution'], 'NOT_RUN')

    def test_entire_prefix_and_suffix_unchanged(self):
        lo, hi = render.region(self.original, render.CHECK_START, render.CHECK_END)
        a, b = render.region(self.generated, render.CHECK_START, render.CHECK_END)
        self.assertEqual(self.original[:lo], self.generated[:a])
        self.assertEqual(self.original[hi:], self.generated[b:])
        self.assertIn(b'frcsr %0;csrr %1,vcsr', self.generated[:a])
        self.assertIn(b'fc!=baseline_fcsr', self.generated[:a])
        self.assertIn(b'errors+=threeway_quantizations!=HEADS;', self.generated[:a])
        self.assertEqual(self.generated.count(b'static float mode_previous'), 1)
        self.assertEqual(self.generated.count(b'__builtin_memcpy('), 7)

    def test_protocol_and_arithmetic_unchanged(self):
        old, new = render.check_body(self.original), render.check_body(self.generated)
        self.assertEqual(re.findall(rb'printf\("[^"\n]*"', old),
                         re.findall(rb'printf\("[^"\n]*"', new))
        for line in old.splitlines():
            if any(x in line for x in (b'fabsf(', b'isfinite(', b'max_abs=', b'pair_max_abs=',
                                       b'output.before', b'if (errors)')):
                self.assertIn(line, new)
        self.assertNotRegex(new, rb'\bbits\(')
        self.assertEqual(new.count(b'fast_hex32('), 1)

    def test_input_drift_rejected(self):
        for bad in (self.original+b'\n',
                    self.original.replace(b'THREEWAY_TRIALS = 6', b'THREEWAY_TRIALS = 5'),
                    self.original.replace(b'fc!=baseline_fcsr', b'0'),
                    self.original.replace(render.OLD_COMPARE, render.OLD_COMPARE*2)):
            with self.subTest(bad=render.digest(bad)), self.assertRaises(ValueError):
                render.render(bad)

    def test_generated_drift_rejected(self):
        for bad in (self.generated+b'\n',
                    self.generated.replace(b'errors+=y_word!=previous_word;', b'errors+=0;'),
                    self.generated.replace(b'fast_hex32(output_word)', b'fast_hex32(0)'),
                    self.generated.replace(b'const uint64_t start=', b'const uint64_t changed='),
                    self.generated.replace(render.NEW_OUTPUT, render.NEW_OUTPUT*2),
                    self.generated.replace(b'0.004f+0.002f', b'0.04f+0.02f')):
            with self.subTest(bad=render.digest(bad)), self.assertRaises(ValueError):
                render.inverse(bad)

    def test_provenance_does_not_accept_other_generated_source(self):
        with self.assertRaises(ValueError):
            render.provenance(self.original, self.generated.replace(b'vc!=5', b'vc!=0'))
        with self.assertRaises(ValueError):
            render.provenance(self.original+b'\n', self.generated)


class HostSemanticTests(unittest.TestCase):
    def test_actual_verifier_predicates_payloads_state_flags_stdout(self):
        compiler = shutil.which('gcc')
        self.assertIsNotNone(compiler, 'GNU host compiler required; no silent skip')
        original = render.ORIGINAL.read_bytes()
        template = (HERE / 'fixture.c').read_bytes()
        marker = b'/* INSERT_ACTUAL_CHECK_BODY */'
        self.assertEqual(template.count(marker), 1)
        outputs = []
        with tempfile.TemporaryDirectory(prefix='untimed-verify-host-') as directory:
            for name, source in [('original', original), ('candidate', render.render(original))]:
                c_path = Path(directory) / (name+'.c')
                exe = Path(directory) / name
                # Structured fixture generation only; tested block is the real source.
                c_path.write_bytes(template.replace(marker, render.check_body(source)))
                command = [compiler, '-std=c11', '-O3', '-Wall', '-Wextra', '-Werror',
                           '-fno-builtin', '-fno-tree-vectorize', '-fno-fast-math',
                           '-ffp-contract=fast', '-frounding-math', '-fsignaling-nans',
                           '-I'+str(render.ROOT), str(c_path), '-lm', '-o', str(exe)]
                compiled = subprocess.run(command, capture_output=True, timeout=60)
                self.assertEqual(compiled.returncode, 0, compiled.stderr.decode())
                ran = subprocess.run([str(exe)], capture_output=True, timeout=60)
                self.assertEqual(ran.returncode, 0, ran.stdout[-1000:])
                outputs.append(ran)
        self.assertEqual(outputs[0].stdout, outputs[1].stdout)
        # Full comparison-state bytes, not merely the displayed diagnostic hash.
        self.assertEqual(outputs[0].stderr, outputs[1].stderr)
        self.assertEqual(len(outputs[0].stderr), 576*(4*6*128*4+3*4))
        lines = outputs[1].stdout.decode('ascii').splitlines()
        expected = None
        records = 0
        for line in lines:
            if line.startswith('CASE '):
                expected = int(re.search(r'expected_errors=(\d+)', line)[1])
            if line.startswith('QUANT_THREEWAY_RESULT '):
                self.assertEqual(int(re.search(r'errors=(\d+)', line)[1]), expected)
                payload = line.partition(' hex=')[2]
                self.assertEqual(len(payload), 6144)
                self.assertRegex(payload, r'^[0-9a-f]{6144}$')
                records += 1
        self.assertEqual(records, 576)
        self.assertEqual(lines[-1], 'HOST_VERIFY_PASS cases=576')
        special = [0,0x80000000,1,0x80000001,0x007fffff,0x807fffff,0x00800000,
                   0x80800000,0x3f800000,0xbf800000,0x7f7fffff,0xff7fffff,
                   0x7f800000,0xff800000,0x7fc00000,0x7fc12345,0xffc12345,
                   0x7f800001,0x7fa12345,0xff800001]
        self.assertEqual(lines[-2], 'PAYLOADS '+''.join(f'{x:08x}' for x in special))
        # The transformed output loop must preserve the same special payloads.
        records = [line.partition(' hex=')[2] for line in lines
                   if line.startswith('QUANT_THREEWAY_RESULT ')]
        for i, word in enumerate(special):
            for payload in records[i*6:(i+1)*6]:
                self.assertEqual(payload[:8], f'{word:08x}')


if __name__ == '__main__':
    unittest.main()
