"""Bounded policy/recipe/negative host checks, not model execution."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run as r
import check as c


class ExecutionTests(unittest.TestCase):
    def test_default_deny_header(self):
        h,text=r.header({'case':'x'},False,'/model/x')
        self.assertEqual(len(h),64);self.assertIn('STAGE5_PROVIDER_ENABLED 0',text)
        self.assertNotEqual(h,r.header({'case':'y'},False,'/model/x')[0])
    def test_frozen_frontend_preserved_except_drains(self):
        old=(r.BINDING/'inputs/model_pair.cpp').read_text();new=r.frontend(old)
        self.assertEqual(new.count('tcdrain(STDOUT_FILENO)'),2)
        self.assertIn('std::memcmp(va.data(), vb.data(), na * sizeof(float))',new)
        with self.assertRaises(ValueError):r.frontend(old.replace('binding_snapshot(mode, step, "before");',''))
    def test_s3_missing_never_imported(self):
        with patch.object(r,'load') as load:
            with self.assertRaises(ValueError):r.checked_s3('/nonexistent',None,'/nonexistent','0'*64)
            load.assert_not_called()
    def test_recorded_s3_json_roundtrip_retains_every_field(self):
        generated={'work':{'lanes':{0:{'qk':3},1:{'qk':3}}},'extra':False}
        recorded=json.loads(json.dumps(generated,allow_nan=False))
        self.assertEqual(r.canonical(generated),r.canonical(recorded))
        recorded['work']['lanes']['0']['qk']=4
        self.assertNotEqual(r.canonical(generated),r.canonical(recorded))
        del recorded['extra']
        self.assertNotEqual(r.canonical(generated),r.canonical(recorded))
    def test_symbols_require_all_real_kernels(self):
        source='\n'.join(f'{i*256:x} 40 T {n}' for i,n in enumerate(r.SYMBOLS,1))
        self.assertEqual(len(r.symbols(source)),4)
        with self.assertRaises(ValueError):r.symbols(source+'\n'+source)
        with self.assertRaises(ValueError):r.symbols('100 40 T '+r.SYMBOLS[0])
    def test_prelink_cannot_emit_launch_service(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'source-pins.json').write_text('{}')
            (p/'prepare.json').write_text(json.dumps(dict(state='LINKED_PROVIDER_NOT_AUTHORIZED',provider_granted=False)))
            with self.assertRaises(ValueError):r.service_command(p,r.sha(p/'source-pins.json'),r.sha(p/'prepare.json'))
            with self.assertRaises(ValueError):r.service_command(p,'0'*64,r.sha(p/'prepare.json'))
    def test_launch_same_image_one_cpu_no_stage4_transport(self):
        ranges={n:[256+i*256,320+i*256] for i,n in enumerate(r.SYMBOLS)}
        cmd=r.recipes(Path('/out'),{'s3':{'executable':'/qemu'},'model':{'disk':'/model.ext4'}},ranges)
        self.assertEqual(cmd[0],'/qemu');self.assertEqual(cmd[cmd.index('-smp')+1],'1')
        self.assertEqual(cmd[cmd.index('-m')+1],'4G');self.assertNotIn('-D',cmd)
        self.assertNotIn('x-ara-stage4',','.join(cmd));self.assertIn('readonly=on',','.join(cmd))
        self.assertIn('nochain',cmd[cmd.index('-d')+1]);self.assertNotIn('-singlestep',cmd)
    def test_native_entries_are_scoped(self):
        symbols={r.SYMBOLS[0]:[256,512],r.SYMBOLS[3]:[512,768]}
        rows=['STAGE5_STEP_BEGIN requested=1 step=1','BIND_COUNTER when=before',
              'Trace 0: 0xabc [00000000/0000000000000100/00000000/00000000] x',
              'Trace 0: 0xdef [00000000/0000000000000200/00000000/00000000] y',
              'BIND_COUNTER when=after','STAGE5_STEP_END requested=1 step=1']
        self.assertEqual(c.native_entries(rows,symbols)[(1,1)],dict(qbs=1,pv_prepare=1))
        for mutated in (rows[2:],rows+[rows[2]], [v.replace('Trace 0:','Trace 1:') for v in rows]):
            with self.assertRaises(ValueError):c.native_entries(mutated,symbols)
    def test_strict_duplicate_json(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x'
            for raw in ('{"x":1,"x":2}','{"x":NaN}','{'):
                p.write_text(raw)
                with self.assertRaises(ValueError):r.read(p)


if __name__=='__main__':unittest.main()
