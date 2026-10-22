import dataclasses
import json
import unittest
from unittest.mock import patch

import preflight_vsmul_saturation796 as tool


class HostTests(unittest.TestCase):
    def test_saturation_and_signed_rounding_all_widths(self):
        for width in (8,16,32,64):
            low=-(1<<(width-1))
            self.assertEqual(tool.rounded_multiply(low,low,width),(-low-1,1))
            self.assertEqual(tool.rounded_multiply(low+1,low//2+1,width),(-low//2-1,0))
            self.assertEqual(tool.rounded_multiply(0,0,width),(0,0))
            self.assertEqual(tool.rounded_multiply(-1,1,width),(0,0))

    def test_all_four_lanes_one_full_packet_defined_tail(self):
        for i in range(12):
            row=tool.case(i)
            self.assertEqual(row['vl']*row['width'],256)
            self.assertEqual([len(v) for v in row['sources']],[128,128])
            self.assertEqual(row['destination'][32:],bytes([0x5a])*96)
            self.assertEqual(row['csr'][4],int(i%3==0))
        self.assertEqual(12*(2*20+3*20+6),tool.CHECKS)

    def test_bad_domain_rejected(self):
        for args in ((128,0,8),(0,0,128),(-129,0,8)):
            with self.assertRaises(ValueError):tool.rounded_multiply(*args)
        for index in (-1,12):
            with self.assertRaises(ValueError):tool.case(index)

    def test_exact_linked_no_implicit_vector(self):
        names=['vsetvli','vle8.v','vle8.v','vmv.v.x','vsetvl','vsmul.vv','vs1r.v','vs1r.v','vs1r.v']
        text='\n'.join('80002000: 02000057 '+n for n in names)
        self.assertEqual(tool.linked(text),names)
        with self.assertRaises(ValueError):tool.linked(text+'\n80003000: 02000057 vle64.v')

    def test_source_is_separate_linked_storage_not_merged_constant(self):
        text=tool.header()
        self.assertIn('\nvolatile uint64_t sm_source[12][2][20]',text)
        self.assertIn('static const uint64_t sm_source_gold',text)

    def test_actual796_zero_targets_and_EL_no_collision(self):
        evidence=tool.source_evidence()
        self.assertEqual((evidence['population'],evidence['zero_slots'],len(evidence['targets'])),(796,114,15))
        self.assertEqual(len(evidence['protected_group5_missing_HOLD']),8)
        self.assertFalse(evidence['EDA_started'])


class ActualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=tool.DEFAULT_OUT/'preflight.json'
        if not path.exists():raise unittest.SkipTest('Software preflight not built yet')
        cls.pre=json.loads(path.read_bytes());cls.symbols=cls.pre['symbols']
        cls.trace=tool.Path(cls.pre['reference']);cls.commits=tool.build.parse_spike_commits(cls.trace)

    def reject(self,commits):
        with patch.object(tool.build,'parse_spike_commits',return_value=commits):
            with self.assertRaises(ValueError):tool.validate(self.trace,self.symbols)

    def test_actual_1272_checks_and_all_writers(self):
        counts=tool.validate(self.trace,self.symbols)
        self.assertEqual(counts,{k:v for k,v in self.pre['counts'].items() if k!='runtime'})

    def test_wrong_saturated_result(self):
        rows=list(self.commits);i=next(i for i,c in enumerate(rows) if c.pc==self.symbols['sm_target'])
        rows[i]=dataclasses.replace(rows[i],vector_writes={24:0});self.reject(rows)

    def test_wrong_VL_or_prestart(self):
        rows=list(self.commits);i=next(i for i,c in enumerate(rows) if c.pc==self.symbols['sm_target'])
        for field,value in (('vector_vl',1),('vector_vstart',1),('vector_sew',64)):
            bad=list(rows);bad[i]=dataclasses.replace(rows[i],**{field:value});self.reject(bad)

    def test_missing_snapshot(self):
        rows=list(self.commits);i=next(i for i,c in enumerate(rows) if c.pc==self.symbols['sm_store_d'])
        self.reject(rows[:i]+rows[i+1:])

    def test_wrong_vxsat_or_guard(self):
        for address in (self.symbols['sm_csr']+32,self.symbols['sm_snapshot']):
            rows=list(self.commits);i=next(i for i,c in enumerate(rows) if any(a==address and v not in (None,0) for a,v in c.memory_accesses))
            c=rows[i];rows[i]=dataclasses.replace(c,memory_accesses=tuple((a,0 if a==address else v) for a,v in c.memory_accesses))
            self.reject(rows)


if __name__=='__main__':unittest.main()
