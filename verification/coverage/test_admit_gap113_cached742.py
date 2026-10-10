import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
import admit_gap113_cached742 as t


class Admission(unittest.TestCase):
    def test_exact_prefix(self):
        before=[str(i) for i in range(741)];t.exact_prefix(before,[str(t.DESIGN),*before])
        for old,inputs in [(before,[str(t.DESIGN),*before[::-1]]),
                           (before,[str(t.DESIGN),*before[:-1]]),
                           (before[:-1]+[before[0]],[str(t.DESIGN),*before[:-1],before[0]]),
                           (before[:-1]+[str(t.VDB)],[str(t.DESIGN),*before[:-1],str(t.VDB)])]:
            with self.assertRaises(ValueError):t.exact_prefix(old,inputs)

    def actual(self):
        q=t.life.read_bound(t.QUAL/'qualification.json',t.QUAL_SHA)
        a=t.life.read_bound(t.QUAL/'runtime-audit.json',q['output_pins'][str(t.QUAL/'runtime-audit.json')])
        return q,a

    def test_actual_oracle_contract_not_full_spike(self):
        q,a=self.actual();t.oracle_contract(q,a)
        self.assertFalse(a['spike_custom_isa_pass'])
        self.assertFalse(q['full_toggle_interval_gain_qualified'])

    def test_incomplete_checks_rejected(self):
        q,a=self.actual()
        for key,value in [('checks',40),('custom_write_bytes',240),('full_vrf_bytes',4096),
                          ('initial_vrf_bytes',0),('csr_values',12),('source_guard_bytes',0),
                          ('custom_preserved_vrf_bytes',0),('spike_custom_isa_pass',True)]:
            bad=copy.deepcopy(a);bad[key]=value
            with self.assertRaises(ValueError):t.oracle_contract(q,bad)
        for key in ('exceptions','protocol_errors','outstanding'):
            bad=copy.deepcopy(a);bad['contract'][key]=1
            with self.assertRaises(ValueError):t.oracle_contract(q,bad)

    def test_per_command_and_status_reject(self):
        q,a=self.actual()
        for key,value in [('backend_vl',160),('preserved_vrf_bytes',0),('native_total_write_bytes',255),('phase',1)]:
            bad=copy.deepcopy(a);bad['bindings'][0][key]=value
            with self.assertRaises(ValueError):t.oracle_contract(q,bad)
        for key,value in [('status','FAIL'),('coverage_admitted',True),('rtl_changed',True)]:
            bad=copy.deepcopy(q);bad[key]=value
            with self.assertRaises(ValueError):t.oracle_contract(bad,a)

    def test_toggle_binary_interval_shape_not_score(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'tgl.gz'
            p.write_bytes(gzip.compress(b'<covdata><instance_data name="s" value="01" chksum="7"/>'
                b'<instance_intervaldata name="s" value="0 256 14 -1" chksum="7"/></covdata>'))
            self.assertEqual(t.toggle_shape(p),({'s':(2,'7')},{'s':('7',1)}))
            for body in (b'<instance_intervaldata name="s" value="0 256 14 -1" chksum="8"/>',
                         b'<instance_intervaldata name="s" value="" chksum="7"/>',
                         b'<instance_intervaldata name="s" value="0 256 14" chksum="7"/>'):
                p.write_bytes(gzip.compress(b'<covdata><instance_data name="s" value="01" chksum="7"/>'+body+b'</covdata>'))
                with self.assertRaises(ValueError):t.toggle_shape(p)


if __name__=='__main__':unittest.main()
