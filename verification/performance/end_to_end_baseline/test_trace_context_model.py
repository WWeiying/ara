import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from collections import Counter

from trace_context_model import fixture as model_fixture,check as check_model,SUITE,PROJECTIONS,call_schema
from test_output_model_check import fixture as control_fixture
from collect_trace_context_model import normalized_link


def fixture():
    layout='GGML_RISCV_QUANT_KV_LAYOUT selection=0 key_panels=16 key_bytes=44608 workspace=13120 k_token_stride=1088 k_head_stride=136'
    pv='GGML_RISCV_QUANT_KV_PV grouped=0 completed_groups=8'
    control=control_fixture().replace('prompt_tokens=41','prompt_tokens=40')
    control=control.replace('GGML_RISCV_QUANT_KV_OUTPUT_TILE ',layout+'\n'+pv+'\nGGML_RISCV_QUANT_KV_OUTPUT_TILE ')
    weights=[dict(tensor=f'blk.{layer}.{name}.weight',k=k,n=n,type='q6_K' if name in ('attn_v','ffn_down') else 'q4_K')
             for layer in range(28) for name,k,n in PROJECTIONS]
    weights.append(dict(tensor='output.weight',k=2048,n=151936,type='q6_K'))
    reference_work={};record=None
    for line in control.splitlines():
        if line=='OUTPUT_MODEL_BEGIN enabled=1':record=0
        elif line=='OUTPUT_MODEL_END enabled=1':record=None
        elif record is not None:
            if line.startswith('OUTPUT_MODEL_STEP '):record+=1
            elif line.startswith(('GGML_RISCV_QUANT_PREFILL ','GGML_RISCV_QUANT_KV ', 'GGML_RISCV_QUANT_KV_')):
                reference_work.setdefault(record,[]).append(line)
    lines=[]
    for variant in range(2):
        lines.extend([f'TRACE_CONTEXT_VARIANT_BEGIN variant={variant}','OUTPUT_MODEL_BEGIN enabled=1',
            'OUTPUT_MODEL_SHAPE model=qwen3_1p7b prompt_tokens=40 n_ctx=128 n_batch=64'])
        counters={}
        for kind in range(2):
            for step in range(2):
                lines.extend(reference_work[kind*3+step])
                for row in call_schema(weights,step):
                    lines.append('GGML_RISCV_QBS_CALL '+' '.join(f'{key}={v}' for key,v in row.items()))
                    profile=row['type'];mode=row['mode'];k=row['k'];m=row['input_rows'];n=row['output_rows']
                    counter=counters.setdefault(profile,Counter())
                    counter.update({mode+'_calls':1,'input_rows':m,'output_rows':n,'activation_elements':k*m,
                        'output_elements':m*n,'dot_elements':m*n*k,'commands_m1':n//32 if m==1 else 0,
                        'commands_m4':m//4*(n//32) if m>1 else 0})
                    if m==1 and k<=4096:counter.update(eligible_context_commands=n//32,eligible_context_calls=1)
                lines.append(f'OUTPUT_MODEL_STEP enabled=1 kind={kind} step={step} token=42 fcsr=9 vcsr=5 outputs=151936')
        lines.append('OUTPUT_MODEL_END enabled=1')
        for profile in ('q4_K','q6_K'):
            counted=counters[profile];m1=counted['commands_m1'];m4=counted['commands_m4'];dot=counted['dot_elements']
            public={k:v for k,v in counted.items() if not k.startswith('eligible_')}
            row=dict(type={'q4_K':'Q4_K','q6_K':'Q6_K'}[profile],**public,split_calls=0,native_qbexec=m1+m4,emulated_commands=0,
                segmented_commands=0,command_dot_elements=dot,context_fill=1,
                context_reuse=counted['eligible_context_commands']-2,context_release=1)
            for m in range(1,9):row[f'commands_m{m}']=m1 if m==1 else m4 if m==4 else 0
            lines.append(f'GGML_RISCV_QBS_COVERAGE type={row["type"]} candidate_tensors=100 selected_tensors=100 candidate_elements=1000 selected_elements=1000')
            lines.append('GGML_RISCV_QBS_EXEC '+' '.join(f'{key}={v}' for key,v in row.items()))
        lines.append(f'TRACE_CONTEXT_VARIANT_END variant={variant}')
    lines.extend(f'TRACE_CONTEXT_COMPARE kind={k} step={s} outputs=151936 bitwise=1 csr_equal=1 token_equal=1'
                 for k in range(2) for s in range(2))
    return '\n'.join(lines+[SUITE,'GUEST_TEST_EXIT=0']),control,weights


def check(text,control,weights):
    return check_model(text,control,weights)


class TraceContextModelTests(unittest.TestCase):
    def test_complete_model_pair(self):
        result=check(*fixture())
        self.assertEqual(result['logits_compared'],607744)
        self.assertEqual(result['native_work_per_variant']['qbs'],788)
        self.assertFalse(result['performance_measured'])

    def test_reject_wrong_results_routes_counts_and_native_summary(self):
        text,control,weights=fixture()
        for old,new in (('token=42','token=43'),('vcsr=5','vcsr=3'),('enabled=1 status=0','enabled=0 status=0'),
            ('status=0 mapping=0','status=1 mapping=0'),('emulated_commands=0','emulated_commands=1'),
            ('split_k=0','split_k=1'),('bitwise=1','bitwise=0'),
            ('variants=2 comparisons=4','variants=1 comparisons=4'),('GUEST_TEST_EXIT=0','GUEST_TEST_EXIT=1')):
            self.assertIn(old,text)
            with self.subTest(old=old),self.assertRaises(ValueError):check(text.replace(old,new,1),control,weights)

    def test_missing_variant_and_step_rejected(self):
        text,control,weights=fixture()
        for prefix in ('TRACE_CONTEXT_VARIANT_END variant=0','OUTPUT_MODEL_STEP enabled=1 kind=0 step=0',
                       'GGML_RISCV_QBS_CALL ','GGML_RISCV_QUANT_KV_OUTPUT_TILE '):
            line=next(s for s in text.splitlines() if s.startswith(prefix))
            with self.subTest(prefix=prefix),self.assertRaises(ValueError):check(text.replace(line+'\n','',1),control,weights)

    def test_shared_wrong_work_cannot_pass(self):
        text,control,weights=fixture()
        for old,new,reason in (('input_rows=40','input_rows=1','Projection differs from sealed'),
            ('mode=gemv','mode=gemm','Projection differs from sealed'),
            ('context_fill=1','context_fill=999999999','Context counts do not match'),
            ('key_bytes=44608','key_bytes=40000','Attention work differs from accepted control'),
            ('grouped=0','grouped=1','PV route')):
            with self.subTest(old=old),self.assertRaisesRegex(ValueError,reason):check(text.replace(old,new),control,weights)

    def test_profile_and_mode_summary_cannot_be_reassigned(self):
        text,control,weights=fixture();lines=text.splitlines()
        for i,line in enumerate(lines):
            if line.startswith('GGML_RISCV_QBS_EXEC '):
                fields=dict(word.split('=',1) for word in line.split()[1:])
                fields['gemv_calls']='788' if fields['type']=='Q6_K' else '0';fields['gemm_calls']='0'
                lines[i]='GGML_RISCV_QBS_EXEC '+' '.join(f'{k}={v}' for k,v in fields.items())
        with self.assertRaisesRegex(ValueError,'Profile/mode summary differs'):
            check('\n'.join(lines),control,weights)

    def test_generated_model_preserves_algorithm_and_turns_on_only_aggregate_trace(self):
        model=Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/e2e_output_model_20261106_01/model.cpp')
        if not model.is_file():self.skipTest('Sealed model fixture unavailable')
        source=model.read_text();after=model_fixture(source)
        self.assertIn('step < 2',after);self.assertIn('generate(1, argv[1])',after)
        self.assertIn('env("GGML_RISCV_QBS_TRACE", "1")',after)
        self.assertIn('env("GGML_RISCV_QBS_TRACE_LIFETIME", "0")',after)
        self.assertIn('llama_decode(ctx, llama_batch_get_one(input.data(), input.size()))',after)
        with self.assertRaises(ValueError):model_fixture(after)

    def test_link_comparison_allows_only_the_archive_and_output_change(self):
        root=Path('/model-run');a=Path('/old/libggml-cpu.a');b=Path('/new/libggml-cpu.a')
        base=['/compiler','-static',str(root/'model.o'),str(a),'/shared/libllama.a','-o',str(root/'base')]
        new=['/compiler','-static',str(root/'model.o'),str(b),'/shared/libllama.a','-o',str(root/'candidate')]
        self.assertEqual(normalized_link(base,root,a),normalized_link(new,root,b))
        changed=list(new);changed[1]='-shared'
        self.assertNotEqual(normalized_link(base,root,a),normalized_link(changed,root,b))
        with self.assertRaises(ValueError):normalized_link(base+[str(a)],root,a)


@unittest.skipUnless(shutil.which('g++'),'host C++ unavailable')
class FullLogitDriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        source=Path(__file__).with_name('trace_context_model_driver.cpp')
        subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',str(source),'-o',str(cls.root/'driver')],
                       check=True,capture_output=True,timeout=60)
        logits=struct.pack('<f',1.)*151936
        cls.payload=struct.pack('<I',151936)+b''.join(struct.pack('<iQQ',42,9,3)+logits for _ in range(4))
        assert len(cls.payload)==2431060

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def execute(self,a,b):
        (self.root/'a').write_bytes(a);(self.root/'b').write_bytes(b)
        return subprocess.run([str(self.root/'driver'),'--compare-only',str(self.root/'a'),str(self.root/'b')],
                              capture_output=True,text=True,timeout=30)

    def test_all_logits_compared(self):
        result=self.execute(self.payload,self.payload)
        self.assertEqual(result.returncode,0);self.assertIn(SUITE,result.stdout)
        changed=bytearray(self.payload);changed[-1]^=1
        result=self.execute(self.payload,changed)
        self.assertNotEqual(result.returncode,0);self.assertIn('reason=paired_logits',result.stderr)

    def test_csr_nonfinite_truncation_and_extra_bytes_rejected(self):
        changed=bytearray(self.payload);struct.pack_into('<Q',changed,8,8)
        nan=bytearray(self.payload);struct.pack_into('<f',nan,24,math.nan)
        for a,b in ((self.payload,changed),(nan,nan),(self.payload,self.payload[:-1]),(self.payload,self.payload+b'x')):
            with self.subTest(size=len(b)):
                result=self.execute(a,b);self.assertNotEqual(result.returncode,0);self.assertNotIn(SUITE,result.stdout)


if __name__=='__main__':unittest.main()
