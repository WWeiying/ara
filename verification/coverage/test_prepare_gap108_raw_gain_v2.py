import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import prepare_gap108_raw_gain_v2 as m
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

    def test_exact_explicit_prefix_and_measured_delta(self):
        before,prior,single = self.samples()
        combined,change = m.population(before,single)
        self.assertEqual(combined['tests'][:-1],before['tests'])
        self.assertEqual(change['metrics'],{'cond':1})

    def test_zero_gain_rejected(self):
        before,prior,single = self.samples()
        single['metrics'] = copy.deepcopy(before['metrics'])
        with self.assertRaises(ValueError):m.population(before,single)


    def test_duplicate_test_rejected(self):
        before,prior,single = self.samples();before['tests'][-1]=single['tests'][0]
        with self.assertRaises(ValueError):m.population(before,single)

    def test_expected_hash_conflict_rejected(self):
        before,prior,single = self.samples();single['input_hashes']['/input']='b'*64
        with self.assertRaises(ValueError):m.population(before,single)

    def test_design_drift_rejected(self):
        before,prior,single = self.samples();single['design']['shape']='different'
        with self.assertRaises(ValueError):m.population(before,single)

    def test_shape_drift_rejected(self):
        before,prior,single = self.samples()
        single['metrics']['cond']['ara_tb.dut.i_ara_soc.i_system']['checksum']='2'
        with self.assertRaises(ValueError):m.population(before,single)

    def test_raw_bit_direction_not_source_index(self):
        row = dict(width=4,bits='0x8')
        self.assertTrue(m.bit(row,0));self.assertFalse(m.bit(row,3))
        with self.assertRaises(ValueError):m.bit(dict(width=4,bits='0x10'),0)


class Gates(unittest.TestCase):
    def records(self):
        record = dict(status='GAP108_SOFTWARE_NATIVE_QUALIFIED_NOT_ADMITTED',full_scalar_isa_verified=False,
            spike_custom_isa_pass=False,coverage_admitted=False,coverage_increment_measured=False,
            gain_requires_latest_formal_baseline=True,simulation_rerun=False,rtl_changed=False)
        audit = dict(status='GAP108_COMPLETE_SOFTWARE_NATIVE_PASS_NOT_FULL_SCALAR_ISA',custom_write_bytes=256,
            custom_active_bytes=8,custom_zero_tail_bytes=248,full_vrf_bytes=8192,initial_vrf_bytes=8192,
            csr_values=24,source_guard_bytes=6880,checks=41,full_scalar_isa_verified=False,
            spike_custom_isa_pass=False,coverage_admitted=False,bindings=[dict(phase=p,pc=pc,backend_vl=32,
                software_vl=1,native_total_write_bytes=128) for p,pc in [(0,0x8000017a),(1,0x80000252)]],
            contract=dict(requests=51,responses=51,exceptions=0,protocol_errors=0,outstanding=0,
                          req_stalled=0,resp_stalled=0))
        audit['numeric_oracles'] = [{k:v[k] for k in ('result_bits','integer_dot','integer_correction',
            'fflags','stage_bits','stage_flags')} for v in m.qualifier.independent_native()]
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
            qual = Path(directory)/'qual'
            with patch.object(m.life,'OUT',Path(directory)),patch.object(m,'QUAL',qual), \
                    patch.object(m,'BASE',Path(directory)/'base'), \
                    patch.object(m,'CONFIG',Path(directory)/'config'), \
                    patch.object(m.life,'read_bound',side_effect=ValueError('reject')) as bound, \
                    patch.object(m.bitmap,'collect') as collect:
                with self.assertRaisesRegex(ValueError, 'reject'):
                    m.prepare(output,m.BASE,m.BASE_SEAL,qual,m.QUAL_SEAL,m.CONFIG,m.CONFIG_SEAL)
                bound.assert_called_once()
                collect.assert_not_called();self.assertFalse(output.exists())

    def test_nonparent_qualification_seal_rejected_before_read(self):
        with patch.object(m.life, 'read_bound') as read, patch.object(m.bitmap, 'collect') as collect:
            with self.assertRaisesRegex(ValueError, 'parent qualified'):
                m.prepare(m.life.OUT/'gap108-test-only-fresh-output', m.BASE, m.BASE_SEAL,
                          m.QUAL.with_name('other'), '0'*64, m.CONFIG, m.CONFIG_SEAL)
            read.assert_not_called(); collect.assert_not_called()


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

    def test_branch_full_parameter_binding_and_metric_width(self):
        args=self.fixture()
        with patch.object(m.inventory,'points',return_value=[dict(raw_index=0)]) as points:
            m.native_definition(*args,metric='branch')
            self.assertEqual(points.call_args[0][0],'branch')

    def test_unreviewed_missing_fsm_checksum_rejected(self):
        with self.assertRaises(ValueError):m.native_definition(*self.fixture(),metric='fsm')

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







