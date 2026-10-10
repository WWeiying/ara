"""Exact architecture and accepted full-PTE slot ownership; diagnostic792 gain only."""
import argparse
import csv
from pathlib import Path
import re
import shlex
import subprocess
from types import FunctionType, SimpleNamespace
import traceback
import xml.etree.ElementTree as ET
import build_itlb_ppn_aba as pre
import collect_itlb_asid_exec_bulk_axi as axi
import coverage_bitmap_delta as bitmap
from rank_cva6_scalar_data767 import typed_nodes

life,require=pre.life,pre.require
original=axi.core.support.old
CONVERTER,CONVERTER_SHA=original.CONVERTER,original.CONVERTER_SHA
SCOPE=pre.prior.SCOPE


def source_layout():
    pins=axi.source_contract()
    layout=axi.core.support.source_layout()
    require(layout['native_packed_width']==189 and layout['RVH']==0,'Frozen update layout differs')
    book=life.read_bound(pre.prior.shared.SOURCE,pre.prior.shared.SOURCE_SHA)
    p=pre.ROOT/'hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv'
    require(life.digest(p)==book[str(p)],'Frozen PTE source differs')
    text=axi.clean(p.read_text())
    pte='localparamtypepte_cva6_t=structpacked{logic[9:0]reserved;logic[CVA6Cfg.PPNW-1:0]ppn;logic[1:0]rsw;logicd;logica;logicg;logicu;logicx;logicw;logicr;logicv;};'
    require(pte in text,
            'Exact Sv39 PTE packing required')
    require(life.digest(CONVERTER)==CONVERTER_SHA,'Historical converter differs')
    return life.merge_pins(life.merge_pins(pins,layout['source_pins']),{str(p):book[str(p)]})


def accepted_gate(records):
    require(len(records)==48,'Exactly48 accepted target-page updates required')
    for phase in range(3):
        rs=[r for r in records if r['phase']==phase]
        require(len(rs)==16 and {r['entry'] for r in rs}==set(range(16)) and
                {r['vpn'] for r in rs}=={pre.prior.shared.vpn(0,e) for e in range(16)},
                'Actual slot/VPN coverage missing or duplicated')
        expected=((pre.PAGES[phase==1]>>12)<<10)|0x4b
        require(all(r['pte']==expected and r['ppn']==pre.PAGES[phase==1]>>12 and
                    r['asid']==[0x5555,0xaaaa,0x5555][phase] for r in rs),
                'Accepted full PTE/PPN/ASID differs from canonical mapping')
    require(all([r['ppn'] for r in records if r['entry']==e]==
                [pre.PAGES[0]>>12,pre.PAGES[1]>>12,pre.PAGES[0]>>12] for e in range(16)),
            'Each actual physical entry must hold A/B/A, not inferred call count')


def waveform(path):
    source_layout();accepted=[]
    def observe(iterator):
        _,decl=next(iterator);yield 'declarations',decl
        prefix=SCOPE+'.';clk=decl['ara_tb.clk']['code'];rst=decl['ara_tb.rst_n']['code']
        packed=decl[prefix+'update_i'];require(packed['width']==189,'Packed update width changed')
        phase=-1;last=None
        def val(state,name):
            bits=state.get(decl[prefix+name]['code'],'x')
            require(set(bits)<=set('01'),'Unknown accepted-update control')
            return int(bits,2)
        for time,before,after in iterator:
            if before.get(clk)=='0' and after.get(clk)=='1' and before.get(rst)=='1':
                if val(before,'update_i.valid') and not val(before,'lu_hit_o') and not val(before,'flush_i'):
                    bits=before.get(packed['code'],'x'*189)
                    require(len(bits)==189 and set(bits)<=set('01'),'Unknown accepted full PTE')
                    asid=val(before,'update_i.asid');mask=val(before,'replace_en')
                    require(mask>0 and mask&(mask-1)==0,'Ambiguous accepted entry')
                    if asid!=last:phase+=1;last=asid
                    pte=int(axi.core.support.packed_field(bits,'content'),2)
                    accepted.append(dict(time_100fs=time,phase=phase,asid=asid,
                        vpn=val(before,'update_i.vpn'),entry=mask.bit_length()-1,
                        pte=pte,ppn=(pte>>10)&((1<<44)-1)))
            yield time,before,after
    def factory(code,namespace):
        require(code is original.wave.vcd.__code__,'Foreign VCD parser boundary')
        return lambda p: observe(axi.project(iter(axi.core.support.projected_vcd(p))))
    owner=SimpleNamespace(SCOPE=SCOPE,shared=SimpleNamespace(vpn=lambda p,e:pre.prior.shared.vpn(0,e)))
    fn=FunctionType(original.waveform.__code__,dict(original.waveform.__globals__,FunctionType=factory,pre=owner))
    result=fn(path);accepted_gate(accepted)
    return dict(result,accepted_full_PTEs=accepted,actual_all16_A_B_A=True,
                PPN_value_xor=0x1ff,serialized_direction_order_calibrated=False,
                source_layout_pins=source_layout())


