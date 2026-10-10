"""Exact17 clip-fault terminal qualification; no simulation, bitmap or admission."""
import argparse
import ast
from collections import Counter,defaultdict
import inspect
import json
import math
from pathlib import Path
import re
from types import SimpleNamespace

import build_narrow_clip_reject_preflight as p
import collect_narrow_reject_r1_cached_strict as inherited
import collect_opivx_vsbc_strict as common
import run_narrow_clip_reject_simulation_450 as runner_module
from ara_verify.contract import parse_contract_summary,check_contract_log
from qualify_store_fault_flush_terminal import elf_instruction

RUNNER_SHA='875c0af5cb0deae977d6d192aebc3e7111b0bab509263ef86055507c12152664'
RUNNER_TEST_SHA='4e7aed1e6570527dd61074914d21faa1cea4d2315ff4256be63e56a8b9f037af'
RUNNER_PATH=Path(runner_module.__file__).resolve()
RUNNER_TEST=RUNNER_PATH.with_name('test_run_narrow_clip_reject_simulation_450.py')
runner_module.require(runner_module.life.digest(RUNNER_PATH)==RUNNER_SHA and
                      runner_module.life.digest(RUNNER_TEST)==RUNNER_TEST_SHA,
                      'Exact reviewed450 runner/test source required')
runner=SimpleNamespace(**runner_module.namespace())
life,require=p.life,p.require
PRE=life.OUT/'narrow-clip-reject-preflight-737-agent-20261006-01'
PRE_SEAL='f0fc1ee53df6af7c7a1b78df9ff2aa5bb4655dc2c805268dcce32606a3b7576e'
OLD_SHA='cd24eb5c8c5398a94cb18a7e9465d483179d5bac2b0cba2d8dc278a95a4fabb8'
WORDS=[int(c['word'],16) for c in p.CASES]
STATUS='CLIP17_EXACT450_TERMINAL_QUALIFICATION_PLAN_NOT_EXECUTED'


def terminal(state, actual, started, record):
    require(state.get('status')=='SIMULATION_EXITED_NOT_ADMITTED' and
            type(state.get('returncode')) is int and state['returncode']==0 and
            state.get('case')==runner.NAME and state.get('timeout') is False and
            state.get('coverage_admitted') is False and state.get('admission_performed') is False and
            state.get('terminal_oracle_verified') is False,'Successful actual OS receipt required')
    require(actual==record and started['command']==record['command'] and
            started['input_elf']==str(runner.ELF) and started['elf_sha256']==runner.ELF_SHA and
            started['image']==str(life.IMAGE) and started['image_sha256']==runner.IMAGE_SHA and
            all(type(x) is int for x in (started['pid'],started['process_group'],state['pid'],started['budget_s'])) and
            started['pid']>0 and started['pid']==started['process_group']==state['pid'] and
            started['budget_s']==runner.BUDGET and started['foreground_lifetime'] is True and
            started['coverage_admitted'] is False,'Startup PID/group/budget/command identity differs')
    require(type(state.get('wall_seconds')) in (float,int) and
            math.isfinite(state['wall_seconds']) and state['wall_seconds']>=0,'Invalid OS wall receipt')


def audit_retirements(rows):
    blob=runner.ELF.read_bytes()
    require(life.digest(runner.ELF)==runner.ELF_SHA,'Sealed ELF drift')
    for row in rows:
        if row['event']=='retire':
            pc,word=int(row['pc'],16),int(row['insn'],16)
            require(word&3==3 and elf_instruction(blob,pc,4)==word,'Retirement opcode outside sealed no-C ELF')


