import copy
import importlib.util
import io
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('abba_analysis_tested',HERE/'analyze.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
spec=importlib.util.spec_from_file_location('existing_retirement_fixtures',
    a.ROOT/'verification/akv/quantized_kv/phase_diagnostic/analysis/test_analyze.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)


class Attribution(unittest.TestCase):
    def setUp(self):
        binary,text=fixture.fixture_elf()
        self.code=a.base.disassembly_map(text,a.base.LinkedELF(binary))
        self.trials=[dict(trial=i,enabled=mode,cycles=100*(i+1)) for i,mode in enumerate((0,1,1,0))]
        self.rows=[]
        for i in range(4):
            pcs=[0x1000,0x1008,0x1100,0x1104,0x1200]+[0x1300,0x1304]*4+[0x1004]
            for pc in pcs:
                row=dict.fromkeys(a.base.COMMIT_HEADER,0)
                row.update(event='retire',cycle=10+len(self.rows)*2,order=len(self.rows),port=0,trans_id=-1,
                    pc=pc,insn=self.code[pc]['bits'])
                if pc in (0x1000,0x1004):
                    row.update(rd=self.code[pc]['bits']>>7&31,rd_wdata=i*1000+(100*(i+1) if pc==0x1004 else 0))
                self.rows.append(row)
    def check(self,rows=None):
        return a.analyze(self.code,io.StringIO(fixture.csv_text(self.rows if rows is None else rows)),
                         self.trials,[0x1000,0x1004],a.phase_map(self.code))
    def test_complete_accounting(self):
        result=self.check();self.assertEqual(len(result['windows']),4)
        self.assertFalse(result['hardware_utilization_claimed'])
        for row in result['windows']:
            self.assertEqual(row['instructions'],12)
            self.assertEqual(sum(row['pc_gaps'].values())+row['end_csr_gap_cycles'],row['monitor_retire_span'])
            self.assertNotEqual(row['monitor_retire_span'],row['csr_cycles'])
    def test_incomplete_or_reordered(self):
        for rows in (self.rows[:-1],self.rows[:5]+self.rows[6:],list(reversed(self.rows))):
            with self.assertRaises(ValueError):self.check(rows)
    def test_bad_instruction_trap_and_timer(self):
        for key,value in (('insn',0),('trap',1),('cycle',0)):
            rows=copy.deepcopy(self.rows);rows[2][key]=value
            with self.subTest(field=key),self.assertRaises(ValueError):self.check(rows)
        rows=copy.deepcopy(self.rows);rows[-1]['rd_wdata']+=1
        with self.assertRaises(ValueError):self.check(rows)
    def test_native_work_not_just_command_count(self):
        rows=copy.deepcopy(self.rows);rows[5]['pc']=0x1304;rows[5]['insn']=self.code[0x1304]['bits']
        with self.assertRaises(ValueError):self.check(rows)
    def test_disallow_wrong_call_order(self):
        self.trials[2]['enabled']=0
        with self.assertRaises(ValueError):self.check()


if __name__=='__main__':unittest.main()
