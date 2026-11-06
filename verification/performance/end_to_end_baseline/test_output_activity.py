import unittest
from collect_output_native import activity,PHASES


def fixture(q4=True):
    lines=[]
    for trial,candidate in enumerate((0,1,1,0)):
        fields=dict(seq=trial+1,m=2,n=20,vlen=1024,lanes=4,success=1,fault=0,
                    validation_fault=0,read_fault=0,weight_bytes=1440 if q4 else 2720,
                    activation_bytes=272,useful_pairs=5120,busy_cycles=10)
        fields.update({'phase_'+name+'_cycles':1 for name in PHASES})
        lines.extend([f'OUTPUT_NATIVE_BEGIN trial={trial} candidate={candidate}',
                      '[QBS_PERF] '+' '.join(f'{k}={v}' for k,v in fields.items()),
                      f'OUTPUT_NATIVE_RESULT trial={trial} candidate={candidate}'])
    return '\n'.join(lines)


class ActivityTests(unittest.TestCase):
    def test_both_formats(self):
        for q4 in (0,1):self.assertEqual(len(activity(fixture(q4),q4)),4)

    def test_missing_or_changed_work(self):
        for old,new in (('m=2','m=4'),('seq=1','seq=2'),('success=1','success=0'),
                        ('phase_overlap_cycles=1','phase_overlap_cycles=0'),
                        ('useful_pairs=5120','useful_pairs=10240')):
            with self.subTest(old=old),self.assertRaises(ValueError):
                activity(fixture().replace(old,new,1),True)

    def test_duplicate_command(self):
        text=fixture();line=next(x for x in text.splitlines() if x.startswith('[QBS_PERF]'))
        with self.assertRaises(ValueError):activity(text.replace(line,line+'\n'+line,1),True)

    def test_incomplete(self):
        with self.assertRaises(ValueError):activity('\n'.join(fixture().splitlines()[:-1]),True)
