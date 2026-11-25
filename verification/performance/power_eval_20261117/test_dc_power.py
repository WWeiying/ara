"""Host-only historical-report tests and mutations; never invoke EDA."""
import importlib.util
import ast
import copy
import json
from pathlib import Path
import re
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('dc_power', HERE / 'dc_power.py')
power = importlib.util.module_from_spec(spec)
spec.loader.exec_module(power)
HIST = power.ROOT / 'hardware/power_saif_20260919'
QBS = HIST / 'qbs_akv_attn_q/dc_power_v4/reports'
RVV = HIST / 'rvv_q8_0_decode_attn_q_rvv/reports'


class HistoricalReports(unittest.TestCase):
    def test_actual_rvv_m1_v3_audit_schema_and_timebase_mutations(self):
        root=power.OUT/'power_gls_20261117_rvv_m1_port_audit_03'
        auditor,version=power.rvv_m1_port_auditor(root)
        self.assertEqual(version,3)
        self.assertEqual(power.sha(auditor),power.RVV_M1_PORT_V3_SHA)
        final=power.read(root/'result.json')
        capture=power.read(root/'cases/m1/result.json')
        plan=power.read(root/'cases/m1/plan.json')
        alignment=power.read(root/'alignment-proof.json')
        timebase=power.read(root/'timebase-proof.json')
        representation=power.read(root/'representation-proof.json')
        power.check_rvv_m1_port_v3(final,capture,plan,alignment,timebase,representation)
        self.assertEqual(timebase['cycles'],21550)
        self.assertEqual(timebase['timestamp_multiplier'],1)
        self.assertEqual(alignment['gate_minus_rtl_cycles'],[-1.5]*5)
        bad=dict(timebase,timestamp_multiplier=10000)
        with self.assertRaises(ValueError):
            power.check_rvv_m1_port_v3(dict(final,timebase=bad),capture,plan,alignment,bad,representation)
        with self.assertRaises(ValueError):
            power.check_rvv_m1_port_v3(final,dict(capture,projection_used_for_power=True),plan,alignment,timebase,representation)
        with self.assertRaises(ValueError):
            power.check_rvv_m1_port_v3(dict(final,control_statistics_unchanged=False),capture,plan,alignment,timebase,representation)

    def test_actual_rvv_port_auditor_is_pinned_and_original_anchor_failure_retained(self):
        root=power.OUT/'power_gls_20261117_rvv_m1_port_audit_01'
        auditor=root/'inputs/audit_m1_port_v1.py'
        self.assertEqual(power.sha(auditor),power.RVV_M1_PORT_AUDITOR_SHA)
        self.assertEqual(power.read(root/'audit-source-pins.json')[str(auditor)],power.RVV_M1_PORT_AUDITOR_SHA)
        old=power.OUT/'power_gls_20261117_baseline_rvv_wide_02/cases/m1/activity-audit.json'
        self.assertEqual(power.read(old)['reasons'],['RTL loop anchor not observed retiring in mapped gate window'])
        plan=power.read(root/'cases/m1/plan.json')
        self.assertEqual(plan['window_basis']['anchor_pc'],'0x800022f4')
        self.assertEqual(plan['window_basis']['original_branch_port'],1)
        self.assertEqual(plan['last_cycle']-plan['first_cycle'],21550)

    def test_rvv_port_audit_contract_scope_and_alignment_mutations(self):
        root=power.OUT/'power_gls_20261117_rvv_m1_port_audit_01'
        plan=power.read(root/'cases/m1/plan.json')
        # Policy-only metadata mutation of actual frozen window/RTL anchors;
        # this fixture is never emitted as campaign audit or power evidence.
        cycles=[v for v in plan['window_basis']['anchor_cycles'] if plan['first_cycle']<=v<=plan['last_cycle']]
        alignment=dict(expected_rtl_cycles=cycles,observed_gate_cycles=[v+1 for v in cycles],
            gate_minus_rtl_cycles=[1]*len(cycles),original_missing_anchor_port=1,measured_companion_port=0,
            companion_pc='0x800022f4',missing_branch_pc='0x800022f8',exact_instruction_equivalence_claimed=False)
        final=dict(state='OFFLINE_ACTIVITY_ELIGIBLE_PORT0_COMPANION_NOT_GLS_PASS',
            original_FAIL_unchanged=True,simulations_launched=0,power_acceptance=False,alignment=alignment)
        capture=dict(state='CAPTURE_COMPLETE_NOT_TASK_PASS',kind='m1',offline_scoped_successor=True,
            original_FAIL_unchanged=True,simulations_launched=0,strict_original_state='FAIL',
            full_gate_task_pass=False,gate_numeric_checked=False,paired_ratio_publishable=False,power_acceptance=False,
            first_cycle=plan['first_cycle'],last_cycle=plan['last_cycle'],elf_sha256=plan['elf_sha256'],clock_period_ns=1)
        power.check_rvv_m1_port_contract(final,capture,plan,alignment)
        with self.assertRaises(ValueError):
            power.check_rvv_m1_port_contract(dict(final,state='FAIL'),capture,plan,alignment)
        with self.assertRaises(ValueError):
            power.check_rvv_m1_port_contract(final,dict(capture,gate_numeric_checked=True),plan,alignment)
        changed=dict(alignment,measured_companion_port=1)
        with self.assertRaises(ValueError):
            power.check_rvv_m1_port_contract(dict(final,alignment=changed),capture,plan,changed)
        changed=dict(alignment,gate_minus_rtl_cycles=[3]*len(cycles))
        with self.assertRaises(ValueError):
            power.check_rvv_m1_port_contract(dict(final,alignment=changed),capture,plan,changed)

    def test_actual_m1_long_independent_auditor_and_original_fail_pins(self):
        root=power.OUT/'power_m1_long_eof_audit_20261117_01'
        auditor=root/'inputs/m1_long_eof_audit_v1.py'
        self.assertEqual(power.sha(auditor),power.M1_LONG_AUDITOR_SHA)
        pins=power.read(root/'source-pins.json')
        original=power.OUT/'power_gls_20261117_long_m1_01/result.json'
        self.assertEqual(pins[str(original)],power.sha(original))
        self.assertEqual(power.read(original)['state'],'FAIL')
        self.assertEqual(power.read(original)['error'],"FileNotFoundError(2, 'No such file or directory')")
        self.assertFalse((original.parent/'roi-selection.json').exists())

    def test_m1_long_audit_policy_real_receipt_mutations(self):
        root=power.OUT/'power_gls_20261117_long_m1_01'
        plan,binding,original=(power.read(root/name) for name in ('plan.json','image-binding.json','result.json'))
        # Policy-only mutation of a real native receipt, using actual long-window
        # log markers; never saved as campaign audit/acceptance evidence.
        prior=power.read(power.OUT/'power_gls_20261117_vrfinit_m1_activity_01/result.json')
        text=(root/'run/run.vcs.log').read_text()
        first=int(re.search(r'^GATE_ROI_BEGIN cycle=\d+ time=(\d+)',text,re.M)[1])
        last=int(re.search(r'^GATE_CAPTURE_WINDOW_COMPLETE cycle=\d+ time=(\d+)',text,re.M)[1])
        cycles=plan['last_cycle']-plan['first_cycle']
        self.assertEqual(cycles,27241)
        ev=dict(prior['vcd_evidence'],first_tick=first,last_tick=last,
                duration_fs=cycles*1000000,clock_edges=2*cycles)
        audit=dict(state='INDEPENDENT_LONG_CAPTURE_ELIGIBLE_NOT_TASK_PASS',original_state='FAIL',
            original_worker_reclassified=False,original_result_unchanged=True,
            task_pass=False,gate_numeric_checked=False,gate_protocol_checked=False,power_acceptance=False,
            SAIF_or_DC_launched=False,new_GLS_launched=False,cycles=cycles,clock_period_ns=1,
            first_cycle=plan['first_cycle'],last_cycle=plan['last_cycle'],elf_sha256=plan['elf_map']['sha256'],
            simv_sha256=binding['simv_sha256'],vcd_evidence=ev)
        power.check_m1_long_audit(audit,original,plan,binding)
        for key,value in (('state','INDEPENDENT_AUDIT_FAIL'),('original_worker_reclassified',True),
                          ('gate_numeric_checked',True),('cycles',19999),('simv_sha256','other-image')):
            with self.assertRaises(ValueError):
                power.check_m1_long_audit(dict(audit,**{key:value}),original,plan,binding)
        changed=copy.deepcopy(audit)
        changed['vcd_evidence']['complete_initial_state']=False
        with self.assertRaises(ValueError):
            power.check_m1_long_audit(changed,original,plan,binding)

    def test_actual_formal_q8_scope_is_not_same_stage(self):
        native=power.read(power.OUT/'power_gls_20261117_long_q8_02/plan.json')
        rvv=power.read(power.OUT/'power_gls_20261117_baseline_rvv_wide_02/cases/q8/plan.json')
        scope=power.formal_semantics(native,rvv)
        self.assertEqual(scope['native']['cycles'],43033)
        self.assertEqual(scope['rvv']['cycles'],20671)
        self.assertFalse(scope['same_stage'])
        self.assertIsNone(scope['same_stage_average_power_ratio'])
        self.assertFalse(scope['automatic_window_trimming'])
        short=dict(rvv,last_cycle=rvv['first_cycle']+19999)
        with self.assertRaises(ValueError):
            power.formal_semantics(native,short)
        with self.assertRaises(ValueError):
            power.formal_semantics(dict(native,environment_diagnostic=True),rvv)

    def test_actual_q8_has_pinned_capture_specific_rtl_admission(self):
        run=power.OUT/'power_gls_20261117_long_q8_02'
        plan=power.read(run/'plan.json')
        admission=run/'admission.json'
        self.assertEqual(power.read(run/'source-pins.json')[str(admission)],power.sha(admission))
        proof=power.rtl_role(power.read(admission),plan['elf_map']['sha256'])
        self.assertEqual(proof['case_id'],'legacy_q8_qbs_sdk_v2_successor')
        self.assertEqual(proof['role'],'RTL numerical/protocol only, not gate protocol')

    def test_cross_phase_report_never_exports_a_same_stage_ratio(self):
        previous=power.OUT/'power_dc_20261117_q8_real_load_pair_01'
        real={r:power.read(previous/r/'result.json') for r in ('qbs','rvv')}
        with tempfile.TemporaryDirectory() as directory:
            pair=Path(directory)
            for role in ('native','rvv'):
                (pair/role).mkdir()
                power.atomic_save(pair/role/'result.json',real['qbs' if role=='native' else role])
            power.save(pair/'pair-plan.json',dict(runs={r:str(pair/r) for r in ('native','rvv')},
                library_sha256=real['qbs']['library_sha256'],limitations=['Unit mutation, not formal capture evidence'],
                semantic_contract=dict(same_stage=False,reason='quantize+matmul versus matmul only')))
            power.complete_real_load_pair(pair)
            result=power.read(pair/'comparison.json')
            self.assertEqual(result['state'],'CROSS_PHASE_DIAGNOSTIC_POWER_ONLY_NOT_SIGNOFF')
            self.assertNotIn('native_over_rvv',result)
            self.assertIn('cross_phase_diagnostic_native_over_rvv',result)
            self.assertIsNone(result['same_stage_average_power_ratio'])
            self.assertIsNone(result['whole_task_energy_ratio'])
            self.assertFalse(result['paired_ratio_publishable'])

    def test_actual_missing_library_plan_is_rejected_before_execution(self):
        old=power.OUT/'power_dc_20261117_activity_follow_02/m1/native'
        plan=power.read(old/'plan.json')
        job=power.read(old/'chain-plan.json')
        self.assertNotIn('library_sha256',plan)
        with self.assertRaisesRegex(ValueError,'missing library_sha256'):
            power.validate_real_load_plan(plan)
        corrected=dict(plan,library_sha256=job['library_sha256'])
        power.validate_real_load_plan(corrected)
        self.assertEqual(len(corrected['library_sha256']),15)
        changed=copy.deepcopy(corrected)
        changed['library_sha256'][next(iter(changed['library_sha256']))]='wrong-library'
        with self.assertRaisesRegex(ValueError,'paired library/frequency'):
            power.validate_real_load_plan(changed)
        self.assertEqual(power.read(old/'result.json')['error'],"KeyError('library_sha256')")
        self.assertFalse((old/'console.log').exists())

    def test_activity_plan_generator_includes_execution_library_contract(self):
        tree=ast.parse(Path(power.__file__).read_text())
        function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='follow_activity')
        plans=[node for node in ast.walk(function) if isinstance(node,ast.Call) and
            isinstance(node.func,ast.Name) and node.func.id=='dict' and
            any(k.arg=='schema' and isinstance(k.value,ast.Constant) and k.value.value=='power-real-pin-load-run-v1'
                for k in node.keywords)]
        self.assertEqual(len(plans),1)
        self.assertIn('library_sha256',{k.arg for k in plans[0].keywords})

    def test_actual_attention_input_identity_not_implementation_order(self):
        native=power.read(power.OUT/'power_attention_prepare_20261117_akv_01/build.json')
        rvv=power.read(power.OUT/'power_attention_prepare_20261117_rvv_01/build.json')
        self.assertEqual(native['paired_source_data'],rvv['paired_source_data'])
        self.assertEqual({k:native['fixture'][k] for k in ('case','data_hash','data_bytes')},
                         {k:rvv['fixture'][k] for k in ('case','data_hash','data_bytes')})
        self.assertNotEqual(native['fixture']['order'],rvv['fixture']['order'])

    def test_actual_rvv_m1_poisoned_snapshot_cannot_be_power_admitted(self):
        original = power.read(power.OUT / 'power_gls_20261117_baseline_rvv_activity_02/cases/m1/result.json')
        ev = original['vcd_evidence']
        self.assertEqual(ev['initial_unknown_value_records'], 1259538)
        self.assertEqual(ev['declared_identifiers'], 1279689)
        # Mutation fixture based on the independently observed mapped PC/ack
        # and dispatcher X values; not a replacement campaign audit receipt.
        report = dict(signals={n:dict(unknown_ticks=1, values={}) for n in
            ('ack','pc','dispatcher','sequencer','vector_valid')}, duration_ticks=1,
            cycles=4292, clock_edges=8584, retire_samples=0, pc_unknown_when_committing=1)
        report['signals'].update(clock=dict(unknown_ticks=0,values={}),reset=dict(unknown_ticks=0,values={'1':1}))
        policy = power.activity_policy(report,'rvv','m1','0x800022f8')
        self.assertEqual(policy['state'],'ACTIVITY_WINDOW_REJECTED')
        self.assertTrue(any('Critical control X/Z' in reason for reason in policy['reasons']))
        self.assertFalse(policy['power_acceptance'])

    def test_activity_reader_probe_and_missing_control_rejection(self):
        fixture = power.ROOT / 'verification/performance/power_eval_20261117/fixtures/window_probe.vcd'
        with tempfile.TemporaryDirectory() as directory:
            probe = Path(directory)/'probe.vcd'
            probe.write_text(fixture.read_text().replace('! clk $end','! clk_i $end'))
            report = power.scan_activity_vcd(probe,1,100000,200000)
        self.assertEqual(report['initial_value_records'],1)
        self.assertEqual(report['clock_edges'],2)
        self.assertEqual(report['signals']['clock']['unknown_ticks'],0)
        self.assertEqual(power.activity_policy(report,'rvv','m1','0x800022f8')['state'], 'ACTIVITY_WINDOW_REJECTED')

    def test_activity_policy_idle_unknowns_do_not_override_critical_checks(self):
        report = dict(signals={n:dict(unknown_ticks=0,values={'0':10}) for n in
            ('clock','ack','pc','dispatcher','sequencer','vector_valid')},duration_ticks=10,
            cycles=5,clock_edges=10,retire_samples=3,anchor_retire_samples=1,
            pc_unknown_when_committing=0,active_payload_unknown_samples=0,
            initial_unknown_value_records=1259538,initial_value_records=1279689)
        report['signals']['reset']=dict(unknown_ticks=0,values={'1':10})
        report['signals']['vector_valid']['values']={'1':5,'0':5}
        self.assertEqual(power.activity_policy(report,'rvv','m1','0x800022f8')['state'], 'ACTIVITY_WINDOW_ELIGIBLE_NOT_GLS_PASS')
        changed=copy.deepcopy(report)
        changed['signals']['dispatcher']['unknown_ticks']=10
        self.assertEqual(power.activity_policy(changed,'rvv','m1','0x800022f8')['state'], 'ACTIVITY_WINDOW_REJECTED')
        changed=copy.deepcopy(report)
        changed['active_payload_unknown_samples']=1
        self.assertEqual(power.activity_policy(changed,'rvv','m1','0x800022f8')['state'], 'ACTIVITY_WINDOW_REJECTED')

    def test_real_load_tcl_disables_approximation_before_timing_without_zeroing_pins(self):
        libs = sorted(power.read(power.DC / 'manifest.json')['library_sha256'])
        for role in ('qbs', 'rvv'):
            text = power.make_real_load_tcl(Path('/paired') / role, libs, role)
            self.assertLess(text.index('set_app_var high_fanout_net_threshold 0'), text.index('  update_timing'))
            self.assertNotIn('set_app_var high_fanout_net_pin_capacitance 0', text)
            self.assertNotRegex(text, r'(?m)^\s*set_load\b')
            self.assertIn('create_clock -name power_clk -period 1.0', text)
            self.assertIn('report_power_calculation [get_nets $name] -nosplit', text)
            self.assertIn('report_net -nosplit -significant_digits 9 -transition_times', text)
            self.assertEqual('qbs_clock_connections.rpt' in text, role == 'qbs')
            for forbidden in ('compile_ultra', 'set_switching_activity', 'read_verilog'):
                self.assertNotIn(forbidden, text)

    def documented_clock_example(self):
        # Actual vendor report example; a parser fixture, not campaign evidence.
        text = (power.TOOLROOT / 'doc/syn/man/cat2/report_power_calculation.2').read_text()
        text = text[text.rfind('         Global Operating Voltage = 0.9'):]
        return 'CLOCK_NET_BEGIN q\n' + text + '\nCLOCK_NET_END q\n'

    def test_clock_calculation_documented_report_units_and_mutations(self):
        text = self.documented_clock_example()
        clock = power.parse_clock_calculations(text)['q']
        self.assertAlmostEqual(clock['capacitance_pf'], .4)
        self.assertAlmostEqual(clock['switching_w'], .0001296)
        self.assertAlmostEqual(clock['toggle_per_ns'], .8)
        for changed in (text.replace('1.000000pf', '1.000000ff'),
                        text.replace('total net capacitance = 0.4', 'total net capacitance = -1'),
                        text.replace('Switching power = 0.1296', 'Switching power = 10'),
                        text + text):
            with self.assertRaises(ValueError):
                power.parse_clock_calculations(changed)

    def test_pair_waits_for_both_and_never_admits_original_model_as_corrected(self):
        with tempfile.TemporaryDirectory() as directory:
            pair = Path(directory)
            for role in ('qbs', 'rvv'):
                (pair / role).mkdir()
            power.save(pair / 'pair-plan.json', dict(runs={k:str(pair/k) for k in ('qbs','rvv')}, limitations=[]))
            old = power.read(power.OUT / 'power_dc_20261117_q8_native_report_audit_01/result.json')
            power.atomic_save(pair / 'qbs/result.json', old)
            power.complete_real_load_pair(pair)
            self.assertFalse((pair / 'comparison.json').exists())
            power.atomic_save(pair / 'rvv/result.json', old)
            power.complete_real_load_pair(pair)
            result = power.read(pair / 'comparison.json')
            self.assertEqual(result['state'], 'FAIL')
            self.assertNotIn('qbs_over_rvv', result)
            self.assertFalse(result['power_acceptance'])
            with self.assertRaises(FileExistsError):
                power.atomic_save(pair / 'qbs/result.json', dict(state='PASS'))

    def actual_q8_pair(self):
        qplan = power.read(power.OUT / 'power_dc_20261117_q8_native_provisional_05/plan.json')
        qbs = power.read(qplan['proof_roles']['rtl']['numerical']['path'])
        smoke = power.read(power.OUT / 'power_gls_20261117_baseline_q8_smoke_03/result.json')
        return qbs, smoke['numerical']

    def test_actual_baseline_qbs_same_task_and_golden_mutations(self):
        qbs, rvv = self.actual_q8_pair()
        self.assertEqual(power.same_q8_task(qbs, rvv), dict(rows=256, k=896, inputs=1, outputs=256))
        changed = copy.deepcopy(rvv)
        changed['benchmark']['rows'] = '64'
        with self.assertRaisesRegex(ValueError, 'task scale'):
            power.same_q8_task(qbs, changed)
        changed = dict(rvv, scalar_model_reference_sha256='different-data')
        with self.assertRaisesRegex(ValueError, 'golden model'):
            power.same_q8_task(qbs, changed)
        with self.assertRaises(ValueError):
            power.same_q8_task(qbs, dict(rvv, state='FAIL'))

    def test_actual_baseline_uses_exact_qbs_library_superset_and_common_tcl(self):
        qplan = power.read(power.OUT / 'power_dc_20261117_q8_native_provisional_05/plan.json')
        gate = power.OUT / 'power_gate_build_20261117_baseline_02'
        receipt = power.read(gate / 'gate-receipt.json')
        libraries = power.shared_libraries(power.read(power.DC / 'manifest.json'), receipt)
        self.assertEqual(libraries, qplan['library_sha256'])
        self.assertEqual(len(libraries), 15)
        self.assertEqual(receipt['memory']['bytes'], 1048576)
        self.assertEqual(receipt['unresolved_mapped_cell_types'], [])
        tcl = power.make_tcl(Path('/baseline'), sorted(libraries), 'ara_tb/dut/i_ara_soc')
        old = (power.OUT / 'power_dc_20261117_q8_native_provisional_05/inputs/power.tcl').read_text()
        self.assertEqual(tcl[tcl.index('proc power_main'):], old[old.index('proc power_main'):])
        self.assertIn('create_clock -name power_clk -period 1.0', tcl)

    def test_actual_baseline_adapter_and_smoke_identity(self):
        run = power.OUT / 'power_gls_20261117_baseline_q8_capture_04'
        worker = run / 'inputs/gate_run_baseline_serial.py'
        self.assertEqual(power.sha(worker), power.BASELINE_ADAPTER_SHA)
        plan, binding = power.read(run / 'plan.json'), power.read(run / 'image-binding.json')
        smoke = power.read(Path(plan['smoke_prerequisite']) / 'result.json')
        self.assertEqual(smoke['state'], 'GATE_SMOKE_PASS')
        self.assertTrue(smoke['full_gate_task_pass'])
        self.assertEqual(smoke['elf_sha256'], plan['elf_map']['sha256'])
        self.assertEqual(smoke['simv_sha256'], binding['simv_sha256'])
        self.assertEqual(binding['baseline_context']['historical_byte_identity'], 'UNPROVEN')

    def test_baseline_eof_adapter_does_not_accept_other_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'result.json').write_text(json.dumps(dict(state='FAIL', error="ValueError('trap')")))
            with self.assertRaisesRegex(ValueError, 'known EOF checker defect'):
                power.baseline_capture_receipt(root, root / 'audit', None, {}, {})

    def test_actual_05_echoed_fatal_is_not_runtime_failure(self):
        root = power.OUT / 'power_dc_20261117_q8_native_provisional_05'
        text = (root / 'console.log').read_text()
        self.assertIn('puts stderr "POWER_DC_FATAL: $reason"', text)
        power.check_log(text)
        with self.assertRaisesRegex(ValueError, 'Tcl power failure'):
            power.check_log(text + '\nPOWER_DC_FATAL: actual runtime failure\n')

    def test_actual_05_power_preserved_without_accepting_156_annotation_gaps(self):
        root = power.OUT / 'power_dc_20261117_q8_native_provisional_05'
        result = power.collect_power_reports(root)
        self.assertTrue(result['dc_execution_completed'])
        self.assertEqual(result['annotation_gate'], 'FAIL')
        self.assertFalse(result['power_acceptance'])
        self.assertEqual(result['annotation_counts']['Pins']['propagated'], 156)
        self.assertAlmostEqual(result['power_watts']['total_w'], 1.0162)
        self.assertAlmostEqual(result['power_watts']['dynamic_w'], 1.0121)
        self.assertAlmostEqual(result['power_watts']['leakage_w'], 0.0041324)

    def test_vendor_read_ddc_procedure_initialization_is_retained(self):
        self.assertNotIn('-no_init', power.DC_FLAGS)
        self.assertIn('-no_home_init', power.DC_FLAGS)
        self.assertIn('-no_local_init', power.DC_FLAGS)
        self.assertIn('proc read_ddc ', power.DC_INIT_FILES[2].read_text())
        self.assertIn('source $synopsys_root/auxx/syn/.dc_procs.tcl', power.DC_INIT_FILES[0].read_text())

    def test_actual_native_eof_audit_and_lineage_mutations(self):
        root = power.OUT / 'power_gate_capture_audit_20261117_q8_slotfix_01'
        audit = power.read(root / 'result.json')
        original_path = Path(audit['original_result']['path'])
        original = power.read(original_path)
        run = original_path.parent
        plan, binding = power.read(run / 'plan.json'), power.read(run / 'image-binding.json')
        power.check_eof_audit_data(audit, original, plan, binding)
        for key, value in (('original_worker_reclassified', True), ('power_acceptance', True),
                           ('elf_sha256', 'other-elf'), ('first_cycle', 1)):
            with self.assertRaises(ValueError):
                power.check_eof_audit_data(dict(audit, **{key:value}), original, plan, binding)
        changed = copy.deepcopy(audit)
        changed['vcd_evidence']['eof_at_selected_end'] = False
        with self.assertRaises(ValueError):
            power.check_eof_audit_data(changed, original, plan, binding)
        with self.assertRaises(ValueError):
            power.check_eof_audit_data(audit, dict(original, state='PASS'), plan, binding)

    def test_real_baseline_same_library_union(self):
        all_on = power.read(power.DC / 'manifest.json')
        baseline = power.read(power.OUT / 'power_gate_build_20261117_baseline_02/gate-receipt.json')
        libraries = power.shared_libraries(all_on, baseline)
        self.assertTrue(all(libraries[p] == h for p,h in all_on['library_sha256'].items()))
        self.assertTrue(all(libraries[p] == h for p,h in baseline['library_database_hashes'].items()))
        self.assertNotEqual(baseline['ddc_sha256'], power.DDC_SHA)
        changed = copy.deepcopy(baseline)
        path = next(iter(all_on['library_sha256']))
        changed['library_database_hashes'][path] = 'conflicting-bytes'
        with self.assertRaises(ValueError):
            power.shared_libraries(all_on, changed)

    def test_power_only_deviation_policy_and_mutations(self):
        # Policy-unit mutation of the historical Q8 shape; not a real audit or
        # authorization receipt, and never saved as campaign evidence.
        entry = self.q8_release_entry()
        conversion = dict(elf_sha256=entry['elf']['sha256'], simv_sha256='gate-image')
        audit = dict(schema='power-numerical-deviation-audit-v1',
            state='POWER_ELIGIBLE_WITH_NUMERICAL_DEVIATION', scope='gate_smoke', purpose='relative_power',
            **conversion, target_path='Q8 QBS full 256-output projection', rationale='policy fixture only',
            task_scale=dict(rtl=dict(m=1,n=256,k=896), gate=dict(m=1,n=256,k=896)),
            errors=dict(outputs=256,mismatches=1,max_abs=0.001,max_rel=0.002,rms=0.0001),
            limits=dict(max_abs=0.002,max_rel=0.003,rms=0.001),
            checks={k:True for k in ('task_complete','target_path_executed','no_exception','no_stall',
                                     'guards_pass','finite_outputs','numerical_only_failure')})
        power.check_deviation_policy(audit, conversion)
        mutations = []
        for flag in audit['checks']:
            changed = copy.deepcopy(audit)
            changed['checks'][flag] = False
            mutations.append(changed)
        for key, value in (('state','PASS'),('elf_sha256','another-elf'),('purpose','correctness_signoff')):
            mutations.append(dict(audit, **{key:value}))
        for key, value in (('max_abs',float('nan')),('max_rel',1),('outputs',255),('mismatches',257)):
            changed = copy.deepcopy(audit)
            changed['errors'][key] = value
            mutations.append(changed)
        changed = copy.deepcopy(audit)
        changed['task_scale']['gate']['k'] = 32
        mutations.append(changed)
        for changed in mutations:
            with self.assertRaises(ValueError):
                power.check_deviation_policy(changed, conversion)

    def test_failed_smoke_never_automatically_becomes_power_eligible(self):
        with tempfile.TemporaryDirectory() as d:
            original = Path(d) / 'result.json'
            original.write_text(json.dumps(dict(state='FAIL',error='numerical mismatch')))
            before = original.read_bytes()
            with self.assertRaisesRegex(ValueError, 'independent power deviation audit'):
                power.validate_smoke(original, {})
            self.assertEqual(before, original.read_bytes())

    def test_actual_gate_netlist_and_ddc_correspondence(self):
        receipt = power.read(power.OUT / 'power_gate_build_20261117_all_on_01/gate-receipt.json')
        status = power.read(power.DC / 'status.json')
        power.check_dc_correspondence(receipt, status, receipt['netlist_sha256'])
        for altered in (dict(receipt, netlist_sha256='other-netlist'),
                        dict(receipt, dc_attempt='/different-attempt')):
            with self.assertRaises(ValueError):
                power.check_dc_correspondence(altered, status, receipt['netlist_sha256'])
        changed = copy.deepcopy(status)
        changed['output_sha256'][str(power.DC / power.DDC_REL)] = 'different-ddc'
        with self.assertRaises(ValueError):
            power.check_dc_correspondence(receipt, changed, receipt['netlist_sha256'])

    def q8_release_entry(self):
        release = power.read(power.OUT / 'power_gate_build_20261117_all_on_01/initial-release.json')
        return next(c for c in release['cases'] if c['id'] == 'legacy_q8_qbs_sdk_v2_successor')

    def test_actual_rtl_numeric_does_not_need_fictitious_elf_field(self):
        entry = self.q8_release_entry()
        numeric = power.read(entry['numerical']['path'])
        self.assertNotIn('elf_sha256', numeric)
        admitted = dict(entry, elf_sha256=entry['elf']['sha256'], original_worker_reclassified=False)
        admission = dict(state='COMPOSITE_RTL_EVIDENCE_ADMITTED_NOT_COMPILE_AUTHORIZATION', cases=[admitted])
        role = power.rtl_role(admission, entry['elf']['sha256'])
        self.assertIn('RTL numerical/protocol only', role['role'])
        with self.assertRaises(ValueError):
            power.rtl_role(admission, 'different-elf')
        with self.assertRaises(ValueError):
            power.rtl_role(dict(admission, state='PASS'), entry['elf']['sha256'])
        changed = copy.deepcopy(admission)
        changed['cases'][0]['numerical']['sha256'] = 'different-numeric-report'
        with self.assertRaises(ValueError):
            power.rtl_role(changed, entry['elf']['sha256'])

    def test_smoke_requires_same_elf_and_gate_not_rtl_protocol_image(self):
        entry = self.q8_release_entry()
        numeric = power.read(entry['numerical']['path'])
        # Schema mutation of preserved RTL Q8 evidence, not a real GLS PASS.
        smoke = dict(power.read(entry['original_result']['path']), state='GATE_SMOKE_PASS', mode='smoke',
                     case_id=entry['id'], full_gate_task_pass=True, simv_sha256='gate-image',
                     log=str(Path(entry['numerical']['path']).parent / 'run.vcs.log'), numerical=numeric)
        conversion = dict(simv_sha256='gate-image', elf_sha256=entry['elf']['sha256'])
        power.check_smoke_roles(smoke, conversion, numeric)
        for field, value in (('simv_sha256', 'rtl-image'), ('state', 'PASS'),
                             ('full_gate_task_pass', False), ('elf_sha256', 'different-attention-elf')):
            with self.assertRaises(ValueError):
                power.check_smoke_roles(dict(smoke, **{field: value}), conversion, numeric)

    def test_unknown_idle_saif_activity_reported_not_rejected(self):
        path = HIST / 'qbs_akv_attn_q/saif/llama_qwen25_shape_decode_n256_qbs.saif'
        with path.open() as stream:
            sample = stream.read(4096)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'historical-prefix.saif'
            p.write_text(sample)
            result = power.saif_unknown_fraction(p)
        self.assertGreater(result['unknown_record_time_fraction'], 0)
        self.assertFalse(result['whole_design_knownness_claim'])
        self.assertFalse(result['zero_unknown_required'])

    def conversion_mutation(self):
        # Derived from the actual historical SAIF header (100 fs); scale its
        # observation window to an exact 1024-cycle boundary, without any EDA.
        header = power.inspect_saif(HIST / 'qbs_akv_attn_q/saif/llama_qwen25_shape_decode_n256_qbs.saif',
                                    'ara_tb/dut/i_ara_soc')
        self.assertEqual(header['timescale'], ['100', 'fs'])
        capture = dict(state='CAPTURE_COMPLETE_NOT_TASK_PASS', first_cycle=10, last_cycle=1034,
                       clock_period_ns=1, elf_sha256='original-elf', simv_sha256='original-image')
        conversion = dict(state='SAIF_CONVERSION_PASS_NOT_POWER', instance=header['instance'],
            elf_sha256='original-elf', simv_sha256='original-image',
            window=dict(first_tick=100000, last_tick=10340000, duration_ticks=10240000,
                        tick_fs=100, duration_fs=1024000000, initial_snapshot_values=1),
            saif_summary=dict(duration_ticks=10240000, tick_fs=100, clock='clk_i',
                              clock_activity=dict(T0=5120000, T1=5120000, TX=0, TC=2048)))
        return conversion, capture

    def test_conversion_duration_clock_and_state_gates(self):
        conversion, capture = self.conversion_mutation()
        power.check_conversion_activity(conversion, capture)
        mutations = []
        for key, value in (('state', 'PASS'), ('instance', 'dut/i_ara_soc'), ('elf_sha256', 'other')):
            modified = copy.deepcopy(conversion)
            modified[key] = value
            mutations.append((modified, capture))
        for part, key, value in (('window', 'initial_snapshot_values', 0),
                                 ('window', 'duration_fs', 1024000001),
                                 ('saif_summary', 'duration_ticks', 1024)):
            modified = copy.deepcopy(conversion)
            modified[part][key] = value
            mutations.append((modified, capture))
        modified = copy.deepcopy(conversion)
        modified['saif_summary']['clock_activity']['TX'] = 1
        mutations.append((modified, capture))
        modified = copy.deepcopy(conversion)
        modified['saif_summary']['clock_activity']['TC'] = 2
        mutations.append((modified, capture))
        for key, value in (('last_cycle', 1033), ('state', 'PASS'), ('clock_period_ns', 2)):
            modified = dict(capture, **{key: value})
            mutations.append((conversion, modified))
        for conv, cap in mutations:
            with self.subTest(conv=conv, cap=cap):
                with self.assertRaises(ValueError):
                    power.check_conversion_activity(conv, cap)

    def test_qbs_real_total(self):
        result = power.parse_power((QBS / 'power_total.rpt').read_text())
        self.assertAlmostEqual(result['total_w'], 0.4099022)
        self.assertAlmostEqual(result['dynamic_w'], 0.4057497)
        self.assertAlmostEqual(result['leakage_w'], 0.0041661)

    def test_rvv_real_total(self):
        result = power.parse_power((RVV / 'power_total.rpt').read_text())
        self.assertAlmostEqual(result['total_w'], 0.2099532)

    def test_equivalent_unit_mutation(self):
        text = (QBS / 'power_total.rpt').read_text()
        text = text.replace('409.9022 mW', '0.4099022 W')
        text = text.replace('4.1661e+06 nW', '4166.1 uW')
        result = power.parse_power(text)
        self.assertAlmostEqual(result['total_w'], 0.4099022)
        self.assertAlmostEqual(result['leakage_w'], 0.0041661)

    def test_total_failures(self):
        text = (QBS / 'power_total.rpt').read_text()
        mutations = [text.replace('409.9022 mW', '409.9022 bananas'),
                     text.replace('409.9022 mW', '409.9022 W'),
                     text.replace('409.9022 mW', '-409.9022 mW'),
                     re.sub(r'^Total\s+.*$', '', text, flags=re.M),
                     text + '\n' + next(x for x in text.splitlines() if x.startswith('Total ')),
                     text.replace('black_box          0.0000', 'black_box          1.0000')]
        for mutation in mutations:
            with self.subTest(mutation=mutation[-150:]):
                with self.assertRaises(ValueError):
                    power.parse_power(mutation)

    def test_rtl_coverage_not_gate_coverage(self):
        text = (RVV / 'saif_coverage.rpt').read_text()
        self.assertEqual(power.parse_annotation(text, gate_level=False)['Seq Cells']['total'], 131367)
        with self.assertRaisesRegex(ValueError, 'RTL-only'):
            power.parse_annotation(text)

    def test_conflicted_100_percent_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            power.parse_annotation((QBS / 'saif_coverage.rpt').read_text(), gate_level=False)

    def test_gate_table_mutation_of_historical_rtl_report(self):
        text = (RVV / 'saif_coverage.rpt').read_text()
        text = text.replace('-rtl_saif', '').replace('Seq Cells', 'Nets').replace('Tri Cells', 'Pins')
        text = text.replace('sequential cells', 'nets').replace('three-state cells', 'pins')
        self.assertEqual(power.parse_annotation(text)['Nets']['total'], 131367)
        with self.assertRaises(ValueError):
            power.parse_annotation(text.replace('0 nets', '1 nets'))

    def test_missing_annotation_mutations(self):
        text = (RVV / 'saif_coverage.rpt').read_text()
        for mutation in (text.replace('234(100.00%)', '233(99.57%)'),
                         text.replace('0 sequential cells', '1 sequential cells'),
                         text.replace('Seq Cells', 'Missing Cells'),
                         text.replace('0(0.00%)', '1(0.00%)', 1), ''):
            with self.assertRaises(ValueError):
                power.parse_annotation(mutation, gate_level=False)

    def test_historical_header_and_instance_mutations(self):
        path = HIST / 'qbs_akv_attn_q/saif/llama_qwen25_shape_decode_n256_qbs.saif'
        result = power.inspect_saif(path, 'ara_tb/dut/i_ara_soc')
        self.assertEqual(result['duration_ticks'], 687455000)
        for instance in ('ara_tb/dut/not_the_soc', 'x;exec bad', 'dut/i_ara_soc'):
            with self.assertRaises(ValueError):
                power.inspect_saif(path, instance)
        with tempfile.TemporaryDirectory() as d:
            mutated = Path(d) / 'empty.saif'
            with path.open() as stream:
                prefix = stream.read(4096)
            mutated.write_text(prefix.replace('(DURATION 687455000)', '(DURATION 0)'))
            with self.assertRaises(ValueError):
                power.inspect_saif(mutated, 'ara_tb/dut/i_ara_soc')

    def test_real_log_is_not_new_runner_acceptance(self):
        text = (QBS / 'dc_power.console.log').read_text()
        with self.assertRaises(ValueError):
            power.check_log(text)

    def test_execution_requires_explicit_flag(self):
        with self.assertRaisesRegex(ValueError, 'authorize'):
            power.execute(Path('/nonexistent'), False)
        with self.assertRaisesRegex(ValueError, 'frozen'):
            power.execute(Path('/nonexistent'), True)

    def test_tcl_no_synthesis_and_correct_sequence(self):
        manifest = power.read(power.DC / 'manifest.json')
        text = power.make_tcl(Path('/tmp/isolated'), sorted(manifest['library_sha256']), 'ara_tb/dut/i_ara_soc')
        self.assertNotRegex(text, r'(?m)^\s*(?:compile|analyze|elaborate|write_ddc)\b')
        self.assertNotIn('202609', text)
        self.assertLess(text.index('set_app_var link_library'), text.index('read_ddc'))
        self.assertLess(text.index('update_timing'), text.index('read_saif'))
        self.assertIn('is_black_box == true', text)
        self.assertIn('report_saif -hierarchy -missing', text)
        self.assertIn('report_power -hierarchy -levels 3', text)
        self.assertNotIn('if {![read_ddc', text)
        self.assertIn('sizeof_collection [get_designs -quiet ara_soc]', text)
        self.assertIn('get_lib_cells -quiet -of_objects $cell', text)
        self.assertIn('$ref eq "**logic_0**" || $ref eq "**logic_1**"', text)
        self.assertIn('if {$unresolved || [sizeof_collection $unmapped]}', text)
        self.assertNotIn('if {[sizeof_collection $black] ||', text)


if __name__ == '__main__':
    unittest.main()
