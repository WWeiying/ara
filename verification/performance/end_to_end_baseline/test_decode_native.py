import unittest

from check_decode_native import check, SCOPE, K, PROFILE, ACCESS, CONTEXT_COUNTERS
from check_projection_native import checksum
from collect_projection_native import PHASES, COUNTERS
from diagnose_projection_pair import WAIT


def fixture():
    golden=[bytes([p+1])*512 for p in range(7)]
    packed=[bytes([i+1])*size for i,size in enumerate((2336,2336,7008,2336))]
    flags=[1]*7;lines=[SCOPE];executions=[]
    for stage,k in enumerate((2048,2048,6144,2048)):
        lines.append(f'DECODE_NATIVE_PREP stage={stage} k={k} cycles=100 before_fcsr={8 if stage==0 else 9} '
            f'fcsr=9 vcsr=3 vstart=0 checksum={checksum(packed[stage])}')
    for part,k in enumerate(K):
        blocks=k//256;weight=32*blocks*(144 if PROFILE[part]==1 else 210)
        beat_counts=[(16+weight+(0 if a in (2,3) else blocks*292)+15)//16 for a in ACCESS[part]]
        execution=sum(max(k,b)+100 for b in beat_counts)+200;executions.append(execution)
        lines.append(f'DECODE_NATIVE_PART part={part} profile={PROFILE[part]} k={k} context={int(part!=5)} '
            f'scope={(1,2,3,1,3,0,0)[part]} admission=10 execution={execution} admitted=0 status=0 '
            f'fcsr=9 vcsr=3 vstart=0 checksum={checksum(golden[part])} errors=0')
        for tile in range(4):
            access=ACCESS[part][tile];reused=int(access in (2,3));blocks=k//256;activation=blocks*292
            weight=32*blocks*(144 if PROFILE[part]==1 else 210)
            c=dict.fromkeys((*COUNTERS,*WAIT,*CONTEXT_COUNTERS),0)
            c.update(seq=part*4+tile+1,m=1,n=32,vlen=1024,lanes=4,success=1,fault=0,validation_fault=0,read_fault=0,
                busy_cycles=max(k,beat_counts[tile])+100,ar=1,r_beats=beat_counts[tile],
                useful_pairs=8192*blocks,dot_active_cycles=256*blocks,activation_access=access,
                activation_bytes=activation,weight_bytes=weight,payload_bytes=16+weight+(0 if reused else activation),
                context_fill_count=int(access==1),context_reuse_count=reused,context_reuse_block_count=blocks if reused else 0,
                context_read_bytes=activation if reused else 0,activation_axi_bytes_saved=activation if reused else 0)
            for i,p in enumerate(PHASES):c['phase_'+p+'_cycles']=c['busy_cycles'] if i==0 else 0
            lines.append('[QBS_PERF] '+' '.join(f'{key}={value}' for key,value in c.items()))
    lines.append(f'DECODE_NATIVE_RESULT preparation=400 admission=70 execution={sum(executions)} '
        f'region={sum(executions)+500} commands=28 outputs=896 errors=0')
    return '\n'.join(lines),golden,packed,list(PROFILE),flags


class DecodeNativeTests(unittest.TestCase):
    def test_full_work_and_existing_reuse(self):
        data=fixture();result=check(*data)
        self.assertEqual(result['useful_pairs'],2359296)
        self.assertEqual(result['dot_issue_count'],73728)
        self.assertEqual(sum(a['counters']['context_fill_count'] for a in result['activity']),3)
        self.assertEqual(sum(a['counters']['context_reuse_count'] for a in result['activity']),21)
        self.assertEqual(result['activity'][5]['activation_axi_payload_bytes'],4*7008)
        self.assertFalse(result['whole_model'])

    def test_reject_weakened_context_csr_and_missing_work(self):
        data=fixture();text=data[0]
        for old,new in (('context=1','context=0'),('scope=2','scope=0'),('activation_access=2','activation_access=0'),
            ('context_read_bytes=2336','context_read_bytes=0'),('vcsr=3','vcsr=5'),('vstart=0','vstart=1'),
            ('commands=28','commands=27'),('outputs=896','outputs=768'),('errors=0','errors=1'),
            ('payload_bytes=36880','payload_bytes=39216')):
            self.assertIn(old,text)
            with self.subTest(old=old),self.assertRaises(ValueError):check(text.replace(old,new,1),*data[1:])

    def test_reject_bad_oracle_and_extra_command(self):
        data=fixture();text=data[0]
        data[1][0]=bytes(512)
        with self.assertRaises(ValueError):check(*data)
        data=fixture();command=next(s for s in text.splitlines() if s.startswith('[QBS_PERF] '))
        with self.assertRaises(ValueError):check(text+'\n'+command,*data[1:])
        with self.assertRaises(ValueError):check(text.replace(command,'',1),*data[1:])

    def test_compute_intake_is_not_axi_traffic(self):
        data=fixture();result=check(*data)
        reused=result['activity'][1]
        self.assertEqual(reused['counters']['activation_bytes'],4*2336)
        self.assertEqual(reused['activation_axi_payload_bytes'],0)
        self.assertEqual(reused['counters']['context_read_bytes'],4*2336)


if __name__ == '__main__':unittest.main()
