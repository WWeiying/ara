import copy
import unittest
import close_cvxif_padding776_offline as p


class ClosureTests(unittest.TestCase):
    def pair(self):
        saved=dict(native_inventory_counts=[[41,36],[45,40]],flag=False,pins={'x':'abc'},other=[1,2])
        actual=copy.deepcopy(saved);actual['native_inventory_counts']=[(41,36),(45,40)]
        return saved,actual

    def test_exact_counts_only(self):p.reconcile(*self.pair())

    def test_changed_count_rejected(self):
        a,b=self.pair();b['native_inventory_counts']=[(42,37),(45,40)]
        with self.assertRaises(ValueError):p.reconcile(a,b)

    def test_bool_count_rejected(self):
        a,b=self.pair();b['native_inventory_counts']=[(True,False),(45,40)]
        with self.assertRaises(ValueError):p.reconcile(a,b)

    def test_other_tuple_not_normalized(self):
        a,b=self.pair();b['other']=(1,2)
        with self.assertRaises(ValueError):p.reconcile(a,b)

    def test_bool_int_other_not_equal(self):
        a,b=self.pair();b['flag']=0
        with self.assertRaises(ValueError):p.reconcile(a,b)

    def test_pin_change_rejected(self):
        a,b=self.pair();b['pins']['x']='changed'
        with self.assertRaises(ValueError):p.reconcile(a,b)

    def test_missing_field_rejected(self):
        a,b=self.pair();del b['flag']
        with self.assertRaises(ValueError):p.reconcile(a,b)

    def test_audit_pair_strict_integer_normalization(self):
        self.assertEqual(p.audit_pair((41,36)),[41,36])
        for row in ((True,False),(41.0,36),('41',36),(41,35),(41,36,0)):
            with self.subTest(row=row),self.assertRaises(ValueError):p.audit_pair(row)

    def test_real_frozen_verify_twice_without_receipt_mutation(self):
        before=p.life.digest(p.CAPTURE/'capture-result.json')
        a=p.closure();b=p.closure()
        self.assertEqual(a,b)
        self.assertEqual(a['native_inventory_counts'],[[41,36],[45,40]])
        self.assertTrue(a['all_original_gates_replayed'])
        self.assertEqual(before,p.RECEIPT_SHA)
        self.assertEqual(p.life.digest(p.CAPTURE/'capture-result.json'),before)


if __name__=='__main__':unittest.main()
