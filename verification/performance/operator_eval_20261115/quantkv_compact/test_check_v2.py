"""Architectural RVC-width regression; mock records are not simulation evidence."""
import csv
from pathlib import Path
import tempfile
import unittest
from contract import OUT
from check_v2 import roi,entry_instruction


class RvcTest(unittest.TestCase):
    def test_instruction_width(self):
        self.assertEqual(entry_instruction(dict(words={10:0xc5a1833a}),10),0x833a)
        self.assertEqual(entry_instruction(dict(words={10:0x00302e73}),10),0x00302e73)

    def test_compressed_entry_and_mutation(self):
        r=dict(elf_ranges=dict(quantkv_compare_bytes=[200,240],qbs_native_execute_command=[300,304],printf_=[400,404]),
               roi_marker_pcs=[100,112],roi_read_pcs=[104,108])
        parsed=dict(words={200:0x00302e73,300:0xc5a1833a,104:0xc00022f3,108:0xc0002373})
        rows=[dict(cycles=10,fcsr=1)]*4; records=[]
        def emit(pc,insn,value=0):
            records.append(dict(cycle=len(records)+1,event='retire',pc=f'{pc:x}',insn=f'{insn:x}',rd_wdata=f'{value:x}',trap='0'))
        def compare(fc,vc):
            emit(200,0x00302e73,fc)
            for i,(csr,value) in enumerate(((15,vc),(8,0),(3,fc),(15,vc),(8,0))):
                emit(204+i*4,(csr<<20)|0x22f3,value)
        compare(0,0)
        for t in range(4):
            emit(100,0xc0002073); emit(104,0xc00022f3,t*100+10)
            for _ in range(4): emit(300,0x833a)
            emit(108,0xc0002373,t*100+20); emit(112,0xc0002073); compare(1,5)
        out=Path(tempfile.mkdtemp(prefix='operator_quantkv_compact_prepare_20261115_rvc_host_',dir=OUT))
        p=out/'mock-commit.csv'
        def write():
            with p.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(records[0])); w.writeheader(); w.writerows(records)
        write(); self.assertEqual(roi(p,r,rows,parsed)['qbs_calls'],16)
        next(x for x in records if x['pc']==f'{300:x}')['insn']='832a'; write()
        with self.assertRaises(ValueError): roi(p,r,rows,parsed)


if __name__=='__main__': unittest.main()