class DynamicBaseline(unittest.TestCase):
    def fixture(self, count=729):
        base = m.life.OUT/'explicit-formal-baseline'
        original = dict(tests=['old%d'%i for i in range(729)], design={'shape':'old'},
                        input_hashes={'/old':'a'*64})
        before = copy.deepcopy(original)
        before['tests'] += ['new%d'%i for i in range(count-729)]
        manifest = dict(output=str(base), schema='EXAMPLE_ADMISSION_V1',
                        output_pins={str(base/'status.json'):'b'*64})
        status = dict(aggregate_passed=count, coverage_admitted=True, status='PASS_RAW_UNION_HISTORICAL_ONLY')
        return manifest,status,before,original,base

    def test_explicit_later_baseline_not_relabelled727(self):
        args = self.fixture()
        self.assertEqual(m.baseline_contract(*args), 729)

    def test_exact_original727_allowed(self):
        self.assertEqual(m.baseline_contract(*self.fixture(729)), 729)

    def test_prefix_reorder_or_drift_rejected(self):
        args = self.fixture()
        args[2]['tests'][0], args[2]['tests'][1] = args[2]['tests'][1], args[2]['tests'][0]
        with self.assertRaisesRegex(ValueError, 'prefix'): m.baseline_contract(*args)

    def test_duplicate_or_wrong_count_rejected(self):
        for mode in ('duplicate', 'count'):
            args = self.fixture()
            if mode == 'duplicate': args[2]['tests'][-1] = args[2]['tests'][0]
            else: args[1]['aggregate_passed'] = 730
            with self.assertRaises(ValueError): m.baseline_contract(*args)

    def test_baseline_unadmitted_or_alias_rejected(self):
        for mode in ('unadmitted', 'alias', 'outside', 'schema'):
            args = self.fixture()
            if mode == 'unadmitted': args[1]['coverage_admitted'] = False
            elif mode == 'alias': args[0]['output'] = str(args[4]) + '-alias'
            elif mode == 'outside': args[0]['output_pins']['/outside/status.json'] = 'b'*64
            else: args[0]['schema'] = 'PREPARED'
            with self.assertRaises(ValueError): m.baseline_contract(*args)

    def test_original_pin_conflict_or_design_drift_rejected(self):
        for mode in ('pins', 'design'):
            args = self.fixture()
            if mode == 'pins': args[2]['input_hashes']['/old'] = 'c'*64
            else: args[2]['design']['shape'] = 'changed'
            with self.assertRaises(ValueError): m.baseline_contract(*args)


class NumericGate(unittest.TestCase):
    def test_old_finite_or_wrong_invalid_flags_rejected(self):
        for key, value in (('result_bits',0x7f800000), ('fflags',16), ('stage_flags',[0]*6)):
            record,audit = Gates().records()
            audit['numeric_oracles'][1][key] = value
            with self.assertRaisesRegex(ValueError, 'numeric'): m.qualification_contract(record,audit)

    def test_target_contract_is_frozen_seven_coordinates(self):
        record = m.life.read_bound(m.qualifier.runner.PRE/'target-static-contract.json',
                                   m.qualifier.runner.TARGET_SEAL)
        self.assertEqual(len(record['targets']),7)
        self.assertEqual(len({(r['scope'],r['point']['raw_index']) for r in record['targets']}),7)



