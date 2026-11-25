import importlib.util
import json
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('rvv_activity_test',HERE/'audit_rvv_activity.py')
a=importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class ActivityTests(unittest.TestCase):
    def test_attention_full_real_outputs_and_mutations(self):
        build=a.OUT/'power_attention_prepare_20261117_rvv_01'
        m=json.loads((build/'build.json').read_text())
        text=(a.CAMPAIGN/'runs/power_attention_rvv/run.vcs.log').read_text()
        result=a.attention_numeric(text,m,build)
        self.assertEqual(result['finite_outputs'],512)
        self.assertEqual([r['bitwise_differences'] for r in result['trials']],[125,125])
        for old,new in (('vstart=0','vstart=1'),('fcsr=11','fcsr=9'),('errors=125','errors=124'),
                        ('model_errors=0','model_errors=1'),('guard_bytes=10344','guard_bytes=0'),
                        ('tokens=137','tokens=136')):
            with self.subTest(old=old),self.assertRaises(ValueError):
                a.attention_numeric(text.replace(old,new,1),m,build)
        lines=text.splitlines()
        target=next(i for i,l in enumerate(lines) if l.startswith('OP_ATTN_OUT trial=0 index=255 '))
        lines[target]='OP_ATTN_OUT trial=0 index=255 bits=7f800000'
        with self.assertRaises(ValueError):a.attention_numeric('\n'.join(lines),m,build)

    def test_m1_real_comparator_and_guard_flag_mutations(self):
        build=a.OUT/'operator_projection_real_prepare_20261115_release_01/cases/qwen3_real_decode_attn_q_m1_n64_rvv_x32'
        m=json.loads((build/'build.json').read_text())
        text=(a.CAMPAIGN/'runs/qwen3_real_decode_attn_q_m1_n64_rvv_x32/run.vcs.log').read_text()
        result=a.m1_numeric(text,m)
        self.assertEqual(result['finite_outputs'],128)
        for old,new in (('vcsr=2','vcsr=0'),('vstart=0','vstart=1'),('status=0','status=1'),
                        ('errors=4','errors=0'),('count=64 mismatches=0','count=64 mismatches=1'),
                        ('count=640 mismatches=0','count=640 mismatches=1')):
            with self.subTest(old=old),self.assertRaises(ValueError):
                a.m1_numeric(text.replace(old,new,1),m)


if __name__=='__main__':unittest.main()
