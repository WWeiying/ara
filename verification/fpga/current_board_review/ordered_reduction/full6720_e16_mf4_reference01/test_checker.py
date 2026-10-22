"""Short real-spec source-event negatives, no reference or full synthetic run."""
import copy
import unittest
from checker import Checker,config,original_call,original_input,parse_line

S=config()
def row(pc,**kw):
    r=dict(pc=pc,insn=int(S['code'][pc]['insn'],16),x={},f={},v={},csr={},mem=[],cfg=None,rest='')
    r.update(kw);return r

def witness(n=3090):
    c=Checker(S);g=original_call(S,n);a=c.a
    c.calls=n;c.cap=3;c.pre=6;c.fresh=18
    c.counts.update(input_SH=16*(g['scenario']+1),seed_SD=16*(g['scenario']+1),mask_SD=8*(g['row']+1),fixture_fields=2*(g['row']+1))
    c.csr=dict(frm=0,fflags=0,vstart=0,vl=64,vtype=8)
    c.regs.update({10:a['input'],11:a['seed'],12:a['output']+8,13:g['vl'],14:16,15:a['mask'],16:g['rm'],17:g['sticky']})
    for name,values,w in [('input',[original_input(S['bits'],g['scenario'],j) for j in range(16)]+[0]*496,2),('seed',[g['seed']]*64,2),('mask',[g['mask']]*64,1),('output',[91]*144,1)]:
        for j,v in enumerate(values):
            c.memory.update({a[name]+j*w+k:(v>>(8*k))&255 for k in range(w)})
    rs=[]
    for i,pc in enumerate(r['pc'] for r in c.helpers[g['op']]):
        r=row(pc)
        if i in (0,3,6,18):
            vl,typ=(64,8) if i in (0,18) else (16 if i==3 else g['vl'],14)
            r['x']={5:vl};r['csr']=dict(vl=vl,vtype=typ,vstart=0)
        if i in (1,2,4,5):
            name,nwords,w,reg=('seed',64,2,16) if i==1 else ('output',64,2,24) if i==2 else ('input',16,2,8) if i==4 else ('mask',2,1,0)
            addr=a[name]+(8 if i==2 else 0)
            r['mem']=[(addr+j*w,None) for j in range(nwords)]
            r['v']={reg:sum(c.memory[addr+j]<<(8*j) for j in range(nwords*w))}
        if i in (7,8):r['x']={29 if i==7 else 30:0}
        if i in (9,10):r['csr']={'frm' if i==9 else 'fflags':g['rm'] if i==9 else g['sticky']}
        if i==11:
            r['csr']=dict(fflags=g['flags'],vstart=0)
            if g['vl']:r['v']={24:int.from_bytes(c.result_bytes(g)[8:136],'little')}
        if i in (12,13,14,15):r['x']={10 if i in (12,15) else 6:0 if i==12 else g['flags'] if i==13 else g['flags']<<32}
        if i in (16,17):r['csr']={'frm' if i==16 else 'fflags':0}
        if i==19:
            b=c.result_bytes(g)[8:136];r['mem']=[(a['output']+8+j,int.from_bytes(b[j:j+2],'little')) for j in range(0,128,2)]
        rs.append(r)
    return c,rs

def play(c,rs):
    for r in rs:
        pair=c.lookup[r['pc']];c.helper(r,pair)
        c.csr.update(r['csr']);c.regs.update(r['x']);c.vec.update(r['v'])
    g=c.g();b=c.result_bytes(g)
    for pc,i in c.readmap.items():c.oracle(pc,c.a['output']+8*i,int.from_bytes(b[i*8:i*8+8],'little'),8)
    return c

class Tests(unittest.TestCase):
    def test_positive_real_spec(self):
        for n in (0,1,2,3,4,5,3090,3091,6719):
            c,rs=witness(n);play(c,rs);self.assertEqual(c.calls,n+1)
    def reject(self,mutate,why):
        c,rs=witness();mutate(c,rs)
        with self.assertRaisesRegex(ValueError,why):play(c,rs)
    def test_missing_NV(self):self.reject(lambda c,r:r[11]['csr'].update(fflags=0),'NV/sticky')
    def test_wrong_nan(self):self.reject(lambda c,r:r[11]['v'].update({24:r[11]['v'][24]^1}),'target128B')
    def test_wrong_type(self):self.reject(lambda c,r:r[3]['csr'].update(vtype=8),'SEW/LMUL')
    def test_wrong_vstart(self):self.reject(lambda c,r:r[12]['x'].update({10:1}),'Returned')
    def test_missing_helper_internal(self):self.reject(lambda c,r:r.pop(7),'helper order')
    def test_wrong_op(self):self.reject(lambda c,r:r[11].update(pc=c.helpers[1][11]['pc']),'helper order')
    def test_wrong_mask(self):self.reject(lambda c,r:c.memory.update({c.a['mask']+63:0}),'Full setup')
    def test_wrong_seed_upper(self):self.reject(lambda c,r:c.memory.update({c.a['seed']+127:0}),'Full setup')
    def test_wrong_input_BSS(self):self.reject(lambda c,r:c.memory.update({c.a['input']+1023:1}),'Full setup')
    def test_wrong_guard(self):self.reject(lambda c,r:c.memory.update({c.a['output']+143:0}),'Full setup')
    def test_missing_fresh(self):self.reject(lambda c,r:setattr(c,'fresh',17),'freshness')
    def test_short_store(self):self.reject(lambda c,r:r[19]['mem'].pop(),'Full128B')
    def test_restore(self):self.reject(lambda c,r:r[17]['csr'].update(fflags=16),'Restore')
    def test_bank_and_row(self):
        c,_=witness();c.active=None;c.fresh=0;c.counts['fixture_fields']=3090
        with self.assertRaisesRegex(ValueError,'bank1'):c.fixture_read(0x8000033e,c.a['fixtures']+1545*16,0x7c00,8)
    def test_missing_oracle_EOF(self):
        c,rs=witness();play(c,rs)
        with self.assertRaisesRegex(ValueError,'EOF'):c.finish()
    def test_oracle_tail(self):
        c,rs=witness()
        for r in rs:c.helper(r,c.lookup[r['pc']]);c.csr.update(r['csr']);c.regs.update(r['x']);c.vec.update(r['v'])
        b=c.result_bytes(c.g())
        for pc,i in c.readmap.items():
            if i==17:
                with self.assertRaisesRegex(ValueError,'all144B'):c.oracle(pc,c.a['output']+136,0,8)
            else:c.oracle(pc,c.a['output']+8*i,int.from_bytes(b[8*i:8*i+8],'little'),8)
    def test_real_decoder_and_encoding(self):
        r=parse_line('core  0: 3 0x80000000 (0x0001c197) x3 0x8001c000\n')
        c=Checker(S);c.boot=5;c.consume(r)
        r['pc']=0x80000004;r['insn']=0x13
        with self.assertRaisesRegex(ValueError,'PC/code'):c.consume(r)
    def test_scope_and_fixture_endpoint(self):
        self.assertEqual(original_call(S,0)['vl'],0)
        self.assertEqual(original_call(S,6719),dict(scenario=7,l=6,mode=3,rm=4,op=2,sticky=1,vl=16,row=3359,bits=S['fixtures'][6719][0],flags=S['fixtures'][6719][1]|1,mask=0x24,seed=S['bits'][12]))
        self.assertEqual(S['fixtures'][4905],(0x7e00,16))
if __name__=='__main__':unittest.main()