def lifecycle(rows,vectors,symbols):
    starts,pending,live={}, {}, {}
    intervals=defaultdict(list);requests=[];responses=[];rejected=[]
    allocs,done=Counter(),Counter();last=-1
    for row in rows:
        cycle,seq,tid=int(row['cycle']),int(row['order']),int(row['trans_id'])
        event=row['event'];require(cycle>=last,'Reversed commit time');last=cycle
        if event=='arch_start':
            require(seq>=0 and seq not in starts and tid not in pending and int(row['trap'])==0,
                    'Duplicate/invalid architecture or live transaction')
            starts[seq]=row;pending[tid]=[seq,False]
        elif event=='cvx_req':
            require(tid in pending and not pending[tid][1],'Unknown/duplicate request')
            owner=pending[tid][0]
            require(row['insn']==starts[owner]['insn'] and seq==-1 and int(row['trap'])==0,
                    'Request opcode/schema differs')
            pending[tid][1]=True;requests.append(owner)
        elif event=='cvx_resp':
            require(tid in pending and pending[tid][1] and seq==-1 and
                    int(row['insn'],16)==int(row['pc'],16)==0 and int(row['trap']) in (0,1),
                    'Unknown/duplicate/malformed response')
            owner=pending.pop(tid)[0];responses.append(owner)
            if int(row['trap']):rejected.append(owner)
        elif event in ('uop_alloc','uop_done'):
            vid=int(row['port'])
            require(seq in starts and 0<=vid<8 and tid==int(starts[seq]['trans_id']) and
                    row['insn']==starts[seq]['insn'] and cycle>=int(starts[seq]['cycle']),
                    'Backend identity/transaction/time differs')
            if event=='uop_alloc':
                require(vid not in live,'Global backend VID reused while live')
                item=dict(owner=seq,start=cycle,end=None);live[vid]=item;intervals[vid].append(item)
                allocs[seq,vid,cycle]+=1
            else:
                require(vid in live and live[vid]['owner']==seq and cycle>=live[vid]['start'],'Unowned/early backend completion')
                live.pop(vid)['end']=cycle;done[seq,vid,cycle]+=1
        else:require(event=='retire' and int(row['trap'])==0,'Unknown event/native trap retirement')
    require(not live and not pending and Counter(requests)==Counter(responses)==Counter(starts.keys()) and
            Counter((s,v) for s,v,c in allocs.elements())==Counter((s,v) for s,v,c in done.elements()),
            'Incomplete CVX/backend conservation')
    bad=[s for s,r in starts.items() if int(r['insn'],16) in WORDS]
    require(len(bad)==17 and [int(starts[s]['insn'],16) for s in bad]==WORDS and rejected==bad,
            'Exact ordered17 fault owners required, including repeated word contexts')
    require(not any(s in bad for s,v,c in allocs) and not any(s in bad for s,v,c in done),
            'Rejected request has backend activity')
    recovery=[s for s,r in starts.items() if int(r['insn'],16)==p.RECOVERY]
    require(len(recovery)==1 and any(s==recovery[0] for s,v,c in allocs),'Recovery backend absent')
    retired=[r for r in rows if r['event']=='retire' and int(r['insn'],16)==p.RECOVERY]
    require(len(retired)==1 and int(retired[0]['pc'],16)==symbols['gnr_recovery'],'Recovery precise retirement differs')
    va,vd=Counter(),Counter();metadata={};last=-1
    for row in vectors:
        seq,vid,cycle=int(row['arch_seq']),int(row['vid']),int(row['cycle']);event=row['event']
        require(cycle>=last and (int(row['nr_lanes']),int(row['vlen_bits']))==(4,1024),'Vector time/shape differs');last=cycle
        require(seq not in bad,'Rejected native activity, including config/zero-BE rows')
        if event=='config':continue
        require(seq in starts and event in ('alloc','done','write') and row['insn']==starts[seq]['insn'],
                'Unknown native owner/opcode/event')
        if event=='alloc':
            key=seq,vid,cycle;require(key not in metadata,'Duplicate native allocation')
            metadata[key]=row;va[key]+=1
        else:
            eligible=[x for x in intervals[vid] if x['start']<=cycle and x['end'] is not None and cycle<=x['end'] and x['owner']==seq]
            require(len(eligible)==1,'Ambiguous/out-of-lifetime native event')
            key=seq,vid,eligible[0]['start'];require(key in metadata,'Native event before allocation')
            require(all(row[k]==metadata[key][k] for k in ('insn','use_vd','vd','eew','vl','vstart')),'Native metadata drift')
            if event=='done':vd[seq,vid,cycle]+=1
            else:require(int(row['use_vd'])==1 and 0<=int(row['lane'])<4,'Invalid native writer')
    require(va==allocs and vd==done,'Commit/vector allocation/completion mismatch')
    ledger=[dict(cell=i,arch_seq=s,opcode='0x%08x'%WORDS[i],fault_pc='0x%016x'%symbols['gnr_bad_%02d'%i],
                 trans_id=int(starts[s]['trans_id']),rejected_backend_uops=0,rejected_native_events=0)
            for i,s in enumerate(bad)]
    return dict(requests=len(requests),responses=len(responses),exceptions=17,rejected_arch_seqs=bad,
        recovery_arch_seq=recovery[0],backend_uops=sum(allocs.values()),rejected_backend_uops=0,
        rejected_vrf_activities=0,per_cell=ledger,response_placeholder_not_used_as_opcode_identity=True)


