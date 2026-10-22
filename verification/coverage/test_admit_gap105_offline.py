"""Admission boundaries; no simulator, bitmap collection, or formal admission."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

import admit_gap105_offline as m


def samples():
    tests = [str(m.OUT/('sealed-test-%d/code.vdb'%i)) for i in range(724)]
    before = dict(design={'shape':'same'},tests=tests,input_hashes={'/expected/input':'a'*64},
        metrics={k:{} for k in ('line','cond','branch','fsm')})
    single = copy.deepcopy(before); single['tests'] = [str(m.RUN/'code.vdb')]
    single['input_hashes'] = {'/new/input':'b'*64}
    for scope,count in m.GAINS.items():
        row = dict(width=count+1,checksum='123',bits='0x0')
        before['metrics']['cond'][scope] = row
        single['metrics']['cond'][scope] = dict(row,bits=hex((1<<count)-1))
    return before,single


class Population(unittest.TestCase):
    def test_exact724_prefix_single725_and191(self):
        before,single = samples(); combined,delta = m.population(before,single)
        self.assertEqual(combined['tests'],before['tests']+[str(m.RUN/'code.vdb')])
        self.assertEqual(delta['metrics'],m.EXPECTED_DELTA)

    def test_duplicate_or_foreign_singleton_rejected(self):
        for variant in ('duplicate','foreign','double'):
            before,single = samples()
            if variant=='duplicate': before['tests'][-1] = str(m.RUN/'code.vdb')
            elif variant=='foreign': single['tests'] = [str(m.OUT/'foreign/code.vdb')]
            else: single['tests'] *= 2
            with self.assertRaises(ValueError): m.population(before,single)

    def test_wrong_baseline_size_or_duplicates_rejected(self):
        for variant in ('size','duplicate'):
            before,single = samples()
            if variant=='size': before['tests'].pop()
            else: before['tests'][-1] = before['tests'][0]
            with self.assertRaises(ValueError): m.population(before,single)

    def test_expected_pin_conflict_not_overwritten(self):
        before,single = samples(); single['input_hashes']['/expected/input'] = '0'*64
        original = copy.deepcopy(before)
        with self.assertRaisesRegex(ValueError,'Conflicting'): m.population(before,single)
        self.assertEqual(before,original)

    def test_no_fresh_gain_rejected(self):
        before,single = samples()
        single['metrics'] = copy.deepcopy(before['metrics'])
        with self.assertRaisesRegex(ValueError,'fresh191'): m.population(before,single)

    def test_wrong_count_scope_or_noncondition_gain_rejected(self):
        for variant in ('count','scope','branch'):
            before,single = samples(); scope = next(iter(m.GAINS))
            if variant=='count': single['metrics']['cond'][scope]['bits'] = '0x1'
            elif variant=='scope':
                before['metrics']['cond'][scope+'.wrong'] = before['metrics']['cond'].pop(scope)
                single['metrics']['cond'][scope+'.wrong'] = single['metrics']['cond'].pop(scope)
            else:
                before['metrics']['branch'][scope] = dict(width=1,checksum='1',bits='0x0')
                single['metrics']['branch'][scope] = dict(width=1,checksum='1',bits='0x1')
            with self.assertRaises(ValueError): m.population(before,single)

    def test_shape_width_or_checksum_changed_rejected(self):
        for key,value in [('width',999),('checksum','wrong')]:
            before,single = samples(); single['metrics']['cond'][next(iter(m.GAINS))][key] = value
            with self.assertRaises(ValueError): m.population(before,single)

    def test_raw_indices_msb_first_and_overflow(self):
        row = dict(width=4,bits='0x8')
        self.assertTrue(m.bit(row,0)); self.assertFalse(m.bit(row,3))
        for i in (-1,4):
            with self.assertRaises(ValueError): m.bit(row,i)
        with self.assertRaises(ValueError): m.bit(dict(width=4,bits='0x10'),0)


class Seals(unittest.TestCase):
    def test_only_reviewed_seals_before_read(self):
        for base,qual in [('0'*64,m.QUAL_SEAL),(m.BASE_SEAL,'0'*64)]:
            with patch.object(m,'bound') as read:
                with self.assertRaises(ValueError): m.evaluate(base,qual)
                read.assert_not_called()

    def test_explicit_admit_seal_required_before_evaluate(self):
        with patch.object(m,'evaluate') as evaluate:
            with self.assertRaises(ValueError):
                m.main(['admit','--output',str(m.OUT/'unused725'),'--base-seal',m.BASE_SEAL,
                        '--qualification-seal',m.QUAL_SEAL])
            evaluate.assert_not_called()

    def test_existing_output_never_overwritten(self):
        with patch.object(m,'evaluate') as evaluate:
            with self.assertRaises(ValueError):
                m.main(['prepare','--output',str(m.QUAL),'--base-seal',m.BASE_SEAL,
                        '--qualification-seal',m.QUAL_SEAL])
            evaluate.assert_not_called()

    def test_bound_file_changed_or_alias_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'evidence'; path.write_bytes(b'correct')
            sha = m.life.digest(path)
            self.assertEqual(m.bound(path,sha),b'correct')
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError): m.bound(path,sha)
            alias = Path(tmp)/'alias'; alias.symlink_to(path)
            with self.assertRaises(ValueError): m.bound(alias,m.life.digest(alias))


class Qualification(unittest.TestCase):
    def setUp(self):
        self.record = json.loads((m.QUAL/'qualification.json').read_bytes())
        self.audit = json.loads((m.QUAL/'runtime-audit.json').read_bytes())

    def test_actual_sealed_contract_scope(self): m.qualification_contract(self.record,self.audit)

    def test_fullscalar_or_spike_claim_rejected(self):
        for which,key in [('record','full_scalar_isa_verified'),('audit','full_scalar_isa_verified'),
                          ('audit','spike_custom_isa_pass')]:
            record,audit = copy.deepcopy(self.record),copy.deepcopy(self.audit)
            (record if which=='record' else audit)[key] = True
            with self.assertRaises(ValueError): m.qualification_contract(record,audit)

    def test_incomplete_region_command_or_csr_rejected(self):
        for key,value in [('full_vrf_bytes',4096),('initial_vrf_bytes',0),('source_guard_bytes',0),
                          ('csr_values',12),('custom_write_bytes',1024),('checks',40)]:
            audit = copy.deepcopy(self.audit); audit[key] = value
            with self.assertRaises(ValueError): m.qualification_contract(self.record,audit)
        audit = copy.deepcopy(self.audit); audit['bindings'][1]['pc'] = 0x8000017a
        with self.assertRaises(ValueError): m.qualification_contract(self.record,audit)

    def test_nonpass_or_admitted_qualification_rejected(self):
        for key,value in [('status','GAP105_NATIVE_QUALIFIER_V5_REJECTED'),('coverage_admitted',True),
                          ('simulation_rerun',True)]:
            record = copy.deepcopy(self.record); record[key] = value
            with self.assertRaises(ValueError): m.qualification_contract(record,self.audit)


class MissingChecksum(unittest.TestCase):
    def test_only_exact_actual_adapter_definition_allowed(self):
        shape = ET.fromstring('<cond><conddef id="-68" chksum="2250470448"/></cond>')
        module = ET.Element('srcdef',dict(id='-68',name='qbs_block_adapter',type='module',chksum='585070731'))
        scope = m.COMPUTE+'.i_block_adapter_bank1'; row = dict(width=5914,checksum=None)
        node,binding = m.condition_definition(shape,module,scope,row,None)
        self.assertEqual(node.get('chksum'),'2250470448')
        self.assertIn('checksum_absent',binding)
        for s,r,i in [(scope+'.wrong',row,None),(scope,dict(row,width=5913),None),(scope,row,'unexpected')]:
            with self.assertRaises(ValueError): m.condition_definition(shape,module,s,r,i)
        shape.append(copy.deepcopy(node))
        with self.assertRaisesRegex(ValueError,'Ambiguous'): m.condition_definition(shape,module,scope,row,None)

    def test_exact724_prefix_and_formal_status_required(self):
        before,_ = samples(); prior = dict(tests=before['tests'][:-1])
        manifest = dict(schema='AKV_LIFECYCLE_HISTORICAL724_ADMISSION_V1',output=str(m.BASE),
                        baseline=str(m.PRIOR),baseline_seal=m.PRIOR_SEAL)
        status = dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',coverage_admitted=True,
                      baseline=723,aggregate_passed=724,new_passed=1)
        m.baseline_contract(manifest,status,before,prior)
        changed = copy.deepcopy(prior); changed['tests'][0],changed['tests'][1] = changed['tests'][1],changed['tests'][0]
        with self.assertRaises(ValueError): m.baseline_contract(manifest,status,before,changed)
        with self.assertRaises(ValueError): m.baseline_contract(manifest,dict(status,coverage_admitted=False),before,prior)


class Compiled(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = json.loads((m.BASE/'combined-bits.json').read_bytes())
        cls.single = json.loads((m.RAW/'single-bits.json').read_bytes())
        cls.pre = json.loads((m.qualifier.frozen.runner.PRE/'preflight-manifest.json').read_bytes())

    def test_existing_raw191_and_all12_complete_compiled_identities(self):
        combined,delta = m.population(self.before,self.single)
        gained,targets = m.compiled_gains(self.before,combined,self.pre,lambda p:p.read_bytes())
        self.assertEqual(len(gained),191); self.assertEqual(len(targets),12)
        self.assertEqual({t['point']['raw_index'] for t in targets},
                         {6475,6613,6616,6911,7049,7052,7347,7485,7488,7783,7921,7924})

    def test_same_raw_index_wrong_native_identity_rejected(self):
        combined,_ = m.population(self.before,self.single)
        pre = copy.deepcopy(self.pre); pre['targets'][0]['native_id'] = 'wrong'
        with self.assertRaisesRegex(ValueError,'native identity'):
            m.compiled_gains(self.before,combined,pre,lambda p:p.read_bytes())


if __name__=='__main__': unittest.main()
