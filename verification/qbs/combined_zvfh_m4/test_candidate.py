"""Static candidate admission only; not a numerical or RTL acceptance test."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
LLAMA = Path('/home/wangwy/llama/llama.cpp')
RELATIVE = Path('ggml/src/ggml-cpu/repack.cpp')
EXPECTED = 'a075a21276c8b7e1b26eaefaf0821cf31e9b427b3f5dc1a3c07b32256d433e9c'
OLD = '#if defined(GGML_USE_RISCV_QBS) && !defined(__riscv_zvfh)'
NEW = '#if defined(GGML_USE_RISCV_QBS)'


def pinned_source(data):
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise ValueError('Production source changed; review before preparing successor')
    return data.decode()


class Candidate(unittest.TestCase):
    def test_exact_two_guard_change(self):
        original_bytes = (LLAMA / RELATIVE).read_bytes()
        original = pinned_source(original_bytes)
        self.assertEqual(original.count(OLD), 2)
        with tempfile.TemporaryDirectory(prefix='qbs-zvfh-admission-') as directory:
            root = Path(directory)
            target = root / RELATIVE
            target.parent.mkdir(parents=True)
            shutil.copyfile(LLAMA / RELATIVE, target)
            subprocess.run(['git', 'apply', '--check', str(HERE / 'enable_q8k.patch')],
                           cwd=root, check=True, capture_output=True)
            subprocess.run(['git', 'apply', str(HERE / 'enable_q8k.patch')],
                           cwd=root, check=True, capture_output=True)
            candidate = target.read_text()
            self.assertEqual(candidate, original.replace(OLD, NEW))
            # Q8_0's Zvfh specialization is deliberately not part of this change.
            begin = original.index('template <> void ggml_quantize_mat_t<1, GGML_TYPE_Q8_0>')
            end = original.index('template <> void ggml_quantize_mat_t<1, GGML_TYPE_Q8_K>', begin)
            self.assertIn(original[begin:end], candidate)
        self.assertEqual((LLAMA / RELATIVE).read_bytes(), original_bytes)

    def test_drift_is_rejected(self):
        with self.assertRaises(ValueError):
            pinned_source((LLAMA / RELATIVE).read_bytes() + b'\n')

    def test_header_available_with_qbs_and_zvfh(self):
        source = pinned_source((LLAMA / RELATIVE).read_bytes())
        self.assertIn('#if defined(GGML_USE_RISCV_QBS)\n#include "arch/riscv/qbs.h"\n'
                      '#include "arch/riscv/q8_0-m4.h"\n#include "arch/riscv/q8_K-m4.h"\n#endif', source)
        header = (LLAMA / RELATIVE.parent / 'arch/riscv/q8_K-m4.h').read_text()
        self.assertNotIn('__riscv_zvfh', header)
        self.assertIn('frm != 0 || k == 0 || !vector_domain(x, k)', header)
        self.assertIn('ggml_quantize_mat_q8_K_4x1_ara_generic(x, vy, k);', header)


if __name__ == '__main__':
    unittest.main()
