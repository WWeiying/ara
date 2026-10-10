"""One finite unordered-sum reset fixture, strict recovery, measured raw FSM delta."""
import argparse
import csv
import json
import re
import subprocess
from pathlib import Path
from types import FunctionType, SimpleNamespace

import prepare_fpu_half_reset744 as template
import qualify_external_reset_fixture as audit
import run_gap115_axi_capture as focused
import capture_sldu_two763_json as static

life, require = template.life, template.require
HERE=Path(__file__).resolve().parent
APP=life.ROOT/'apps/riscv-tests/isa/rv64uv/vgap_vmfpu_ured_intra_reset.c'
PRE=life.OUT/'vmfpu-ured-intra-reset-preflight763-agent-20261007-01'
RUN=life.OUT/'vmfpu-ured-intra-reset-old-image763-agent-20261007-01'
QUAL=life.OUT/'vmfpu-ured-intra-reset-qualified763-agent-20261007-01'
PLAN=RUN.with_name(RUN.name+'.prepared.json')
TCL=HERE/'vmfpu_ured_external_reset.tcl'
BASE=static.proof.BASE
BASE_SHA=static.proof.BASE_SHA
ARA='ara_tb.dut.i_ara_soc.i_system.i_ara'
shared=template.old.shared.shared


def expected_word(i):
    require(0<=i<512,'Full VRF index')
    reg=i//16
    if reg==1:return 0x4000000000000000
    if i==32:return 0x4060400000000000
    if 8<=reg<16:return 0x3ff0000000000000
    if reg>=24:return 0x123456789abcdef0
    return 0x0101010101010101*(0x40+reg)


def oracle(value):
    require([value('g75_result',0,4),value('g75_result',4,4),value('num_failed',0,4),value('tohost')]
            ==[680,0,0,1],'Terminal/check count')
    require(value('reduction_scalar')==0x4060400000000000,'Finite exact reduction130 differs')
    for i in range(512):require(value('fpar_vrf',8*i)==expected_word(i),'Full VRF differs')
    require([value('fpar_csr',8*i) for i in range(5)]==[128,27,0,0,0],'CSR/flags/round differs')


def states():
    return [ARA+'.gen_lanes[%d].i_lane.i_vfus.i_vmfpu.mfpu_state_q'%i for i in range(4)]


def selection():
    ss=states();guard=ss[0].rsplit('.',1)[0]+'.vinsn_issue_q_valid'
    counts=[s.rsplit('.',1)[0]+'.vinsn_queue_q.issue_cnt' for s in ss]
    return dict(ext_target=ss[0],ext_value=1,ext_guard=guard,ext_states=ss,
                ext_dump_objects=['ara_tb.clk','ara_tb.rst_n',ARA+'.axi_req_o',ARA+'.axi_resp_i',
                                  guard,*ss,*counts])


def selection_text(c):
    require(c==selection(),'Exact native state/positive owner selection required')
    atom=static.prior.runner.atom
    return ''.join('set '+k+' '+(('[list '+' '.join(map(atom,v))+']') if isinstance(v,list) else atom(v))+'\n'
                   for k,v in c.items())


