import copy
import unittest
import admit_external_reset_half746 as m


class Contracts(unittest.TestCase):
    def fixture(self):
        old=dict(design={'fixed':'shape'},tests=['/old/%d'%i for i in range(745)],input_hashes={'/pin':'a'*64},metrics={
            'line':{str(i):dict(width=2,checksum='9',bits='0x1') for i in range(6159)},
            **{k:{'scope':dict(width=2,checksum='9',bits='0x1')} for k in ('cond','branch','fsm')}})
        single=copy.deepcopy(old);single['tests']=[str(m.q.run.OUT/'code.vdb')];single['metrics']['fsm']['scope']['bits']='0x2'
        return old,single

    def test_actual_qualification_boundaries(self):
        q=m.life.read_bound(m.QUAL/'qualification.json',m.QUAL_SHA)
        self.assertEqual(q['raw_delta'],dict(line=0,cond=3,branch=0,fsm=16))
        self.assertFalse(q['uvm_check_report_pass']);self.assertFalse(q['coverage_admitted'])

    def test_independentOR(self):
        old,single=self.fixture();new=m.merge(old,single)
        self.assertEqual(new['metrics']['fsm']['scope']['bits'],'0x3')
        self.assertEqual(new['tests'],old['tests']+single['tests'])

    def test_wrong_prefix_shape_or_metric_rejected(self):
        for kind in ('count','duplicate','checksum','universe'):
            old,single=self.fixture()
            if kind=='count':old['tests'].pop()
            elif kind=='duplicate':old['tests'][-1]=single['tests'][0]
            elif kind=='checksum':single['metrics']['fsm']['scope']['checksum']='foreign'
            else:del single['metrics']['fsm']['scope']
            with self.assertRaises(ValueError):m.merge(old,single)

    def test_pin_conflict_rejected(self):
        with self.assertRaises(ValueError):m.life.merge_pins({'/pin':'a'*64},{'/pin':'b'*64})


if __name__=='__main__':unittest.main()
