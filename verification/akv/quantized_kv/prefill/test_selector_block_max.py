from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]


class BlockMaxTest(unittest.TestCase):
    def check(self,compiler,extra):
        with tempfile.TemporaryDirectory(prefix='selector-block-max-') as directory:
            binary=Path(directory)/'test'
            subprocess.run([compiler,'-std=gnu11','-O2','-Wall','-Wextra','-Werror',
                '-fno-fast-math','-ffp-contract=off',*extra,'-I'+str(ROOT),
                '-I'+str(ROOT/'software/qbs/include'),HERE/'test_selector_block_max.c',
                ROOT/'software/akv/experimental/quantized_kv/runtime.c',
                ROOT/'software/qbs/src/qbs_runtime.c',ROOT/'verification/qbs/qbs_ref.c',
                '-lm','-o',binary],check=True,timeout=120)
            result=subprocess.run([binary],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(result.stdout,'SELECTOR_BLOCK_MAX_PASS cases=2819 flags_equal=1 rejection_priority=1\n')

    def test_gcc(self):self.check(shutil.which('gcc'),[])
    def test_ubsan(self):self.check('/usr/bin/clang',['-fsanitize=undefined','-fno-sanitize-recover=undefined'])

    def test_exact_function_delta(self):
        source=(HERE/'selector_before_block_max.h').read_text()
        old=source[source.index('static inline int akv_quant_select_strided_before_block_max('):source.index('\n#undef AKV_QUANT_PROVEN_ALIGNMENT')]
        removed='        if ((bits & UINT32_C(0x7f800000)) == UINT32_C(0x7f800000)) return AKV_QUANT_SELECT_NONFINITE;\n'
        self.assertEqual(old.count(removed),1)
        expected=old.replace(removed,'').replace('      /* Conservative source-domain guard',
            '      /* The maximum absolute bit pattern is nonfinite iff any element is. */\n'
            '      if (maximum >= UINT32_C(0x7f800000)) return AKV_QUANT_SELECT_NONFINITE;\n'
            '      /* Conservative source-domain guard')
        expected=expected.replace('akv_quant_select_strided_before_block_max(','akv_quant_select_strided(')
        candidate=(ROOT/'software/akv/experimental/quantized_kv/selection_strided.h').read_text()
        actual=candidate[candidate.index('static inline int akv_quant_select_strided('):candidate.index('\n#undef AKV_QUANT_PROVEN_ALIGNMENT')]
        self.assertEqual(actual,expected)


if __name__=='__main__':unittest.main()
