import unittest

from diagnose_supply_prefill import command_budget


def command(profile):
    return dict(m=4,n=32,activation_access=0,success=1,fault=0,accumulator_updates=1024,
                useful_pairs=262144,dot_active_cycles=4096,
                fp_uop_issue=6144 if profile==1 else 3072,r_beats=1737 if profile==1 else 2313)


class PrefillBudgetTests(unittest.TestCase):
    def test_affine_work_is_not_six_ops_on_one_port(self):
        result=command_budget(command(1),1)
        self.assertEqual((result['casts'],result['multiplies'],result['fmas']),(2048,2048,2048))
        self.assertEqual(result['arithmetic_port_issue_floor'],4096)
        self.assertEqual(result['hypothetical_128_product_dot_issue_floor'],2048)
        self.assertEqual(result['hypothetical_fixed_ports_command_service_floor'],4096)
        self.assertTrue(result['arithmetic_floor_exceeds_hypothetical_dot'])

    def test_symmetric_read_service_must_not_be_omitted(self):
        result=command_budget(command(2),2)
        self.assertEqual(result['arithmetic_port_issue_floor'],2048)
        self.assertEqual(result['cast_port_issue_floor'],1024)
        self.assertEqual(result['hypothetical_fixed_ports_command_service_floor'],2313)
        self.assertFalse(result['arithmetic_floor_exceeds_hypothetical_dot'])

    def test_unreviewed_geometry_flags_uops_or_profile_rejected(self):
        for key,value in (('m',1),('n',16),('activation_access',2),('success',0),('fault',1),
                          ('accumulator_updates',512),('fp_uop_issue',6143),('dot_active_cycles',2048)):
            row=command(1);row[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):command_budget(row,1)
        with self.assertRaises(ValueError):command_budget(command(1),3)


if __name__=='__main__':unittest.main()
