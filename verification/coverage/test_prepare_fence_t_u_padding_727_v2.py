import dis
import unittest
import prepare_fence_t_u_padding_727_v2 as tool


class ScopeTests(unittest.TestCase):
    def test_generated_pin_has_no_shadowed_module_attribute(self):
        function = tool.adapted()
        self.assertFalse(any(i.opname == 'LOAD_ATTR' and i.argval == '__file__'
                             for i in dis.get_instructions(function)))
        self.assertIn('verification/coverage/prepare_fence_t_u_padding_static.py',
                      function.__code__.co_consts)
        self.assertEqual(function.__globals__['BASE'], tool.predecessor.BASE)
        self.assertEqual(function.__globals__['BUILD'], tool.predecessor.old.BUILD)


if __name__ == '__main__':
    unittest.main()