def build():
    require(not PRE.exists(),'Fresh preflight required')
    bp=BASE/'admission-manifest.json';book=life.read_bound(bp,BASE_SHA)
    bits=life.read_bound(BASE/'combined-bits.json',book['output_pins'][str(BASE/'combined-bits.json')])
    require(len(bits['tests'])==len(set(bits['tests']))==763,'Exact763 baseline required')
    sourcebook=life.read_bound(static.proof.BOOK,static.BOOK_SHA)
    pins={str(bp):BASE_SHA,str(BASE/'combined-bits.json'):book['output_pins'][str(BASE/'combined-bits.json')]}
    for rel in ('hardware/src/lane/vmfpu.sv','hardware/include/ara_pkg.sv','hardware/tb/ara_tb.sv'):
        p=life.ROOT/rel;pins[str(p)]=sourcebook[str(p)]
    vm=(life.ROOT/'hardware/src/lane/vmfpu.sv').read_text()
    require("assign vinsn_issue_q_valid = (vinsn_queue_q.issue_cnt != '0);" in vm,
            'Queue positive-owner guard definition differs')
    for p in (APP,Path(__file__).resolve(),HERE/'test_run_vmfpu_ured_reset763.py',TCL,audit.run.DRIVER,
              life.ROOT/'verification/tests/gap75_start.S',life.ROOT/'verification/tests/gap75.ld',
              Path(template.__file__),Path(audit.__file__),Path(focused.__file__),Path(static.__file__)):
        pins[str(p)]=life.digest(p)
    old=life.OUT/'fpu-half-active-reset-preflight744-agent-20261007-01/compile-command.json'
    cmd=json.loads(old.read_bytes());pins[str(old)]=life.digest(old)
    cmd=[str(APP) if x.endswith('/vgap_fpu_half_active_reset.c') else str(PRE/'input.elf')
         if x.endswith('/fpu-half-active-reset-preflight744-agent-20261007-01/input.elf') else x for x in cmd]
    require('-O2' in cmd and 'ZCC' not in ' '.join(cmd),'Non-ZCC O2 toolchain')
    pins[cmd[0]]=life.digest(cmd[0]);life.check(pins);PRE.mkdir()
    life.save(PRE/'compile-command.json',cmd)
    with (PRE/'build.log').open('x') as log:subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT,timeout=120)
    reader=template.old.shared.template.s.LLVM/'llvm-readelf'
    names=('ured_seed2','ured_ones','ured_reduce','ured_wait','fpar_first_ar_load','fpar_vrf','fpar_csr','reduction_scalar',
           'g75_result','num_failed','tohost','trap_fail','source','snapshot')
    symbols={k:template.old.shared.template.s._elf_symbol(PRE/'input.elf',reader,k) for k in names}
    spike=Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
    pins[str(reader)]=life.digest(reader);pins[str(spike)]=life.digest(spike)
    sc=[str(spike),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',str(PRE/'input.elf')]
    life.save(PRE/'spike-command.json',sc)
    with (PRE/'spike.trace').open('x') as log:subprocess.run(sc,check=True,stdout=log,stderr=subprocess.STDOUT,timeout=120)
    commits=shared.spike_trace.parse_spike_commits(PRE/'spike.trace')
    writes={a:v for c in commits for a,v in c.memory_accesses if v is not None}
    oracle(lambda n,o=0,size=8:writes.get(symbols[n]+o))
    require(not any(c.pc==symbols['trap_fail'] for c in commits) and
            'exception ' not in (PRE/'spike.trace').read_text(),'Spike trap')
    require(not any(c.instruction&127 in (7,39) for c in commits
                    if 0x80000000<=c.pc<symbols['fpar_first_ar_load']),'Vector memory before reset opportunity')
    words={n:next(c.instruction for c in commits if c.pc==symbols[n]) for n in ('ured_reduce','ured_wait')}
    require(words['ured_reduce']&0xfc00707f==0x04001057,'Not exact unmasked floating unordered sum')
    targets=[]
    for s in states():
        row=bits['metrics']['fsm'][s.rsplit('.',1)[0]]
        require(row['width']==37 and row['checksum']=='3873291691' and not
                ((int(row['bits'],16)>>(36-19))&1),'INTRA reset target hit/identity differs')
        targets.append(dict(scope=s.rsplit('.',1)[0],raw_position=19,name='INTRA_LANE_REDUCTION->NO_REDUCTION',baseline=row))
    for p in PRE.iterdir():pins[str(p)]=life.digest(p)
    life.check(pins)
    pre=dict(status='FINITE_URED_SPIKE_FULL680_PASS_NO_VCS',symbols=symbols,counts=shared.reference_counts(commits,symbols),
        words=words,targets=targets,pins=pins,checks=680,full_vrf_bytes=4096,source_guard_bytes=1280,
        CSR=[128,27,0,0,0],gold=0x4060400000000000,baseline=763,selection=selection(),
        finite_tree_proof='All128 operands1 and seed2; every partial sum is positive integer<=130, '
                          'exact in binary64 independent of tree/order; no exception or fflags.',coverage_admitted=False)
    life.save(PRE/'preflight.json',pre)
    print('PREFLIGHT '+life.digest(PRE/'preflight.json')+' '+str(pre['counts']),flush=True)


def prepare(preseal):
    pre=life.read_bound(PRE/'preflight.json',preseal)
    require(not PLAN.exists() and not RUN.exists() and pre['selection']==selection(),'Fresh exact fixture only')
    image=life.read_bound(life.PLAN,life.PLAN_SEAL);require(len(image['image'])==66,'Frozen66 image required')
    pins=life.merge_pins(pre['pins'],image['image'])
    for p,sha in ((PRE/'preflight.json',preseal),(life.PLAN,life.PLAN_SEAL),
                  (focused.DOC,focused.DOC_SHA),(focused.CONVERTER,focused.CONVERTER_SHA)):
        pins=life.merge_pins(pins,{str(p):sha})
    for p in (Path(life.__file__),Path(shared.__file__),Path(audit.events.__file__),
              Path(audit.coverage.__file__),Path(shared.spike_trace.__file__)):
        pins[str(p)]=life.digest(p)
    sel=RUN.with_name(RUN.name+'.selection.tcl');entry=RUN.with_name(RUN.name+'.entry.tcl')
    with sel.open('x') as f:f.write(selection_text(selection()))
    with entry.open('x') as f:f.write('file copy {'+str(sel)+'} external-reset-selection.tcl\nsource {'+str(TCL)+'}\n')
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in (sel,entry)});life.check(pins)
    name='vmfpu_ured_intra_native_state_reset'
    cmd=[str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1','+PRELOAD='+str(PRE/'input.elf'),
         '+TESTCASE='+name,'+COMMIT_TOHOST=80001000','+COMMIT_TRACE='+str(RUN/'commit_trace.csv'),
         '+VECTOR_TRACE='+str(RUN/'vector_trace.csv'),'-cm','line+cond+fsm+tgl+branch','-cm_dir',str(RUN/'code.vdb'),
         '-cm_name',name,'+ARA_UVM_TRACE_LIMIT=100000','+ARA_CONTRACT_TRACE_LIMIT=100000','-ucli','-do',str(entry)]
    life.save(PLAN,dict(case=name,command=cmd,pins=pins,timeout_s=600,selection=selection(),preseal=preseal,
        reset_cycles=4,reset_pin='ara_tb.rst_n',selection_sha256=life.digest(sel),coverage_admitted=False,
        no_internal_force=True,automatic_retry=False,baseline=763))
    print('PREPARED '+life.digest(PLAN),flush=True)


