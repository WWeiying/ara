from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent


class SourceIdentity(unittest.TestCase):
    def test_only_group_sum_changes(self):
        source=Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv/q8_K-m4-packed.h').read_text()
        source=source.replace('namespace ggml_riscv_q8_K_m4_packed','namespace qbs_m4_parallel_sums')
        source=source.replace('#include "q8_K-m4.h"','#include "q8_K-m4.h"\n#include "candidate.h"')
        first=source.index('inline void sums(')
        last=source.index('\n// Qualified',first)
        source=source[:first]+'''inline void sums(vint8m1_t q, int16_t *destination, size_t vl) {
    qbs_m4_group_sums(q,destination,vl);
}
'''+source[last:]
        self.assertEqual((HERE/'quantizer_candidate.h').read_text(),source)


if __name__=='__main__':unittest.main()
