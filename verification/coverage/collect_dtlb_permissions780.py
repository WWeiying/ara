"""Strict offline scalar/permission/replacement collector; no launch or admission."""
from collections import Counter
import argparse
import csv
from pathlib import Path
import re
import subprocess
from types import FunctionType

import collect_dtlb_ppn_swap1200 as native
import run_dtlb_permissions780 as runner
from ara_verify import spike_trace, vector_commit, contract

life,require=runner.life,runner.require
SCOPE=native.SCOPE
MMU=SCOPE.rsplit('.',1)[0]
namespace=dict(vars(native),runner=runner)
terminal_gate=FunctionType(native.terminal_gate.__code__,namespace)
identity_gate=FunctionType(native.identity_gate.__code__,namespace)


def architecture_gate(rows,commits,s):
    require(rows and all(tuple(r)==native.FIELDS and all(v not in ('',None) for v in r.values())
                        for r in rows), 'Full exact commit schema')
    require([int(r['order']) for r in rows]==list(range(len(rows))), 'Full native order')
    traps=[r for r in rows if int(r['trap'])]
    require([int(r['pc'],16) for r in traps]==[s[x] for x in
            ('dpa_load','dpa_load','dpa_store','dpa_load','dpa_store')], 'Exact five ordered fault sites')
    for r in traps:
        require(int(r['trap'])==1 and int(r['rd'])==0 and
                int(r['mem_rmask'],16)==int(r['mem_wmask'],16)==0,
                'Fault retirement cannot carry architectural data effects')
    actual=[dict(r,order=str(i)) for i,r in enumerate(r for r in rows if int(r['trap'])==0)]
    result=native.memory_gate(actual,commits)
    return dict(result,trap_rows_checked=5,normalization='Only five exact no-effect trap rows removed; '
                'original full order checked first. All committed integer/RVC memory checked.')


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
        require(exceptions==[s[x] for x in ('dpa_load','dpa_load','dpa_store','dpa_load','dpa_store')],
                'Exact native exception diagnostics; causes independently checked by handler ISA/gold')
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


def wave_gate(iterator):
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
    require(scalar['ara_trap_events']==5,'Exact native trap count')
    logs((run/'console.log').read_text(),(run/'run.vcs.log').read_text(),q['symbols'])
    vector=vector_commit.compare_vector_commits(runner.PRE.parent/'spike.trace',run/'commit_trace.csv',run/'vector_trace.csv',0x80000000)
    native.vector_zero(vector)
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
        for name,value in (('memory-audit.json',memory),('scalar-comparison.json',scalar),
                           ('vector-comparison.json',vector),('actual-replacements.json',wave)):
            life.save(out/name,value)
        life.check(pins);require(members==sorted(p for p in run.rglob('*') if p.is_file()),'Postrun membership drift')
        life.save(out/'qualification.json',dict(status='DTLB_PERMISSIONS780_QUALIFIED_NOT_ADMITTED',
            baseline=780,prepared_seal=seal,input_pins=pins,
            output_pins={str(p):life.digest(p) for p in out.iterdir() if p.is_file()},
            coverage_admitted=False,coverage_gain_not_checked=True))
        print('QUALIFIED_NOT_ADMITTED',life.digest(out/'qualification.json'),flush=True)
    except Exception as error:
        life.save(out/'failure.json',dict(reason=str(error),coverage_admitted=False));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared',type=Path,required=True);parser.add_argument('--seal',required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    collect(args.prepared.absolute(),args.seal,args.output.absolute())
