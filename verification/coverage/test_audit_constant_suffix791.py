import unittest

import audit_constant_suffix791 as a


class TestSupplement(unittest.TestCase):
    def test_exact_append(self):
        before=['design']+['test%d'%i for i in range(788)]
        a.append_gate(before,before+['new'],789)

    def test_reorder(self):
        before=['design']+['test%d'%i for i in range(788)]
        after=before+['new'];after[2],after[3]=after[3],after[2]
        with self.assertRaises(Exception):a.append_gate(before,after,789)

    def test_duplicate(self):
        before=['design']+['test%d'%i for i in range(788)]
        with self.assertRaises(Exception):a.append_gate(before,before+[before[-1]],789)

    def test_source_zero_activation(self):
        families=[('test',{'scope':dict(width=4,checksum='1',positions=[1,2])})]
        with self.assertRaises(Exception):a.old.audit_rows({'scope':dict(width=4,checksum='1',bits='0x4')},families)

    def test_shape_drift(self):
        families=[('test',{'scope':dict(width=4,checksum='1',positions=[1,2])})]
        with self.assertRaises(Exception):a.old.audit_rows({'scope':dict(width=4,checksum='2',bits='0x0')},families)

    def test_zero_pass(self):
        families=[('test',{'scope':dict(width=4,checksum='1',positions=[1,2])})]
        value=a.old.audit_rows({'scope':dict(width=4,checksum='1',bits='0x9')},families)
        self.assertEqual(value['test']['activated_directions'],0)


if __name__=='__main__':unittest.main()
