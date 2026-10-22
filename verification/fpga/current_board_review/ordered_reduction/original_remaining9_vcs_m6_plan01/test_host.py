#!/usr/bin/env python3
"""Shape-derived Host transport witnesses and negative gates, never DUT/reference."""
import copy
import csv
import json
from pathlib import Path
import re
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
import replay
from replay import checker as c


def fixture(spec, fault=None):
    order = cycle = 0
    symbols, sites = spec['symbols'], spec['sites']
    cfg=spec['config'];w,cap=cfg['word_bytes'],cfg['cap']
    actual=c.read(c.REF/cfg['shape']/'reference01/ledger.json')['setup']
    lookup = spec['instructions']
    from ara_verify.trace import is_vector_instruction

    def row(pc, rd=0, value=0, address=0, rmask=0, wmask=0, wdata=0, event='retire', insn=None):
        nonlocal order, cycle
        code = int(lookup[f'{pc:x}']['insn'], 16) if insn is None else insn
        out = dict(cycle=str(cycle), event=event, order=str(order), port='0', trans_id='0',
                   pc=f'{pc:x}', insn=f'{code:x}', rd=str(rd), rd_wdata=f'{value:x}',
                   mem_addr=f'{address:x}', mem_rmask=f'{rmask:x}', mem_wmask=f'{wmask:x}',
                   mem_wdata=f'{wdata:x}', trap='0')
        cycle += 1
        if event == 'retire':
            order += 1
        return out

    def store(site, address, value, width):
        return row(sites[site], address=address, wmask=((1 << width) - 1) << (address % 8), wdata=value)

    def reg(regno, value):
        code = next(v for v in lookup.values() if
                    (int(v['insn'], 16) >> 7) & 31 == regno and
                    (int(v['insn'], 16) & 127 == 0x13 or
                     (int(v['insn'], 16) & 3 == 1 and int(v['insn'], 16) >> 13 == 2)))
        return row(code['pc'], rd=regno, value=value)

    for instr in spec['csr_prelude']:
        encoding = int(instr['insn'], 16)
        if is_vector_instruction(encoding):
            yield row(instr['pc'], event='cvx_req')
            yield row(instr['pc'], event='cvx_resp')
        rd = (encoding >> 7) & 31
        yield row(instr['pc'], rd=rd, value=128 if rd else 0)
    for i, instr in enumerate(spec['capacity_routine']):
        if is_vector_instruction(int(instr['insn'], 16)):
            yield row(instr['pc'], event='cvx_req')
            yield row(instr['pc'], event='cvx_resp')
        rd, value = [(5, (1 << 64) - 1), (10, cap), (0, 0)][i]
        yield row(instr['pc'], rd=rd, value=value)
    for index in range(3360):
        if index % 420 == 0:
            for i in range(cap):
                value = c.input_value(spec['input_bits'],index//420,i,cfg['sew'])
                if index==1260:
                    value=int.from_bytes(bytes(actual['input'][i*w:(i+1)*w]),'little')
                if index == 1260 and i == 5 and fault == 'input':
                    value ^= 1
                if index==1260 and i==cap-1 and fault=='last_input':value ^= 1
                yield store('input_store', symbols['input'] + w * i, value, w)
            for i in range(64):
                value = spec['input_bits'][[1,14,2,12,2,8,1,12][index//420]]
                if index == 1260 and i == 63 and fault == 'seed':
                    value = 0
                yield store('seed_store', symbols['seed'] + w * i, value, w)
        for field in (0, 8):
            value = spec['fixtures'][3360 + index][field // 8]
            if index == 1545 and fault == 'bank':
                pass  # Corrupt address even when bank0 has the same numeric tuple.
            yield row(sites['fixture_bits' if field == 0 else 'fixture_flags'],
                      rd=14 if field == 0 else 15, value=value,
                      address=symbols['fixtures'] + (3360 + index - (3360 if index==1545 and fault=='bank' else 0)) * 16 + field,
                      rmask=255 if field == 0 else 15)
        for i in range(64):
            if index == 0 and i == 0 and fault == 'missing_loop':
                continue
            value = [255,0,85,36][(index//15)%4]
            if fault == 'mask' and index == 1545 and i == 0:value=0
            yield store('mask_store', symbols['mask'] + i, value, 1)
        if index != 1545:
            continue
        for i in range(144):
            yield store('output_init', symbols['output'] + i, 0x5b, 1)
        args = [symbols['input'], symbols['seed'], symbols['output'] + 8, cfg['vl'], cap, symbols['mask'], 0, 0]
        if fault == 'args':
            args[3] = 4
        if fault == 'pointer':
            args[1] = symbols['input']
        for r, value in enumerate(args, 10):
            yield reg(r, value)
        for i, instr in enumerate(spec['routine']):
            if i == 17 and fault == 'missing_restore':
                continue
            encoding = int(instr['insn'], 16)
            if i == 11 and fault == 'encoding':
                encoding ^= 1 << 25
            if is_vector_instruction(encoding):
                yield row(instr['pc'], event='cvx_req', insn=encoding)
                yield row(instr['pc'], event='cvx_resp', insn=encoding)
            values = {0: (5, 128//w), 3: (5, cap), 6: (5, cfg['vl']), 7: (29, 0), 8: (30, 0),
                      12: (10, 0), 13: (6, 16), 14: (6, 16 << 32), 15: (10, 16 << 32), 18: (5, 128//w)}
            r, value = values.get(i, (0, 0))
            if fault == 'NV' and i == 13:
                value = 0
            if fault == 'vstart' and i == 12:
                value = 1
            if fault == 'saved_csr' and i == 7:
                value = 1
            if fault == 'type' and i == 3:
                value = cap+1
            yield row(instr['pc'], rd=r, value=value, insn=encoding)
        for i in range(144):
            if fault == 'missing_oracle' and i == 143:
                continue
            value = (b'\x5b'*8+cfg['nan'].to_bytes(w,'little')+b'\x5b'*(136-w))[i]
            corrupted = {'nan': 9, 'guard_left': 0, 'guard_right': 143, 'tail_first': 8+w, 'tail_last': 135}
            if fault in corrupted and i == corrupted[fault]:
                value ^= 1
            yield row(sites['output_read'], rd=(int(lookup[f"{sites['output_read']:x}"]['insn'],16)>>7)&31, value=value, address=symbols['output'] + i,
                      rmask=1 << ((symbols['output'] + i) % 8))
        if fault == 'truncated':
            return
    yield row(spec['exit_store']['pc'], address=spec['exit_address'], wmask=255, wdata=int(fault == 'exit'))
    yield row(spec['park']['pc'], rd=int(fault == 'park'))


class Gates(unittest.TestCase):
    checks=[]

    @classmethod
    def setUpClass(cls):
        cls.ledger,_,_=c.common.image_context(replay.IMAGE)
        replay.accepted_reference()
        cls.specs={s:c.specification(s) for s in c.SHAPES}

    def record(self,name):self.checks.append(name)

    def console(self,spec):
        n=spec['config']['identity']
        return '\n'.join(['BOARD_CASE_BEGIN '+n,c.marker(spec),'BOARD_CASE_PASS '+n,
                          'BOARD_REPLAY_PASS',c.common.SUCCESS,'$finish'])

    def write_csv(self,path,rows):
        rows=iter(rows);first=next(rows)
        with path.open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(first));writer.writeheader();writer.writerow(first);writer.writerows(rows)

    def test_all9_full_source_positive_generic_and_strict(self):
        from ara_verify.trace import validate_trace
        for shape,spec in self.specs.items():
            with self.subTest(shape=shape),tempfile.TemporaryDirectory(dir=c.HERE) as tmp:
                path=Path(tmp)/'synthetic.csv';self.write_csv(path,fixture(spec))
                generic=validate_trace(path)
                with path.open() as stream:strict=c.retirement(csv.DictReader(stream),spec)
                self.assertEqual(strict['retired_rows'],generic['retire_count'])
                self.assertEqual(strict['shape'],shape)
                self.assertEqual(strict['initialization_counts']['input_store'],8*spec['config']['cap'])
                self.assertEqual((strict['output_bytes'],strict['fixture_field_reads'],strict['rvv_retirements']), (144,6720,11))
                c.console_gate(self.console(spec),spec)
                self.record(shape+':actual_ELF_full_source_positive')

    def test_both_widths_fractional_m8_negative_matrix(self):
        faults={'input':'all-scenario input','last_input':'all-scenario input','seed':'seed64',
            'mask':'all-mode mask','args':'arguments','pointer':'arguments','bank':'Fixture',
            'encoding':'Actual ELF','NV':'flags/vstart','vstart':'flags/vstart','saved_csr':'saved CSR',
            'missing_restore':'consecutively','type':'vset','nan':'Original144','guard_left':'Original144',
            'guard_right':'Original144','tail_first':'Original144','tail_last':'Original144',
            'missing_oracle':'Incomplete oracle','missing_loop':'all-mode mask','truncated':'Incomplete original loops',
            'exit':'CTRL exit','park':'Post-exit'}
        for shape in ('e16_mf2','e16_m8','e32_mf2','e32_m8'):
            for fault,reason in faults.items():
                with self.subTest(shape=shape,fault=fault),self.assertRaisesRegex(ValueError,reason):
                    c.retirement(fixture(self.specs[shape],fault),self.specs[shape])
                self.record(shape+':negative:'+fault)

    def injected(self,spec,instr,before=None):
        from ara_verify.trace import is_vector_instruction
        boundary=spec['exit_store']['pc'] if before is None else before
        cycle=order=0;inserted=False
        for row in fixture(spec):
            if row['event']=='retire' and int(row['pc'],16)==boundary and not inserted:
                inserted=True
                events=['cvx_req','cvx_resp','retire'] if is_vector_instruction(int(instr['insn'],16)) else ['retire']
                for event in events:
                    new={k:'0' for k in row}
                    new.update(cycle=str(cycle),event=event,order=str(order),pc=f"{instr['pc']:x}",insn=instr['insn'])
                    yield new;cycle+=1;order+=event=='retire'
            yield dict(row,cycle=str(cycle),order=str(order));cycle+=1;order+=row['event']=='retire'
        assert inserted

    def test_unused_and_window_and_CSR_both_widths(self):
        for shape in ('e16_m8','e32_mf2'):
            s=self.specs[shape];p=c.read(c.REF/shape/'sourceproof.json')
            rows=[]
            for helper in ('op_1','op_2'):
                for index in (11,14,20):
                    pc,code,text=p['helper_windows']['soc'][helper]['new'][index]
                    rows.append((helper+str(index),dict(pc=pc,insn=code,text=text),'Unused helper PC range',None))
            rows.extend([('duplicate_op0_integer',s['routine'][14],'op0 interior',None),
                         ('preentry_op0_integer',s['routine'][14],'op0 interior',s['routine'][0]['pc']),
                         ('duplicate_op0_entry',s['routine'][0],'op0 interior',None),
                         ('capacity_duplicate',s['capacity_routine'][0],'Capacity source',None),
                         ('capacity_interior',s['capacity_routine'][1],'Capacity source',None),
                         ('late_vlenb',s['csr_prelude'][-1],'CSR outside',None),
                         ('late_vstart',s['csr_prelude'][4],'CSR outside',None)])
            for name,inst,why,before in rows:
                with self.subTest(shape=shape,name=name),self.assertRaisesRegex(ValueError,why):
                    c.retirement(self.injected(s,inst,before),s)
                self.record(shape+':'+name)

    def test_unused_all42_PC_immediate_eachshape(self):
        for shape,spec in self.specs.items():
            p=c.read(c.REF/shape/'sourceproof.json')
            for helper in ('op_1','op_2'):
                for pc,insn,_ in p['helper_windows']['soc'][helper]['new']:
                    row=dict(cycle='0',event='retire',order='0',pc=f'{pc:x}',insn=insn,trap='0',rd='0',rd_wdata='0',
                        mem_addr='0',mem_rmask='0',mem_wmask='0',mem_wdata='0')
                    with self.assertRaisesRegex(ValueError,'Unused helper PC range'):c.retirement([row],spec)
                    self.record(shape+':unused_PC:'+hex(pc))

    def test_actual_type_encoding_and_PC_crossshape(self):
        for shape,other in [('e16_m8','e32_m8'),('e32_mf2','e16_mf2')]:
            s=self.specs[shape];other_code=self.specs[other]['routine'][3]['insn']
            def changed():
                for r in fixture(s):
                    if int(r['pc'],16)==s['routine'][3]['pc']:r=dict(r,insn=other_code)
                    yield r
            with self.assertRaisesRegex(ValueError,'Actual ELF'):c.retirement(changed(),s)
            self.record(shape+':wrong_SEW_type_encoding')

    def test_full_artifact_unused_vector_negative_and_no_oracle(self):
        from ara_verify.trace import validate_trace
        for shape in ('e16_m8','e32_mf2'):
            s=self.specs[shape];case=next(x for x in replay.scope() if x['shape']==shape)
            p=c.read(c.REF/shape/'sourceproof.json');pc,code,text=p['helper_windows']['soc']['op_1']['new'][11]
            with tempfile.TemporaryDirectory(dir=c.HERE) as tmp:
                root=Path(tmp);(root/'work').mkdir();csvpath=root/'commit_trace.csv'
                self.write_csv(csvpath,self.injected(s,dict(pc=pc,insn=code,text=text)))
                generic=validate_trace(csvpath)
                (root/'input.elf').write_bytes(Path(case['elf']).read_bytes())
                c.common.save(root/'trace_summary.json',dict(status='VALID',**generic))
                c.common.save(root/'inputs.json',dict(binary=dict(source=case['elf'],path=str(root/'input.elf'),sha256=case['sha256']),
                    simv=dict(path=self.ledger['simv'],image_sha256=self.ledger['files'])))
                c.common.save(root/'command.json',dict(cwd=str(root/'work'),command=[self.ledger['simv'],'-l','run.vcs.log',
                    '+ntb_random_seed=1','+PRELOAD='+str(root/'input.elf'),'+TESTCASE='+case['id'],'+NO_FSDB','+COMMIT_TRACE='+str(csvpath)]))
                for log in (root/'console.log',root/'work/run.vcs.log'):log.write_text(self.console(s))
                result=SimpleNamespace(name=case['id'],status='PASS',returncode=0,reason='',elapsed_s=1,artifact_dir=root)
                with self.assertRaisesRegex(ValueError,'Unused helper PC range'):c.artifacts(result,case,self.ledger,s,validate_trace)
                (root/'console.log').write_text(self.console(s).replace(c.marker(s),''))
                with self.assertRaises(ValueError):c.artifacts(result,case,self.ledger,s,validate_trace)
                self.record(shape+':full_artifact_unused_and_missing_oracle')

    def test_console_width_membership_and_failure(self):
        for shape in ('e16_mf2','e32_m8'):
            s=self.specs[shape];text=self.console(s);c.console_gate(text,s)
            for bad in (text.replace(c.marker(s),''),text+'\nBOARD_REPLAY_PASS',text+'\nRVV_FP_REDSPECIAL_DETAIL scenario=3',
                        text.replace('sew='+str(s['config']['sew']),'sew=64')):
                with self.assertRaises(ValueError):c.console_gate(bad,s)
            self.record(shape+':console_veto')

    def test_actual_partial_DETAIL_monitor_both_widths(self):
        import ara_verify.runner as engine
        for shape in ('e16_m8','e32_mf2'):
            lines=(c.REF/shape/'host/missing_nv.log').read_text().splitlines()
            line,=[s for s in lines if s.startswith('RVV_FP_REDSPECIAL_DETAIL')]
            partial=line.split(' expected_flags=',1)[0];self.assertNotIn('FAIL',partial)
            with tempfile.TemporaryDirectory(dir=c.HERE) as tmp,patch.object(engine,'FAIL_RE',re.compile(engine.FAIL_RE.pattern+'|'+c.VETO.pattern,re.I)):
                cmd=[sys.executable,'-c','import os,time;os.write(1,'+repr(partial.encode())+');time.sleep(30)']
                rc,elapsed,timed,failure=engine._run_monitored(cmd,Path(tmp),Path(tmp)/'monitor.log',10,threading.Event())
                self.assertTrue(failure);self.assertFalse(timed);self.assertNotEqual(rc,0);self.assertLess(elapsed,5)
            self.record(shape+':actual_partial_DETAIL_monitor')

    def test_failure_cancel_lateabort_validationexception(self):
        for status,mode in [('FAIL','ordinary'),('PASS','late_abort'),('PASS','exception')]:
            abort=threading.Event()
            class Parent:
                def __init__(self):pass
                def _run_test(self,*_):return SimpleNamespace(status=status,reason='')
            def check(_):
                if mode=='late_abort':abort.set()
                if mode=='exception':raise ValueError('actual strict check fails')
            admission=Mock();result=replay.checked_runner(Parent,abort,check,admission)()._run_test(SimpleNamespace(name='x'),None)
            self.assertTrue(abort.is_set());self.assertNotEqual(result.status,'PASS');admission.assert_called_once()
            self.record('cancellation:'+mode)

    def test_sticky_cancel_stops_new_dispatch(self):
        abort=threading.Event();abort.set()
        class Parent:
            def __init__(self):pass
            def _run_test(self,*_):
                assert self.cancel_event.is_set()
                return SimpleNamespace(status='CANCELLED',reason='prior failure')
        admission=Mock();check=Mock()
        replay.checked_runner(Parent,abort,check,admission)()._run_test(SimpleNamespace(name='next'),None)
        admission.assert_not_called();check.assert_not_called();self.record('stop_new_dispatch')

    def test_noabort_atomic_publish(self):
        with tempfile.TemporaryDirectory(dir=c.HERE) as tmp:
            abort=threading.Event();abort.set();terminal=dict(status=replay.PASS)
            c.common.publish(Path(tmp),terminal,abort)
            self.assertEqual(c.read(Path(tmp)/'complete.json')['status'],'NOT_PASS')
        self.record('sticky_atomic_publish')

    def plan(self):
        return dict(status='PREPARED_NOT_RUN',image=str(replay.IMAGE),image_sha256=c.sha(replay.IMAGE/'image.json'),
            cases=replay.scope(),specs=self.specs,jobs=3,timeout_s=5400,service_timeout_s=19800,worker_timeout_s=18900,
            unit=replay.UNIT,no_build=True,no_retry=True,no_fsdb=True,stop_first_fail=True,reserved_slots=0,
            reference_ready_sha256=replay.READY_SHA,reference_review_sha256=replay.REVIEW_SHA,
            mf4_acceptance_contract=replay.MF4_CONTRACT,pins={str(Path(replay.__file__).resolve()):c.sha(Path(replay.__file__))})

    def test_plan_image_ELF_and_budget_drift(self):
        plan=self.plan();replay.validate(plan,replay.IMAGE)
        changedcases=copy.deepcopy(plan['cases']);changedcases[-1]['sha256']='0'*64
        for key,value in [('jobs',2),('timeout_s',5401),('service_timeout_s',19801),('worker_timeout_s',19000),
                ('image_sha256','0'*64),('cases',changedcases),('cases',plan['cases'][:-1]),('specs',{}),
                ('mf4_acceptance_contract',{}),('no_retry',False),('reserved_slots',-1)]:
            with self.assertRaises(ValueError):replay.validate(dict(plan,**{key:value}),replay.IMAGE)
            self.record('plan_drift:'+key)

    def test_fresh_terminal_disk(self):
        with tempfile.TemporaryDirectory(dir=c.HERE) as tmp,patch.object(replay,'validate') as valid:
            root=Path(tmp);c.common.save(root/'plan.json',{'old':True});digest=c.sha(root/'plan.json')
            replay.terminal_plan_gate(root,digest,replay.IMAGE);valid.assert_called_once_with({'old':True},replay.IMAGE)
            c.common.save(root/'plan.json',{'late':True})
            with self.assertRaisesRegex(ValueError,'Late disk'):replay.terminal_plan_gate(root,digest,replay.IMAGE)
        self.record('terminal_fresh_plan_SHA')

    def test_COMPLETE_exact9_and_noabort(self):
        cases=replay.scope();results=[SimpleNamespace(name=x['id'],status='PASS',returncode=0) for x in cases]
        meta=dict(status='COMPLETE',status_counts={'PASS':9},tests=[x['id'] for x in cases],completed_at='now',
            jobs=3,timeout_s=5400,simv=self.ledger['simv'],commit_trace=True,code_coverage=False)
        replay.terminal_gate(results,meta,threading.Event(),self.ledger)
        for key,value in [('status','INTERRUPTED'),('status_counts',{'PASS':8}),('tests',meta['tests'][:-1]),('jobs',1),('completed_at',None)]:
            with self.assertRaises(ValueError):replay.terminal_gate(results,dict(meta,**{key:value}),threading.Event(),self.ledger)
            self.record('terminal:'+key)
        abort=threading.Event();abort.set()
        with self.assertRaises(ValueError):replay.terminal_gate(results,meta,abort,self.ledger)
        self.record('terminal:late_abort')

    def test_owner_and_deadline_no_budget_extension(self):
        props=dict(Id=replay.UNIT,LoadState='loaded',ActiveState='active',SubState='running',MainPID='123',
            ControlGroup='/user/'+replay.UNIT,RuntimeMaxUSec='5h 30min',KillMode='control-group',Restart='no')
        replay.owner_gate(props,'0::/user/'+replay.UNIT,123)
        for key,value in [('MainPID','124'),('RuntimeMaxUSec','6h'),('ActiveState','inactive'),('LoadState','not-found'),('Restart','always')]:
            with self.assertRaises(ValueError):replay.owner_gate(dict(props,**{key:value}),'0::/user/'+replay.UNIT,123)
            self.record('service:'+key)
        replay.deadline_gate(0,18900)
        with self.assertRaises(ValueError):replay.deadline_gate(12901,18900)
        self.record('unchanged_case_deadline')

    def test_mf4_independent_DUT_gate_not_reference(self):
        with tempfile.TemporaryDirectory(dir=c.HERE) as tmp:
            root=Path(tmp);evidence=root/'evidence';evidence.write_text('HOST ONLY SYNTHETIC')
            complete=root/'complete.json'
            original=dict(status='PASS_M6_ORIGINAL_E16_MF4_SINGLE144_NOT_FULL_PARENT',plan_sha256=replay.MF4_PLAN_SHA,
                aborted=False,pins_unchanged=True,results=[dict(name='original_e16_mf4',status='PASS',returncode=0,reason='',elapsed_s=1)],
                evidence_pins={str(evidence):c.sha(evidence)})
            c.common.save(complete,original)
            proof=dict(status=replay.MF4_STATUS,plan_sha256=replay.MF4_PLAN_SHA,soc_elf_sha256=replay.MF4_ELF_SHA,
                image_sha256='image',complete_path=str(complete),complete_sha256=c.sha(complete),evidence_pins=original['evidence_pins'])
            path=root/'proof.json';c.common.save(path,proof)
            replay.mf4_gate(path,c.sha(path),'image')
            for key,value in [('status','INDEPENDENT_REFERENCE_ALL9_ACCEPTED_NOT_DUT'),('soc_elf_sha256','bad'),('image_sha256','bad')]:
                c.common.save(path,dict(proof,**{key:value}))
                with self.assertRaises(ValueError):replay.mf4_gate(path,c.sha(path),'image')
                self.record('mf4gate:'+key)
            c.common.save(complete,dict(original,aborted=True));c.common.save(path,dict(proof,complete_sha256=c.sha(complete)))
            with self.assertRaises(ValueError):replay.mf4_gate(path,c.sha(path),'image')
            self.record('mf4gate:aborted')
            with self.assertRaises(ValueError):replay.mf4_gate(None,None,'image')
            self.record('mf4gate:missing')

    def test_parent_authorization_must_bind_gate(self):
        with tempfile.TemporaryDirectory(dir=c.HERE) as tmp:
            path=Path(tmp)/'review.json';review=dict(decision='AUTHORIZE_ORIGINAL_REMAINING9_M6_ONCE',plan_sha256='plan',unit=replay.UNIT,
                reference_review_sha256=replay.REVIEW_SHA,mf4_acceptance_sha256='mf4',budget_risk_accepted=True)
            c.common.save(path,review);replay.authorization_gate('plan',path,c.sha(path),'mf4')
            with self.assertRaises(ValueError):replay.authorization_gate('plan',path,c.sha(path),'other')
            with self.assertRaises(ValueError):replay.authorization_gate('plan',None,None,'mf4')
        self.record('new_parent_and_mf4_pin')


if __name__=='__main__':
    out=c.HERE/'host01.json'
    if out.exists():raise SystemExit('Do not overwrite existing Host results')
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Gates)
    with (c.HERE/'host01.log').open('x') as log:result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    c.common.save(out,dict(status='PASS_HOST_ONLY' if result.wasSuccessful() else 'HOST_FAIL',test_methods=result.testsRun,
        checks=len(Gates.checks),check_names=Gates.checks,failures=len(result.failures)+len(result.errors),shapes=c.SHAPES,
        script_sha256=c.sha(Path(__file__)),checker_sha256=c.sha(c.HERE/'checker.py'),runner_sha256=c.sha(c.HERE/'replay.py'),
        live_queries=False,DUT_started=False,reference_started=False))
    print(json.dumps({k:v for k,v in c.read(out).items() if k!='check_names'}),flush=True)
    raise SystemExit(not result.wasSuccessful())

