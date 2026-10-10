from types import SimpleNamespace
import unittest
from unittest.mock import patch
import recheck_random_policy_sidecar as s


def item(dest=False,policy=False):
    return SimpleNamespace(vector_writes={14:0x5a} if dest else {},
        vector_tail_agnostic=False if policy else None,
        vector_mask_agnostic=False if policy else None,
        vector_vl=1 if policy else None,vector_vstart=0 if policy else None)


class PolicyTests(unittest.TestCase):
    def test_exact_scalar_move_encoding(self):
        for word in (0x42e01057,0x43601057):self.assertTrue(s.scalar_move_to_f0(word))
        for word in (0x42e00057,0x42e09057,0x40e01057,0x46e01057,0x42e010d7):
            self.assertFalse(s.scalar_move_to_f0(word))

    def check(self,value=0x5a,pre=None,dest=False,policy=False):
        return s.audit_byte(SimpleNamespace(instruction=0x42e01057),item(dest,policy),14,0,value,
                            {14:0x5a} if pre is None else pre,{14:0x5a},{},1024)

    def test_missing_policy_preservation_is_compared(self):
        self.assertEqual(self.check(),'PRESERVED')

    def test_preservation_changed_unknown_or_missing_pre_reject(self):
        for value,pre in [(0x5b,{14:0x5a}),(None,{14:0x5a}),(0x5a,{})]:
            with self.subTest(value=value,pre=pre),self.assertRaisesRegex(ValueError,'preservation'):
                self.check(value,pre)

    def test_real_destination_missing_policy_reject(self):
        with self.assertRaisesRegex(ValueError,'Missing ISA'):self.check(dest=True)

    def test_each_policy_field_required_for_destination(self):
        for field in ('vector_tail_agnostic','vector_mask_agnostic','vector_vl','vector_vstart'):
            x=item(True,True);setattr(x,field,None)
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'Missing ISA'):
                s.audit_byte(SimpleNamespace(instruction=0x42e01057),x,14,0,0x5a,{14:0x5a},{14:0x5a},{},1024)

    def test_valid_policy_keeps_active_unknown_rejection(self):
        with patch.object(s.v,'_architectural_compare_mask',return_value=255):
            self.assertEqual(self.check(dest=True,policy=True),'KNOWN_ACTIVE')
            with self.assertRaisesRegex(ValueError,'active unknown'):self.check(None,dest=True,policy=True)

    def test_only_proven_isa_unknown_mask_can_relax_byte(self):
        with patch.object(s.v,'_architectural_compare_mask',return_value=0):
            self.assertEqual(self.check(None,dest=True,policy=True),'ISA_UNKNOWN')
            with self.assertRaisesRegex(ValueError,'preservation'):self.check(None)


if __name__=='__main__':unittest.main()
