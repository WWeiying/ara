import copy
import json
import re
import unittest
import prove_c910_pack_literals770 as p


class LiteralTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=p.SOURCE.read_text();cls.reference=json.loads(p.STATIC.read_bytes())
    def test_actual_semantic_bits(self):
        rows=p.semantics(self.source,self.reference)
        self.assertEqual(sum(len(r['constant_values']) for r in rows),1048)
        half=next(r for r in rows if r['name']=='ex4_half_rst_norm')
        self.assertEqual(half['constant_values'],{str(b):1 for b in range(16,64)})
    def reject(self,old,new):
        self.assertIn(old,self.source)
        # Mutate a selected literal producer, not an earlier protected denorm mux.
        target = ('ex4_half_lfn' if "48'h" in old else
                  'ex4_sing_lfn' if "32'h" in old else 'ex4_doub_lfn')
        m=re.search(r'assign\s+'+target+r'\[63:0\]\s*=.*?;',self.source,re.S)
        if old in m.group():
            mutated=self.source[:m.start()]+m.group().replace(old,new,1)+self.source[m.end():]
        else:mutated=self.source.replace(old,new,1)
        with self.assertRaises(ValueError):p.semantics(mutated,self.reference)
    def test_literal_change(self):self.reject("48'hffffffffffff","48'hfffffffffff0")
    def test_dynamic_boxing(self):self.reject("48'hffffffffffff",'vfdsu_ex4_qnan_f[47:0]')
    def test_extra_writer(self):
        with self.assertRaises(ValueError):p.semantics(self.source+'\nassign ex4_half_rst_norm[63:0] = 64\'b0;',self.reference)
    def test_procedural_writer(self):self.reject('assign ex4_half_lfn[63:0]','always_comb ex4_half_lfn[63:0]')
    def test_signed_cast_rejected(self):self.reject("32'hffffffff","$signed(32'hffffffff)")
    def test_unknown_literal(self):self.reject("48'hffffffffffff","48'hxxxxxxxxxxxx")
    def test_widened_literal(self):self.reject("48'hffffffffffff","49'hffffffffffff")
    def test_replication_change(self):self.reject("{52{1'b1}}","{52{1'b0}}")
    def test_dynamic_sign_not_selected(self):
        r=copy.deepcopy(self.reference);r['signals'][0]['selected_ranges']=[[63,0]]
        with self.assertRaises(ValueError):p.semantics(self.source,r)
    def test_no_partial_field_oldEL_silently_subtracted(self):
        scope=self.reference['scopes'][0]
        with self.assertRaises(ValueError):p.old_overlap('INSTANCE: '+scope+'\nToggle ex4_half_rst_norm [63:16]',{scope},{'ex4_half_rst_norm'})
    def test_literal_bit_order(self):self.assertEqual(p.symbolic("4'h9"),[1,0,0,1])


if __name__=='__main__':unittest.main()