def run(seal):
    record=life.read_bound(PLAN,seal);require(not RUN.exists(),'One-shot no retry')
    record['pins']=life.merge_pins(record['pins'],{str(PLAN):seal})
    life.run(RUN,record)
    require(life.digest(RUN/'external-reset-selection.tcl')==record['selection_sha256'],'Executed selection drift')
    vpd=RUN/'external-reset.vpd';require(0<vpd.stat().st_size<=64*1024*1024,'Focused VPD bound')
    with (RUN/'conversion.log').open('x') as log:
        subprocess.run([str(focused.CONVERTER),'+splitpacked',str(vpd),str(RUN/'external-reset.vcd')],
                       check=True,stdout=log,stderr=subprocess.STDOUT,timeout=60)
    collect(record,seal)


def exact_vector(pre,commits,vectors):
    import ara_verify.vector_commit as m
    ns=dict(vars(m));original=m._is_non_bit_exact_vector_result
    for name,fn in list(ns.items()):
        if isinstance(fn,FunctionType) and fn.__globals__ is vars(m):
            ns[name]=FunctionType(fn.__code__,ns,name,fn.__defaults__,fn.__closure__)
            ns[name].__kwdefaults__=fn.__kwdefaults__
    ns['_is_non_bit_exact_vector_result']=lambda word:False if word==pre['words']['ured_reduce'] else original(word)
    return ns['compare_vector_commits'](PRE/'spike.trace',commits,vectors,0x80000000)


