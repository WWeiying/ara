import copy
import json
import unittest
import verify_vlsu_padding51_native770_offline as v


class OfflineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=json.loads((v.RUN/'config.json').read_bytes())

    def fixture(self,index=0):
        return copy.deepcopy(self.config['instances'][index]), {
            stage:(v.RUN/f'native_{stage}_{index}.tsv').read_text()
            for stage in ('before','selected','reset','reloaded','final')}

    def test_all_actual_five_stage_inventories(self):
        counts=[v.audit(*self.fixture(index)) for index in range(4)]
        self.assertEqual(sum(n[0] for n in counts),1404)
        self.assertEqual(sum(n[1] for n in counts),1353)

    def shape_mutation(self,key,value):
        i,s=self.fixture();node=next(n for n in i['protected_shape'] if n['name']=='axi_ar_o.user');node[key]=value
        with self.assertRaises(ValueError):v.audit(i,s)
    def test_wider_port_rejected(self):self.shape_mutation('left','1')
    def test_array_not_scalar_alias(self):self.shape_mutation('tag','arrays')
    def test_role_rejected(self):self.shape_mutation('portnode','2')
    def test_scalar_shape_not_accepted_as_vector(self):self.shape_mutation('tag','node')
    def test_nonzero_index_rejected(self):self.shape_mutation('left','14')

    def test_port_full_row_changed_each_stage(self):
        for stage in ('selected','reset','reloaded','final'):
            i,s=self.fixture()
            s[stage]=s[stage].replace('axi_ar_o.user\tport\t0.00%', 'axi_ar_o.user\tport\t1.00%')
            self.assertNotEqual(s[stage],self.fixture()[1][stage])
            with self.assertRaises(ValueError):v.audit(i,s)

    def test_native_meta_mismatch(self):
        i,s=self.fixture();s['before']=s['before'].replace('axi_ar_o.user\taxi_ar_o.user\taxi_ar_o.user', 'axi_ar_o.user\tother\taxi_ar_o.user')
        with self.assertRaises(ValueError):v.audit(i,s)
    def test_no_blanket_index_strip(self):
        i,s=self.fixture(1)
        for stage in s:s[stage]=s[stage].replace('mem_q[0].vaddr','mem_q.vaddr')
        with self.assertRaises(ValueError):v.audit(i,s)
    def test_missing_protected_field(self):
        i,s=self.fixture();s['before']='\n'.join(line for line in s['before'].splitlines() if 'axi_ar_o.user' not in line)+'\n'
        with self.assertRaises(ValueError):v.audit(i,s)
    def test_wrong_owner(self):
        i,s=self.fixture();i['scope']=v.PREFIX+'i_vstu'
        with self.assertRaises(ValueError):v.audit(i,s)
    def test_extra_native_row_rejected(self):
        i,s=self.fixture();s['before']+='99999\tx\tx\tx\treg\t0.00%\t\n'
        with self.assertRaises(ValueError):v.audit(i,s)


if __name__=='__main__':unittest.main()
