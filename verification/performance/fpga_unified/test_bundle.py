#!/usr/bin/env python3
"""Check frozen adapter overlays and the board launcher without running target code."""
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def load_build():
    spec = importlib.util.spec_from_file_location('unified_build', HERE / 'build.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BundleTests(unittest.TestCase):
    def test_scoped_patches_preserve_board_features(self):
        helper = load_build()
        with tempfile.TemporaryDirectory(prefix='unified-patches-') as temporary:
            root = Path(temporary)
            paths = ('ggml/src/ggml-cpu/arch/riscv/qbs.cpp',
                     'ggml/src/ggml-cpu/arch/riscv/akv.cpp')
            for path in paths:
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(helper.git(helper.LLAMA, 'show', helper.LLAMA_BASE + ':' + path))
            for patch in ('qbs_trace_context.patch', 'akv_auto.patch'):
                subprocess.run(['git', 'apply', '--unsafe-paths', '--directory=' + str(root),
                                str(HERE / patch)], check=True)
            self.assertEqual(helper.sha(root / paths[0]),
                             '9aa982ff55414f92d8fc10df8b09cc29eb013dcd2b81deadcbed99216158c8f9')
            source = (root / paths[1]).read_text()
            self.assertIn('akv_attention_execute_v2_native_auto(&device(), plan, workspace)', source)
            self.assertIn('akv_attention_can_use_plain_scores', source)
            self.assertIn('ggml_riscv_quant_kv_flash_attn', source)
            self.assertIn('akv_attention_execute_v2(plan, emulate, nullptr)', source)

    def launcher(self, arm, temporary, fail=False):
        root = Path(temporary)
        bundle = root / 'bundle'
        bundle.mkdir()
        shutil.copy2(HERE / 'run_board.sh', bundle / 'run_board.sh')
        # Fake executables expose only the launch contract, not target behavior.
        fake = ('#!/bin/sh\n'
                'printf "PAIR=%s\\n" "${AKV_PAIR_HEADS-absent}" >&2\n'
                'printf "QUANT=%s\\n" "$GGML_RISCV_AKV_QUANT_KV" >&2\n'
                'printf "M4=%s\\n" "$GGML_RISCV_QBS_M4_PREPARE" >&2\n'
                'printf "LEAK=%s\\n" "${AKV_QK_PANEL4-absent}" >&2\n'
                'for value do printf "ARG:%s\\n" "$value" >&2; done\n'
                'printf "test-logits" > "$LLAMA_SIMPLE_LOGITS_FILE"\n'
                'exit ' + ('17' if fail else '0') + '\n')
        lines = []
        for name in ('llama-f16-accepted', 'llama-f16-unified'):
            binary = bundle / name
            binary.write_text(fake)
            binary.chmod(0o755)
            lines.append(hashlib.sha256(binary.read_bytes()).hexdigest() + '  ' + name)
        (bundle / 'SHA256SUMS').write_text('\n'.join(lines) + '\n')
        model, prompt = root / 'model with space.gguf', root / 'prompt with space.txt'
        model.write_text('test model')
        prompt.write_text('line1\nline2\n\n')
        output = root / 'output'
        result = subprocess.run(['sh', bundle / 'run_board.sh', arm, model, prompt, '64', output],
            env=dict(os.environ, AKV_PAIR_HEADS='1', AKV_QK_PANEL4='0'), capture_output=True, text=True)
        self.assertEqual(result.returncode, 17 if fail else 0, result.stdout + result.stderr)
        log = (output / 'stderr.log').read_text()
        self.assertIn('PAIR=' + ('0' if arm == 'generic' else 'absent') + '\n', log)
        self.assertIn('QUANT=0\nM4=1\nLEAK=absent\n', log)
        self.assertIn('ARG:line1\nline2\n\n\n', log)
        self.assertIn('ARG:-t\nARG:1\n', log)
        self.assertEqual((output / 'exit_code').read_text().strip(), '17' if fail else '0')
        self.assertTrue((output / 'finished_at').is_file())
        again = subprocess.run(['sh', bundle / 'run_board.sh', arm, model, prompt, '64', output],
                               capture_output=True)
        self.assertNotEqual(again.returncode, 0)

    def test_auto_does_not_inherit_pair_override(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.launcher('auto', temporary)

    def test_generic_forces_legacy_and_no_quantized_kv(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.launcher('generic', temporary)

    def test_accepted_retains_original_program(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.launcher('accepted', temporary)

    def test_failure_propagated_without_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.launcher('auto', temporary, fail=True)


if __name__ == '__main__':
    unittest.main()
