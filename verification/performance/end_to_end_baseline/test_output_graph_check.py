import unittest
from check_output_graph import PROFILES,check


def fixture():
    lines=[]
    for name,(h,kv,t,n,commands,values) in PROFILES.items():
        for trial in range(3):
            candidate=int(trial!=0)
            lines += [f'OUTPUT_GRAPH_BEGIN name={name} candidate={candidate} repeat={trial}',
                f'GGML_RISCV_QUANT_KV status=0 mapping=0 memory=1 runtime_called=1 command_attempts={commands} groups={kv} value_decodes={values} executor_status=0',
                f'GGML_RISCV_QUANT_KV_REGISTER_PV enabled={1-candidate} status=0 completed_groups={kv}',
                f'GGML_RISCV_QUANT_KV_OUTPUT_TILE enabled={candidate} status=0 completed_groups={kv}',
                f'OUTPUT_GRAPH_END name={name} candidate={candidate} repeat={trial} flags=9 max_abs=0.000001']
        lines.append(f'OUTPUT_GRAPH_PROFILE_PASS name={name} heads={h} kv={kv} visible={t} outputs={n} native_calls=3 rejected=2 exact=1 inputs_unchanged=1')
    return '\n'.join(lines+['OUTPUT_GRAPH_SUITE_PASS profiles=4 native_calls=12 fallback_calls=8','GUEST_TEST_EXIT=0'])


class GraphTraceTests(unittest.TestCase):
    def test_complete(self):self.assertEqual(check(fixture())['native_commands'],144)
    def test_rejects_wrong_route_and_missing_work(self):
        for old,new in (('OUTPUT_TILE enabled=1','OUTPUT_TILE enabled=0'),
                        ('command_attempts=16','command_attempts=0'),('groups=8','groups=0'),
                        ('flags=9','flags=1'),('repeat=2','repeat=1'),('GUEST_TEST_EXIT=0','GUEST_TEST_EXIT=1')):
            with self.subTest(old=old),self.assertRaises(ValueError):check(fixture().replace(old,new,1))
    def test_rejects_missing_trace(self):
        text='\n'.join(l for l in fixture().splitlines() if not l.startswith('GGML_RISCV_QUANT_KV_OUTPUT_TILE'))
        with self.assertRaises(ValueError):check(text)
    def test_rejects_extra_outside_call(self):
        with self.assertRaises(ValueError):check(fixture()+'\nGGML_RISCV_QUANT_KV status=0')
