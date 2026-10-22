import copy
import csv
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import qualify_qbs_payload_matrix4_uart as m


class MatrixQualification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.symbols,cls.data,cls.sites,cls.native=m.elf_view()
        cls.data=staticmethod(cls.data)
        cls.audit=m.runtime(m.RUN)
        with (m.RUN/'commit_trace.csv').open() as f:cls.rows=list(csv.DictReader(f))
        cls.parsed=m.full8.inherited.support._parse_vector_trace(m.RUN/'vector_trace.csv')

    def test_actual_full_four(self):
        self.assertEqual(len(self.audit['bindings']),4)
        self.assertEqual(self.audit['contract']['requests'],92)
        self.assertEqual(self.audit['custom_write_bytes'],1024)
        self.assertEqual(self.audit['full_vrf_bytes'],16384)
        self.assertFalse(self.audit['full_scalar_isa_verified'])
        for b in self.audit['bindings']:
            self.assertEqual(sum(b['readback_bytes'].values()),9072)

    def test_native_unpacked_independent_gold(self):
        for phase in range(4):
            self.assertEqual(self.native[phase]['result_bits'],m.recipe.fixture(phase)[2])
        w,a,_=m.recipe.fixture(0)
        for bad in ('weight','bsum','scale'):
            weight=bytearray(w[78:78+1680]);act=bytearray(a[72:72+2336])
            if bad=='weight':weight[0]^=1
            elif bad=='bsum':act[2080]^=1
            else:act[0]^=1
            if bad=='weight':self.assertNotEqual(m.unpack(weight,act)['result_bits'],self.native[0]['result_bits'])
            else:
                with self.assertRaises(ValueError):m.unpack(weight,act)

    def test_bad_numeric_duplicate_unknown_source(self):
        activity=next(a for a in self.parsed[2].values() if a.instruction==m.full8.WORD)
        expected=m.full8.custom_expected(self.native[0])
        for bad in ('numeric','duplicate','unknown','source'):
            a=copy.deepcopy(activity);w=a.writes[0]
            if bad=='numeric':a.writes[0]=replace(w,data=w.data^1)
            elif bad=='duplicate':a.writes.append(w)
            elif bad=='unknown':a.writes[0]=replace(w,known_be=0)
            else:a.writes[0]=replace(w,source=3)
            with self.assertRaises(ValueError):m.full8.activity_bytes(a,expected,0,10**9,custom=True)

    def test_incomplete_command_population(self):
        parsed=copy.deepcopy(self.parsed);parsed[2].pop(next(iter(parsed[2])))
        with patch.object(m.full8.inherited.support,'_parse_vector_trace',return_value=parsed):
            with self.assertRaises(ValueError):m.runtime(m.RUN)

    def test_source_guard_csr_descriptor_readbacks(self):
        expected=m.regions(0,self.symbols,self.data,self.native)
        for name in expected:
            base=self.symbols[name][0]
            selected=[r for r in self.rows if r['event']=='retire' and int(r['mem_rmask'],16) and base<=int(r['mem_addr'],16)<base+len(expected[name])]
            self.assertTrue(selected,name)
            m.readback(selected,0,10**9,self.symbols,{name:expected[name]},self.data)
            bad=copy.deepcopy(selected);bad[0]['rd_wdata']='%016x'%(int(bad[0]['rd_wdata'],16)^1)
            with self.assertRaises(ValueError):m.readback(bad,0,10**9,self.symbols,{name:expected[name]},self.data)
            with self.assertRaises(ValueError):m.readback([],0,10**9,self.symbols,{name:expected[name]},self.data)

    def test_x0_not_generic_register_waiver(self):
        expected=m.regions(0,self.symbols,self.data,self.native)
        name='weight0';base=self.symbols[name][0]
        selected=[r for r in self.rows if r['event']=='retire' and int(r['mem_rmask'],16) and base<=int(r['mem_addr'],16)<base+len(expected[name])]
        self.assertTrue(all(r['rd']=='0' for r in selected))
        with self.assertRaises(ValueError):m.full8.inherited.readback(selected,0,10**9,self.symbols,{name:expected[name]})
        with self.assertRaises(ValueError):m.readback(selected,0,10**9,self.symbols,{'frame0':expected[name]},self.data)
        bad=copy.deepcopy(selected);bad[0]['pc']='0000000080000000'
        with self.assertRaises(ValueError):m.readback(bad,0,10**9,self.symbols,{name:expected[name]},self.data)

    def test_error_duplicate_terminal_and_missing_phase(self):
        text=(m.RUN/'run.vcs.log').read_text()
        for bad in ('error','duplicate','missing','stall'):
            s=text
            if bad=='error':s+='\nUVM_ERROR actual error message\n'
            elif bad=='duplicate':s+='\nPASSED: qbs_payload_matrix4 commands=4 errors=0\n'
            elif bad=='missing':s=s.replace('QBS_MATRIX phase=3 checks=24 errors=0','')
            else:s=s.replace('req_stalled=0 resp_stalled=0','req_stalled=1 resp_stalled=0')
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'log';p.write_text(s)
                with self.assertRaises(ValueError):m.software(p)


if __name__=='__main__':unittest.main()
