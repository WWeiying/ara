#!/usr/bin/env python3
"""Host-only synthetic RVFI boundaries using actual SoC ELF and source models."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
sys.dont_write_bytecode=True
import checker as c
import replay as w

def put(check,name,value,offset=0):
    for j,b in enumerate(value.to_bytes(8,'little')): check.mem[check.s[name]+offset+j]=b

def row(pc,insn,a,read=False,value=0,rd=0,size=8):
    r={f:'0' for f in c.FIELDS}
    r.update(event='retire',pc=f'{pc:x}',insn=f'{insn:x}',mem_addr=f'{a:x}',
             mem_rmask=f'{((1<<size)-1)<<(a%8):x}' if read else '0',
             mem_wmask='0' if read else f'{((1<<size)-1)<<(a%8):x}',
             mem_wdata=f'{value:x}',rd=str(rd),rd_wdata=f'{value:x}')
    return r

def main():
    require=c.require; spec=c.specification(); tests=[]; negatives=[]
    def yes(name,fn): fn(); tests.append(name)
    def no(name,fn):
        try: fn()
        except (ValueError,KeyError,TypeError,IndexError): negatives.append(name); return
        raise AssertionError('Accepted negative '+name)
    code={int(p):v for p,v in spec['code'].items()}; s=spec['symbols']
    storepc=next(p for p in code if s['mx_reset']<=p<s['mx_compare'] and
                 (d:=c.reference.scalar(code[p])) and d['kind']=='write' and d['size']==8 and d['register']!=d['base'])
    loadpc=next(p for p in code if s['mx_compare']<=p<s['mx_allowed'] and
                (d:=c.reference.scalar(code[p])) and d['kind']=='read' and d['size']==8 and d['register']!=d['base'])
    sd=c.reference.scalar(code[storepc]); ld=c.reference.scalar(code[loadpc])
    ch=c.Checker(spec)
    def write(a,v):
        ch.regs[sd['base']]=a-sd['offset']; ch.regs[sd['register']]=v
        ch.scalar(row(storepc,code[storepc],a,value=v),code[storepc])
    def load(a,v):
        ch.regs[ld['base']]=a-ld['offset']
        ch.scalar(row(loadpc,code[loadpc],a,True,v,ld['register']),code[loadpc])
    def full_host():
        for cfg in ch.configs:
            case=cfg['id']
            for name,data in [('input',c.m.INPUT),('memory',c.m.FILL if cfg['store'] else c.m.MEMORY),
                              ('output',c.m.FILL),('expected',ch.gold[case])]:
                for i in range(1024): write(s['mx_'+name]+8*i,int.from_bytes(data[8*i:8*i+8],'little'))
            for i in range(16): write(s['mx_mask']+8*i,0 if cfg['off'] else c.MASK)
            for name,value in [('mx_case',case),('mx_scene',0),('mx_return',c.MASK),('mx_outcome',0)]: put(ch,name,value)
            ch.checkpoint()
            # All eligible misalignment cases take the legal numerical alternative
            # here. There is deliberately no required 120/24 Spike partition.
            ch.requests.append(case); ch.calls.append(case)
            ch.invalidate(s['mx_memory' if cfg['store'] else 'mx_output'],8192)
            ch.comparing=True
            for i in range(1024):
                value=int.from_bytes(ch.gold[case][8*i:8*i+8],'little')
                load(s['mx_memory' if cfg['store'] else 'mx_output']+8*i,value)
                load(s['mx_expected']+8*i,value)
            ch.comparing=False
            record=[0,9,cfg['vl'] if cfg['store'] else 128,9,s['mx_ecall'],0,0x800,8<<60,2,0]
            ch.capture={j:record[j] for j in range(8)}; ch.captures.append(ch.capture)
            ch.post={0xc20:record[2],0xc21:9,8:0}
            for j,v in enumerate(record): put(ch,'mx_records',v,80*case+8*j)
            for j,v in enumerate([record[2],9,0,0]): put(ch,'mx_post',v,32*case+8*j)
            for name,v in [('mx_satp',8<<60),('mx_outcome',1),('mx_errors',0),('mx_fatal',0)]: put(ch,name,v)
            ch.checkpoint()
        ch.capacity=1; ch.ctrl=[0]
        for name,v in [('mx_supported',144),('mx_unsupported',0),('mx_noactive',96),('mx_words_checked',144*1024),
                       ('mx_source_exit',0),('mx_done',0x7365673134340001)]: put(ch,name,v)
        require(ch.finish()['status']=='FULL144_NUMERICAL_PASS','Eligible cases may all complete numerically')
    yes('full144_actual_address_BE_value_boundary_all_numerical',full_host)
    # Completed summary mutations must not turn partial scope into full PASS.
    no('missing_last_oracle_word',lambda:(setattr(ch,'words',ch.words-1),ch.finish()))
    ch.words+=1
    no('wrong_last_case',lambda:(setattr(ch,'current',142),ch.finish())); ch.current=143
    no('wrong_source_exit',lambda:(put(ch,'mx_source_exit',77),ch.finish())); put(ch,'mx_source_exit',0)
    no('wrong_return_counter',lambda:(put(ch,'mx_noactive',95),ch.finish())); put(ch,'mx_noactive',96)
    cfg=next(x for x in ch.configs if x['offset'] and x['vl'] and not x['off'])
    record=[0,9,cfg['vl'],6 if cfg['store'] else 4,s[f"target_{cfg['op']}"],0,0x800,8<<60,1,c.MASK]
    yes('eligible_capability_record',lambda:c.capability(cfg,record[4],record))
    for label,index,value in [('wrong_target',4,record[4]+4),('wrong_cause',3,13),('wrong_phase',8,2),
                              ('fabricated_return',9,0),('wrong_vl',2,0),('wrong_vtype',1,0)]:
        bad=list(record); bad[index]=value
        no(label,lambda bad=bad:c.capability(cfg,record[4],bad))
    for key,value in [('offset',0),('vl',0),('off',True)]:
        bad=dict(cfg); bad[key]=value
        no('capability_ineligible_'+key,lambda bad=bad:c.capability(bad,record[4],record))
    q=c.Checker(spec); address=s['mx_output']
    q.regs[ld['base']]=address-ld['offset']; q.invalidate(address,8192)
    good=row(loadpc,code[loadpc],address,True,0,ld['register'])
    yes('scalar_observed_unknown_vector_byte',lambda:q.scalar(good,code[loadpc]))
    bad=dict(good,mem_rmask='7f'); no('wrong_BE',lambda:q.scalar(bad,code[loadpc]))
    bad=dict(good,mem_addr=f'{address+8:x}'); no('wrong_address',lambda:q.scalar(bad,code[loadpc]))
    bad=dict(good,rd_wdata='1'); no('wrong_observed_value',lambda:q.scalar(bad,code[loadpc]))
    bad=dict(good,mem_rmask='0'); no('missing_actual_memory_event',lambda:q.scalar(bad,code[loadpc]))
    q.current=0; q.comparing=True; q.invalidate(address,8192)
    expected=int.from_bytes(q.gold[0][:8],'little')
    bad=dict(good,rd_wdata=f'{expected^1:x}'); no('wrong_full_result',lambda:q.scalar(bad,code[loadpc]))
    q.regs[ld['base']]=address+8184-ld['offset']; q.invalidate(address+8184,8)
    expected=int.from_bytes(q.gold[0][-8:],'little')
    bad=row(loadpc,code[loadpc],address+8184,True,expected^0x8000000000000000,ld['register'])
    no('wrong_last_guard_byte',lambda:q.scalar(bad,code[loadpc]))
    cfg0=ch.configs[0]; put(q,'mx_case',0); q.current=-1
    no('self_shadow_without_actual_reset_stores',q.checkpoint)
    no('wrong_actual_instruction',lambda:q.row(dict(good,insn='00000013')))
    no('uop_done_without_owner',lambda:q.event(dict(good,event='uop_done'),code[loadpc]))
    no('cvx_response_without_owner',lambda:q.event(dict(good,event='cvx_resp'),code[loadpc]))
    backend=c.Checker(spec)
    staged=next(i for i in code.values() if i&127==7 and (i>>12)&7 in (0,5,6,7) and i not in backend.target_codes)
    backend.arch={0:(staged,0)}; backend.memory_requests=[staged]; backend.done=[0]
    yes('actual_staging_owner_completed',backend.backend_coverage)
    backend.done=[]; no('remove_backend_alloc_done_pair',backend.backend_coverage)
    backend.arch={}; no('remove_all_architecture_owners',backend.backend_coverage)
    target=code[s['target_0']]; backend.arch={0:(target,0)}; backend.memory_requests=[target]
    yes('VL0_target_can_elide_backend',backend.backend_coverage)
    backend.arch={0:(target,2)}; no('active_success_target_requires_owner_done',backend.backend_coverage)
    backend.arch={0:(target,3)}; no('alloff_nonzero_target_still_requires_owner_done',backend.backend_coverage)
    backend.arch={0:(target,2)}
    backend.exceptions=[2]; yes('early_fault_owner_may_have_no_uop',backend.backend_coverage)
    text='SEGMENT144_CAPABILITY_COMPLETE\nCore Test *** FAILED *** (tohost = 77)\n$finish called\n'
    yes('capability_protocol77',lambda:c.protocol(text,77))
    numerical='SEGMENT144_NUMERICAL_PASS\nCore Test *** SUCCESS *** (tohost = 0)\n$finish called\n'
    yes('numerical_protocol0',lambda:c.protocol(numerical,0))
    for label,extra in [('fatal','Fatal: unexpected'),('error','Error-[ASSERT]'),('otherfail','FAILED extra'),
                        ('sourcefail','SEGMENT144_FAIL'),('unexpectedfatal','UnexpectedFatal')]:
        no(label,lambda extra=extra:c.protocol(text+extra,77))
    no('wrong_protocol_source_pair',lambda:c.protocol(numerical,77))
    no('wrong_tohost',lambda:c.protocol(text.replace('77','78'),77))
    no('missing_finish',lambda:c.protocol(text.replace('$finish','end'),77))
    matcher=c.FailureMatcher(); yes('complete77_not_immediate_failure',lambda:require(not matcher.search(text),'Exact77 monitor'))
    yes('partial77_deferred_not_rewritten',lambda:require(not matcher.search('Core Test *** FAILED'),'Partial terminal line'))
    yes('partial_sourcefail_immediate',lambda:require(matcher.search('SEGMENT144_FAIL'),'Immediate source failure'))
    yes('otherfailed_immediate',lambda:require(matcher.search('Core Test *** FAILED *** (tohost = 2)'),'Other numeric failure'))
    raw=dict(returncode=0,elapsed_s=10,timed_out=False,failure_seen=False,aborted=False)
    yes('actual_rc0_source77_separate',lambda:w.outcome_gate(raw,77))
    yes('actual_rc77_source77_separate',lambda:w.outcome_gate(dict(raw,returncode=77),77))
    no('rc77_not_numerical0',lambda:w.outcome_gate(dict(raw,returncode=77),0))
    for key,value in [('returncode',None),('returncode',255),('timed_out',True),('failure_seen',True),('aborted',True),('elapsed_s',10801)]:
        no('monitor_'+key+'_'+str(value),lambda key=key,value=value:w.outcome_gate(dict(raw,**{key:value}),77))
    no('unreviewed_entry',lambda:w.entry('x',None,None,None,None))
    ledger,repo,_=w.common.image_context(w.IMAGE)
    import ara_verify.runner as engine
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); old=engine.FAIL_RE; engine.FAIL_RE=matcher
        try:
            start=time.monotonic()
            cmd=[sys.executable,'-c',"import sys,time;sys.stdout.write('SEGMENT144_FAIL');sys.stdout.flush();time.sleep(20)"]
            rc,elapsed,timed,failed=engine._run_monitored(cmd,root,root/'monitor.log',5,threading.Event())
            require(failed and not timed and elapsed<5 and type(rc) is int,'Actual immediate partial-line monitor')
            tests.append('real_process_partial_FAIL_stopped_before_timeout')
        finally: engine.FAIL_RE=old
        outcome=root/'child_outcome.unvalidated.json'; w.save(outcome,dict(raw,returncode=77))
        try: raise ValueError('deliberate post-check exception')
        except ValueError: require(w.read(outcome)['returncode']==77,'Durable numeric rc survives checker exception')
        tests.append('durable_child_before_checker_exception')
        stop=threading.Event(); stop.set(); w.common.publish(root,dict(status='FULL144_NUMERICAL_PASS'),stop)
        require(w.read(root/'complete.json')['status']=='NOT_PASS','Late abort must win'); tests.append('late_abort_terminal')
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); (root/'work').mkdir(); (root/'input.elf').write_bytes(Path(spec['elf']).read_bytes())
        inputs=dict(binary=dict(source=spec['elf'],path=str(root/'input.elf'),sha256=spec['elf_sha256']),
                    simv=dict(path=ledger['simv'],image_sha256=ledger['files']))
        command=dict(command=w.command_for(ledger,root),cwd=str(root/'work'))
        w.save(root/'inputs.json',inputs); w.save(root/'command.json',command)
        yes('actual_private_metadata',lambda:w.metadata(root,dict(spec=spec),ledger))
        for label,change in [('seed',lambda x:x['command'].__setitem__(3,'+ntb_random_seed=2')),
                             ('preload',lambda x:x['command'].__setitem__(4,'+PRELOAD=/tmp/wrong.elf')),
                             ('cwd',lambda x:x.__setitem__('cwd','/tmp'))]:
            bad=copy.deepcopy(command); change(bad); (root/'command.json').write_text(json.dumps(bad))
            no('metadata_'+label,lambda:w.metadata(root,dict(spec=spec),ledger))
        (root/'command.json').write_text(json.dumps(command)); (root/'input.elf').write_bytes(b'wrong ELF')
        no('private_ELF_drift',lambda:w.metadata(root,dict(spec=spec),ledger))
    pins={str(Path(p).resolve()):w.sha(p) for p in (c.__file__,w.__file__,__file__)}
    result=dict(status='PASS_HOST_ONLY_NOT_DUT',positive_tests=tests,negative_tests=negatives,
                positives=len(tests),negatives=len(negatives),cases=144,full_setup_bytes=144*8192*4,
                full_numerical_bytes=144*8192,synthetic_RVFI_not_hardware=True,pins=pins)
    w.save(c.HERE/'host02.json',result)
    print(json.dumps({k:result[k] for k in ('status','positives','negatives','cases','full_setup_bytes','full_numerical_bytes')}))

if __name__=='__main__': main()
