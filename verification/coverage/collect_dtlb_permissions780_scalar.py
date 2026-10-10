"""Source-bound scalar page faults: frozen collector successor, offline only."""
from collections import Counter
import argparse
import csv
from pathlib import Path
import re
import subprocess
from types import FunctionType

import collect_dtlb_ppn_swap1200 as native
import run_dtlb_permissions780 as runner
import collect_dtlb_ppn_swap1200_schema as zero_schema
from ara_verify import spike_trace, vector_commit, contract

life,require=runner.life,runner.require
SCOPE=native.SCOPE
MMU=SCOPE.rsplit('.',1)[0]
namespace=dict(vars(native),runner=runner)
terminal_gate=FunctionType(native.terminal_gate.__code__,namespace)
identity_gate=FunctionType(native.identity_gate.__code__,namespace)


def source_trap_contract():
    book=life.read_bound(runner.software.p.shared.SOURCE,runner.software.p.shared.SOURCE_SHA)
    pins={}
    for rel in ('hardware/deps/cva6/core/cva6_rvfi.sv','hardware/tb/ara_commit_monitor.sv'):
        path=life.ROOT/rel;pins[str(path)]=book[str(path)]
        require(life.digest(path)==pins[str(path)],'Frozen trap observation source')
    rvfi=(life.ROOT/'hardware/deps/cva6/core/cva6_rvfi.sv').read_text()
    normalized=re.sub(r'\s+','',re.sub(r'/\*.*?\*/|//[^\n]*','',rvfi,flags=re.S))
    formula=('valid=(commit_ack[i]&&!ex_commit_valid&&!commit_drop[i])||'
        '(exception&&(ex_commit_cause==riscv::ENV_CALL_MMODE||'
        'ex_commit_cause==riscv::ENV_CALL_SMODE||ex_commit_cause==riscv::ENV_CALL_UMODE));')
    require(formula in normalized,'Complete RVFI valid formula')
    monitor=(life.ROOT/'hardware/tb/ara_commit_monitor.sv').read_text()
    require('if (rvfi_instr_i[port].valid)' in monitor,'Frozen valid-gated commit monitor')
    return pins


def handler_gate(rows,commits,s):
    reference={a:v for c in commits for a,v in c.memory_accesses if v is not None}
    fault_cases=[r for r in runner.software.audit.cases() if r['mcause']]
    groups=[];active=None
    for index,row in enumerate(rows):
        pc=int(row['pc'],16);word=int(row['insn'],16)
        if pc==s['dpa_handler_begin']:
            require(active is None,'No nested handler')
            enables=[r for r in rows[:index] if int(r['pc'],16)==s['dpa_enable']]
            require(enables,'Fault has an explicit preceding MPRV window')
            active=dict(start_cycle=int(row['cycle']),enable_cycle=int(enables[-1]['cycle']),
                        reads={},start_order=int(row['order']))
        if active is None: continue
        require(s['dpa_handler_begin']<=pc<s['dpa_handler_end'],'No unexpected handler control transfer')
        rd=int(row['rd'])
        require(rd in (0,5,6,7),'Only compiler-reserved handler GPR clobbers')
        if word&127==0x73 and (word>>12)&7==2 and (word>>15)&31==0 and rd:
            active['reads'].setdefault(word>>20,[]).append(int(row['rd_wdata'],16))
        if word==0x30200073:
            k=len(groups);require(k<5 and index+1<len(rows),'Exactly five complete handler returns')
            case=fault_cases[k];site=s['dpa_store' if case['operation']=='store' else 'dpa_load']
            expected={0x342:[case['mcause']],0x341:[site,site],
                      0x343:[runner.software.p.address(0)],
                      0x300:[reference[s['dpa_traps']+32*k+24]]}
            require(active['reads']==expected,'Exact handler mcause/mepc/mtval/mstatus, no substituted gold')
            require(int(rows[index+1]['pc'],16)==site+4,'Exact 32-bit fault-site resume, including 2mod4 PCs')
            groups.append(dict(enable_cycle=active['enable_cycle'],handler_cycle=active['start_cycle'],
                start_order=active['start_order'],return_order=int(row['order']),
                cause=case['mcause'],fault_pc=site,tval=runner.software.p.address(0),
                mstatus=expected[0x300][0],resume_pc=site+4))
            active=None
    require(active is None and len(groups)==5,'Five exact native handler lifetimes')
    return groups


