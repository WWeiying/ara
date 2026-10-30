"""Source-level preparation checks, not a compiled/numerical/RTL gate."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
ORIGINAL = ROOT / 'verification/out/q4-untimed-verify-fixed-layout-20261025-01/attention_threeway_untimed.c'


class PairPreparationTests(unittest.TestCase):
    def module(self):
        spec = importlib.util.spec_from_file_location('grouped_prepare_unit', HERE / 'prepare.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_archive_translation_exact(self):
        p = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / p.QDIR / 'online.h'
            archived = root / 'old/candidate/source' / live.relative_to(root)
            archived.parent.mkdir(parents=True)
            archived.write_bytes(b'original SDK')
            prior = dict(artifacts={}, input_pins={str(live): p.sha(archived)})
            with patch.object(p, 'ROOT', root):
                pins, translated = p.historical_pins(prior, root / 'old')
                self.assertNotIn(str(live), pins)
                self.assertEqual(translated[str(live)], str(archived))
                archived.write_bytes(b'changed SDK')
                with self.assertRaisesRegex(ValueError, 'No exact historical'):
                    p.historical_pins(prior, root / 'old')

    def test_other_archive_pin_cannot_be_waived(self):
        p = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'data.bin'
            path.write_bytes(b'original')
            prior = dict(artifacts={str(path): p.sha(path)}, input_pins={})
            path.write_bytes(b'drift')
            with self.assertRaisesRegex(ValueError, 'artifact/input drift'):
                p.historical_pins(prior, Path(tmp))

    def test_reused_dependencies_require_hashes_and_no_sdk(self):
        p = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            obj, dep = root / 'object.o', root / 'header.h'
            obj.write_bytes(b'object'); dep.write_bytes(b'header')
            row = dict(object=str(obj), object_sha256=p.sha(obj), dependencies={str(dep): p.sha(dep)})
            proof = dict(rebuilt=False, original_object=str(obj), original_sha256=p.sha(obj), sides={'candidate': row})
            proofs = [dict(rebuilt=True)] * 3 + [proof] * 14
            path = root / 'dependencies.json'
            path.write_text(json.dumps(proofs))
            prior = dict(artifacts={str(path): p.sha(path)})
            pins = {str(dep): p.sha(dep)}
            with patch.object(p, 'PRIOR', root / 'build.json'):
                self.assertEqual(len(p.reused_dependencies(prior, pins)), 14)
                dep.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'Unproven reused dependency'):
                    p.reused_dependencies(prior, pins)

    def test_missing_sdk_blocks_before_output(self):
        spec = importlib.util.spec_from_file_location('grouped_pair_prepare_test', HERE / 'prepare.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(module, 'HERE', root), self.assertRaisesRegex(ValueError, 'SDK API not landed'):
                module.prepare(root / 'out/blocked')
            self.assertFalse((root / 'out').exists())

    def test_original_mapper_preserved(self):
        old = ORIGINAL.read_bytes()
        self.assertEqual(hashlib.sha256(old).hexdigest(),
                         'd609762ba1857f4b797cf08e00cd4e9975f14920306cb3abc004b1ec0f9eac6c')
        text = old.decode()
        mapper = text[text.index('static void threeway_tensors('):text.index('\ntypedef struct {')]
        current = (HERE / 'main.c').read_text()
        new = current[current.index('static void pair_tensors('):current.index('\nint main(void)')]
        self.assertEqual(new, mapper.replace('threeway_tensors', 'pair_tensors'))

    def test_no_raw_output_array_or_sdk_kernel_copy(self):
        text = (HERE / 'main.c').read_text()
        self.assertNotIn('fast_hex32(', text)
        self.assertNotIn('vfmacc', text)
        self.assertNotIn('expf(', text)
        self.assertIn('#include "sdk_adapter.h"', text)
        self.assertIn('const unsigned order[]={0,1,1,0};', text)
        self.assertIn('exact_all=1', text)

    def test_full_call_timer_and_checks(self):
        text = (HERE / 'main.c').read_text()
        begin = text.index('const uint64_t start=strided_cycles();')
        map_ = text.index('const int map_status=akv_quant_ggml_map(')
        execute = text.index('pair_sdk_execute(')
        drain = text.index('    drain();', execute)
        end = text.index('const uint64_t elapsed=strided_cycles()-start;')
        csr = text.index('__asm__ volatile("frcsr', end)
        gold = text.index('const float y=output.data', csr)
        self.assertTrue(begin < map_ < execute < drain < end < csr < gold)
        for token in ('report.native.command_attempts!=8', 'report.native.value_decodes!=128',
                      'report.key_panels!=4', 'report.key_bytes!=9216', 'pair_quantizations!=HEADS',
                      'errors+=differences!=0',
                      '0.004f+0.002f*fabsf(gold)', 'UINT32_C(0xa5a5a5a5)', 'fc!=first_fcsr', 'vc!=5'):
            self.assertIn(token, text)
        self.assertNotIn('grouped_updates', text)
        adapter = (HERE / 'sdk_adapter.h').read_text()
        self.assertIn('enabled ? akv_quant_strided_execute_grouped_pv(', adapter)
        self.assertIn(': akv_quant_strided_execute(', adapter)


if __name__ == '__main__':
    unittest.main()