class HistoricalTargetSource(unittest.TestCase):
    def test_expected_build_pin_not_current_hash(self):
        path = m.life.ROOT/'hardware/deps/fpnew/src/fpnew_rounding.sv'
        self.assertEqual(m.historical_source_pin(path, {str(path):'a'*64}), {str(path):'a'*64})

    def test_other_source_or_alias_not_accepted(self):
        path = m.life.ROOT/'hardware/deps/fpnew/src/fpnew_rounding.sv'
        for other in (path.with_name('fpnew_cast_multi.sv'), Path(str(path.parent)+'/../src/'+path.name)):
            with self.assertRaises(ValueError):
                m.historical_source_pin(other, {str(other):'a'*64})

    def test_missing_expected_pin_or_conflict_rejected(self):
        path = m.life.ROOT/'hardware/deps/fpnew/src/fpnew_rounding.sv'
        with self.assertRaises(ValueError): m.historical_source_pin(path, {})
        with self.assertRaises(ValueError):
            m.life.merge_pins({str(path):'b'*64}, m.historical_source_pin(path,{str(path):'a'*64}))


class ReviewedInputs(unittest.TestCase):
    def test_seal_requires_full_lowercase_sha(self):
        for seal in ('', 'x'*64, 'A'*64, None, 'a'*63):
            with self.assertRaises(ValueError): m.seal_contract(seal)
        m.seal_contract('a'*64)

    def test_other_baseline_or_config_rejected_before_read(self):
        for base, seal, config, config_seal in (
                (m.BASE, 'b'*64, m.CONFIG, m.CONFIG_SEAL),
                (m.BASE.with_name('old728'), m.BASE_SEAL, m.CONFIG, m.CONFIG_SEAL),
                (m.BASE, m.BASE_SEAL, m.CONFIG, 'b'*64)):
            with patch.object(m.life,'read_bound') as read, patch.object(m.bitmap,'collect') as collect:
                with self.assertRaises(ValueError):
                    m.prepare(m.life.OUT/'gap108-test-only-fresh',base,seal,m.QUAL,m.QUAL_SEAL,config,config_seal)
                read.assert_not_called();collect.assert_not_called()

    def test_new_rounding_source_expected_build_pin_conflict_rejected(self):
        path=m.life.ROOT/'hardware/deps/fpnew/src/fpnew_rounding.sv'
        with self.assertRaises(ValueError):
            m.life.merge_pins({str(path):'b'*64},m.historical_source_pin(path,{str(path):'a'*64}))