def observed(rows,symbols):
    retired=[r for r in rows if r['event']=='retire']
    require(retired and all(int(r['insn'],16)&3==3 for r in retired),'No-C case rejects all compressed retirement')
    require(life.digest(Path(inherited.__file__))==OLD_SHA,'Frozen observed oracle changed')
    source=inspect.getsource(inherited.observed);tree=ast.parse(source)
    sizes={24:17,26:3,15489:2094,106496:12288,13312:1536,119808:13824,312:221}
    # Only this source-pinned function contains these documented array extents/counts.
    expected={24:5,26:2,15489:1,106496:1,13312:1,119808:1,312:1}
    actual=Counter(n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and type(n.value) is int and n.value in sizes)
    require(actual==Counter(expected),'Unexpected frozen signature dimension constants')
    positions=sorted((n.lineno,n.col_offset,n.value) for n in ast.walk(tree)
                     if isinstance(n,ast.Constant) and type(n.value) is int and n.value in sizes)
    require([(line,value) for line,col,value in positions]==
            [(5,26),(6,24),(38,24),(46,24),(47,24),(49,15489),(49,26),(49,24),
             (49,106496),(50,13312),(50,119808),(50,312)],'Frozen dimension positions differ')
    class Dimensions(ast.NodeTransformer):
        def visit_Constant(self,node):
            return ast.copy_location(ast.Constant(sizes[node.value]),node) if type(node.value) is int and node.value in sizes else node
    namespace=dict(inherited.observed.__globals__,oracle=type('Oracle',(),{'signatures':staticmethod(p.oracle_functions()['signatures'])}))
    exec(compile(ast.fix_missing_locations(Dimensions().visit(tree)),str(Path(__file__).resolve())+':observed','exec'),namespace)
    return namespace['observed'](rows,symbols)


def tracer_exact(text,rows,symbols):
    regex=re.compile(r'^\s*\d+ns\s+(\d+)\s+([MSU])\s+([0-9a-fA-F]{16})\s+\d+\s+([0-9a-fA-F]{8})\b')
    actual=[m.groups() for line in text.splitlines() if (m:=regex.match(line))]
    retired=[r for r in rows if r['event']=='retire']
    wanted=[(str(int(r['cycle'])),'M',r['pc'],r['insn']) for r in retired]
    require(wanted and actual[:len(wanted)]==wanted,'Full no-C tracer/retire prefix differs')
    tail=actual[len(wanted):]
    require(not tail or tail==[(wanted[-1][0],'M','%016x'%(int(wanted[-1][2],16)+4),'0000006f')],
            'Unexpected no-C post-terminal tracer tail')
    events=re.findall(r'Exception @\s*([0-9a-fA-F]+), PC: ([0-9a-fA-F]+), Cause: ([^,\n]+)',text)
    require(len(events)==text.count('Exception @')==17 and [(int(e[1],16),e[2]) for e in events]==
            [(symbols['gnr_bad_%02d'%i],'Illegal Instruction') for i in range(17)] and
            [int(v,16) for v in re.findall(r'tval: ([0-9a-fA-F]+)',text)]==WORDS,
            'Exact17 exception EPC/cause/tval differs')
    return dict(exceptions=17,cause=2,pcs=[symbols['gnr_bad_%02d'%i] for i in range(17)],tvals=WORDS,tracer_tail=tail)


