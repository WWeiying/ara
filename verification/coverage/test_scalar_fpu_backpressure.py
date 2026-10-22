"""Exact arithmetic/encoding and actual preedge hold protocol negative tests."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import run_scalar_fpu_backpressure as p

FRAMES=[]
def stub(path):
    yield from FRAMES

def frames(bad=None):
    widths={'state_q':1,'flush_i':1,'fpu_valid_i':1,'fpu_ready_o':1,'fpu_in_ready':1,
            'hold_inputs':1,'use_hold':1,'operand_a_d':64,'operand_b_d':64,'operand_a_q':64,'operand_b_q':64}
    decl={p.signal(k):dict(code=k,width=w) for k,w in widths.items()}
    decl.update({'ara_tb.clk':dict(code='clk',width=1),'ara_tb.rst_n':dict(code='rst',width=1)})
    def state(**kw):
        r={k:'0' for k in widths};r.update(clk='0',rst='1');r.update({k:format(v,'b') for k,v in kw.items()});return r
    capture=state(fpu_valid_i=1,hold_inputs=1,operand_a_d=17,operand_b_d=23)
    hold=state(state_q=1,use_hold=1,operand_a_q=17,operand_b_q=23)
    release=dict(hold,fpu_in_ready='1',fpu_ready_o='1')
    idle=state(fpu_in_ready=1,fpu_ready_o=1)
    if bad=='operand':hold['operand_b_q']='11000'
    if bad=='flush':hold['flush_i']='1'
    if bad=='token':release['fpu_ready_o']='0'
    if bad=='ready':idle['state_q']='1'
    if bad=='unknown':hold['operand_a_q']='x'
    if bad=='hold':hold['hold_inputs']='1'
    values=[capture,hold,release,idle]
    if bad=='unreleased':values=[capture,hold]
    if bad=='none':values=[idle,idle]
    return [(None,decl)]+[(i,b,dict(b,clk='1')) for i,b in enumerate(values)]

class Tests(unittest.TestCase):
    def test_exact_oracle(self):
        rows=p.cases()
        self.assertEqual([r['width'] for r in rows],[32,64])
        self.assertEqual([len(r['inputs']) for r in rows],[12,12])
        self.assertEqual(rows[0]['expected'][:4],[0xffffffff3f800000,0xffffffffbf800000,
                                               0xffffffffbf800000,0xffffffff3f800000])
        self.assertTrue(all(r['flags']==0 for r in rows))
    def test_inexact_not_allowed(self):
        with self.assertRaises(ValueError):p.encoded(p.Fraction(1,3),32)
    def test_opcode(self):
        for width in (32,64):
            for i in range(8):
                word=(0x53 | (p.destination(i)<<7) | ((i*2 if i<4 else i+6)<<15) |
                      ((i*2+1 if i<4 else 0)<<20) | (int(width==64)<<25) | ((3 if i<4 else 11)<<27))
                p.opcode(word,width,i)
                for changed in (word^(1<<7),word^(1<<15),word^(1<<12),word^(1<<25)):
                    with self.assertRaises(ValueError):p.opcode(changed,width,i)
    def audit(self,bad=None):
        global FRAMES
        FRAMES=frames(bad)
        with patch.object(p,'wave',SimpleNamespace(vcd=stub)):return p.wave_audit('fixture')
    def test_real_hold_sequence(self):
        r=self.audit();self.assertTrue(r['observed']);self.assertEqual(r['captured_released'],1)
    def test_no_backpressure_is_not_claimed(self):self.assertFalse(self.audit('none')['observed'])
    def test_negative_sequences(self):
        for bad in ('operand','flush','token','ready','unknown','hold','unreleased'):
            with self.subTest(bad=bad),self.assertRaises(ValueError):self.audit(bad)
    def test_command_no_mutation(self):
        c=p.command(p.PRE/'input.elf')
        self.assertIn('+NO_FSDB',c);self.assertIn('-ucli',c)
        self.assertEqual(c[-1],str(p.PROBE));self.assertFalse(any('force' in x for x in c))

if __name__=='__main__':unittest.main()
