"""Public-entry transcript negative tests; original numerical gate stays active."""
from pathlib import Path
import unittest

from check_common_attention import CAP,check_log
import test_attention_check as original_checks

HERE=Path(__file__).resolve().parent


class CommonAttentionTest(unittest.TestCase):
    def transcript(self,kind):
        original_checks.AttentionCheckTest.setUpClass()
        original=original_checks.AttentionCheckTest()
        text=original.transcript(kind)
        golden,rtl=original.gold,original.rtl
        lines=[CAP]
        for line in text.splitlines():
            for trial in (1,2):
                if line.startswith(f'QUANT_ATTN_RESULT trial={trial} '):
                    lines.append(f'QUANT_COMMON_ENTRY trial={trial} map=0 status=0 selection=0 groups=1 commands=8 values=128')
            lines.append(line)
        return '\n'.join(lines),golden,rtl

    def test_both_profiles(self):
        for kind in (0,1):
            text,gold,rtl=self.transcript(kind)
            result=check_log(text,kind,gold,rtl)
            self.assertTrue(result['mapping_timed'])
            self.assertTrue(result['admission_timed'])
            self.assertFalse(result['deployment_approved'])

    def test_missing_or_false_entry(self):
        text,gold,rtl=self.transcript(0)
        entry='QUANT_COMMON_ENTRY trial=1 map=0 status=0 selection=0 groups=1 commands=8 values=128'
        variants=[text.replace(CAP,'',1),text.replace(CAP,CAP+'\n'+CAP,1),
            text.replace(entry,'',1),text.replace(entry,entry+'\n'+entry,1),
            text.replace('workspace=4352','workspace=8192',1),
            text.replace('map_timed=1','map_timed=0',1),
            text.replace('admission_timed=1','admission_timed=0',1),
            text.replace('map=0','map=1',1),text.replace('status=0','status=1',1),
            text.replace('selection=0','selection=5',1),text.replace('groups=1','groups=0',1),
            text.replace('commands=8','commands=7',1),text.replace('values=128','values=127',1),
            text+'\n'+entry]
        for index,variant in enumerate(variants):
            with self.subTest(index=index),self.assertRaises(ValueError):
                check_log(variant,0,gold,rtl)

    def test_source_counts_admission_not_only_math(self):
        text=(HERE/'attention_common_main.c').read_text()
        timed=text.split('const uint64_t start=common_cycles();',1)[1].split('const uint64_t elapsed=',1)[0]
        self.assertIn('akv_quant_ggml_map(',timed)
        self.assertIn('akv_quant_native_execute(',timed)
        self.assertIn('akv_quant_online_head_major(',timed)
        self.assertIn('qbs_native_execute_command,NULL',text)
        self.assertNotIn('qbs_ref_execute',text)
        self.assertIn('"rdcycle %0" : "=r"(result) : : "memory"',text)

    def test_original_numerical_and_work_checks_are_not_bypassed(self):
        text,gold,rtl=self.transcript(0)
        for variant in (text.replace('hex=3f800000','hex=7fc00000',1),
                        text.replace('calls=8 ','calls=7 ',1),
                        text.replace('success=1','success=0',1),
                        text.replace('UVM_ERROR : 0','UVM_ERROR : 1',1)):
            with self.assertRaises(ValueError):
                check_log(variant,0,gold,rtl)
        with self.assertRaises(ValueError):
            check_log(text,0,bytes(6144),rtl)


if __name__=='__main__':
    unittest.main()