def stdout_gate(console,log,control):
    require(log.count('Core Test *** SUCCESS ***')==1 and 'Core Test *** FAILED ***' not in log,'Missing/repeated/nonPASS core marker')
    for text in (console,log):
        for line in text.splitlines():
            if re.search(r'\b(?:UVM_ERROR|UVM_FATAL)\b',line):
                require(re.fullmatch(r'\s*(?:UVM_ERROR|UVM_FATAL)\s*:\s*0+\s*',line) is not None,'UVM error/fatal')
        require(not re.search(r'\b(?:Error:|Fatal:|Error-\[|Fatal-\[)',text),'Simulator diagnostic error')
    lines=[line for line in console.splitlines() if '[ARA_CONTRACT]' in line]
    require(len(lines)==1,'Unique complete contract summary required')
    value=parse_contract_summary(lines[0]);require(value is not None,'Malformed/missing contract fields')
    require((value['requests'],value['responses'],value['exceptions'])==
            (control['requests'],control['responses'],17) and
            all(value[k]==0 for k in ('protocol_errors','outstanding','req_stalled','resp_stalled')),
            'CVX/exception/stall/protocol contract differs')
    return value


def vector_gate(result,rejected,reference):
    inherited.vector_exact(result,rejected,reference)
    require(type(result.get('vector_destination_requests')) is int and
            result['vector_destination_requests']==33 and type(result.get('prefix_vector_destination_requests')) is int and
            result['prefix_vector_destination_requests']==33 and
            all(result.get(k)==[] for k in ('verified_zero_write_traps','verified_identity_write_traps',
                                          'verified_probed_load_faults','verified_trapped_destination_requests')),
            'Exact33 normal writers required; no exceptional-write accommodation')
    require(type(result.get('compared_bytes')) is int and result['compared_bytes']==4100 and
            type(result['instructions'][-1].get('compared_bytes')) is int and
            result['instructions'][-1]['compared_bytes']==4,
            'Exact32 full registers plus four recovery bytes required')


def dependencies():
    return [Path(__file__).resolve(),Path(__file__).with_name('test_qualify_narrow_clip_reject_terminal.py'),
            Path(inherited.__file__),Path(common.__file__),Path(p.__file__),RUNNER_PATH,
            Path(elf_instruction.__code__.co_filename).resolve(),
            RUNNER_TEST,
            Path(p.__file__).with_name('test_actual_narrow_clip_reject_preflight.py'),
            *sorted((life.ROOT/'verification/ara_verify').rglob('*.py'))]


def prepared_gate(record,run,pre):
    expected=[str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
        '+PRELOAD='+str(PRE/'input.elf'),'+TESTCASE='+p.APP.stem,'+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(run/'commit_trace.csv'),'+VECTOR_TRACE='+str(run/'vector_trace.csv'),
        '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(run/'code.vdb'),'-cm_name',p.APP.stem]
    require(record['command']==expected and record['output']==str(run) and record['case']==p.APP.stem and
            record['preflight']==str(PRE/'preflight-manifest.json') and record['preflight_seal']==PRE_SEAL and
            type(record['timeout_s']) is int and record['timeout_s']==runner.BUDGET==450 and
            record['coverage_admitted'] is False and record['admission_performed'] is False,
            'Exact prepared no-FSDB450 command/preflight contract required')
    require(life.digest(RUNNER_PATH)==RUNNER_SHA and life.digest(RUNNER_TEST)==RUNNER_TEST_SHA and
            record['pins'].get(str(RUNNER_PATH))==RUNNER_SHA and
            record['pins'].get(str(RUNNER_TEST))==RUNNER_TEST_SHA,
            'Missing/drifting exact450 runner/test pins')
    require(record['targets']==pre['targets'] and all(record['pins'].get(x)==h for x,h in pre['pins'].items()),
            'Missing preflight/source/tool/target pins')
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(image['image'])==66 and all(record['pins'].get(x)==h for x,h in image['image'].items()),'Missing frozen66 image pins')
    runner.verify_prepared(run,record)