def initial_bytes(commits,vectors,pre):
    owners={int(r['arch_seq']):r for r in vectors if r['event']=='alloc'}
    pcs={int(r['order']):int(r['pc'],16) for r in commits if r['event']=='retire'}
    count=0
    for r in vectors:
        if r['event']!='write':continue
        owner=owners[int(r['arch_seq'])];word=int(owner['insn'],16);vd=int(owner['vd'])
        require(int(owner['eew'])==3 and word&0xfc00707f==0x5c004057,
                'Unexpected epoch0 writer; reduction must have no pre-reset result')
        pc=pcs.get(int(r['arch_seq']))
        require(pc is not None,'Epoch0 writer without real retired PC')
        expected=0x4000000000000000 if pc==pre['symbols']['ured_seed2'] else (
            0x3ff0000000000000 if pc==pre['symbols']['ured_ones'] else 0x0101010101010101*(0x40+vd))
        require((pc!=pre['symbols']['ured_seed2'] or vd==1) and
                (pc!=pre['symbols']['ured_ones'] or vd==8),'Seed writer owner differs')
        be=int(r['be'],16);actual=int(r['wdata'],16)
        for i in range(8):
            if be>>i&1:
                require((actual>>(8*i))&255==(expected>>(8*i))&255,'Epoch0 seed byte differs');count+=1
    return count


def frontend_epochs(log,epochs,allowed):
    ev=audit.events
    observed=list(ev.uvm._RESET_OBSERVED.finditer(log))
    require([int(m['epoch']) for m in observed]==[1,2],'Reset epochs differ')
    boundary=int(observed[1]['cycle'])
    ue,ui=ev.uvm._events(log,'[CVXIF/EVENT]',ev.uvm._UVM_EVENT,10)
    ce,ci=ev.uvm._events(log,'[ARA_CONTRACT_TRACE]',ev.uvm._CONTRACT_EVENT,16)
    require(not ui and not ci and ev.uvm._event_digest(ue)==ev.uvm._event_digest(ce)
            and len(ue)<100000,'Independent CVXIF event trace differs')
    summaries=[]
    for i,(rows,_) in enumerate(epochs):
        selected=[e for e in ce if (e[0]<boundary if i==0 else e[0]>boundary)]
        counts=ev.traffic(selected);pending={}
        for e in selected:
            if e[1]:require(e[2] not in pending,'Duplicate frontend owner');pending[e[2]]=e[3]
            if e[4]:require(e[5] in pending,'Orphan frontend response');pending.pop(e[5])
        require((not pending if i else all(word in allowed for word in pending.values())),
                'Unexpected cancelled frontend opcode or recovery outstanding')
        commits=[(int(r['cycle']),r['event'],int(r['trans_id']),int(r['insn'],16) if r['event']=='cvx_req' else 0,int(r['trap']))
                 for r in rows if r['event'] in ('cvx_req','cvx_resp')]
        flattened=[(e[0],name,key,insn,exc) for e in selected for name,key,insn,exc in
                   ([('cvx_req',e[2],e[3],0)] if e[1] else [])+([('cvx_resp',e[5],0,e[6])] if e[4] else [])]
        require(ev.relative_events(commits)==ev.relative_events(flattened),'Commit/CVXIF epoch identity differs')
        summaries.append(dict(counts=counts,cancelled=pending))
    return summaries


