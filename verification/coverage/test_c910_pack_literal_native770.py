import unittest
import c910_pack_literal_native770 as n


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.c=dict(instances=[dict(scope='scope',design_module_checksum='1',toggle_checksum='2',signals=[dict(name='ex4_half_rst_norm',scalar=False,left=63,right=0,bits=list(range(16,64)),native_label='ex4_half_rst_norm[63:0]')])])
        self.text='CHECKSUM: "1 2"\nINSTANCE: scope\nToggle ex4_half_rst_norm [63:16] "net ex4_half_rst_norm[63:0]"\n'
    def test_native_wire_net(self):self.assertEqual(len(n.parse_el(self.text,self.c)),96)
    def test_generated_directional(self):self.assertEqual(len(n.parse_el(n.native.primitive.candidate(self.c),self.c)),96)
    def reject(self,old,new):
        with self.assertRaises(ValueError):n.parse_el(self.text.replace(old,new),self.c)
    def test_sign_excluded_rejected(self):self.reject('[63:16]','[63:15]')
    def test_whole_field(self):self.reject(' [63:16]','')
    def test_bounds(self):self.reject('norm[63:0]','norm[64:0]')
    def test_reg_not_sourcewire(self):self.reject('"net ','"reg ')
    def test_unknown_mux(self):self.reject('ex4_half_rst_norm','ex4_rst_norm')
    def test_wrong_checksum(self):self.reject('"1 2"','"1 3"')
    def test_missing_direction(self):self.reject('Toggle ','Toggle 0to1 ')
    def test_duplicate(self):
        with self.assertRaises(ValueError):n.parse_el(self.text+self.text,self.c)
    def test_no_launch_authority(self):
        with self.assertRaises(ValueError):n.run(n.life.OUT/'unused','seal',None)
    def test_protected_reset_and_reload(self):
        header='handle\tpath\tmeta\tname\ttype\tcoverage\tdisplay\n'
        text=header+'1\tx\tx\tex4_half_rst_norm[63:0]\twire\t25%\t\n2\tflag\tflag\tflag\tport\t0%\t\n'
        i={**self.c['instances'][0],'all_typed_labels':['ex4_half_rst_norm[63:0]','flag'],'protected_shape':[dict(tag='node',name='flag',portnode='3')]}
        stages={s:text for s in ('before','selected','reset','reloaded','final')};self.assertEqual(n.audit(i,stages),(2,1))
        stages['final']=text.replace('25%','50%')
        with self.assertRaises(ValueError):n.audit(i,stages)
    def test_array_suffix_never_stripped(self):
        header='handle\tpath\tmeta\tname\ttype\tcoverage\tdisplay\n'
        text=header+'1\tx\tx\tex4_half_rst_norm[63:0]\twire\t25%\t\n2\ta\ta\ta\treg\t0%\t\n'
        i={**self.c['instances'][0],'all_typed_labels':['ex4_half_rst_norm[63:0]','a[0]'],'protected_shape':[dict(tag='arrays',name='a',portnode='0')]}
        with self.assertRaises(ValueError):n.audit(i,{s:text for s in ('before','selected','reset','reloaded','final')})


if __name__=='__main__':unittest.main()
