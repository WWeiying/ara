import unittest
import vlsu_address_padding_native770 as n


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.c = dict(instances=[dict(scope='scope', design_module_checksum='1', toggle_checksum='2',
                    signals=[dict(name='mem_q[0].vaddr', scalar=False, left=127, right=0,
                                  bits=list(range(64,128)), native_label='mem_q[0].vaddr[127:0]')])])
        self.text = 'CHECKSUM: "1 2"\nINSTANCE: scope\nToggle mem_q[0].vaddr [127:64] "reg mem_q[0].vaddr[127:0]"\n'

    def test_exact_partial(self): self.assertEqual(len(n.parse_el(self.text, self.c)),128)
    def test_directional_generated_candidate(self):
        self.assertEqual(len(n.parse_el(n.native.primitive.candidate(self.c), self.c)),128)
    def test_low_bit_rejected(self):
        with self.assertRaises(ValueError): n.parse_el(self.text.replace('[127:64]', '[127:63]'), self.c)
    def test_whole_field_rejected(self):
        with self.assertRaises(ValueError): n.parse_el(self.text.replace(' [127:64]', ''), self.c)
    def test_checksum_rejected(self):
        with self.assertRaises(ValueError): n.parse_el(self.text.replace('"1 2"','"1 3"'), self.c)
    def test_wrong_decl_bounds(self):
        with self.assertRaises(ValueError): n.parse_el(self.text.replace('vaddr[127:0]', 'vaddr[126:0]'), self.c)
    def test_reg_net_not_equivalent(self):
        with self.assertRaises(ValueError): n.parse_el(self.text.replace('"reg ', '"net '), self.c)
    def test_extra_scope(self):
        with self.assertRaises(ValueError): n.parse_el(self.text.replace('scope','other'), self.c)
    def test_missing_direction(self):
        with self.assertRaises(ValueError): n.parse_el(self.text.replace('Toggle ', 'Toggle 0to1 '), self.c)
    def test_duplicate(self):
        with self.assertRaises(ValueError): n.parse_el(self.text + self.text, self.c)
    def test_no_authority_no_run(self):
        with self.assertRaises(ValueError): n.run(n.life.OUT / 'unused', 'a', None)
    def test_exact_fifo_parameter_name(self):
        self.assertIn('DEPTH=16,', n.definition_name('x.i_store_b_metadata','fifo_v3'))
        self.assertIn('DEPTH=4,', n.definition_name('x.i_addrgen_req_queue','fifo_v3'))
        with self.assertRaises(ValueError): n.definition_name('x.i_store_b_metadata','other_fifo')
    def test_protected_row_changed(self):
        header='handle\tpath\tmeta\tname\ttype\tcoverage\tdisplay\n'
        before=header+'1\tx\tm\tmem_q[0].vaddr[127:0]\treg\t25%\tA\n2\ty\tn\tvalid\treg\t0%\tB\n'
        i={**self.c['instances'][0], 'all_typed_labels':['mem_q[0].vaddr[127:0]', 'valid']}
        stages={s:before for s in ('before','selected','reset','reloaded','final')}
        self.assertEqual(n.native.audit_native(i,stages),(2,1))
        stages['selected']=before.replace('0%\tB','50%\tB')
        with self.assertRaises(ValueError): n.native.audit_native(i,stages)


if __name__ == '__main__': unittest.main()
