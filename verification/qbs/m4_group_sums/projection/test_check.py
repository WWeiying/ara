import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('qkv_slice_checker',Path(__file__).with_name('check.py'))
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)


class SliceTest(unittest.TestCase):
    def log(self,functional=False):
        rows=['M4_SUMS_QKV_SCOPE reuse_both=1 cold_producer_only=1']
        for i in range(4):
            r=int(i in (1,2))
            rows.append(f'M4_SUMS_QKV_TRIAL id={i} candidate={r} admit=10 prep=20 execute=30 total=70 '
                        f'hits=2 misses=1 stores=1 fcsr=17 vcsr=5 errors=0')
        prefix='M4_SUMS_QKV_FUNCTIONAL_RESULT' if functional else 'M4_SUMS_QKV_RESULT'
        return '\n'.join(rows+[prefix+' errors=0 trials=4 m=4 k=1536 outputs=8192 commands=256'])
    def test_timing(self):
        self.assertEqual(checker.check_output(self.log())['speedup'],1)
    def test_functional_cannot_be_timing(self):
        with self.assertRaises(ValueError):checker.check_output(self.log(True))
        r=checker.check_output(self.log(True),timed=False)
        self.assertNotIn('total',r['trials'][0]);self.assertNotIn('speedup',r)
    def test_bad_results(self):
        for a,b in [('hits=2','hits=1'),('fcsr=17','fcsr=1'),('vcsr=5','vcsr=0'),('total=70','total=1'),('errors=0','errors=1')]:
            with self.subTest(change=a),self.assertRaises(ValueError):checker.check_output(self.log().replace(a,b,1))
    def test_native_bytes(self):
        header='cycle,event,arch_seq,vid,lane,source,insn,use_vd,vd,eew,vl,vstart,addr,be,wdata,nr_lanes,vlen_bits\n'
        rows=['0,config,0,0,0,0,00000000,0,0,0,0,0,0,00,0,4,1024\n']
        for seq in range(256):
            rows.append(f'1,alloc,{seq},0,0,0,06b5045b,1,8,2,128,0,0,00,0,4,1024\n')
            for lane in range(4):
                for address in range(32,48):
                    rows.append(f'2,write,{seq},0,{lane},0,06b5045b,1,8,2,128,0,{address},ff,0,4,1024\n')
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'trace.csv';path.write_text(header+''.join(rows))
            self.assertEqual(checker.check_trace(path),dict(commands=256,result_bytes=131072))
            path.write_text(header+''.join(rows[:-1]))
            with self.assertRaises(ValueError):checker.check_trace(path)


if __name__=='__main__':unittest.main()