def collect(record,seal):
    require(not QUAL.exists(),'Fresh terminal qualification only')
    pre=life.read_bound(PRE/'preflight.json',record['preseal']);life.check(record['pins']);QUAL.mkdir()
    ev=audit.events;reset=ev.run.reset
    try:
        log=(RUN/'run.vcs.log').read_text();console=(RUN/'console.log').read_text()
        require(console.count('Core Test *** SUCCESS ***')==1 and not re.search(
            r'(?m)^UVM_(ERROR|FATAL)\b|\[ARA_CONTRACT_ERROR\]|trace.*truncat|EXT_RESET_ERROR',log+console),'Terminal failure')
        cf,cr=reset.read_csv(RUN/'commit_trace.csv');vf,vr=reset.read_csv(RUN/'vector_trace.csv')
        epochs,_=reset.split_epochs(cr,vr)
        for i,(rows,vectors) in enumerate(epochs):
            ep=QUAL/('epoch%d'%i);ep.mkdir();reset.write_csv(ep/'commit_trace.csv',cf,rows);reset.write_csv(ep/'vector_trace.csv',vf,vectors)
        pending={}
        for r in epochs[0][1]:
            if r['event']=='alloc':pending[int(r['vid'])]=r
            elif r['event']=='done':require(int(r['vid']) in pending,'Orphan completion');pending.pop(int(r['vid']))
        allowed=set(pre['words'].values())
        require(pending and pre['words']['ured_reduce'] in {int(r['insn'],16) for r in pending.values()} and
                all(int(r['insn'],16) in allowed for r in pending.values()),'Wrong reset-cancelled backend owner')
        backend=[ev.backend(*epochs[0],{int(r['arch_seq']) for r in pending.values()}),ev.backend(*epochs[1],set())]
        seedbytes=initial_bytes(*epochs[0],pre)
        frontend=frontend_epochs(log,epochs,allowed)
        prefix=shared.spike_trace.compare_commit_prefix(PRE/'spike.trace',QUAL/'epoch0/commit_trace.csv',
                                                      0x80000000,rvfi_store_data_layout='unshifted')
        require(prefix['status']=='PREFIX' and prefix['mismatch'] is None and
                prefix['skipped_unobservable_register_values']==prefix['ara_trap_events']==0,'Cancelled prefix differs')
        scalar=shared.spike_trace.compare_commit_prefix(PRE/'spike.trace',QUAL/'epoch1/commit_trace.csv',
            0x80000000,terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
        shared.scalar_exact(scalar,pre['counts'])
        vector=exact_vector(pre,QUAL/'epoch1/commit_trace.csv',QUAL/'epoch1/vector_trace.csv')
        require(vector['status']=='PASS' and all(vector[k]==0 for k in ('skipped_unknown_bytes','non_bit_exact_instructions','unobservable_instructions'))
                and not vector['incomplete_requests'] and not vector['unretired_requests'],'Recovery full vector differs')
        memory={}
        for row in epochs[1][0]:
            if row['event']=='retire':
                store=shared.scalar_store(row)
                if store:memory.update({store[0]+i:b for i,b in enumerate(store[1])})
        def value(name,offset=0,size=8):
            address=pre['symbols'][name]+offset
            require(all(address+i in memory for i in range(size)),'Missing full recovery oracle byte')
            return int.from_bytes(bytes(memory[address+i] for i in range(size)),'little')
        oracle(value)
        source=__import__('inspect').getsource(audit.wave)
        require(source.count("'stage': 4")==1,'Frozen waveform stage type changed')
        source=source.replace("'stage': 4","'stage': 3")
        ns=dict(audit.wave.__globals__,gold=SimpleNamespace(expected_word=expected_word))
        exec(compile(source,str(Path(__file__).resolve()),'exec'),ns)
        axi=ns['wave'](RUN/'external-reset.vcd',record['selection'],pre['symbols']['source']+128,pre['symbols']['snapshot'])
        axi['status']='FOUR_INTRA_VALID_FOUR_CYCLE_RESET_ALL_AR_R_AW_W_B_PASS'
        names=states()+[s.rsplit('.',1)[0]+'.vinsn_queue_q.issue_cnt' for s in states()]+['ara_tb.rst_n']
        ns=dict(audit.parser.vcd.__globals__,ROOT='ara_tb',WIDTHS={p[7:]:1 if p=='ara_tb.rst_n' else 3 for p in names})
        it=iter(FunctionType(audit.parser.vcd.__code__,ns)(RUN/'external-reset.vcd'));_,decl=next(it);windows=[]
        for time,before,after in it:
            code=decl['ara_tb.rst_n']['code']
            if before.get(code)=='1' and after.get(code)=='0':
                samples={p:int(before[decl[p]['code']],2) for p in names[:-1]}
                require(all(samples[p]==1 for p in states()) and all(samples[p]>0 for p in names[4:-1]),'Actual INTRA/positive-owner reset window differs')
                windows.append(dict(time=time,values=samples))
        require(len(windows)==1 and windows[0]['time']==axi['resets_100fs'][0],'Unique reset boundary differs')
        uvm=reset.check_real_uvm_log(RUN/'run.vcs.log',require_events=True,require_backend=True,require_axi=True,
                                   vector_trace=RUN/'vector_trace.csv',reset_kind='state')
        require(uvm['uvm_backend_event_sha256']==uvm['vector_backend_event_sha256'] and
                all(uvm['contract_counts'][k]==0 for k in ('exceptions','protocol_errors','outstanding')),'Lifecycle/protocol differs')
        book=life.read_bound(BASE/'admission-manifest.json',BASE_SHA);bp=BASE/'combined-bits.json'
        before=life.read_bound(bp,book['output_pins'][str(bp)])
        with (QUAL/'single-inputs.txt').open('x') as f:f.write(str(audit.coverage.DESIGN)+'\n'+str(RUN/'code.vdb')+'\n')
        single=audit.coverage.bitmap.collect(QUAL/'single-inputs.txt');combined=audit.coverage.bitmap.combine(before,single)
        delta=audit.coverage.all_delta(before,combined);hits=[]
        for t in pre['targets']:
            new=single['metrics']['fsm'][t['scope']];old=before['metrics']['fsm'][t['scope']]
            require((new['width'],new['checksum'])==(old['width'],old['checksum']),'FSM design/shape differs')
            hits.append(dict(scope=t['scope'],raw_position=19,single=bool(int(new['bits'],16)&(1<<17)),
                             new=bool((int(new['bits'],16)&~int(old['bits'],16))&(1<<17))))
        for name,obj in [('prefix-scalar.json',prefix),('recovery-scalar.json',scalar),('recovery-vector.json',vector),
            ('axi-audit.json',axi),('reset-window.json',windows),('backend-audit.json',backend),('uvm-audit.json',uvm),
            ('frontend-audit.json',frontend),
            ('single-bits.json',single),('raw-delta.json',delta),('fsm-targets.json',hits)]:life.save(QUAL/name,obj)
        life.check(record['pins'])
        pins={**record['pins'],**{str(p):life.digest(p) for p in RUN.rglob('*') if p.is_file()},
              **{str(p):life.digest(p) for p in QUAL.rglob('*') if p.is_file()}}
        life.save(QUAL/'qualification.json',dict(status='FINITE_URED_FOUR_INTRA_EXTERNAL_RESET_ARCHITECTURE_PASS_NOT_ADMITTED',
            plan_seal=seal,baseline=763,checks=680,full_vrf_bytes=4096,CSR_flags0=True,epoch_count=2,
            source_guards_checked=True,actual_reset_targets=sum(t['new'] for t in hits),raw_delta=delta['metrics'],
            finite_tree_proof=pre['finite_tree_proof'],backend=backend,epoch0_seed_bytes=seedbytes,
            frontend=frontend,pins=pins,coverage_admitted=False))
        print('QUALIFIED '+life.digest(QUAL/'qualification.json')+' actual_new_FSM_targets='+str(sum(t['new'] for t in hits)),flush=True)
    except Exception as error:
        life.save(QUAL/'failure.json',dict(status='HOLD_NOT_ADMITTED',first_error=str(error),no_retry=True));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('build','prepare','run'))
    p.add_argument('--seal');a=p.parse_args()
    if a.mode=='build':build()
    elif a.mode=='prepare':prepare(a.seal)
    else:run(a.seal)