def architecture_gate(rows,commits,s):
    require(rows and all(tuple(r)==native.FIELDS and all(v not in ('',None) for v in r.values())
                        for r in rows),'Full exact commit schema')
    require([int(r['order']) for r in rows]==list(range(len(rows))),'Full native order')
    require(all(int(r['trap'])==0 for r in rows),'Non-ECALL scalar page faults have no RVFI valid row')
    result=native.memory_gate(rows,commits)
    source_trap_contract()
    return dict(result,trap_rows_observable=False,native_trap_rows=0,
                handler_faults=handler_gate(rows,commits,s),
                trap_observation='Exact CSR/GPR handler gold plus active-MMU phase and cycle linkage; '
                'RVFI valid formula excludes non-ECALL faults. No row fabricated or skipped.')


def logs(console,vcs,s):
    for text in (console,vcs):
        lines=text.splitlines()
        require(lines.count('Core Test *** SUCCESS ***')==1,'One successful core terminal')
        exceptions=[]
        for line in lines:
            if re.search(r'\bUVM_(ERROR|FATAL)\b',line):
                require(re.fullmatch(r'\s*UVM_(?:ERROR|FATAL)\s*:\s*0\s*',line) is not None,
                        'Actual UVM diagnostic')
            require(not re.match(r'^\s*(?:Error[-:]|Fatal[-:]|\[ARA_CONTRACT_ERROR\]|DTLB_PERMISSIONS_ERROR)',line)
                    and 'Core Test *** FAILED' not in line,'Actual simulator/probe error')
            if line.startswith('Exception @'):
                match=re.match(r'Exception @\s+\d+, PC: ([0-9a-fA-F]+), Cause: ([^,]+),',line)
                require(match is not None,'Unknown exception diagnostic')
                exceptions.append(int(match[1],16))
        require(exceptions==[], 'This scalar-only case has no vector Exception@ diagnostics; '
                'scalar trap evidence comes from handler and MMU, not absence of prints')
        summaries=[contract.parse_contract_summary(x) for x in lines if '[ARA_CONTRACT]' in x]
        require(len(summaries)==1 and summaries[0] is not None and all(v==0 for v in summaries[0].values()),
                'Complete zero-vector contract')
    expected=['ara_tb.clk','ara_tb.rst_n',native.MONITOR]
    expected += [SCOPE+'.'+x for x in ('update_i','replace_en','lu_hit','lu_hit_o','lu_access_i',
                'lu_vaddr_i','lu_asid_i','plru_tree_q','flush_i','s_st_enbl_i','content_q','tags_q',
                'asid_to_be_flushed_i','vaddr_to_be_flushed_i')]
    expected += [native.LOAD+'.'+x for x in ('pop_ld_o','valid_i','translation_req_o','dtlb_hit_i',
                'vaddr_o','paddr_i','dtlb_ppn_i','flush_i','ex_i')]
    expected += [MMU+'.'+x for x in ('ld_st_priv_lvl_i','sum_i','mxr_i','lsu_is_store_i','lsu_req_i',
                'lsu_req_q','lsu_vaddr_i','lsu_valid_o','lsu_exception_o','dtlb_pte_q','dtlb_hit_q')]
    require([x for x in console.splitlines() if x.startswith('DTLB_PERMISSIONS_OBJECT ')]==
            ['DTLB_PERMISSIONS_OBJECT '+x for x in expected] and
            console.splitlines().count('DTLB_PERMISSIONS_READY')==1,'Exact observed objects/READY')


