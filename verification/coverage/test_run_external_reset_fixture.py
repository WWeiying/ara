import copy
import unittest
import run_external_reset_fixture as m


class Fixture(unittest.TestCase):
    def config(self):
        return m.configuration(m.life.read_bound(m.PRE/'preflight.json', m.PRE_SHA))

    def test_exact_slot0_stage_code_format(self):
        c = self.config()
        self.assertEqual(c['ext_value'], 6)
        self.assertIn('.gen_lanes[0].', c['ext_target'])
        self.assertIn('.gen_num_lanes[0].', c['ext_target'])
        self.assertTrue(c['ext_guard'].endswith('.vfdsu_ex2_half'))
        self.assertIn('set ext_value 6\n', m.selection(c))

    def test_no_builtin_reset_and_fixed_ELF(self):
        cmd = m.command()
        self.assertFalse(any(x.startswith('+ARA_UVM_RESET_') for x in cmd))
        self.assertIn('+PRELOAD='+str(m.PRE/'input.elf'), cmd)
        self.assertIn('+NO_FSDB', cmd)
        self.assertEqual(cmd[0], str(m.life.IMAGE))

    def test_explicit_dump_no_recursive_objects(self):
        c = self.config()
        self.assertEqual(len(c['ext_dump_objects']), 7)
        self.assertNotIn('force', m.selection(c))
        self.assertNotIn('*', m.selection(c))

    def test_bad_selection_rejected(self):
        for kind in ('code', 'duplicate', 'injection', 'missing_guard'):
            c = copy.deepcopy(self.config())
            if kind == 'code': c['ext_value'] = 2
            elif kind == 'duplicate': c['ext_dump_objects'][-1] = c['ext_dump_objects'][0]
            elif kind == 'injection': c['ext_dump_objects'][-1] += ';force'
            else: c['ext_guard'] = 'ara_tb.dut.foreign'
            with self.assertRaises(ValueError): m.selection(c)

    def test_source_pin_conflict_preserved(self):
        with self.assertRaises(ValueError): m.life.merge_pins({'/frozen': 'a'*64}, {'/frozen': 'b'*64})


if __name__ == '__main__': unittest.main()