def csr_lifecycle(rows,reference):
    def selected(word):return word&0x707f==0x2073 and word>>15&31==0 and word>>20 in (8,15)
    gold=[c for c in reference if selected(c.instruction)]
    retired=[r for r in rows if r['event']=='retire' and selected(int(r['insn'],16))]
    require(len(gold)==len(retired)==6,'Exactly six reference-bound readonly CSR instructions')
    starts=[];pending={}
    for row in rows:
        event=row['event']
        if event=='retire':continue
        require(event in ('arch_start','cvx_req','cvx_resp') and not int(row['trap']) and
                int(row['mem_rmask'],16)==int(row['mem_wmask'],16)==0,'Foreign backend event/effect')
        tid,time=int(row['trans_id']),int(row['cycle'])
        if event=='arch_start':
            word=int(row['insn'],16)
            require(selected(word) and tid not in pending and int(row['order'])==len(starts),
                    'Foreign/replayed CSR start')
            r=dict(word=word,tid=tid,start=time);starts.append(r);pending[tid]=r
        elif event=='cvx_req':
            require(tid in pending and 'request' not in pending[tid] and
                int(row['insn'],16)==pending[tid]['word'] and time>=pending[tid]['start'],'CSR request differs')
            pending[tid]['request']=time
        else:
            require(tid in pending and 'request' in pending[tid] and time>=pending[tid]['request'],
                    'Orphan/duplicate/early response')
            pending.pop(tid)['response']=time
    require(len(starts)==6 and not pending,'Incomplete CSR conservation')
    for start,retire,expected in zip(starts,retired,gold):
        require(start['word']==expected.instruction==int(retire['insn'],16) and
                int(retire['pc'],16)==expected.pc and start['response']<=int(retire['cycle']) and
                expected.gpr_writes=={int(retire['rd']):int(retire['rd_wdata'],16)},
                'Exact readonly CSR PC/value/response-retire relation differs')
    return dict(status='SIX_REFERENCE_BOUND_READONLY_CSR_CONSERVED',records=starts,
                independent_requests_may_overlap=True,all_architectural_consumers_in_full_scalar_comparison=True)


def baseline():
    path=pre.BASE/'admission-manifest.json';m=life.read_bound(path,pre.BASE_SHA)
    require(m['coverage_admitted'] is True,'Formal792 admission required')
    authority=life.merge_pins(m['input_pins'],m['output_pins'])
    paths=[pre.BASE/n for n in ('combined-inputs.txt','combined-bits.json','combined-toggle-bits.json')]
    pins={str(path):pre.BASE_SHA,**{str(p):authority[str(p)] for p in paths}}
    life.check(pins);bits=life.read_bound(paths[1],pins[str(paths[1])]);toggle=life.read_bound(paths[2],pins[str(paths[2])])
    ledger=paths[0].read_text().splitlines()
    require(len(bits['tests'])==len(set(bits['tests']))==792 and ledger==[ledger[0],*bits['tests']],
            'Exact792 membership/prefix required')
    for rel,h in bits['design'].items():
        p=Path(ledger[0])/'snps/coverage/db'/rel
        require(authority.get(str(p))==h,'Historical compiled identity missing')
        pins[str(p)]=h
    for rel in ('design/verilog.design.xml','shape/tgl.verilog.shape.xml','shape/tgl.verilog.info.xml'):
        p=Path(ledger[0])/'snps/coverage/db'/rel
        require(str(p) in authority,'Missing sealed native Toggle design input')
        pins[str(p)]=authority[str(p)]
    life.check(pins);return bits,toggle,ledger,pins


def write_single_inputs(path,design,vdb):
    require(design.is_absolute() and vdb.is_absolute() and
            not any(c in str(design)+str(vdb) for c in '\r\n'), 'Exact input paths required')
    with path.open('x') as f:
        f.write(str(design)+'\n'+str(vdb)+'\n')
    require(path.read_text().splitlines()==[str(design),str(vdb)],'Exact plaintext singleton inputs differ')


def native_identity(sim,args,record,design):
    tests=sim.findall('srctest')
    require(sim.tag=='test' and len(tests)==1,'One native test identity required')
    test=tests[0]
    require(shlex.split(test.get('cmdline',''))==record['command'] and
            test.get('workdir')==record['output'] and test.get('seed')=='1' and
            test.get('teststatus')=='unknown','Exact native command/workdir/seed; unknown is not PASS')
    require(args.tag=='vcm_args' and args.get('compvdbpath')==design and
            sorted(n.get('vcm_opt') for n in args.findall('vcm_arg_data') if n.get('vcm_opt'))==
            ['-cm branch','-cm cond','-cm fsm','-cm line','-cm tgl'],
            'Exact compiled VDB/five native metrics required')
    require(all(re.fullmatch(r'\d+',test.get(k,'')) for k in ('starttime','finishtime')) and
            int(test.get('finishtime'))>int(test.get('starttime')),'Native duration missing or invalid')
    return dict(command=record['command'],workdir=record['output'],seed=1,compvdb=design,
                XML_teststatus='unknown',functional_PASS_authority='complete independent architecture oracle')


