import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import clip17_raw_admission as m


class Tests(unittest.TestCase):
    def samples(self):
        metrics = {metric:{} for metric in m.bitmap.METRICS}
        for metric in metrics:
            for i in range(6159 if metric == 'line' else 1):
                metrics[metric]['ara_tb.dut.i_ara_soc.i_system.fixture%d'%i] = dict(width=4, checksum='1', bits='0x1')
        before = dict(design={'fixture':'a'*64}, tests=['/test/%d'%i for i in range(737)],
                      input_hashes={'/fixture/before':'a'*64}, metrics=metrics)
        single = copy.deepcopy(before); single['tests']=[str(m.RUN/'code.vdb')]
        single['input_hashes']={'/fixture/single':'b'*64}
        single['metrics']['line']['ara_tb.dut.i_ara_soc.i_system.fixture0']['bits']='0x2'
        return before,single

    def qualification(self):
        result=dict(status='CLIP17_FULL_SCALAR_MEMORY_VECTOR_CSR_TRAP_QUALIFIED_NOT_ADMITTED',run=str(m.RUN),
            baseline=737,preflight_seal=m.q.PRE_SEAL,checks=2094,expected_traps=17,normal_vector_writers=33,
            timeout_s=450,native_known_write_bytes=4100,runner_sha256=m.q.RUNNER_SHA,runner_test_sha256=m.q.RUNNER_TEST_SHA,
            full_scalar_differential_qualified=True,all_scalar_memory_differential_qualified=True,software_noC=True,
            compressed_retirements=0,skipped_scalar_memory=0,full_VRF_snapshots=3,per_cell_rejected_backend_uops=0,
            per_cell_rejected_native_events=0,OS_returncode=0,terminal_source='FOREGROUND_RUNNER_OS_RETURN_RECEIPT')
        result.update({k:False for k in ('coverage_admitted','raw_bitmap_collected','rtl_changed','simulations_started',
            'new_RTL_signoff','native_cycle_qualified','whole_ISA_qualified','official_denominator_verified','application_approval')})
        return result

    def test_full6162OR_exact737prefix(self):
        before,single=self.samples();combined,delta=m.union(before,single)
        self.assertEqual(combined['tests'],before['tests']+single['tests'])
        self.assertEqual(delta['metrics']['line'],1)
        self.assertEqual(combined['metrics']['line']['ara_tb.dut.i_ara_soc.i_system.fixture0']['bits'],'0x3')

    def test_duplicate_wrong_population_singleton(self):
        for kind in ('duplicate','population','singleton'):
            before,single=self.samples()
            if kind=='duplicate':before['tests'][-1]=before['tests'][0]
            elif kind=='population':before['tests'].pop()
            else:single['tests']=['/foreign.vdb']
            with self.assertRaises(ValueError):m.union(before,single)

    def test_shape_design_universe_overflow(self):
        for kind in ('shape','design','universe','overflow'):
            before,single=self.samples()
            if kind=='shape':single['metrics']['cond']['ara_tb.dut.i_ara_soc.i_system.fixture0']['checksum']='2'
            elif kind=='design':single['design']={'fixture':'c'*64}
            elif kind=='universe':single['metrics']['line'].pop('ara_tb.dut.i_ara_soc.i_system.fixture0')
            else:single['metrics']['cond']['ara_tb.dut.i_ara_soc.i_system.fixture0']['bits']='0x10'
            with self.assertRaises(ValueError):m.union(before,single)

    def test_missing_input_hashes_rejected(self):
        before,single=self.samples();single['input_hashes']={}
        with self.assertRaises(ValueError):m.union(before,single)

    def test_zero_gain_HOLD(self):
        d={'metrics':dict.fromkeys(m.bitmap.METRICS,0)}
        self.assertEqual(m.gain_status(d,[{'fresh_target_gain':True}]),m.HOLD)

    def test_incidental_gain_without_primary_HOLD(self):
        d={'metrics':dict.fromkeys(m.bitmap.METRICS,0)};d['metrics']['line']=1
        self.assertEqual(m.gain_status(d,[{'fresh_target_gain':False}]),m.HOLD)
        self.assertEqual(m.gain_status(d,[{'fresh_target_gain':True}]),m.POSITIVE)

    def test_invalid_delta_negative_bool_missing(self):
        for value in (-1,True):
            d={'metrics':dict.fromkeys(m.bitmap.METRICS,0)};d['metrics']['line']=value
            with self.assertRaises(ValueError):m.gain_status(d,[])
        with self.assertRaises(ValueError):m.gain_status({'metrics':{}},[])

    def test_exact_qualification_and_no_promotion(self):
        m.qualification_gate(self.qualification())
        for key,value in [('checks',2093),('expected_traps',16),('timeout_s',300),('native_known_write_bytes',4096),
                          ('per_cell_rejected_native_events',1),('OS_returncode',None),('application_approval',True),
                          ('whole_ISA_qualified',True),('run','/foreign')]:
            result=self.qualification();result[key]=value
            with self.assertRaises(ValueError):m.qualification_gate(result)

    def test_real_preflight42targets_no_new_collection(self):
        pre=m.life.read_bound(m.q.PRE/'preflight-manifest.json',m.q.PRE_SEAL)
        self.assertEqual(len(pre['targets']),42)
        before,single=self.samples()
        with self.assertRaises(ValueError):m.target_hits(before,single,pre['targets'][:-1])

    def test_admission_rejects_HOLD_before_outputs(self):
        with patch.object(m,'candidate',return_value=({'status':m.HOLD},{},{},'')):
            with self.assertRaises(ValueError):m.admission_products(m.OUT/'synthetic','a'*64)

    def test_no_unauthorized_admit_read(self):
        with patch.object(m,'admission_products') as evaluate:
            with self.assertRaises(ValueError):m.main(['admit','--seal','a'*64])
            evaluate.assert_not_called()

    def test_fresh_direct_path_no_overwrite(self):
        with self.assertRaises(ValueError):m.canonical(m.BASE,True)
        with tempfile.TemporaryDirectory(dir=m.OUT) as tmp:
            with self.assertRaises(ValueError):m.canonical(Path(tmp)/'child',True)

    def test_plan_identity_reject_before_inputs(self):
        with patch.object(m,'inputs') as inputs:
            with self.assertRaises(ValueError):m.evaluate(dict(status='other',baseline=str(m.BASE),baseline_seal=m.BASE_SEAL,coverage_admitted=False))
            inputs.assert_not_called()


if __name__=='__main__':unittest.main()
