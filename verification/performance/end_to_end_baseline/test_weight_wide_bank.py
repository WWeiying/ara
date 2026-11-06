"""Host-only independent checker tests; never launches or mocks an SRAM/DUT."""
from functools import lru_cache
from pathlib import Path
import unittest
from unittest.mock import patch

import run_weight_wide_bank as b


def line(tag,row):
    return tag+' '+' '.join(f'{k}={v}' for k,v in row.items())


@lru_cache(None)
def fixture():
    records=[line('WB_SUITE_BEGIN',dict(version=1)),line('WB_RESOURCE',b.RESOURCES)]
    normal=b.expected_profiles()
    records += [line('WB_PROFILE_PASS',dict(row,max_drain=2,unthrottled_stalls=0,mixed_stalls=1,side_mixed_stalls=1)) for row in normal]
    totals={k:sum(p[k] for p in normal) for k in ('packets','native','payload','side','reads','read_bytes','idle')}
    for p in b.PROFILES:
        for group in (0,1):
            for stage in (0,1):
                for reset in (0,1):
                    size=b.PROFILES[p][0];a=32 if group else min(32,size)
                    records.append(line('WB_ABORT_PASS',dict(profile=p,group=group,stage=stage,reset=reset,
                                                           packets=1,accepted=a,committed=0,discarded=a,outputs=stage)))
                    totals['packets']+=1;totals['native']+=a
                    rp,rn=p%9+1,p%4+1
                    records.append(line('WB_REUSE_PASS',dict(profile=rp,rows=rn,group=1-group,phase=(p*7+stage)%32)))
                    for k,v in b.epoch_counts(rp,rn,1-group,(p*7+stage)%32).items():totals[k]+=v
                    totals['reads']+=1;totals['read_bytes']+=rn*16*(1+int(b.PROFILES[rp][3]!=0))
    end=dict(cases=4608,reuse_cases=72,abort_cases=72,cancel_cases=72,accepted=totals.pop('native'),
             **totals,input_stalls=1,blocked_outputs=1,early_reads=1,max_drain=2,unthrottled_stalls=0,
             mixed_stalls=9,side_mixed_stalls=9)
    records.append(line('WB_BANK_COMPONENT_PASS',end))
    return '\n'.join(records)+'\n'


class BankCheckerTests(unittest.TestCase):
    def test_exact_full_sweep_counts(self):
        profiles=b.expected_profiles()
        self.assertEqual(sum(x['native'] for x in profiles),1044480)
        self.assertEqual(sum(x['payload'] for x in profiles),921600)
        self.assertEqual(sum(x['side'] for x in profiles),122880)
        self.assertEqual(sum(x['packets'] for x in profiles),40452)
        self.assertEqual(sum(x['reads'] for x in profiles),45056)
        self.assertEqual(sum(x['read_bytes'] for x in profiles),2785280)
        self.assertEqual(b.check(fixture())['totals']['cases'],4608)

    def test_old_word_half_addresses(self):
        self.assertEqual([b.word16(1,k,0) for k in range(0,256,16)],[0,1,0,1,2,3,2,3,4,5,4,5,6,7,6,7])
        self.assertEqual([b.word16(2,k,1) for k in range(0,256,16)],[0,1]*4+[2,3]*4)
        self.assertEqual([b.word16(5,k,0) for k in range(0,256,16)],[0,1]*4+[2,3]*4)
        self.assertEqual([b.word16(3,k,0) for k in (0,16)],[0,0])
        self.assertEqual([b.word16(6,k,0) for k in (0,16)],[0,1])

    def test_zero_exit_fatal_never_counts_as_normal_pass(self):
        for text in (fixture()+'Fatal: WB_UNTHROTTLED_II1\n',fixture()+'Error: compile failed\n',
                     fixture()+'Assertion test failed\n',fixture()+fixture()):
            with self.assertRaises(ValueError):b.check(text)

    def test_missing_profiles_bytes_hold_and_resource_rejected(self):
        text=fixture()
        for bad in (text.replace('profile=9 cases=512','profile=8 cases=512'),
                    text.replace('native=184320','native=184319'),text.replace('idle=1536','idle=0',1),
                    text.replace('logical_sram_bytes=768','logical_sram_bytes=2048'),
                    text.replace('target_sram_mc_physical_bytes=2048','target_sram_mc_physical_bytes=768'),
                    text.replace('WB_SUITE_BEGIN version=1\n','')):
            with self.assertRaises(ValueError):b.check(bad)

    def test_local_ii1_and_drain_are_hard_gates(self):
        for bad in (fixture().replace('unthrottled_stalls=0','unthrottled_stalls=1',1),
                    fixture().replace('max_drain=2','max_drain=4',1)):
            with self.assertRaises(ValueError):b.check(bad)

    def test_abort_counts_and_pending_output_required(self):
        text=fixture()
        for bad in (text.replace('outputs=1','outputs=0',1),text.replace('discarded=32','discarded=31',1),
                    text.replace('stage=0 reset=0 packets=1','stage=0 reset=0 packets=2',1),
                    text.replace('cancel_cases=72','cancel_cases=71')):
            with self.assertRaises(ValueError):b.check(bad)

    def test_mixed_target_stall_coverage_cannot_be_omitted(self):
        for bad in (fixture().replace('mixed_stalls=1','mixed_stalls=0'),
                    fixture().replace('mixed_stalls=9','mixed_stalls=0')):
            with self.assertRaises(ValueError):b.check(bad)

    def test_authorization_required_before_files_or_execution(self):
        for sha,authorized in ((b.DUT_SHA,False),('0'*64,True)):
            with self.assertRaises(ValueError):b.run(b.OUT,sha,authorized)
        with patch.object(b,'ownership',return_value=[]),patch.object(Path,'mkdir',side_effect=FileExistsError),\
             patch.object(b,'write_new') as write:
            with self.assertRaises(FileExistsError):b.run(b.OUT,b.DUT_SHA,True)
            write.assert_not_called()

    def test_no_pin_replacement_after_freeze(self):
        pins,path=b.Pins(),Path(__file__).resolve()
        with patch.object(b,'digest',side_effect=['a','b','b']):
            pins.pin(path)
            with self.assertRaises(ValueError):pins.pin(path)
            self.assertEqual(pins.values[str(path)],'a')
            with self.assertRaises(ValueError):pins.verify()


if __name__=='__main__':unittest.main()