class HistoricalLzc(unittest.TestCase):
    def row(self):
        path = m.DESIGN/'snps/coverage/db/shape/cond.verilog.shape.xml'
        shape = m.inventory.read_xml(path)
        definitions = [node for node in shape if node.tag == 'conddef' and
                       node.get('chksum') == '1006763157']
        self.assertEqual(len(definitions), 1)
        points = {p['raw_index']:p for p in m.inventory.points('cond', definitions[0], 392)}
        return dict(scope=m.LZC_SCOPE,metric='cond',width=392,checksum='1006763157',
            compiled_definition_checksum='1006763157',binding='data_and_metric_info_checksum',
            source=str(m.LZC_SOURCE),point=points[8],before_hit=False,single_hit=True,after_hit=True)

    def test_real_compiled_point_exact(self):
        m.lzc_gain_contract([self.row()])

    def test_exact_path_build_pin(self):
        self.assertEqual(m.historical_lzc_pin(m.LZC_SOURCE,{str(m.LZC_SOURCE):m.LZC_SHA}),
                         {str(m.LZC_SOURCE):m.LZC_SHA})

    def test_other_source_dotdot_missing_build_or_hash_drift(self):
        for path,book in (
                (m.LZC_SOURCE.with_name('other.sv'),{str(m.LZC_SOURCE.with_name('other.sv')):m.LZC_SHA}),
                (Path(str(m.LZC_SOURCE.parent)+'/../src/lzc.sv'),{str(m.LZC_SOURCE):m.LZC_SHA}),
                (m.LZC_SOURCE,{}), (m.LZC_SOURCE,{str(m.LZC_SOURCE):'0'*64})):
            with self.assertRaises(ValueError):m.historical_lzc_pin(path,book)

    def test_source_symlink_and_expected_pin_conflict_rejected(self):
        with patch.object(Path,'is_symlink',return_value=True):
            with self.assertRaises(ValueError):
                m.historical_lzc_pin(m.LZC_SOURCE,{str(m.LZC_SOURCE):m.LZC_SHA})
        with self.assertRaises(ValueError):
            m.life.merge_pins({str(m.LZC_SOURCE):'0'*64},
                m.historical_lzc_pin(m.LZC_SOURCE,{str(m.LZC_SOURCE):m.LZC_SHA}))

    def test_actual_source_drift_checked_not_rebased(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'lzc.sv';path.write_text('changed source')
            with patch.object(m,'LZC_SOURCE',path):
                pins=m.historical_lzc_pin(path,{str(path):m.LZC_SHA})
                with self.assertRaises(ValueError):m.life.check(pins)

    def test_missing_duplicate_and_other_instance_rejected(self):
        row=self.row()
        for rows in ([],[row,row],[dict(row,scope=m.LZC_SCOPE+'.other')]):
            with self.assertRaises(ValueError):m.lzc_gain_contract(rows)

    def test_raw_native_vector_expression_generate_checksum_drift(self):
        for key,value in (('raw_index',9),('native_id','5'),('file_id','other'),
                          ('vector','10'),('expression','different'),('row',0)):
            row=self.row();row['point'][key]=value
            with self.assertRaises(ValueError):m.lzc_gain_contract([row])
        for key,value in (('checksum','0'),('width',391),('single_hit',False),
                          ('compiled_definition_checksum','0')):
            with self.assertRaises(ValueError):m.lzc_gain_contract([dict(self.row(),**{key:value})])
        for field,key,value in (('spec','generate_info','level=2,l=0'),
                                ('attributes','chksum','0'),
                                ('truth_table','vecs','001110')):
            row=self.row();row['point'][field][key]=value
            with self.assertRaises(ValueError):m.lzc_gain_contract([row])

    def test_wrong_saved_singleton_or_seal_no_read_or_collect(self):
        for path,seal in ((m.ORIGINAL_SINGLE,'0'*64),
                          (m.ORIGINAL_SINGLE.with_name('other.json'),m.ORIGINAL_SINGLE_SEAL)):
            with patch.object(m.life,'read_bound') as read,patch.object(m.bitmap,'collect') as collect:
                with self.assertRaises(ValueError):
                    m.prepare(m.life.OUT/'gap108-test-only-fresh',m.BASE,m.BASE_SEAL,m.QUAL,m.QUAL_SEAL,
                              m.CONFIG,m.CONFIG_SEAL,path,seal)
                read.assert_not_called();collect.assert_not_called()

    def test_other_qualification_seal_rejected_before_read(self):
        with patch.object(m.life,'read_bound') as read,patch.object(m.bitmap,'collect') as collect:
            with self.assertRaises(ValueError):
                m.prepare(m.life.OUT/'gap108-test-only-fresh',m.BASE,m.BASE_SEAL,m.QUAL,'0'*64,
                          m.CONFIG,m.CONFIG_SEAL)
            read.assert_not_called();collect.assert_not_called()


if __name__ == '__main__': unittest.main()