def prepare(run,runseal,output):
    require(run.parent==life.OUT and run.resolve()==run and output.parent==life.OUT and output.resolve()==output and
            not output.exists(),'Canonical run/fresh qualification plan required')
    recordpath=run.with_name(run.name+'.prepared.json');record=life.read_bound(recordpath,runseal)
    pre=p.verify(PRE,PRE_SEAL);prepared_gate(record,run,pre)
    pins=life.merge_pins(record['pins'],{str(recordpath):runseal,str(PRE/'preflight-manifest.json'):PRE_SEAL})
    deps=dependencies()
    pins=life.merge_pins(pins,{str(x.absolute()):life.digest(x) for x in deps});life.check(pins)
    output.mkdir();life.save(output/'plan.json',dict(status=STATUS,run=str(run),prepared=str(recordpath),prepared_seal=runseal,
        preflight=str(PRE),preflight_seal=PRE_SEAL,pins=pins,reference_counts=pre['reference_counts'],
        targets=pre['targets'],qualification_only=True,coverage_admitted=False,simulations_started=False))
    print(json.dumps(dict(plan=str(output/'plan.json'),seal=life.digest(output/'plan.json'))))


def verify_plan(path,seal):
    plan=life.read_bound(path,seal)
    require(plan['status']==STATUS and plan['preflight']==str(PRE) and plan['preflight_seal']==PRE_SEAL and
            plan['coverage_admitted'] is False and plan['qualification_only'] is True,'Exact qualification plan required')
    run=Path(plan['run']);require(run.parent==life.OUT and run.resolve()==run and
            plan['prepared']==str(run.with_name(run.name+'.prepared.json')),'Canonical prepared/run binding')
    life.check(plan['pins']);pre=p.verify(PRE,PRE_SEAL)
    record=life.read_bound(Path(plan['prepared']),plan['prepared_seal']);prepared_gate(record,run,pre)
    mandatory=life.merge_pins(record['pins'],{plan['prepared']:plan['prepared_seal'],
        str(PRE/'preflight-manifest.json'):PRE_SEAL})
    mandatory=life.merge_pins(mandatory,{str(x.absolute()):life.digest(x) for x in dependencies()})
    require(all(plan['pins'].get(x)==h for x,h in mandatory.items()),'Missing mandatory qualification dependency pins')
    require(plan['targets']==pre['targets'] and plan['reference_counts']==pre['reference_counts'],'Plan target/reference drift')
    return plan,record,pre