def replacement_gate(iterator):
    _,decl=next(iterator)
    widths={'ara_tb.clk':1,'ara_tb.rst_n':1,native.MONITOR:64}
    widths.update({SCOPE+'.'+k:w for k,w in dict(update_i=189,replace_en=16,lu_hit_o=1,
        flush_i=1,asid_to_be_flushed_i=16,vaddr_to_be_flushed_i=64).items()})
    widths.update({MMU+'.'+k:w for k,w in dict(ld_st_priv_lvl_i=2,sum_i=1,mxr_i=1,
        lsu_is_store_i=1,lsu_req_i=1,lsu_req_q=1,lsu_vaddr_i=64,lsu_valid_o=1,
        lsu_exception_o=203,dtlb_pte_q=64,dtlb_hit_q=1).items()})
    for name,w in widths.items(): require(decl.get(name,{}).get('width')==w,'Exact native shape '+name)
    def bits(state,name):
        d=decl[name];value=state.get(d['code'],'x'*d['width'])
        require(len(value)==d['width'],'Exact wave width');return value
    def val(state,name):
        value=bits(state,name);require(set(value)<=set('01'),'Unknown active '+name);return int(value,2)
    def part(value,hi,lo):
        b=value[len(value)-1-hi:len(value)-lo]
        require(set(b)<=set('01'),'Unknown active packed field');return int(b,2)
    events=[];fenced=False;last_cycle=-1;global_flushes=0;error_samples=[]
    profile=runner.software.audit.cases()
    expected=[(runner.software.p.shared.vpn(0,i),runner.software.p.pte(runner.software.p.pa(17*i),f))
              for f in (0xc7,0x79,0xc7) for i in range(16)]
    expected += [(runner.software.p.shared.vpn(0,0),runner.software.p.pte(runner.software.p.pa(0),r['pte_flags']))
                 for i,r in enumerate(profile) if i!=3]
    for time,before,after in iterator:
        require(not(last_cycle>=0 and before.get(decl['ara_tb.rst_n']['code'])=='1' and
                    after.get(decl['ara_tb.rst_n']['code'])=='0'),'No post-startup reset')
        if before.get(decl['ara_tb.clk']['code'])!='0' or after.get(decl['ara_tb.clk']['code'])!='1' or \
                before.get(decl['ara_tb.rst_n']['code'])!='1': continue
        cycle=val(before,native.MONITOR);require(cycle>last_cycle,'Monotonic native cycle');last_cycle=cycle
        if val(before,SCOPE+'.flush_i'):
            if val(before,SCOPE+'.asid_to_be_flushed_i')==1:
                require(val(before,SCOPE+'.vaddr_to_be_flushed_i')==0 and len(events)==32,
                        'ASID-only fence at exact G phase')
                tags=native.packed_slots(decl,after,SCOPE+'.tags_q',61)
                contents=native.packed_slots(decl,before,SCOPE+'.content_q',128)
                require(all(part(t,0,0)==1 and part(c,69,69)==1 for t,c in zip(tags,contents)),
                        'G mappings survive ASID-specific SFENCE')
                global_flushes+=1
            else:
                require(val(before,SCOPE+'.asid_to_be_flushed_i')==0,'Foreign ASID flush')
                fenced=True
        update=bits(before,SCOPE+'.update_i')
        if part(update,188,188) and not val(before,SCOPE+'.flush_i') and not val(before,SCOPE+'.lu_hit_o'):
            index=len(events);require(index<len(expected),'Extra DTLB replacement')
            if index%16==0 and index<48: require(fenced,'Phase full fence');fenced=False
            mask=val(before,SCOPE+'.replace_en');require(mask>0 and mask&(mask-1)==0,'One exact replacement slot')
            owner=mask.bit_length()-1;require(owner<16,'Legal native slot')
            vpn,pte=expected[index]
            require(part(update,185,159)==vpn and part(update,158,143)==1 and
                    part(update,127,64)==pte,'Exact native replacement VPN/ASID/PTE attributes')
            content=native.packed_slots(decl,after,SCOPE+'.content_q',128)
            tags=native.packed_slots(decl,after,SCOPE+'.tags_q',61)
            require(part(content[owner],127,64)==pte and part(tags[owner],0,0)==1,
                    'Exact source-bound committed replacement content/tag')
            events.append(dict(cycle=cycle,slot=owner,vpn=vpn,pte=pte))
        if val(before,MMU+'.lsu_req_q') and val(before,MMU+'.lsu_valid_o'):
            exception=bits(before,MMU+'.lsu_exception_o')
            if part(exception,0,0):
                cause,tval=part(exception,202,139),part(exception,138,75)
                require(cause in (13,15) and tval==runner.software.p.address(0),'Exact active permission fault')
                error_samples.append(dict(cycle=cycle,cause=cause,tval=tval,
                    store=val(before,MMU+'.lsu_is_store_i'),effective_privilege=val(before,MMU+'.ld_st_priv_lvl_i'),
                    SUM=val(before,MMU+'.sum_i'),MXR=val(before,MMU+'.mxr_i')))
    require(len(events)==56 and global_flushes>=1 and error_samples,'Complete actual replacement/global/fault evidence')
    for phase in range(3):
        require({e['slot'] for e in events[phase*16:(phase+1)*16]}==set(range(16)),
                'Actual every slot per contrasting phase, not a host PLRU guess')
    return dict(status='ACTUAL56_REPLACEMENTS_16_SLOTS_PER_PHASE_AND_GLOBAL_RETENTION_PASS',
                replacements=events,global_asid_fence_cycles=global_flushes,fault_samples=error_samples,
                measured_coverage_gain=None)


