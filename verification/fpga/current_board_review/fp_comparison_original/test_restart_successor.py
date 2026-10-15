"""No simulations: exact membership, held682, and reserved-capacity tests."""
import copy
import unittest
import replay_restart_successor as r


class Successor(unittest.TestCase):
    def setUp(self):
        self.old=r.read(r.OLD/'plan.json')
        self.data=copy.deepcopy(self.old)
        self.data['cases']=[x for x in self.old['cases'] if x['id'] in r.NAMES]
        self.data['held_cases']=[dict(status='HOLD_NOT_RUN',case=x) for x in self.old['cases'] if x['id'] not in r.NAMES]
        self.units={n:'ara-test-'+n+'.service' for n in (*r.QUOTAS,'gather','final38')}

    def process(self,name):
        return dict(cgroup='0::/user.slice/'+self.units[name],pid=1)

    def test_exact_two(self):r.contract(self.data)

    def test_682_not_executable(self):
        self.data['cases'].append(self.data['held_cases'][0]['case'])
        with self.assertRaises(ValueError):r.contract(self.data)

    def test_682_not_removed(self):
        self.data['held_cases']=[]
        with self.assertRaises(ValueError):r.contract(self.data)

    def test_682_oracle_unchanged(self):
        self.data['held_cases'][0]['case']['pass_markers']=[]
        with self.assertRaises(ValueError):r.contract(self.data)

    def test_no_short_timeout(self):
        self.data['cases'][0]['timeout_s']=600
        with self.assertRaises(ValueError):r.contract(self.data)

    def test_no_extra_jobs(self):
        self.data['jobs']=3
        with self.assertRaises(ValueError):r.contract(self.data)

    def test_quotas_held_when_idle(self):
        self.assertEqual(r.resource_math([],32*1024**3,self.units)['total_live_plus_reserved'],20)

    def test_24_allowed(self):
        unknown=[dict(pid=i,cgroup='0::/external') for i in range(4)]
        self.assertEqual(r.resource_math(unknown,32*1024**3,self.units)['total_live_plus_reserved'],24)

    def test_25_rejected(self):
        unknown=[dict(pid=i,cgroup='0::/external') for i in range(5)]
        with self.assertRaises(ValueError):r.resource_math(unknown,32*1024**3,self.units)

    def test_gather_must_exit(self):
        with self.assertRaises(ValueError):r.resource_math([self.process('gather')],32*1024**3,self.units)

    def test_38_must_exit(self):
        with self.assertRaises(ValueError):r.resource_math([self.process('final38')],32*1024**3,self.units)

    def test_three_own_workers_rejected(self):
        with self.assertRaises(ValueError):r.resource_math([self.process('fp')]*3,32*1024**3,self.units)

    def test_mem_floor(self):
        with self.assertRaises(ValueError):r.resource_math([],32*1024**3-1,self.units)

    def test_no_duplicate_units(self):
        self.units['fp']=self.units['whole']
        with self.assertRaises(ValueError):r.resource_math([],32*1024**3,self.units)

    def test_live_above_reservation_charged(self):
        self.assertEqual(r.resource_math([self.process('nf8')]*10,32*1024**3,self.units)['total_live_plus_reserved'],22)


if __name__=='__main__':unittest.main()
