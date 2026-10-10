"""Synthetic OR/compiled fixtures, never measured GAP110 coverage evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import prepare_gap110_raw_gain_v2 as m
PRODUCT='ara_tb.dut.i_ara_soc.i_system.'


class Population(unittest.TestCase):
    def samples(self):
        metrics={k:{PRODUCT+k:dict(width=4,checksum='1',bits='0x1')} for k in ('line','branch','fsm')}
        metrics['cond']={PRODUCT+str(i):dict(width=4,checksum='1',bits='0x1') for i in range(6159)}
        before=dict(tests=['old%d'%i for i in range(733)],design={'shape':'sealed'},
                    input_hashes={'/input':'a'*64},metrics=metrics)
        single=copy.deepcopy(before);single['tests']=[str(m.qualifier.RUN/'code.vdb')]
        single['metrics']['cond'][PRODUCT+'0']['bits']='0x2'
        return before,single

    def test_exact6162_or_and733_prefix(self):
        before,single=self.samples();combined,delta=m.population(before,single)
        self.assertEqual(combined['tests'],before['tests']+single['tests'])
        self.assertEqual(len(set(combined['tests'])),734)
        self.assertEqual(delta['metrics'],dict(line=0,cond=1,branch=0,fsm=0))
        for metric,rows in before['metrics'].items():
            for scope,row in rows.items():
                self.assertEqual(int(combined['metrics'][metric][scope]['bits'],16),
                                 int(row['bits'],16)|int(single['metrics'][metric][scope]['bits'],16))

    def test_zero_gain_duplicate_and_pin_conflict_rejected(self):
        for mode in ('zero','duplicate','pin','width','design','instances'):
            before,single=self.samples()
            if mode=='zero':single['metrics']=copy.deepcopy(before['metrics'])
            elif mode=='duplicate':before['tests'][-1]=single['tests'][0]
            elif mode=='pin':single['input_hashes']['/input']='b'*64
            elif mode=='width':single['metrics']['cond'][PRODUCT+'0']['width']=5
            elif mode=='design':single['design']['shape']='other'
            else:del before['metrics']['cond'][PRODUCT+'1']
            with self.assertRaises(ValueError):m.population(before,single)


class Baseline(unittest.TestCase):
    def fixture(self):
        original=dict(tests=['old%d'%i for i in range(732)],design={'shape':'same'},input_hashes={'/input':'a'*64})
        before=copy.deepcopy(original);before['tests'].append('store-fault')
        manifest=dict(output=str(m.BASE),schema='STORE_FAULT_FLUSH_HISTORICAL_ADMISSION_V1',
                      output_pins={str(m.BASE/'status.json'):'a'*64})
        status=dict(aggregate_passed=733,coverage_admitted=True,status='PASS_RAW_UNION_HISTORICAL_ONLY')
        return manifest,status,before,original,m.BASE

    def test_formal733_not_static732(self):self.assertEqual(m.baseline_contract(*self.fixture()),733)

    def test_prefix_reorder_duplicate_unadmitted_foreign_rejected(self):
        for mode in ('prefix','duplicate','count','unadmitted','foreign','design'):
            args=self.fixture()
            if mode=='prefix':args[2]['tests'][0],args[2]['tests'][1]=args[2]['tests'][1],args[2]['tests'][0]
            elif mode=='duplicate':args[2]['tests'][-1]=args[2]['tests'][0]
            elif mode=='count':args[1]['aggregate_passed']=732
            elif mode=='unadmitted':args[1]['coverage_admitted']=False
            elif mode=='foreign':args[0]['output_pins']['/foreign']='b'*64
            else:args[2]['design']['shape']='changed'
            with self.assertRaises(ValueError):m.baseline_contract(*args)


class Qualification(unittest.TestCase):
    def records(self):
        record=dict(status='GAP110_SOFTWARE_NATIVE_QUALIFIED_NOT_ADMITTED',
            full_scalar_isa_verified=False,spike_custom_isa_pass=False,coverage_admitted=False,
            coverage_increment_measured=False,gain_requires_latest_formal_baseline=True,
            simulation_rerun=False,rtl_changed=False)
        audit=dict(status='GAP110_COMPLETE_SOFTWARE_NATIVE_PASS_NOT_FULL_SCALAR_ISA',
            custom_write_bytes=240,custom_active_bytes=240,custom_preserved_vrf_bytes=7952,
            full_vrf_bytes=8192,initial_vrf_bytes=8192,csr_values=24,source_guard_bytes=7328,
            checks=41,full_scalar_isa_verified=False,spike_custom_isa_pass=False,coverage_admitted=False,
            bindings=[dict(phase=p,pc=pc,backend_vl=160,software_vl=vl,native_total_write_bytes=count)
                      for p,pc,vl,count in [(0,0x8000017a,7,140),(1,0x80000252,5,100)]],
            contract=dict(requests=51,responses=51,exceptions=0,protocol_errors=0,outstanding=0,
                          req_stalled=0,resp_stalled=0),
            numeric_oracles=[{k:v[k] for k in ('result_bits','integer_dots','fflags','n')}
                             for v in m.qualifier.independent_native()])
        return record,audit

    def test_exact_bounded_native(self):m.qualification_contract(*self.records())

    def test_unqualified_fullisa_and_lifecycle_rejected(self):
        for mode in ('status','isa','bytes','vl','response','flags'):
            record,audit=self.records()
            if mode=='status':record['status']='SUCCESS'
            elif mode=='isa':record['full_scalar_isa_verified']=True
            elif mode=='bytes':audit['custom_write_bytes']=256
            elif mode=='vl':audit['bindings'][0]['software_vl']=1
            elif mode=='response':audit['contract']['responses']=50
            else:audit['numeric_oracles'][0]['fflags']=1
            with self.assertRaises(ValueError):m.qualification_contract(record,audit)

    def test_rejection_before_rawcollect_or_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(m.life,'OUT',Path(tmp)),patch.object(m,'BASE',Path(tmp)/'base'), \
                    patch.object(m,'QUAL',Path(tmp)/'qual'),patch.object(m,'CONFIG',Path(tmp)/'config'), \
                    patch.object(m.life,'read_bound',side_effect=ValueError('not qualified')), \
                    patch.object(m.bitmap,'collect') as collect:
                out=Path(tmp)/'fresh'
                with self.assertRaisesRegex(ValueError,'not qualified'):
                    m.prepare(out,m.BASE,m.BASE_SEAL,m.QUAL,m.QUAL_SEAL,m.CONFIG,m.CONFIG_SEAL,m.SAVED_SINGLE,m.SAVED_SHA)
                collect.assert_not_called();self.assertFalse(out.exists())

    def test_other_baseline_and_old_qualifier_rejected_before_read(self):
        for base,qual,config in [(m.BASE.with_name('old732'),m.QUAL,m.CONFIG),
                                (m.BASE,m.QUAL.with_name('old-v1'),m.CONFIG),
                                (m.BASE,m.QUAL,m.CONFIG.with_name('old-config'))]:
            with patch.object(m.life,'read_bound') as read:
                with self.assertRaises(ValueError):
                    m.prepare(m.life.OUT/'gap110-fixture-fresh',base,m.BASE_SEAL,qual,m.QUAL_SEAL,config,m.CONFIG_SEAL,m.SAVED_SINGLE,m.SAVED_SHA)
                read.assert_not_called()


class Compiled(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre=m.life.read_bound(m.qualifier.runner.PRE/'target-static-contract.json',m.qualifier.runner.TARGET_SEAL)
        manifest=m.life.read_bound(m.BASE/'admission-manifest.json',m.BASE_SEAL)
        cls.full=m.life.read_bound(m.BASE/'combined-bits.json',manifest['output_pins'][str(m.BASE/'combined-bits.json')])

    def fixture(self):
        scope=self.pre['targets'][0]['scope']
        before=dict(metrics={'cond':{scope:copy.deepcopy(self.full['metrics']['cond'][scope])},
                             'line':{},'branch':{},'fsm':{}})
        single=copy.deepcopy(before)
        row=single['metrics']['cond'][scope];bits=int(row['bits'],16)
        for target in self.pre['targets']:bits|=1<<(row['width']-1-target['point']['raw_index'])
        row['bits']=hex(bits)
        return before,single,copy.deepcopy(single)

    def test_exact26_compiled_leaf_and733_zero_binding_synthetic_hits(self):
        before,single,combined=self.fixture()
        gained,hits=m.compiled(before,single,combined,self.pre,lambda p:Path(p).read_bytes())
        self.assertEqual(len(gained),26);self.assertEqual(len(hits),26)
        self.assertTrue(all(not h['before_hit'] and h['single_hit'] and h['after_hit'] for h in hits))

    def test_native_coordinate_and_missing_target_hit_rejected(self):
        before,single,combined=self.fixture()
        bad=copy.deepcopy(self.pre);bad['targets'][0]['point']['native_id']='wrong'
        with self.assertRaisesRegex(ValueError,'compiled identity'):
            m.compiled(before,single,combined,bad,lambda p:Path(p).read_bytes())
        with self.assertRaisesRegex(ValueError,'Not all26'):
            m.compiled(before,before,before,self.pre,lambda p:Path(p).read_bytes())


class Sources(unittest.TestCase):
    def test_profile_integer_engine_exact_historical_pin_and_drift_rejected(self):
        path=m.life.ROOT/'hardware/src/vlsu/qbs/qbs_profile_engine_int.sv'
        build=m.life.read_bound(m.qualifier.BUILD,m.qualifier.BUILD_SHA)
        expected='576304613df34547c7d80b04739a4a0164febd719cfcbc463d6465db6d966978'
        pins=m.historical_source_pin(path,build)
        self.assertEqual(pins,{str(path):expected})
        m.life.check(pins)
        with patch.object(m.life,'digest',return_value='0'*64):
            with self.assertRaises(ValueError):m.life.check(pins)
        with self.assertRaises(ValueError):m.historical_source_pin(path,{})
        with self.assertRaises(ValueError):
            m.life.merge_pins({str(path):'0'*64},pins)
        foreign=path.with_name('qbs_profile_engine_other.sv')
        with self.assertRaises(ValueError):
            m.historical_source_pin(foreign,{str(foreign):expected})

    def test_historical_build_expected_not_current_hash(self):
        path=m.life.ROOT/'hardware/src/vlsu/qbs/qbs_payload_buffer.sv'
        self.assertEqual(m.historical_source_pin(path,{str(path):'a'*64}),{str(path):'a'*64})
        with self.assertRaises(ValueError):m.life.merge_pins({str(path):'b'*64},m.historical_source_pin(path,{str(path):'a'*64}))

    def test_foreign_dotdot_and_missing_buildpin_rejected(self):
        path=m.life.ROOT/'hardware/src/vlsu/qbs/qbs_payload_buffer.sv'
        for other in (path.with_name('foreign.sv'),Path(str(path.parent)+'/../qbs/'+path.name)):
            with self.assertRaises(ValueError):m.historical_source_pin(other,{str(other):'a'*64})
        with self.assertRaises(ValueError):m.historical_source_pin(path,{})


class HelperAncestry(unittest.TestCase):
    def records(self):
        base=m.qualifier.runner.BASE
        manifest=m.life.read_bound(base/'admission-manifest.json',m.qualifier.runner.BASE_SEAL)
        path=base/'evidence-pins.json'
        book=m.life.read_bound(path,manifest['output_pins'][str(path)])
        for name in ('gap108-offline-admitted-730-parent-20261006-01',
                     'gap106-offline-admitted-727-parent-20261006-01'):
            path=m.life.OUT/name/'evidence-pins.json'
            book=m.life.merge_pins(book,m.life.read_bound(path,book[str(path)]))
        qualified=m.life.read_bound(m.QUAL/'qualification.json',m.QUAL_SEAL)
        pins=m.life.read_bound(m.QUAL/'evidence-pins.json',qualified['pins_sha256'])
        return pins,book

    def test_recursive_mapping_actual_historical_sha_not_current_trust(self):
        pins,book=self.records()
        bound=m.bind_reused_helpers(pins,book)
        for name,sha in (
            ('prepare_gap107_raw_gain_v2.py','18252cdd98c2c5c8d0e01e9959477bee65fb37b484224aa9c89436957b949794'),
            ('prepare_gap106_admission_727_v4.py','2f478a6b551730f878bdc17d738b052960be01d5d22203b75e19591ddac8f8e3'),
            ('qualify_gap106_native.py','70404f4e7a18e54f2323ab0c9076e44b59f7097a117e4f437c5e337cc80c7cde'),
            ('run_gap106_simulation.py','cd1a1eecf492305a8623eeafbe9e47fa23cd1ff904734cb7c5c2a08cb8db9619')):
            self.assertEqual(bound[str(Path(m.__file__).with_name(name))],sha)

    def test_missing_conflicting_or_changed_recursive_helper_rejected(self):
        target=str(Path(m.mapping.mapping.mapping.__file__).resolve())
        for mode in ('missing','conflict','drift'):
            pins,book=self.records()
            pins.pop(target,None)
            if mode=='missing':book.pop(target)
            elif mode=='conflict':pins[target]='0'*64
            else:book[target]='0'*64
            with self.assertRaises(ValueError):m.bind_reused_helpers(pins,book)

    def test_actual_prepare_verifies_saved_compiled_gain_before_output(self):
        output=m.life.OUT/'gap110-fixture-only-before-collect'
        self.assertFalse(output.exists())
        class GateReached(Exception):pass
        actual_compiled=m.compiled
        def verify_compiled(*args):
            gained,hits=actual_compiled(*args)
            self.assertEqual(len(gained),35)
            self.assertEqual(len(hits),26)
            self.assertEqual(sum(len(rows) for rows in args[0]['metrics'].values()),6162)
            self.assertTrue(all(not h['before_hit'] and h['single_hit'] and h['after_hit'] for h in hits))
            source_counts={}
            for point in gained:
                self.assertEqual(point['metric'],'cond')
                source_counts[point['source']]=source_counts.get(point['source'],0)+1
            self.assertEqual(source_counts,{
                str(m.life.ROOT/'hardware/src/vlsu/qbs/qbs_payload_buffer.sv'):32,
                str(m.life.ROOT/'hardware/src/vlsu/qbs/qbs_profile_engine_int.sv'):3})
            return gained,hits
        with patch.object(Path,'mkdir',side_effect=GateReached) as mkdir, \
                patch.object(m.bitmap,'collect') as collect, \
                patch.object(m,'compiled',side_effect=verify_compiled) as compiled:
            with self.assertRaises(GateReached):
                m.prepare(output,m.BASE,m.BASE_SEAL,m.QUAL,m.QUAL_SEAL,m.CONFIG,m.CONFIG_SEAL,m.SAVED_SINGLE,m.SAVED_SHA)
            compiled.assert_called_once();mkdir.assert_called_once();collect.assert_not_called()
        self.assertFalse(output.exists())


class CompiledReadGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest=m.life.read_bound(m.BASE/'admission-manifest.json',m.BASE_SEAL)
        cls.before=m.life.read_bound(m.BASE/'combined-bits.json',manifest['output_pins'][str(m.BASE/'combined-bits.json')])
        cls.single=m.life.read_bound(m.SAVED_SINGLE,m.SAVED_SHA)
        cls.combined,cls.change=m.population(cls.before,cls.single)

    def test_all_selected_actual_design_inputs_bound_before_parse(self):
        pins,book=HelperAncestry().records()
        bound=m.bind_compiled_inputs(pins,book,self.before,self.combined)
        paths=m.compiled_inputs(self.before,self.combined)
        self.assertEqual(len(paths),9)
        info=m.DESIGN/'snps/coverage/db/shape/tgl.verilog.info.xml'
        self.assertEqual(bound[str(info)],'5603b64b35df34925586b68ba6bf429c7e92836b239c94e9c193c666e3d70b0a')
        self.assertEqual(self.change['metrics'],dict(line=0,cond=35,branch=0,fsm=0))

    def test_missing_or_conflicting_tgl_info_pin_rejected(self):
        info=m.DESIGN/'snps/coverage/db/shape/tgl.verilog.info.xml'
        for mode in ('missing','conflict','drift'):
            pins,book=HelperAncestry().records();pins.pop(str(info),None)
            before=copy.deepcopy(self.before)
            before['design'].pop('shape/tgl.verilog.info.xml',None)
            if mode=='missing':book.pop(str(info),None)
            elif mode=='conflict':pins[str(info)]='0'*64
            else:book[str(info)]='0'*64
            with self.assertRaises(ValueError):m.bind_compiled_inputs(pins,book,before,self.combined)

    def test_compiled_readgate_before_any_xml_parser(self):
        info=m.DESIGN/'snps/coverage/db/shape/tgl.verilog.info.xml'
        def read(path):
            if path==info:raise ValueError('missing tgl expected pin')
            return Path(path).read_bytes()
        with patch.object(m.inventory,'read_xml') as parse:
            with self.assertRaisesRegex(ValueError,'missing tgl expected pin'):
                m.compiled(self.before,self.single,self.combined,{'targets':[]},read)
            parse.assert_not_called()

    def test_saved_singleton_only_before_any_read_or_collection(self):
        for path,seal in ((None,None),(m.SAVED_SINGLE,'0'*64),
                          (m.SAVED_SINGLE.with_name('other.json'),m.SAVED_SHA)):
            with patch.object(m.life,'read_bound') as read,patch.object(m.bitmap,'collect') as collect:
                with self.assertRaisesRegex(ValueError,'preserved'):
                    m.prepare(m.life.OUT/'gap110-v2-test-only-fresh',m.BASE,m.BASE_SEAL,
                              m.QUAL,m.QUAL_SEAL,m.CONFIG,m.CONFIG_SEAL,path,seal)
                read.assert_not_called();collect.assert_not_called()

    def test_actual_written_input_lines_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'single-inputs.txt'
            m.write_single_inputs(path)
            self.assertEqual(path.read_text().splitlines(),[str(m.DESIGN),str(m.qualifier.RUN/'code.vdb')])
            self.assertTrue(path.read_bytes().endswith(bytes([10])))
            with self.assertRaises(FileExistsError):m.write_single_inputs(path)
    def test_actual_prepare_missing_ancestor_helper_rejected_before_replay_or_output(self):
        output=m.life.OUT/'gap110-fixture-only-missing-helper'
        target=str(Path(m.mapping.mapping.mapping.__file__).resolve())
        original=m.life.read_bound
        def read(path,seal):
            value=original(path,seal)
            if Path(path).name=='evidence-pins.json':
                value=dict(value);value.pop(target,None)
            return value
        with patch.object(m.life,'read_bound',read),patch.object(m.qualifier,'runtime') as replay, \
                patch.object(m.bitmap,'collect') as collect,patch.object(Path,'mkdir') as mkdir:
            with self.assertRaisesRegex(ValueError,'Unbound reused helper'):
                m.prepare(output,m.BASE,m.BASE_SEAL,m.QUAL,m.QUAL_SEAL,m.CONFIG,m.CONFIG_SEAL,m.SAVED_SINGLE,m.SAVED_SHA)
            replay.assert_not_called();collect.assert_not_called();mkdir.assert_not_called()
        self.assertFalse(output.exists())


if __name__=='__main__':unittest.main()
