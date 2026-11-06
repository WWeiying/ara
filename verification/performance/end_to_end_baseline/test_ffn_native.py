import unittest
import copy

from check_ffn_native import check, SCOPE
from check_projection_native import checksum
from collect_projection_native import PHASES
from collect_ffn_native import compare


def fixture(wide):
    golden = [bytes([i+1])*2048 for i in range(3)]
    packed = [bytes([4])*9344,bytes([5])*28032]
    profiles = [1,1,2]; flags = [1,1,1]; lines = [SCOPE]
    for stage,k in enumerate((2048,6144)):
        lines.append(f'FFN_NATIVE_PREP stage={stage} k={k} cycles=100 fcsr=9 valid=1 checksum={checksum(packed[stage])}')
    executions = []
    for part,k in enumerate((2048,2048,6144)):
        blocks = k//256; dot = blocks*(512 if wide else 1024)
        execution = 4*(dot+100)+200; executions.append(execution)
        lines.append(f'FFN_NATIVE_PART part={part} profile={profiles[part]} k={k} admission=10 execution={execution} '
                     f'fcsr=9 vcsr=5 checksum={checksum(golden[part])} errors=0')
        for j in range(4):
            row = dict(seq=4*part+j+1,m=4,n=32,vlen=1024,lanes=4,success=1,fault=0,validation_fault=0,read_fault=0,
                       useful_pairs=32768*blocks,dot_active_cycles=dot,activation_access=0,
                       activation_bytes=1168*blocks,weight_bytes=32*blocks*(144 if part<2 else 210),busy_cycles=dot+100)
            for i,p in enumerate(PHASES): row['phase_'+p+'_cycles'] = dot+100 if i == 0 else 0
            lines.append('[QBS_PERF] '+' '.join(f'{key}={value}' for key,value in row.items()))
    lines.append(f'FFN_NATIVE_RESULT preparation=200 admission=30 execution={sum(executions)} '
                 f'region={sum(executions)+300} commands=12 outputs=1536 errors=0')
    return '\n'.join(lines),golden,packed,profiles,flags


class FFNNativeTests(unittest.TestCase):
    def test_both_images_same_work(self):
        a = fixture(0); b = fixture(1)
        original = check(a[0],0,*a[1:]); candidate = check(b[0],1,*b[1:])
        self.assertEqual(original['dot_issue_count'],2*candidate['dot_issue_count'])
        self.assertEqual(original['useful_pairs'],5242880)
        self.assertFalse(candidate['full_n'])

    def test_output_flags_work_and_tail_rejected(self):
        data = fixture(1); text = data[0]
        for old,new in (('outputs=1536','outputs=1024'),('k=6144','k=2048'),('fcsr=9','fcsr=8'),
                        ('errors=0','errors=1'),('commands=12','commands=11'),('useful_pairs=262144','useful_pairs=131072')):
            with self.assertRaises(ValueError): check(text.replace(old,new,1),1,*data[1:])

    def test_extra_or_missing_command_rejected(self):
        data = fixture(0); text = data[0]
        command = next(line for line in text.splitlines() if line.startswith('[QBS_PERF] '))
        with self.assertRaises(ValueError): check(text+'\n'+command,0,*data[1:])
        with self.assertRaises(ValueError): check(text.replace(command,'',1),0,*data[1:])

    def test_wrong_oracle_cannot_pass_signature(self):
        data = fixture(0); data[1][0] = b'x'*2048
        with self.assertRaises(ValueError): check(data[0],0,*data[1:])

    def test_pair_preserves_work_without_assuming_identical_prep_timing(self):
        reports = []
        keys = ('payload_bytes','weight_bytes','activation_bytes','useful_pairs','fp_uop_issue','accumulator_updates')
        for wide in (0,1):
            data = fixture(wide)
            reports.append(dict(wide=wide,build='same',elf_sha256='same',measured=check(data[0],wide,*data[1:]),
                                activity=[dict(counters={key:1 for key in keys}) for _ in range(3)]))
        self.assertGreater(compare(*reports)['region_ratio'],1)
        changed = copy.deepcopy(reports)
        changed[1]['measured']['preparation'][1]['cycles'] += 10
        changed[1]['measured']['total']['preparation'] += 10
        changed[1]['measured']['total']['region'] += 10
        self.assertNotEqual(compare(*changed)['preparation_cycles'][0],compare(*changed)['preparation_cycles'][1])
        changed[1]['activity'][0]['counters']['weight_bytes'] += 1
        with self.assertRaises(ValueError): compare(*changed)


if __name__ == '__main__': unittest.main()
