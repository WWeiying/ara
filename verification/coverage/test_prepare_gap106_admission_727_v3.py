import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import prepare_gap106_admission_727_v3 as m
import xml.etree.ElementTree as ET


class Population(unittest.TestCase):
    def samples(self):
        prior = dict(tests=['old%d'%i for i in range(725)])
        before = dict(tests=prior['tests']+['old725'],design={'shape':'sealed'},input_hashes={'/input':'a'*64},
            metrics={'cond':{'ara_tb.dut.i_ara_soc.i_system':dict(width=4,checksum='1',bits='0x1')}})
        single = copy.deepcopy(before)
        single['tests'] = [str(m.qualifier.RUN/'code.vdb')]
        single['metrics']['cond']['ara_tb.dut.i_ara_soc.i_system']['bits']='0x2'
        return before,prior,single

    def test_exact726_prefix_and_measured_delta(self):
        before,prior,single = self.samples()
        combined,change = m.population(before,prior,single)
        self.assertEqual(combined['tests'][:-1],before['tests'])
        self.assertEqual(change['metrics'],{'cond':1})

    def test_zero_gain_rejected(self):
        before,prior,single = self.samples()
        single['metrics'] = copy.deepcopy(before['metrics'])
        with self.assertRaises(ValueError):m.population(before,prior,single)

    def test_wrong_prefix_rejected(self):
        before,prior,single = self.samples();before['tests'][0]='different'
        with self.assertRaises(ValueError):m.population(before,prior,single)

    def test_duplicate_test_rejected(self):
        before,prior,single = self.samples();before['tests'][-1]=single['tests'][0]
        with self.assertRaises(ValueError):m.population(before,prior,single)

    def test_expected_hash_conflict_rejected(self):
        before,prior,single = self.samples();single['input_hashes']['/input']='b'*64
        with self.assertRaises(ValueError):m.population(before,prior,single)

    def test_design_drift_rejected(self):
        before,prior,single = self.samples();single['design']['shape']='different'
        with self.assertRaises(ValueError):m.population(before,prior,single)

    def test_shape_drift_rejected(self):
        before,prior,single = self.samples()
        single['metrics']['cond']['ara_tb.dut.i_ara_soc.i_system']['checksum']='2'
        with self.assertRaises(ValueError):m.population(before,prior,single)

    def test_raw_bit_direction_not_source_index(self):
        row = dict(width=4,bits='0x8')
        self.assertTrue(m.bit(row,0));self.assertFalse(m.bit(row,3))
        with self.assertRaises(ValueError):m.bit(dict(width=4,bits='0x10'),0)


class Gates(unittest.TestCase):
    def records(self):
        record = dict(status='GAP106_SOFTWARE_NATIVE_QUALIFIED_NOT_ADMITTED',full_scalar_isa_verified=False,
            spike_custom_isa_pass=False,coverage_admitted=False,coverage_increment_measured=False,
            gain_requires_latest_formal_baseline=True,simulation_rerun=False,rtl_changed=False)
        audit = dict(status='GAP106_COMPLETE_SOFTWARE_NATIVE_PASS_NOT_FULL_SCALAR_ISA',custom_write_bytes=256,
            custom_active_bytes=8,custom_zero_tail_bytes=248,full_vrf_bytes=8192,initial_vrf_bytes=8192,
            csr_values=24,source_guard_bytes=6880,checks=41,full_scalar_isa_verified=False,
            spike_custom_isa_pass=False,coverage_admitted=False,bindings=[dict(phase=p,pc=pc,backend_vl=32,
                software_vl=1,native_total_write_bytes=128) for p,pc in [(0,0x8000017a),(1,0x80000252)]],
            contract=dict(requests=51,responses=51,exceptions=0,protocol_errors=0,outstanding=0,
                          req_stalled=0,resp_stalled=0))
        return record,audit

    def test_native_scope_exact(self):
        m.qualification_contract(*self.records())

    def test_core_success_not_qualification(self):
        record,audit = self.records();record['status']='SUCCESS'
        with self.assertRaises(ValueError):m.qualification_contract(record,audit)

    def test_false_full_isa_claim_rejected(self):
        record,audit = self.records();record['full_scalar_isa_verified']=True
        with self.assertRaises(ValueError):m.qualification_contract(record,audit)

    def test_wrong_pc_vl_writecount_rejected(self):
        for key,value in [('pc',0),('backend_vl',1),('native_total_write_bytes',4)]:
            record,audit = self.records();audit['bindings'][0][key]=value
            with self.assertRaises(ValueError):m.qualification_contract(record,audit)

    def test_bad_lifecycle_rejected(self):
        record,audit = self.records();audit['contract']['outstanding']=1
        with self.assertRaises(ValueError):m.qualification_contract(record,audit)

    def test_unqualified_no_collect_or_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'candidate'
            with patch.object(m.life,'OUT',Path(directory)),patch.object(m.life,'read_bound',side_effect=ValueError('reject')), \
                    patch.object(m.bitmap,'collect') as collect:
                with self.assertRaises(ValueError):m.prepare(output,'badseal')
                collect.assert_not_called();self.assertFalse(output.exists())


class NativeBinding(unittest.TestCase):
    def fixture(self):
        module=ET.Element('srcdef',dict(name='fpnew_fma',id='-171',chksum='2431620414'))
        params="FpFormat=0,NumPipeRegs=2,PipeConfig=3,WIDTH=32,EXP_BITS=8,MAN_BITS=23"
        tgl=ET.Element('tgldef',dict(id='-171',name='fpnew_fma ( parameter '+params+' )',chksum='tglseal'))
        shape=ET.Element('shape')
        cond=ET.SubElement(shape,'conddef',dict(id='-171',chksum='compiledseal',
                    name='fpnew_fma ( parameter '+params+' + '+params+' )'))
        scope=m.pre_scope()+'.i_fpnew.gen_operation_groups[0].i_opgroup_block.gen_parallel_slices[0].active_format.i_fmt_slice.gen_num_lanes[0].active_lane.lane_instance.i_fma'
        return shape,module,scope,dict(width=1,checksum=None),None,tgl

    def test_exact_full_parameter_binding_not_null_checksum_acceptance(self):
        args=self.fixture()
        with patch.object(m.inventory,'points',return_value=[dict(raw_index=0)]):
            definition,binding=m.native_definition(*args)
        self.assertEqual(definition.get('chksum'),'compiledseal')
        self.assertIn('full_parameter',binding)

    def test_other_scope_null_checksum_rejected(self):
        args=list(self.fixture());args[2]+='.other'
        with self.assertRaises(ValueError):m.native_definition(*args)

    def test_wrong_pipeline_variant_rejected(self):
        args=list(self.fixture())
        args[-1].set('name',args[-1].get('name').replace('NumPipeRegs=2','NumPipeRegs=4'))
        with self.assertRaises(ValueError):m.native_definition(*args)

    def test_ambiguous_definition_rejected(self):
        args=self.fixture();args[0].append(copy.deepcopy(args[0][0]))
        with self.assertRaises(ValueError):m.native_definition(*args)

    def test_data_info_checksum_mismatch_rejected(self):
        args=list(self.fixture());args[3]['checksum']='expected';args[4]='changed'
        with self.assertRaises(ValueError):m.native_definition(*args)


if __name__=='__main__':unittest.main()


