import unittest

from check_rms_norm import check,check_activity,SCOPE,ORDER
from check_projection_native import checksum


def fixture():
    prefill=bytes(32768);decode=bytes(8192);lines=[SCOPE]
    for rows,golden in ((1,decode),(4,prefill)):
        for trial,candidate in enumerate(ORDER):
            lines.append(f'RMS_NORM_TRIAL rows={rows} trial={trial} candidate={candidate} cycles={200 if candidate else 100} '
                         f'fcsr=9 vcsr=5 vstart=0 checksum={checksum(golden)} errors=0')
    lines.append('RMS_NORM_RESULT trials=8 outputs_checked=40960 boundary_cases=53 sum_cases=10 errors=0')
    return '\n'.join(lines),prefill,decode


class RMSNormCheckTests(unittest.TestCase):
    def test_slower_candidate_is_not_hidden(self):
        r=check(*fixture())
        self.assertEqual([v['call_speedup'] for v in r['cases']],[0.5,0.5])
        self.assertFalse(r['whole_model'])

    def test_reject_incomplete_or_wrong_data_state(self):
        text,p,d=fixture()
        for a,b in (('rows=1 trial=1 candidate=1','rows=1 trial=1 candidate=0'),('fcsr=9','fcsr=8'),
                    ('vcsr=5','vcsr=0'),('vstart=0','vstart=1'),('errors=0','errors=1'),
                    ('boundary_cases=53','boundary_cases=52'),('cycles=200','cycles=0')):
            with self.subTest(a=a),self.assertRaises(ValueError):check(text.replace(a,b,1),p,d)
        with self.assertRaises(ValueError):check(text,p[:-1],d)

    def test_actual_reduction_work_is_required(self):
        header='cycle,event,arch_seq,insn,vl,vstart,nr_lanes,vlen_bits\n'
        insn=(0b110011<<26)|(1<<25)|(1<<12)|0x57
        trace=header+'0,config,0,00000000,0,0,4,1024\n'+''.join(
            f'{i},alloc,{i},{insn:08x},128,0,4,1024\n' for i in range(288))
        self.assertEqual(check_activity(trace)['ordered_widening_reduction_allocations'],288)
        for altered in (trace.rsplit('\n',2)[0]+'\n',trace.replace('128,0,4,1024','0,0,4,1024',1),
                        trace.replace('config,0,00000000,0,0,4,1024','config,0,00000000,0,0,4,512')):
            with self.assertRaises(ValueError):check_activity(altered)


if __name__=='__main__':unittest.main()