def measure(run,output):
    before,toggle,ledger,pins=baseline()
    write_single_inputs(output/'single-inputs.txt',Path(ledger[0]),run/'code.vdb')
    single=bitmap.collect(output/'single-inputs.txt');after=bitmap.combine(before,single)
    require(after['tests']==before['tests']+single['tests'] and len(single['tests'])==1 and
            single['tests'][0] not in before['tests'],'Exact prefix plus unique singleton required')
    count=0
    for metric,scopes in before['metrics'].items():
        for scope,row in scopes.items():
            require(int(after['metrics'][metric][scope]['bits'],16)==
                int(row['bits'],16)|int(single['metrics'][metric][scope]['bits'],16),'Independent OR differs')
            count+=1
    require(count==6162,'Complete6162 metric instances required')
    import run_itlb_ppn_aba as runner
    folder=run/'code.vdb/snps/coverage/db/testdata'/runner.CASE
    require(list(folder.parent.iterdir())==[folder],'One exact native testcase required')
    identity_paths=[folder/n for n in ('siminfo.xml','vcmArguments.xml')]
    record=life.read_bound(run/'manifest.json',life.digest(run/'manifest.json'))
    identity=native_identity(*(pre.prior.native.xml(p) for p in identity_paths),record,ledger[0])
    life.save(output/'native-VDB-identity.json',identity)
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in identity_paths})
    files=list((run/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(files)==1,'Unique native Toggle sample required')
    sample,sha=pre.prior.native.rows(files[0],[SCOPE]);pins[str(files[0])]=sha
    previous={SCOPE:toggle[SCOPE]};merged=pre.prior.native.union(previous,sample)
    gained=pre.prior.native.gains(previous,merged)[SCOPE]
    shape=Path(ledger[0])/'snps/coverage/db/shape/tgl.verilog.shape.xml'
    db=shape.parent.parent
    checks,defs=pre.prior.native.definitions(pre.prior.native.xml(db/'design/verilog.design.xml'),
        pre.prior.native.xml(db/'shape/tgl.verilog.info.xml'),pre.prior.native.xml(shape),[SCOPE])
    require(checks[SCOPE]==sample[SCOPE]['checksum']=='817233724','Exact compiled/data TLB checksum required')
    nodes,_=typed_nodes(defs[SCOPE]['shape'],previous[SCOPE]);targets=[]
    for n in nodes:
        if re.fullmatch(r'content_[qn]\[\d+\]\.pte\.ppn',n['name']):
            off=n['serialized_offset'];positions=[i for i in n['missing_coordinates'] if off<=i<off+18]
            targets.append(dict(name=n['name'],candidate_serialized_positions=positions,
                hit_positions=sorted(set(positions)&set(gained))))
    require(len(targets)==32,'Exact32 PPN objects required')
    gain=dict(baseline=792,scope=SCOPE,new_positions=len(gained),new_serialized_positions=gained,
        target_new_positions=sum(len(t['hit_positions']) for t in targets),targets=targets,
        direction_order_calibrated=False,official_percentage=False,
        candidate_coordinate_semantics='first18 serialized positions per compiled PPN object; NOT native bit0..8 binding',
        native_summary_hit_metadata_not_recomputed=True)
    for name,value in [('single-bits.json',single),('diagnostic-combined-bits.json',after),
                       ('raw-delta.json',bitmap.delta(before,after)),('toggle-gain.json',gain)]:life.save(output/name,value)
    pins=life.merge_pins(pins,single['input_hashes'])
    return gain,pins


def collect(prepared,seal,output):
    import run_itlb_ppn_aba as runner
    require(not output.exists(),'Fresh offline qualification only')
    r=life.read_bound(prepared,seal);run=runner.validate(r);q=life.read_bound(Path(r['preflight']),r['preflight_seal'])
    pins=life.merge_pins(r['pins'],{str(prepared):seal});life.check(pins)
    require(life.read_bound(run/'manifest.json',life.digest(run/'manifest.json'))==dict(r,pins=pins),'Executed manifest differs')
    terminal=life.read_bound(run/'simulation-status.json',life.digest(run/'simulation-status.json'))
    require(terminal['status']=='SIMULATION_EXITED_NOT_ADMITTED' and type(terminal['returncode']) is int and
            terminal['returncode']==0 and terminal['timed_out'] is False and terminal['prepared_seal']==seal,
            'No exact successful terminal')
    identity=life.read_bound(run/'live-identity.json',life.digest(run/'live-identity.json'))
    require(identity['pid']==terminal['pid'] and identity['command']==r['command'] and
            identity['cwd']==str(run) and identity['exe']==str(life.IMAGE.resolve()) and
            identity['prepared_seal']==seal and any(x.endswith('/'+runner.SERVICE) for x in identity['cgroup'].splitlines()),
            'Saved native execution ownership differs')
    output.mkdir()
    try:
        ref=pre.reference(Path(r['preflight']).parent/'spike.trace',q['symbols'])
        require(pre.architecture.reference_counts(ref,q['symbols'])==q['counts'],'Frozen reference counts differ')
        original.markers((run/'console.log').read_text())
        scalar=pre.architecture.spike_trace.compare_commit_prefix(Path(r['preflight']).parent/'spike.trace',
            run/'commit_trace.csv',0x80000000,terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
        life.save(output/'scalar-comparison.json',scalar);original.exact_scalar(scalar,q['counts'])
        with (run/'commit_trace.csv').open() as f:rows=list(csv.DictReader(f))
        csr=csr_lifecycle(rows,ref);life.save(output/'csr-lifecycle.json',csr)
        retired=[r for r in rows if r['event']=='retire']
        owner=SimpleNamespace(address=pre.address)
        traps=FunctionType(original.trap_contract.__code__,dict(original.trap_contract.__globals__,pre=owner))(retired,q['symbols'])
        nontrap=[dict(r,order=str(i)) for i,r in enumerate(x for x in retired if not int(x['trap']))]
        cs=original.reference.native_reference(nontrap)
        require(len(cs)==len(ref) and bulk_interval(cs)==cs,'Complete exact native interval required')
        for i,(a,b) in enumerate(zip(cs,ref)):
            require((a.pc,a.instruction,a.gpr_writes,a.memory_accesses)==(b.pc,b.instruction,b.gpr_writes,b.memory_accesses),
                    'Complete scalar divergence at '+str(i))
        expanded=[];index=0
        for c in cs:
            if c.pc==q['symbols']['itm_handler']:
                p,e=divmod(index,16);index+=1
                expanded.append(pre.architecture.spike_trace.SpikeCommit(pc=pre.address(p,e)+8,instruction=0x73,
                    gpr_writes={},fpr_writes={},vector_writes={},csr_writes={},memory_accesses=()))
            expanded.append(c)
        require(index==48,'Exactly48 previously verified native traps');pre.validate(expanded,q['symbols'])
        with (run/'vector_trace.csv').open() as f:vr=list(csv.DictReader(f))
        require(all(x['event']=='config' for x in vr),'Unexpected vector write')
        life.save(output/'native-oracle.json',dict(checks=pre.CHECKS,failed=0,traps=traps,
            complete_scalar_PC_GPR_memory=True,physical_A_B_code_distinguished=True,
            full_preload_and_postexecute_guards=True,CSR_restored=True,UVM_final_report_claimed=False))
        vpd=run/'itlb-exec.vpd';require(0<vpd.stat().st_size<=r['wave_limit_bytes'],'Focused64MB limit')
        with (output/'convert.log').open('x') as log:
            subprocess.run([str(CONVERTER),'-splitpacked',str(vpd),str(output/'itlb-exec.vcd')],
                stdout=log,stderr=subprocess.STDOUT,timeout=120,check=True)
        life.save(output/'itlb-axi-observations.json',waveform(output/'itlb-exec.vcd'))
        gain,extra=measure(run,output);pins=life.merge_pins(pins,extra)
        for p in run.rglob('*'):
            if p.is_file():pins=life.merge_pins(pins,{str(p):life.digest(p)})
        life.check(pins);life.save(output/'evidence-pins.json',pins)
        life.save(output/'qualification.json',dict(status='ITLB_PPN_ABA792_ARCHITECTURE_ACTUAL16_SLOT_QUALIFIED_NOT_ADMITTED',
            baseline=792,software_checks=pre.CHECKS,toggle_new_positions=gain['new_positions'],
            target_new_positions=gain['target_new_positions'],coverage_admitted=False,official_percentage=False,
            input_pins=pins,output_pins={str(p):life.digest(p) for p in output.iterdir() if p.is_file()}))
        print('QUALIFIED_NOT_ADMITTED',life.digest(output/'qualification.json'),flush=True)
    except Exception as error:
        life.save(output/'failure.json',dict(reason=str(error),traceback=traceback.format_exc(),coverage_admitted=False));raise


def bulk_interval(cs):
    return pre.bulk.reference_interval(cs)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--seal',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    collect(a.prepared.absolute(),a.seal,a.output.absolute())
