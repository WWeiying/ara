import copy
import unittest
import launch_tlb_rvh0_726 as m


class SerializedContract(unittest.TestCase):
    def test_actual_prepared_contract_json_roundtrip(self):
        out=m.frozen.life.OUT/'tlb-rvh0-726-native-agent-20261007-01'
        c=m.frozen.life.read_bound(out/'config.json','71726d6f801ec648b6c8acbe27043a984345ed2d99b45534847d0cbc90c66735')
        _,_,pins=m.proof()
        c['pins']=m.frozen.life.merge_pins(c['pins'],pins)
        m.contract(c)
        for key,value in [('induction',dict(c['induction'],boundary='foreign')),('timeout_seconds',901),('population_application',True)]:
            changed=copy.deepcopy(c);changed[key]=value
            with self.assertRaises(ValueError):m.contract(changed)


if __name__=='__main__':unittest.main()