def wave_gate(iterator):
    result=replacement_gate(iterator)
    expected=[r for r in runner.software.audit.cases() if r['mcause']]
    samples=result['fault_samples']
    require(len(samples)==5,'Exactly five active MMU permission faults')
    for sample,case in zip(samples,expected):
        require(sample['cause']==case['mcause'] and sample['tval']==case['mtval'] and
                sample['effective_privilege']==int(case['effective_privilege']=='S') and
                sample['SUM']==int(case['SUM']) and sample['MXR']==int(case['MXR']),
                'Exact active-MMU fault phase privilege/SUM/MXR/cause/tval')
        sample['fault_operation']='store' if sample['cause']==15 else 'load'
    result['input_store_note']='lsu_is_store_i is current input, not latched lsu_is_store_q fault owner; '
    result['input_store_note']+='recorded but never used as fault operation. Cause+handler PC prove operation.'
    return result


def link_fault_cycles(wave,memory):
    handlers=memory['handler_faults'];samples=wave['fault_samples']
    require(len(handlers)==len(samples)==5,'Five matched fault/handler records')
    for handler,sample in zip(handlers,samples):
        require(handler['enable_cycle']<=sample['cycle']<handler['handler_cycle'] and
                handler['cause']==sample['cause'] and handler['tval']==sample['tval'],
                'Fault MMU sample inside exact owner MPRV-to-handler window')
    return dict(faults=5,status='FIVE_MMU_FAULTS_EXACT_HANDLER_CSR_AND_OWNER_WINDOWS_PASS')


