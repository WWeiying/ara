import unittest
import check_macro_topology as checker


def fixture():
    return '\n'.join(f'AKV_RESOURCE_MACRO role={role} address_bits={bits} data_bits={data} path={path}'
                     for path, (role, bits, data) in checker.EXPECTED.items()) + '\nAKV_RESOURCE_TOPOLOGY_END\n'


class MacroTopologyTests(unittest.TestCase):
    def test_exact_bound_topology(self):
        self.assertEqual(checker.check(fixture())['logical_capacity_bytes'], 34816)

    def test_generic_empty_cannot_pass(self):
        with self.assertRaises(ValueError):
            checker.check('AKV_RESOURCE_TOPOLOGY_END\n')

    def test_missing_extra_changed_and_failure(self):
        text = fixture()
        first = text.splitlines()[0]
        for bad in (text.replace(first + '\n', ''), first + '\n' + text,
                    text.replace('address_bits=6', 'address_bits=7'),
                    text.replace('data_bits=256', 'data_bits=128', 1),
                    text.replace('gen_context_bank[7]', 'gen_context_bank[8]'),
                    text.replace('AKV_RESOURCE_TOPOLOGY_END', ''), text + 'Fatal: test\n',
                    text + first + '\n', text + 'AKV_RESOURCE_UNKNOWN\n'):
            with self.subTest(text=bad), self.assertRaises(ValueError):
                checker.check(bad)


if __name__ == '__main__':
    unittest.main()
