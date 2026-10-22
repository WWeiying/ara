"""Conditionally authorized single CSV traversal, never runs a DUT or reference."""
import argparse
from collections import Counter
import csv
import hashlib
import importlib.util
import sys
import time

sys.dont_write_bytecode=True
from support import *


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def main(prepared_sha,complete_sha):
    require(prepared_sha and sha(HERE/'prepared.json')==prepared_sha,'Actual prepared audit SHA required')
    prepared=read(HERE/'prepared.json');verify(prepared['code_pins'])
    require(not (HERE/'terminal01').exists(),'Single exclusive audit attempt only')
    out=HERE/'terminal01';out.mkdir()
    save(out/'invocation.json',dict(argv=sys.argv,started=time.time(),complete_sha256=complete_sha,
                                  prepared_sha256=prepared_sha,no_DUT=True))
    try:
        plan,done,digest=terminal_gate()
        require(digest==complete_sha,'Admitted terminal SHA changed')
        sys.path.insert(0,str(W))
        worker=load(W/'replay.py','gather66_terminal_frozen_worker')
        for name in ('console.log','work/run.vcs.log'):
            path=ROOT/name;text=path.read_text();bad=worker.checker.VETO.search(text)
            if bad:
                line=text.count('\n',0,bad.start())+1
                save(out/'FIRST_FAILURE.json',dict(path=str(path),line=line,raw_line=text.splitlines()[line-1]))
                raise ValueError('Raw first-error veto; no CSV traversal')
            worker.checker.console_gate(text)
        ledger=read(Path(plan['image'])/'image.json')
        result=type('Result',(),dict(done['results'][0],artifact_dir=ROOT))()
        worker.checker.common.check_artifacts(result,dict(plan['case'],original_name=NAME),ledger)
        worker.terminal_gate([result],read(P/'replay/run.json'),__import__('threading').Event(),ledger)
        require(sha(Path(plan['image'])/'image.json')==plan['image_sha256'],'Frozen M6 image differs')
        # Import the pinned frozen trace sequence matcher, not its file-reading validator.
        repo=Path(ledger['snapshot'])/'sources'
        trace=load(repo/'verification/ara_verify/trace.py','gather66_frozen_trace_rules')
        mature=load(TRANSPORT,'gather66_mature_lossless_transport')
        gold=worker.checker.model();spec=plan['spec']
        class Observer(mature.Observer):
            def __init__(self):
                self.count,self.pcs=Counter(),Counter()
                self.pending,self.uops={},{}
                self.requests,self.arch,self.retvec=[],[],[]
                self.first=self.last=-1;self.maxcvx=self.maxuop=0
                self.before,self.after=hashlib.sha256(),hashlib.sha256()
                self.regs=[0]*32;self.ordinal=self.step=0
                self.categories=Counter();self.endpoint=Counter();self.selected={}
            def retirement(self,row,cycle,insn,order):
                pc=int(row['pc'],16);routine=spec['routine'];a=spec['addresses']
                if self.step: require(pc==routine[self.step]['pc'],'Noncontiguous original13 helper')
                if pc==routine[0]['pc']:
                    self.ordinal+=1
                    require(self.regs[11]==a['indices'] and self.regs[11]!=a['indices16'] and
                            self.regs[16]==0,'Actual ordinary index/a6 differs')
                if pc in [r['pc'] for r in routine]:
                    j=[r['pc'] for r in routine].index(pc)
                    require(j==self.step,'Original helper order differs')
                    self.step=(j+1)%13
                if pc==routine[8]['pc']:
                    require(insn==0x308fbc57 and self.regs[28]==self.regs[16]==0,'VI31/a6/t3 differs')
                address=int(row['mem_addr'],16);value=int(row['rd_wdata'],16)
                if self.ordinal and int(row['mem_rmask'],16) and a['output']<address<a['output']+513:
                    element=address-a['output']-1;g=gold['rows'][self.ordinal-1]
                    active=g['vstart']<=element<g['vl'] and (g['predicate'][element//8]>>(element%8))&1
                    category='active' if active else 'prestart' if element<g['vstart'] else 'tail' if element>=g['vl'] else 'inactive'
                    self.categories[category]+=1
                    if self.ordinal==66:self.endpoint[category]+=1
                    if (self.ordinal,element) in ((18,0),(18,1),(66,0),(66,127),(66,128),(66,255),(66,256),(66,511)):
                        self.selected[f'call{self.ordinal}_element{element}']=dict(value=value,cycle=cycle,pc=hex(pc),category=category)
                rd=int(row['rd'])
                if rd:self.regs[rd]=value
            def finish(self):
                require(not self.pending and not self.uops and self.step==0 and self.ordinal==66,'Incomplete transport/helper')
                require(self.count['rows']==self.count['unmodified_delivered_rows'] and
                        self.before.digest()==self.after.digest(),'Original rows were not delivered unchanged')
                replay=trace._validate_retired_request_sequence(self.retvec,self.requests)
                arch_replay=trace._validate_retired_request_sequence(self.arch,self.requests) if self.arch else 0
                return dict(rows=self.count['rows'],first_cycle=self.first,last_cycle=self.last,
                    retire_count=self.count['retire'],vector_retire_count=len(self.retvec),
                    cvx_request_count=self.count['cvx_req'],cvx_response_count=self.count['cvx_resp'],
                    cvx_max_inflight=self.maxcvx,cvx_replay_count=replay,arch_request_replay_count=arch_replay,
                    cvx_exception_count=0,architecture_request_count=len(self.arch),
                    backend_uop_alloc_count=self.count['uop_alloc'],backend_uop_done_count=self.count['uop_done'],
                    backend_uop_max_inflight=self.maxuop)
        observer=Observer();raw_hash=hashlib.sha256();path=ROOT/'commit_trace.csv';stat=stat_identity(path)
        save(out/'parse_started.json',dict(csv=str(path),sha256=done['evidence_pins'][str(path)],
                                         full_csv_attempt=1,started=time.time()))
        begin=time.monotonic()
        with path.open('rb') as stream:
            def lines():
                for line in stream:raw_hash.update(line);yield line.decode('utf-8')
            strict=worker.checker.retirement(observer.rows(csv.DictReader(lines())),spec,gold)
        generic=observer.finish();elapsed=time.monotonic()-begin
        require(raw_hash.hexdigest()==done['evidence_pins'][str(path)],'Actual complete CSV hash differs')
        require(stat_identity(path)==stat,'CSV changed during sole traversal')
        require((strict['csv_rows'],strict['csv_last_cycle'],strict['retired_rows'])==
                (generic['rows'],generic['last_cycle'],generic['retire_count']),'Strict/generic counts differ')
        report=dict(generic=generic,strict=strict,csv_sha256=raw_hash.hexdigest())
        save(out/'recomputed_strict_prefix.json',report)
        require(report==read(ROOT/'strict_prefix.json') and
                (out/'recomputed_strict_prefix.json').read_bytes()==(ROOT/'strict_prefix.json').read_bytes(),
                'Actual CSV recomputation differs structurally/byte-wise from stored checker')
        require(dict(generic,status='VALID')==read(ROOT/'trace_summary.json'),'Stored generic differs')
        require((strict['fullcap_checks'],strict['guards'],strict['actual_output_scalar_loads'],
                 strict['helper_instruction_retirements'],strict['returned_vstart_zero'],
                 strict['setup_values_per_call'],strict['setup_bytes_per_call'])==(33792,132,33924,858,66,2178,2690),
                'Full original numeric scope incomplete')
        require(strict['routine_retire_counts']==[66]*13 and len(strict['actual_vlenb_reads'])==2 and
                len(strict['actual_capacity_returns'])==1 and strict['soc_ctrl_exit']==0 and
                strict['post_exit_park_retired']>0,'Actual CSR/capacity/CTRL/park incomplete')
        require([c['original_tuple'] for c in strict['calls']]==[r['tuple'] for r in gold['rows']],
                'Original66 ordered tuples differ')
        require(dict(observer.endpoint)==dict(prestart=128,active=128,tail=256) and
                sum(observer.categories.values())==33792,'Full endpoint/result categories differ')
        for key,value in [('call18_element0',177),('call18_element1',91),('call66_element0',91),
                          ('call66_element127',91),('call66_element128',177),('call66_element255',177),
                          ('call66_element256',91),('call66_element511',91)]:
            require(observer.selected[key]['value']==value,'Actual returned-tuple discriminator differs: '+key)
        save(out/'actual_evidence.json',dict(all_categories=dict(observer.categories),endpoint=dict(observer.endpoint),
            selected=observer.selected,before_sha256=observer.before.hexdigest(),after_sha256=observer.after.hexdigest()))
        verify(done['evidence_pins'],skip=(str(path),));static_gate();verify(prepared['code_pins'])
        require(sha(P/'complete.json')==digest and stat_identity(path)==stat,'Original terminal/artifacts changed')
        save(out/'audit.json',dict(status='ACCEPTED_E8M4_VI31_PREFIX66_DUT_CASE_ONLY_NOT_FULL2688',
            plan_sha256=PLAN_SHA,complete_sha256=digest,case_returncode=0,monitor_returncode=0,
            timed_out=False,failure_seen=False,aborted=False,retries=0,CSV_parses=1,
            calls=66,predecessors=65,capacity=512,results=33792,guards=132,helper_instructions=858,
            returned_vstart_zero=66,setup_values_per_call=2178,setup_bytes_per_call=2690,
            csv_rows=generic['rows'],retired=generic['retire_count'],last_cycle=generic['last_cycle'],
            recompute_seconds=elapsed,plan_pins_verified=744,terminal_evidence_pins_verified=14,
            recomputed_equals_stored_structure_and_bytes=True,original_inputs_unchanged=True,
            outer_worker_exit0_inferred=False,outer_service_exit0_inferred=False,
            outer_service_actual_exit='UNKNOWN_NOT_NEEDED_FOR_DUT_CASE_SCOPE',
            historical_stopped_tuple=None,full2688=False,original_Linux_execution=False,
            full_parent=False,no_DUT_or_Host_or_reference_run=True))
        print('ACCEPTED_E8M4_VI31_PREFIX66_DUT_CASE_ONLY_NOT_FULL2688',flush=True)
    except BaseException as error:
        save(out/'NOT_ACCEPTED.json',dict(status='NOT_ACCEPTED_NO_RETRY',error=repr(error),full_csv_rerun=False))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorize-terminal-audit',action='store_true')
    parser.add_argument('--prepared-sha256',required=True)
    parser.add_argument('--complete-sha256',required=True)
    args=parser.parse_args()
    require(args.authorize_terminal_audit,'Explicit conditional offline audit permission required')
    main(args.prepared_sha256,args.complete_sha256)