def collect(prepared,seal,out):
    record=runner.check(prepared,seal);run=Path(record['output'])
    require(run.is_dir() and not out.exists() and out.parent==life.OUT,'Terminal run and fresh output')
    terminal_gate(life.read_bound(run/'simulation-status.json',life.digest(run/'simulation-status.json')))
    identity_gate(life.read_bound(run/'live-simv-identity.json',life.digest(run/'live-simv-identity.json')),record)
    require(life.read_bound(run/'manifest.json',life.digest(run/'manifest.json'))==
            dict(record,pins=life.merge_pins(record['pins'],{str(prepared):seal})),'Actual exact run manifest')
    members=sorted(p for p in run.rglob('*') if p.is_file())
    require(members and not any(p.is_symlink() for p in run.rglob('*')),'Exact nonaliased run members')
    pins=life.merge_pins(record['pins'],{str(prepared):seal})
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in members})
    pins=life.merge_pins(pins,source_trap_contract())
    for path in (Path(__file__),Path(__file__).with_name('test_collect_dtlb_permissions780_scalar.py'),
                 Path(zero_schema.__file__),Path(native.__file__)):
        pins=life.merge_pins(pins,{str(path.resolve()):life.digest(path)})
    require(life.digest(Path(native.__file__))==zero_schema.FROZEN_SHA and
            life.digest(Path(vector_commit.__file__))==zero_schema.VECTOR_SHA,'Frozen typed-zero dependencies')
    life.check(pins)
    q=life.read_bound(runner.PRE,runner.PRE_SHA);commits=runner.software.parse_spike_commits(runner.PRE.parent/'spike.trace')
    require(runner.software.validate(commits,q['symbols'])==q['counts'],'Frozen software oracle')
    with (run/'commit_trace.csv').open() as f:
        reader=csv.DictReader(f);require(tuple(reader.fieldnames or ())==native.FIELDS,'Exact CSV schema');rows=list(reader)
    memory=architecture_gate(rows,commits,q['symbols'])
    scalar=spike_trace.compare_commit_prefix(runner.PRE.parent/'spike.trace',run/'commit_trace.csv',0x80000000,
        terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
    expected={k:q['counts'][k] for k in ('matched_instructions','matched_scalar_writes',
        'matched_floating_writes','matched_scalar_memory_accesses')}
    runner.software.p.shared.architecture.scalar_exact(scalar,expected)
    require(scalar['ara_trap_events']==0,'Source-bound nonobservable scalar trap rows')
    logs((run/'console.log').read_text(),(run/'run.vcs.log').read_text(),q['symbols'])
    vector=vector_commit.compare_vector_commits(runner.PRE.parent/'spike.trace',run/'commit_trace.csv',run/'vector_trace.csv',0x80000000)
    zero_schema.vector_zero(vector)
    vpd=run/'dtlb-permissions.vpd';require(0<vpd.stat().st_size<=256*1024*1024,'Focused VPD bound')
    require(life.digest(native.CONVERTER)==native.CONVERTER_SHA,'Converter identity')
    require(len(list((run/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml')))==1,
            'Complete native Toggle testdata')
    out.mkdir()
    try:
        vcd=out/'dtlb-permissions.vcd'
        with (out/'convert.log').open('x') as f:
            subprocess.run([str(native.CONVERTER),'-splitpacked',str(vpd),str(vcd)],stdout=f,stderr=subprocess.STDOUT,
                           timeout=180,check=True)
        parser=FunctionType(native.vcd_reader.vcd.__code__,dict(native.vcd_reader.vcd.__globals__,ROOT='ara_tb',WIDTHS={'clk':1,'rst_n':1}))
        wave=wave_gate(iter(parser(vcd)))
        wave['handler_cycle_linkage']=link_fault_cycles(wave,memory)
        for name,value in (('memory-audit.json',memory),('scalar-comparison.json',scalar),
                           ('vector-comparison.json',vector),('actual-replacements.json',wave)):
            life.save(out/name,value)
        life.check(pins);require(members==sorted(p for p in run.rglob('*') if p.is_file()),'Postrun membership drift')
        life.save(out/'qualification.json',dict(status='DTLB_PERMISSIONS780_SCALAR_FAULT_QUALIFIED_NOT_ADMITTED',
            baseline=780,prepared_seal=seal,input_pins=pins,
            output_pins={str(p):life.digest(p) for p in out.iterdir() if p.is_file()},
            coverage_admitted=False,coverage_gain_not_checked=True,
            vector_data_scope='UNOBSERVABLE_ZERO_REQUESTS',scalar_faults_proven=5,
            scalar_trap_rows_observable=False,VCS_rerun=False))
        print('QUALIFIED_NOT_ADMITTED',life.digest(out/'qualification.json'),flush=True)
    except Exception as error:
        life.save(out/'failure.json',dict(reason=str(error),coverage_admitted=False));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared',type=Path,required=True);parser.add_argument('--seal',required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    collect(args.prepared.absolute(),args.seal,args.output.absolute())
