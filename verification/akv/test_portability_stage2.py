#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


package = load('package', ROOT / 'hardware/scripts/llama_q4km_extract/package_attention_capture.py')
generator = load('generator', ROOT / 'apps/llama_q4km_operator/script/gen_data.py')
summary = load('summary', Path(__file__).with_name('summarize_portability_stage2.py'))
runner = load('runner', Path(__file__).with_name('run_portability_stage2.py'))


class PortabilityEvidenceTest(unittest.TestCase):
    def test_finite_alibi_prefix_and_rejections(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'mask.bin'
            path.write_bytes(struct.pack('<4H', 0xc000, 0xbc00, 0, 0xfc00))
            self.assertEqual(package.active_mask_prefix(path, 4), 3)
            for values in ((0xfc00, 0xfc00, 0xfc00, 0xfc00),
                           (0, 0xfc00, 0, 0xfc00), (0, 0x7e00, 0, 0xfc00)):
                path.write_bytes(struct.pack('<4H', *values))
                with self.assertRaises(SystemExit):
                    package.active_mask_prefix(path, 4)

    def test_gqa32_packaging_and_mode_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            block = root / 'decode/block'
            block.mkdir(parents=True)
            definitions = [('attn_q_input-0', 'f32', [64, 1, 32, 1]),
                           ('attn_k_input-0', 'f16', [64, 4, 1, 1]),
                           ('attn_v_input-0', 'f16', [64, 4, 1, 1]),
                           ('attn_mask_input-0', 'f16', [4, 1, 1, 1]),
                           ('kqv_out-0', 'f32', [2048, 1, 1, 1])]
            for name, dtype, shape in definitions:
                size = (4 if dtype == 'f32' else 2)
                for dimension in shape:
                    size *= dimension
                (block / f'{name}.json').write_text(json.dumps({'shape': shape, 'type': dtype, 'nbytes': size}))
                (block / f'{name}.bin').write_bytes(bytes(size))
            (block / 'attn_mask_input-0.bin').write_bytes(struct.pack('<4H', 0xc000, 0xbc00, 0, 0xfc00))
            (block / 'attention_params-0.json').write_text(json.dumps({'scale': .125, 'max_bias': 8.0}))
            subprocess.run([sys.executable, package.__file__, root, '--model', 'test-fixture'], check=True, capture_output=True)
            case_path = root / 'replay/cases/operator/decode/attention_core/case.json'
            case = json.loads(case_path.read_text())
            self.assertEqual(case['provenance']['gqa_rows'], 32)
            self.assertEqual(case['provenance']['active_kv'], 3)
            with patch.object(generator, 'CAPTURE_ROOT', root):
                _, flags, _, params, _ = generator.make_spec('operator/decode/attention_core', 'akv_v2_portable')
                self.assertEqual(flags, generator.ATTENTION_AKV_V2 | generator.ATTENTION_PORTABLE)
                self.assertEqual(params[3], 8)
                with self.assertRaises(SystemExit):
                    generator.make_spec('operator/decode/attention_core', 'akv_v2')
                generator.make_spec('operator/decode/attention_core', 'rvv')
                case['sinks_enabled'] = True
                case_path.write_text(json.dumps(case))
                with self.assertRaises(SystemExit):
                    generator.make_spec('operator/decode/attention_core', 'akv_v2_portable')

    def test_only_combined_run_contributes_coverage(self):
        text = ('AKV_TOKEN_RUN_BEGIN=RVV\nGGML_RISCV_AKV_COVERAGE candidate_ops=12 executed_ops=0\n'
                'AKV_TOKEN_RUN_BEGIN=QBS_AKV_V2\nGGML_RISCV_AKV_COVERAGE candidate_ops=12 executed_ops=8\n'
                'GGML_RISCV_AKV_FALLBACK mode=prefill reason=feature portable=1\n'
                'AKV_TOKEN_RUN_EXIT=QBS_AKV_V2:0\nAKV_LOGITS_TOP1_EQUAL=1\n')
        result = summary.model_records(text)
        self.assertEqual(len(result['coverage']), 1)
        self.assertEqual(result['coverage'][0]['executed_ops'], '8')
        self.assertEqual(result['fallback_by_phase'], {'prefill:feature': 1})
        self.assertEqual(result['numerical']['AKV_LOGITS_TOP1_EQUAL'], '1')

    def test_failed_or_different_capture_is_not_a_baseline(self):
        row = dict(case='qwen', effective_kv=16, capture_manifest_sha256='one', simv_sha256='sim', run_dir='run')
        rows = [{**row, 'status': 'PASS', 'implementation': 'rvv', 'kernel_cycles': '100'},
                {**row, 'status': 'PASS', 'implementation': 'akv_v2_portable', 'kernel_cycles': '25'},
                {**row, 'status': 'FAIL', 'implementation': 'akv_v2_portable'},
                {**row, 'status': 'PASS', 'implementation': 'akv_v2_portable', 'capture_manifest_sha256': 'two', 'kernel_cycles': '20'}]
        summary.add_comparisons(rows)
        self.assertEqual(rows[1]['speedup_vs_rvv'], 4)
        self.assertNotIn('speedup_vs_rvv', rows[2])
        self.assertNotIn('speedup_vs_rvv', rows[3])

    def test_shell_snapshot_preserves_zero_and_arguments(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'run-ara-attention-core.sh'
            path.write_text('printf "%s\\n%s\\n" "$0" "$1"\n')
            log = root / 'test.log'
            self.assertEqual(runner.command(['bash', path, 'akv_v2_portable'], log), 0)
            self.assertEqual(log.read_text().splitlines(), [str(path), 'akv_v2_portable'])
            self.assertEqual(log.with_suffix('.launcher.sh').read_text(), path.read_text())


if __name__ == '__main__':
    unittest.main()
