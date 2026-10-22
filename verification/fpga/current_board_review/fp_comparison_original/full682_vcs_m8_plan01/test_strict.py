"""Whole682 model witnesses with exact ELF instructions, no simulator."""
import json
import re
import time
import unittest
from pathlib import Path
import strict as c
from model import model, CAP
from newscope import HERE, PREP

def fixture(s,fault=None,tailones=False):
    code=s['code'];a=s['symbols'];golds=model()['rows']
    aliases=['zero','ra','sp','gp','tp','t0','t1','t2','s0','s1','a0','a1','a2','a3','a4','a5','a6','a7','s2','s3','s4','s5','s6','s7','s8','s9','s10','s11','t3','t4','t5','t6']
    def row(r,rd=0,value=0,address=0,rmask=0,wmask=0,wdata=0):
        return dict(pc=r['pc'],insn=int(r['insn'],16),rd=rd,value=value,address=address,rmask=rmask,wmask=wmask,wdata=wdata)
    setters={}
    for n in range(1,32):
        hits=[r for r in code.values() if r['pc']<s['capacity'][0]['pc'] and
              re.match(r'(?:auipc|lui|li|addi|mv)\t'+aliases[n]+r'(?:,|$)',r['text'])]
        if hits:setters[n]=hits[0]
    def setreg(n,v):return row(setters[n],rd=n,value=v)
    for i,r in enumerate(s['prelude']):
        if i in (1,2):yield setreg(5,a['trap_entry'] if i==1 else 0x6600)
        yield row(r,rd=(int(r['insn'],16)>>7)&31,value=128 if i==5 else 0)
    for i,r in enumerate(s['capacity']):
        yield row(r,rd=5 if i==0 else 10 if i==1 else 0,value=(1<<64)-1 if i==0 else CAP if i==1 else 0)
    if fault=='capacity_twice':yield row(s['capacity'][0],rd=5,value=(1<<64)-1)
    if fault=='helper_interior':yield row(s['routines'][9][11])
    for j,g in enumerate(golds):
        if fault=='skip_predecessor' and j==49:continue
        for pc,addr,value,width in c.setup(s,g):
            r=code[f'{pc:x}'];d=c.memop(int(r['insn'],16))
            yield setreg(d['base'],addr-d['offset'])
            if not(fault=='unknown_source' and j==0 and addr==a['mask']):yield setreg(d['register'],value)
            if fault=='input' and j==0 and addr==a['a']:value^=1
            mask=((1<<width)-1)<<(addr%8)
            if fault=='byte_enable' and j==0 and addr==a['a']:mask^=1
            yield row(r,address=addr,wmask=mask,wdata=value)
        args=[a['a'],a['b'],a['output']+1,g['vl'],CAP,a['mask'],0,g['sticky']]
        if fault=='pointer' and j==0:args[1]=a['a']
        for n,v in enumerate(args,10):yield setreg(n,v)
        rr=s['routines'][g['op']];delta=5 if g['op']>=4 else 0
        for i,r in enumerate(rr):
            rd=value=addr=rmask=0
            if i==0:rd=30
            if i in (1,5+delta,13+delta):rd,value=5,g['vl'] if i==5+delta else CAP
            if delta:
                if i==5:rd,value,addr,rmask=7,g['b'][0],a['b'],3<<(a['b']%8)
                if i==6:rd,value=28,(1<<64)-1
                if i==7:rd,value=28,0xffffffffffff0000
                if i==8:rd,value=7,0xffffffffffff0000|g['b'][0]
                if fault=='boxing' and i==8:value^=1<<63
            if i==8+delta:rd,value=10,int(fault=='vstart' and j==681)
            if i==9+delta:
                rd,value=6,g['flags']
                if fault=='flags' and j==681:value^=16
            if i==10+delta:rd,value=6,g['flags']<<32
            if i==11+delta:rd,value=10,g['flags']<<32
            if fault=='restore' and j==0 and i==12+delta:continue
            yield row(r,rd,value,addr,rmask)
        if fault=='duplicate_interior' and j==0:yield row(rr[11],rd=10)
        record=a['packed_cases']+144*j
        for k in range(195):
            if fault=='last_byte' and j==681 and k in (189,190,191):continue
            if k<192:
                byte,part=divmod(k,3);zero,one=c.packed(g,byte);key=('one','zero','bits')[part]
                addr=record+(80+byte if part==0 else 16+byte) if part<2 else a['output']+1+byte
                value=one if part==0 else zero
                if part==2:
                    value=sum((max(g['allowed'][byte*8+b]) if tailones else min(g['allowed'][byte*8+b]))<<b for b in range(8))
                    if fault=='vl0_result' and j==0 and byte==0:value^=1
                    if fault=='active_bit511' and j==49 and byte==63:value^=128
                if fault=='gold_table' and j==0 and part==0:value^=1
                width=1
            else:
                key=('flags','guard0','guard1')[k-192]
                addr=record+14 if key=='flags' else a['output']+(0 if key=='guard0' else 65)
                width=2 if key=='flags' else 1;value=g['flags'] if key=='flags' else 91
                if fault=='guard' and j==681 and key=='guard1':value^=1
            r=code[f"{s['sites'][key]:x}"];d=c.memop(int(r['insn'],16))
            yield setreg(d['base'],addr-d['offset'])
            yield row(r,rd=d['register'],value=value,address=addr,rmask=((1<<width)-1)<<(addr%8))
    yield row(s['exit_store'],address=s['exit_address'],wmask=255,wdata=int(s['spike']) if fault!='exit' else 2)
    yield row(s['park'])

class StrictTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.s=c.specification(PREP/'run01/soc.elf')
    def test_full682_both_allowed_tail_choices(self):
        for tail in (False,True):
            r=c.audit(fixture(self.s,tailones=tail),self.s)
            self.assertEqual((r['target_calls'],r['full_result_bit_checks'],r['guard_checks'],r['helper_instructions']),(682,349184,1364,12592))
    def test_negative_contracts(self):
        for f in ('capacity_twice','helper_interior','skip_predecessor','input','byte_enable','unknown_source',
                  'pointer','boxing','vstart','flags','restore','duplicate_interior','last_byte','vl0_result',
                  'active_bit511','gold_table','guard','exit'):
            with self.subTest(fault=f),self.assertRaises(ValueError):c.audit(fixture(self.s,f),self.s)
    def test_every_helper_interior_rejected_outside_window(self):
        for rr in self.s['routines']:
            for r in rr[1:]:
                with self.assertRaises(ValueError):c.audit([dict(pc=r['pc'],insn=int(r['insn'],16))],self.s)
    def test_model_all_original_fixture_pairs(self):
        from model import INPUT,compare
        text=(HERE.parent/'prepared02/prepared/alias_v8_e16m8_prefix682/original/fixtures.h').read_text()
        expected=json.loads(text.split('expected[6][16][16]=')[1].split(';')[0].replace('{','[').replace('}',']'))
        self.assertEqual(expected,[[[list(compare(op,a,b)) for b in INPUT] for a in INPUT] for op in range(6)])

if __name__=='__main__':
    import hashlib
    start=time.monotonic();r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(StrictTests))
    pins={str(HERE/n):hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in ('newscope.py','model.py','elf.py','strict.py','test_strict.py')}
    with (HERE/'host_strict01.json').open('x') as f:json.dump(dict(status='PASS_HOST_ONLY' if r.wasSuccessful() else 'FAIL_HOST',tests=r.testsRun,failures=len(r.failures),errors=len(r.errors),elapsed_s=time.monotonic()-start,pins=pins),f,indent=2)
    raise SystemExit(not r.wasSuccessful())
