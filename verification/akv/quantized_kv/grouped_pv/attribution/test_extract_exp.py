import copy
import importlib.util
import io
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('extract_exp_tested',Path(__file__).with_name('extract_exp.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class Extraction(unittest.TestCase):
    def setUp(self):
        self.code={pc:dict(bits=bits,mnemonic=name,function=function) for pc,bits,name,function in
            ((0x1000,0xc0002573,'rdcycle','main'),(0x1004,0xc00025f3,'rdcycle','main'),
             (0x1100,0x08f57553,'fsub.s','caller'),(0x1104,0x00a52027,'fsw','caller'),
             (0x1200,0xff010113,'addi','expf'),(0x1204,0x20948553,'fmv.s','expf'),
             (0x1208,0x8082,'ret','expf'))}
        self.args={0x1000:'a0',0x1004:'a1',0x1100:'fa0,fa0,fa5',0x1104:'fa0,0(a0)',
                   0x1200:'sp,sp,-16',0x1204:'fa0,fs1',0x1208:''}
        self.rows=[];self.windows=[]
        def row(pc,rd=0,value=0):
            entry=dict.fromkeys(module.analysis.base.COMMIT_HEADER,0)
            entry.update(event='retire',order=len(self.rows),cycle=10+len(self.rows),port=0,trans_id=-1,
                         pc=pc,insn=self.code[pc]['bits'],rd=rd,rd_wdata=value)
            self.rows.append(entry)
        for trial in range(4):
            start=len(self.rows);row(0x1000)
            for bits in (0xbf800000,0xc0000000):
                row(0x1100,10,0xffffffff00000000|bits)
                row(0x1104,0,0)  # FP store must not overwrite tracked fa0.
                row(0x1200);row(0x1204,10,0xffffffff3f000000);row(0x1208)
            end=len(self.rows);row(0x1004)
            self.windows.append(dict(start=dict(order=start),end=dict(order=end)))
    def run_extract(self,rows=None,args=None):
        source=self.rows if rows is None else rows
        fields=module.analysis.base.COMMIT_HEADER;hex_fields=module.analysis.base.csv_module.HEX_FIELDS
        text=','.join(fields)+'\n'+'\n'.join(','.join(
            f'{r[k]:x}' if k in hex_fields else str(r[k]) for k in fields) for r in source)+'\n'
        return module.extract(self.code,self.args if args is None else args,io.StringIO(text),0x1200,self.windows,2)
    def test_real_abi_values_and_store_read(self):
        result=self.run_extract();self.assertEqual(len(result),4)
        self.assertEqual(result[0][0]['input_bits'],'bf800000')
        self.assertEqual(result[0][0]['output_bits'],'3f000000')
    def test_missing_argument_rejected(self):
        args=dict(self.args);args[0x1100]='fs0,fa0,fa5'
        with self.assertRaises(ValueError):self.run_extract(args=args)
    def test_bad_boxing_rejected(self):
        rows=copy.deepcopy(self.rows);rows[1]['rd_wdata']=0xbf800000
        with self.assertRaises(ValueError):self.run_extract(rows)
    def test_missing_return_and_cross_trial_mismatch(self):
        with self.assertRaises(ValueError):self.run_extract(self.rows[:-2])
        rows=copy.deepcopy(self.rows);rows[-3]['rd_wdata']=0xffffffff3e800000
        with self.assertRaises(ValueError):self.run_extract(rows)


if __name__=='__main__':unittest.main()