def collect(planpath,seal,output):
    plan,record,pre=verify_plan(planpath,seal);run=Path(plan['run'])
    require(output.parent==life.OUT and output.resolve()==output and not output.exists(),'Fresh terminal qualification output required')
    require((run/'simulation-status.json').is_file(),'HOLD no terminal: no qualification output created')
    pins=life.merge_pins(plan['pins'],{str(planpath):seal})
    def read(name):
        path=run/name;require(path.resolve()==path and path.is_file(),'Missing/aliased terminal evidence')
        raw=path.read_bytes();h=__import__('hashlib').sha256(raw).hexdigest()
        require(life.digest(path)==h,'Changing terminal evidence')
        pins.update(life.merge_pins(pins,{str(path):h}));return raw
    output.mkdir()
    try:
        state=json.loads(read('simulation-status.json'))
        require(state['status']=='SIMULATION_EXITED_NOT_ADMITTED' and type(state['returncode']) is int and
                state['returncode']==0 and state['case']==p.APP.stem and state['coverage_admitted'] is False and
                state['admission_performed'] is False,'Failed/timeout/nonterminal run')
        terminal(state,json.loads(read('manifest.json')),json.loads(read('started.json')),record)
        rows=common.read_csv(read('commit_trace.csv'),common.COMMIT_FIELDS)
        vectors=common.read_csv(read('vector_trace.csv'),common.VECTOR_FIELDS)
        audit_retirements(rows)
        control=lifecycle(rows,vectors,pre['symbols']);gold=observed(rows,pre['symbols'])
        trap=tracer_exact(read('trace_hart_0.log').decode(),rows,pre['symbols']);read('trace_hart_0_commit.log')
        contract=stdout_gate(read('console.log').decode(),read('run.vcs.log').decode(),control)
        require(not check_contract_log(run/'run.vcs.log'),'Contract checker failure')
        scalar=common.spike_trace.compare_commit_prefix(PRE/'spike.trace',run/'commit_trace.csv',0x80000000,
            terminal_tohost_address=pre['symbols']['tohost'],rvfi_store_data_layout='unshifted')
        common.scalar_exact(scalar,pre['reference_counts'])
        reference=p.frozen.shared.parse_spike_commits(PRE/'spike.trace')
        vector=common.compare_vector_commits(PRE/'spike.trace',run/'commit_trace.csv',run/'vector_trace.csv',0x80000000)
        vector_gate(vector,control['rejected_arch_seqs'],reference)
        # No-C retirement plus complete scalar memory count leaves no RVC memory gap.
        vdb=run/'code.vdb';members=sorted(x for x in vdb.rglob('*') if x.is_file())
        require(members and not any(x.is_symlink() for x in vdb.rglob('*')),'Missing/aliased VDB')
        for path in members:read(str(path.relative_to(run)))
        artifacts={'scalar-comparison.json':scalar,'vector-comparison.json':vector,'observed-signatures.json':gold,
                   'lifecycle.json':control,'trap-proof.json':trap,'contract-summary.json':contract}
        for name,value in artifacts.items():life.save(output/name,value)
        require(members==sorted(x for x in vdb.rglob('*') if x.is_file()),'VDB membership drift');life.check(pins)
        result=dict(status='CLIP17_FULL_SCALAR_MEMORY_VECTOR_CSR_TRAP_QUALIFIED_NOT_ADMITTED',run=str(run),
            baseline=737,preflight_seal=PRE_SEAL,checks=2094,expected_traps=17,normal_vector_writers=33,
            runner_sha256=RUNNER_SHA,runner_test_sha256=RUNNER_TEST_SHA,timeout_s=450,
            full_scalar_differential_qualified=True,all_scalar_memory_differential_qualified=True,
            software_noC=True,compressed_retirements=0,skipped_scalar_memory=0,full_VRF_snapshots=3,
            per_cell_rejected_backend_uops=0,per_cell_rejected_native_events=0,coverage_admitted=False,
            raw_bitmap_collected=False,rtl_changed=False,simulations_started=False,new_RTL_signoff=False,
            OS_returncode=0,terminal_source='FOREGROUND_RUNNER_OS_RETURN_RECEIPT',native_known_write_bytes=4100,
            native_cycle_qualified=False,whole_ISA_qualified=False,official_denominator_verified=False,application_approval=False)
        life.save(output/'status.json',result)
        life.save(output/'qualification-seal.json',dict(input_pins=pins,
            output_pins={str(x):life.digest(x) for x in output.iterdir() if x.is_file()},result=result))
        print(json.dumps(dict(output=str(output),seal=life.digest(output/'qualification-seal.json'),result=result)))
    except Exception as error:
        life.save(output/'failure.json',dict(status='QUALIFICATION_HOLD_NOT_ADMITTED',reason=str(error)));raise


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('prepare','verify','collect'))
    for name in ('run','output','plan'):parser.add_argument('--'+name,type=Path)
    for name in ('run-seal','seal'):parser.add_argument('--'+name)
    a=parser.parse_args()
    if a.mode=='prepare':require(a.run and a.run_seal and a.output,'Prepare arguments');prepare(a.run.absolute(),a.run_seal,a.output.absolute())
    else:
        require(a.plan and a.seal,'Plan/seal required')
        if a.mode=='verify':verify_plan(a.plan.absolute(),a.seal);print('VERIFY_PASS NO_VCS NO_COLLECTION')
        else:require(a.output,'Fresh output required');collect(a.plan.absolute(),a.seal,a.output.absolute())


if __name__=='__main__':main()
