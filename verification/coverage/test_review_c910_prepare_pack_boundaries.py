import copy
import unittest
import review_c910_prepare_pack_boundaries as m


class Boundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.review=m.r.load(m.REVIEW,m.SEAL)

    def test_actual_exact240_complement(self):
        targets,protected,scalar=m.exact_targets(self.review)
        self.assertEqual((len(targets),len(protected),len(scalar)),(240,3280,220))

    def test_no_extra_or_scalar_scope(self):
        for mode in ('extra','scalar','wrongmodule','wrongslot'):
            review=copy.deepcopy(self.review);module=review['modules'][0]
            if mode=='extra':module['vector_scopes'].append(module['vector_scopes'][0])
            elif mode=='scalar':module['vector_scopes'][0]=module['protected_scalar_scopes'][0]
            elif mode=='wrongmodule':module['vector_scopes'][0]+='.child'
            else:module['vector_scopes'][0]=module['vector_scopes'][0].replace('gen_num_lanes[0]','gen_num_lanes[4]')
            with self.assertRaises(ValueError):m.exact_targets(review)

    def test_target_range_or_port_change(self):
        for key,value in (('left','1'),('portnode','2'),('excluded','1'),('name','ex4_rst_qnan')):
            review=copy.deepcopy(self.review);review['modules'][0]['targets'][0][key]=value
            with self.assertRaises(ValueError):m.exact_targets(review)

    def test_special_and_round_roles_retained(self):
        for module in self.review['modules']:
            for node in module['protected_native_shape_objects']:
                self.assertTrue(m.role(module['module'],node).endswith('RETAIN'))
        node=dict(name='ex1_qnan_f',kind='vectornode',portnode='0')
        self.assertIn('NAN',m.role('ct_vfdsu_prepare',node))
        node['name']='ex1_rm';self.assertIn('ROUND',m.role('ct_vfdsu_prepare',node))


if __name__=='__main__':unittest.main()
