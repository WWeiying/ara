"""Host-only scalar RVFI/protocol witnesses and real frozen-parent monitor paths."""
import copy
import csv
from dataclasses import replace
import io
from itertools import islice
import json
import signal
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode=True
import replay
from replay import checker as c
from newscope import *


def fixture(spec,fault=None):
    order=cycle=arch_order=0
    sy,sites=spec['symbols'],spec['sites']
    config=spec['config']
    from ara_verify.trace import is_vector_instruction
    def row(pc,rd=0,value=0,address=0,rmask=0,wmask=0,wdata=0,event='retire',insn=None,event_order=None):
        nonlocal order,cycle
        encoding=int(spec['instructions'][f'{pc:x}']['insn'],16) if insn is None else insn
        result=dict(cycle=str(cycle),event=event,order=str(order if event_order is None else event_order),
                    port='0',trans_id='0',pc=f'{pc:x}',insn=f'{encoding:x}',rd=str(rd),rd_wdata=f'{value:x}',
                    mem_addr=f'{address:x}',mem_rmask=f'{rmask:x}',mem_wmask=f'{wmask:x}',
                    mem_wdata=f'{wdata:x}',trap='0')
        cycle+=1
        if event=='retire': order+=1
        return result
    def retirement(instr,rd=0,value=0):
        nonlocal arch_order
        encoding=int(instr['insn'],16)
        if is_vector_instruction(encoding):
            yield row(instr['pc'],event='cvx_req',insn=encoding)
            yield row(instr['pc'],event='arch_start',event_order=arch_order,insn=encoding)
            yield row(instr['pc'],event='uop_alloc',event_order=arch_order,insn=encoding)
            yield row(instr['pc'],event='uop_done',event_order=arch_order,insn=encoding)
            arch_order+=1
            yield row(instr['pc'],event='cvx_resp',insn=encoding)
        yield row(instr['pc'],rd=rd,value=value,insn=encoding)
    def store(site,address,value,width):
        return row(sites[site],address=address,wmask=((1<<width)-1)<<(address%8),wdata=value)
    def reg(regno,value):
        instruction=next(r for r in spec['instructions'].values() if
             (int(r['insn'],16)>>7)&31==regno and
             (int(r['insn'],16)&127==0x13 or (int(r['insn'],16)&3==1 and int(r['insn'],16)>>13==2)))
        return row(instruction['pc'],rd=regno,value=value)
    for instr in spec['csr_prelude']:
        rd=(int(instr['insn'],16)>>7)&31
        yield from retirement(instr,rd,128 if rd else 0)
    for index,instr in enumerate(spec['capacity_routine']):
        rd,value=[(5,(1<<64)-1),(10,32),(0,0)][index]
        if fault=='CAP' and index==1: value=16
        yield from retirement(instr,rd,value)
    for index in range(3360):
        if index%420==0:
            scenario=index//420
            for element in range(32):
                value=c.input_value(spec['input_bits'],scenario,element)
                if fault=='input' and scenario==1 and element==31: value^=1
                yield store('input_store',sy['input']+4*element,value,4)
            for element in range(64):
                value=spec['input_bits'][[1,14,2,12,2,8,1,12][scenario]]
                if fault=='seed' and scenario==1 and element==63: value^=1
                yield store('seed_store',sy['seed']+4*element,value,4)
        for field in (0,8):
            address=sy['fixtures']+(3360+index)*16+field
            if fault=='bank' and index==config['fixture_row']: address-=3360*16
            yield row(sites['fixture_bits' if field==0 else 'fixture_flags'],rd=14 if field==0 else 15,
                      value=spec['fixtures'][3360+index][field//8],address=address,rmask=255 if field==0 else 15)
        for element in range(64):
            if fault=='missing_loop' and index==0 and element==0: continue
            value=[255,0,85,36][(index//15)%4]
            if fault=='mask' and index==config['fixture_row'] and element==0: value^=1
            yield store('mask_store',sy['mask']+element,value,1)
        if index!=config['fixture_row']: continue
        for element in range(144):
            yield store('output_init',sy['output']+element,91,1)
        args=[sy['input'],sy['seed'],sy['output']+8,3,32,sy['mask'],0,0]
        for name,arg,new in [('VL',3,4),('arg_CAP',4,16),('frm',6,1),('sticky',7,1),('pointer',1,sy['input'])]:
            if fault==name: args[arg]=new
        for r,value in enumerate(args,10): yield reg(r,value)
        returns={0:(5,32),3:(5,32),6:(5,3),7:(29,0),8:(30,0),12:(10,0),13:(6,0),
                 14:(6,0),15:(10,0),18:(5,32)}
        for i,instr in enumerate(spec['routine']):
            if fault=='missing_restore' and i==17: continue
            actual=dict(instr)
            if fault=='encoding' and i==11: actual['insn']='14881c57'
            rd,value=returns.get(i,(0,0))
            if fault=='NV' and i==13: value=16
            if fault=='vstart' and i==12: value=1
            if fault=='saved_csr' and i==7: value=1
            if fault=='vset' and i==6: value=4
            if fault=='unknown_event' and i==11:
                yield row(instr['pc'],event='unknown')
            yield from retirement(actual,rd,value)
        for element in range(144):
            if fault=='missing_oracle' and element==143: continue
            value=config['expected'].to_bytes(4,'little')[element-8] if 8<=element<12 else 91
            corrupt={'result':8,'guard_left':0,'guard_right':143,'tail_first':12,'tail_last':135}
            if fault in corrupt and element==corrupt[fault]: value^=1
            yield row(sites['output_read'],rd=10,value=value,address=sy['output']+element,
                      rmask=1<<((sy['output']+element)%8))
        if fault=='truncated': return
    yield row(spec['exit_store']['pc'],address=spec['exit_address'],wmask=255,wdata=int(fault=='exit'))
    yield row(spec['park']['pc'],rd=int(fault=='park'))


class Gates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger,cls.repo,cls.framework=c.common.image_context(IMAGE)
        cls.specs={name:c.specification(name) for name in NAMES}

    def test_both_full_scalar_generic_six_event_positives(self):
        from ara_verify.trace import validate_trace
        for spec in self.specs.values():
            with tempfile.TemporaryDirectory(dir=HERE) as tmp:
                path=Path(tmp)/'synthetic.csv'
                iterator=fixture(spec); first=next(iterator)
                with path.open('w',newline='') as stream:
                    writer=csv.DictWriter(stream,fieldnames=list(first))
                    writer.writeheader(); writer.writerow(first); writer.writerows(iterator)
                generic=validate_trace(path)
                with path.open() as stream:
                    strict=c.retirement(csv.DictReader(stream),spec)
                self.assertEqual(strict['retired_rows'],generic['retire_count'])
                self.assertEqual(strict['output_bytes'],144)
                self.assertEqual(strict['fixture_field_reads'],6720)
                self.assertEqual(strict['target_calls'],1)
                self.assertGreater(generic['backend_uop_done_count'],0)

    def test_all_scalar_source_and_oracle_negatives_both_cases(self):
        faults=['input','seed','bank','missing_loop','mask','VL','arg_CAP','CAP','frm','sticky','pointer',
                'missing_restore','encoding','NV','vstart','saved_csr','vset','unknown_event','missing_oracle',
                'result','guard_left','guard_right','tail_first','tail_last','truncated','exit','park']
        for spec in self.specs.values():
            for fault in faults:
                with self.subTest(name=spec['name'],fault=fault):
                    with self.assertRaises(ValueError):
                        c.retirement(fixture(spec,fault),spec)

    def test_every_unused_helper_pc_rejected(self):
        for spec in self.specs.values():
            for lo,hi in spec['unused_ranges']:
                for row in spec['instructions'].values():
                    if lo<=row['pc']<hi:
                        raw=dict(cycle='0',event='retire',order='0',pc=f"{row['pc']:x}",
                                 insn=row['insn'],rd='0',rd_wdata='0',mem_addr='0',mem_rmask='0',
                                 mem_wmask='0',mem_wdata='0',trap='0')
                        with self.assertRaisesRegex(ValueError,'Unused helper PC range'):
                            c.retirement([raw],spec)

    def test_raw_pass_fail_veto_identity_and_duplicate(self):
        for name in NAMES:
            text='\n'.join(['BOARD_CASE_BEGIN '+name,MARKER,'BOARD_CASE_PASS '+name,'BOARD_REPLAY_PASS',
                            c.common.SUCCESS,'$finish'])
            c.console_gate(text,name)
            for bad in (text+'\nFAIL',text+'\nRVV_FP_REDSPECIAL_DETAIL',text.replace(name,'wrong_runtime'),
                        text+'\n'+MARKER,text.replace('$finish','')):
                with self.assertRaises(ValueError): c.console_gate(bad,name)

    def test_generic_protocol_negatives(self):
        from ara_verify.trace import validate_trace,TraceValidationError
        spec=self.specs[NAMES[0]]
        # A compact real-code CVX sequence including all normal nonretire events.
        base=list(islice(fixture(spec),40))
        for fault in ('unknown','unmatched_done','pending','order','exception'):
            with tempfile.TemporaryDirectory(dir=HERE) as tmp:
                rows=copy.deepcopy(base)
                if fault=='unknown': rows[0]['event']='bogus'
                elif fault=='unmatched_done':
                    row=next(r for r in rows if r['event']=='uop_done'); row['port']='9'
                elif fault=='pending': rows=[r for r in rows if r['event']!='uop_done']
                elif fault=='order': rows[0]['order']='999'
                else:
                    row=next(r for r in rows if r['event']=='cvx_resp'); row['trap']='1'
                path=Path(tmp)/'raw.csv'
                with path.open('w',newline='') as stream:
                    writer=csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader();writer.writerows(rows)
                with self.assertRaises(TraceValidationError): validate_trace(path)

    def test_two_monitor_routing_numeric0_17_timeout_and_provenance_exception(self):
        for code,timed_out,bad_metadata in [(0,False,True),(17,False,True),(-9,True,False)]:
            with tempfile.TemporaryDirectory(dir=HERE) as tmp:
                root=Path(tmp)/NAMES[0]; (root/'work').mkdir(parents=True)
                command=replay.monitor_command(root,self.ledger['simv'],NAMES[0])
                (root/'command.json').write_text('invalid' if bad_metadata else json.dumps(dict(command=command,cwd=str(root/'work'))))
                abort=threading.Event()
                wrapped=replay.monitored(lambda *a:(code,3.0,timed_out,False),abort,
                                         {NAMES[0]:root},self.ledger['simv'])
                if bad_metadata:
                    with self.assertRaises(json.JSONDecodeError):
                        wrapped(command,root/'work',root/'console.log',TIMEOUT)
                else: wrapped(command,root/'work',root/'console.log',TIMEOUT)
                receipt=c.read(root/'child_outcome.unvalidated.json')
                self.assertEqual(receipt['returncode'],code)
                self.assertEqual(receipt['timed_out'],timed_out)
                self.assertTrue(abort.is_set())
                self.assertFalse(receipt['architectural_acceptance'])
                if code!=0:
                    self.assertEqual(c.read(root/'first_cause.json')['kind'],'MONITOR_OUTCOME')

    def test_real_frozen_parent_early_postcheck_exception_preserves_monitor0_and17(self):
        parent,options,testcase,_=self.framework
        import ara_verify.runner as engine
        for code in (0,17):
            with self.subTest(actual_monitor_code=code),tempfile.TemporaryDirectory(dir=HERE) as tmp:
                out=Path(tmp); root=out/'replay/tests'/NAMES[0]
                (root/'work').mkdir(parents=True); (root/'input.elf').write_bytes(b'host_only')
                opts=replay.build_options(options,self.repo,out,self.ledger)
                abort=threading.Event()
                runner=replay.checked_runner(parent,abort,lambda result:None,lambda name:None)(opts,[],[])
                runner._suite_frozen=True
                runner._frozen_binaries[NAMES[0]]='host_only_hash'
                def actual_monitor(command,cwd,console,timeout,cancel_event=None):
                    Path(console).write_text(c.common.SUCCESS)
                    (Path(cwd)/'run.vcs.log').write_text(c.common.SUCCESS)
                    (root/'commit_trace.csv').write_text('host_only')
                    if code==17:
                        (root/'command.json').write_text('invalid post-monitor metadata')
                    return (code,3.0,False,False)
                test=testcase(NAMES[0],'app','',Path(cases_elf(NAMES[0])),NAMES[0],TIMEOUT)
                with patch.object(engine,'simulation_image',return_value={}),\
                     patch.object(engine,'_run_monitored',actual_monitor),\
                     patch.object(engine,'validate_trace',return_value={}),\
                     patch.object(engine,'check_inputs',side_effect=RuntimeError('real_parent_postcheck')):
                    with replay.engine_hooks(engine,abort,{NAMES[0]:root},self.ledger['simv']):
                        with self.assertRaises(RuntimeError if code==0 else json.JSONDecodeError):
                            runner._run_test(test,Path(self.ledger['simv']))
                self.assertEqual(c.read(root/'child_outcome.unvalidated.json')['returncode'],code)
                self.assertEqual(c.read(root/'first_cause.json')['returncode'],code)
                self.assertEqual(c.read(out/'first_cause.json')['returncode'],code)
                self.assertTrue(abort.is_set())

    def test_concurrent_monitor_isolation(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            roots={name:Path(tmp)/name for name in NAMES}
            for name,root in roots.items():
                (root/'work').mkdir(parents=True)
                command=replay.monitor_command(root,self.ledger['simv'],name)
                (root/'command.json').write_text(json.dumps(dict(command=command,cwd=str(root/'work'))))
            abort=threading.Event()
            wrapped=replay.monitored(lambda *a:(0,1.0,False,False),abort,roots,self.ledger['simv'])
            def call(item):
                name,root=item
                return wrapped(replay.monitor_command(root,self.ledger['simv'],name),root/'work',root/'console.log',TIMEOUT)
            with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(call,roots.items()))
            for name,root in roots.items(): self.assertEqual(c.read(root/'child_outcome.unvalidated.json')['name'],name)
            self.assertFalse(abort.is_set())

    def test_monitor_rejects_wrong_private_cwd_identity_or_budget(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            root=Path(tmp)/NAMES[0]; (root/'work').mkdir(parents=True)
            original=SimpleNamespace(calls=0)
            def fake(*args): original.calls+=1; return (0,1,False,False)
            for wrong in ('cwd','identity','timeout'):
                abort=threading.Event()
                wrapped=replay.monitored(fake,abort,{NAMES[0]:root},self.ledger['simv'])
                command=replay.monitor_command(root,self.ledger['simv'],NAMES[0])
                if wrong=='identity': command[5]='+TESTCASE='+NAMES[1]
                with self.assertRaises(ValueError):
                    wrapped(command,root/('other' if wrong=='cwd' else 'work'),root/'console.log',
                            1 if wrong=='timeout' else TIMEOUT)
            self.assertEqual(original.calls,0)

    def test_exact_complete_membership_and_late_abort(self):
        good=[SimpleNamespace(name=n,status='PASS',returncode=0,elapsed_s=1.0,reason='') for n in NAMES]
        meta=dict(status='COMPLETE',status_counts={'PASS':2},tests=NAMES,completed_at='actual',
                  jobs=2,timeout_s=TIMEOUT,seed=1,simv=self.ledger['simv'],commit_trace=True,code_coverage=False)
        replay.terminal_gate(good,meta,threading.Event(),self.ledger)
        for bad in [good[:1],[good[0],good[0]]]:
            with self.assertRaises(ValueError): replay.terminal_gate(bad,meta,threading.Event(),self.ledger)
        abort=threading.Event();abort.set()
        with self.assertRaises(ValueError): replay.terminal_gate(good,meta,abort,self.ledger)
        with self.assertRaises(ValueError): replay.terminal_gate(good,dict(meta,status='INTERRUPTED'),threading.Event(),self.ledger)

    def test_owner_resource_and_source_ready_gate(self):
        props=dict(Id=UNIT,LoadState='loaded',ActiveState='active',SubState='running',MainPID='1',
                   ControlGroup='/user/'+UNIT,RuntimeMaxUSec='2h',KillMode='control-group',Restart='no')
        replay.owner_gate(props,'0::/user/'+UNIT,1)
        with self.assertRaises(ValueError): replay.owner_gate(dict(props,RuntimeMaxUSec='3h'),'0::/user/'+UNIT,1)
        c.common.resource_math([],32*1024**3,HERE,2,0)
        with self.assertRaises(ValueError): c.common.resource_math([],31*1024**3,HERE,2,0)
        with self.assertRaises(ValueError): c.common.resource_math([],32*1024**3,HERE,2,23)
        pins=replay.accepted_reference()
        self.assertEqual(pins[str(READY)],READY_SHA)

    def test_pin_drift_and_late_signal_publication(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            root=Path(tmp)
            file=root/'pin';file.write_text('original')
            pins={str(file):c.sha(file)}
            with self.assertRaises(ValueError):
                replay.merge_pins(pins,{str(file):'different'})
            file.write_text('drift')
            with self.assertRaises(ValueError): c.common.base.verify_pins(pins)
            abort=threading.Event()
            terminal=dict(status=PASS)
            with patch.object(c.common.signal,'sigpending',side_effect=[set(),{signal.SIGTERM}]):
                c.common.publish(root,terminal,abort)
            self.assertEqual(c.read(root/'complete.json')['status'],'NOT_PASS')
            self.assertTrue(abort.is_set())


def cases_elf(name):
    return REF/shape(name)/'soc/program.elf'


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Gates)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    pins={str(HERE/name):c.sha(HERE/name) for name in ('newscope.py','checker.py','replay.py','test_host.py')}
    replay.durable(HERE/'host04.json',dict(status='PASS_HOST_ONLY_NOT_DUT' if result.wasSuccessful() else 'FAIL_HOST',
             tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),pins=pins,
             coverage=dict(scalar_mutations=54,unused_helper_pc_negatives=84,normal_events=6,
                           console_negatives=10,protocol_negatives=5,
                           actual_frozen_parent_codes=[0,17],timeout_numeric_code=-9,
                           concurrent_monitor_cases=2,late_signal=True,pin_drift=True),
             DUT_started=False,Spike_started=False,build_invoked=False))
    raise SystemExit(not result.wasSuccessful())
