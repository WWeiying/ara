"""Terminal-only bulk ITLB qualification and exact773 gain; never admission."""
import argparse
import csv
from pathlib import Path
import subprocess
import re
from types import SimpleNamespace
import traceback
import build_itlb_asid_exec_bulk as bulk
import collect_itlb_asid_exec_linear as support

life,require=bulk.life,bulk.require
bitmap,reference=support.bitmap,support.reference
CONVERTER,CONVERTER_SHA=support.CONVERTER,support.CONVERTER_SHA
markers,waveform,csr_lifecycle,source_layout=support.markers,support.waveform,support.csr_lifecycle,support.source_layout
exact_scalar=support.exact_scalar
BASE=life.OUT/'sv39-fault-alternating-offline-admitted-773-agent-20261007-01'
BASE_SHA='65710f130e698571f9e17800e57361b0baa2a9d407a02287409797de64f64060'
PREFLIGHT_SHA='ea0f3507627a7759ab41e1044d41c0186fd796c7e217fc542db9189d2b280499'


def baseline():
    manifest=BASE/'admission-manifest.json'
    record=life.read_bound(manifest,BASE_SHA)
    require(record['coverage_admitted'] is True,'Formal773 admission required')
    pins=life.merge_pins(record['input_pins'],record['output_pins'])
    pins=life.merge_pins(pins,{str(manifest):BASE_SHA})
    bits=life.read_bound(BASE/'combined-bits.json',pins[str(BASE/'combined-bits.json')])
    path=BASE/'combined-inputs.txt'
    require(life.digest(path)==pins[str(path)],'773 ledger drift')
    ledger=path.read_text().splitlines()
    require(len(bits['tests'])==len(set(bits['tests']))==773 and ledger[1:]==bits['tests'] and
        Path(ledger[0]).is_absolute(),'Exact773 prefix required')
    db=Path(ledger[0])/'snps/coverage/db'
    require(all(pins.get(str(db/rel))==sha for rel,sha in bits['design'].items()),
        'Compiled ledger design must have all exact historical pins')
    return bits,ledger,pins


def full_union(before,single):
    require(len(before['tests'])==len(set(before['tests']))==773 and len(single['tests'])==1 and
        single['tests'][0] not in before['tests'],'Exact773 plus unique singleton required')
    after=bitmap.combine(before,single);n=0
    for metric,scopes in before['metrics'].items():
        for scope,r in scopes.items():
            require(int(after['metrics'][metric][scope]['bits'],16)==
                int(r['bits'],16)|int(single['metrics'][metric][scope]['bits'],16),'Independent OR differs')
            n+=1
    require(n==6162 and after['tests']==before['tests']+single['tests'],'Full6162 prefix/OR differs')
    return after


def code_write_dominance(commits,symbols):
    base=symbols['itm_code'];stores=[0]*8192;reads=[0]*8192;first_fetch=None;fetches=0
    targets={bulk.address(p,e) for p in range(3) for e in range(16)}
    for order,commit in enumerate(commits):
        if commit.pc in targets:
            require(all(n==1 for n in stores),'Code fetch before complete one-write-per-word initialization')
            fetches+=1
            if first_fetch is None:first_fetch=order
        for address,value in commit.memory_accesses:
            if not base<=address<base+65536:continue
            access=reference.scalar_memory(commit.instruction)
            require(access==('read' if value is None else 'write',8) and (address-base)%8==0,
                'Code access must be one complete aligned64bit word')
            index=(address-base)//8
            if value is None:
                require(stores[index]==1 and reads[index]==0,'Guard read before initialization or duplicate read')
                reads[index]+=1
            else:
                entry,word=divmod(index,512)
                require(stores[index]==0 and reads[index]==0 and value==bulk.codeword(entry,word),
                    'Redundant/late/incorrect code initialization write')
                stores[index]+=1
    require(first_fetch is not None and fetches==48 and all(n==1 for n in stores) and
        all(n==1 for n in reads),'Complete48 fetches/8192 stores/8192 guard reads required')
    return dict(status='NATIVE_INITIALIZATION_DOMINATES_ALL_FETCHES_AND_GUARD_READS',
        word_stores=8192,word_reads=8192,first_thunk_instruction_order=first_fetch,
        S_mode_entries=48,no_redundant_writes=True,initial_ELF_memory_readback_claimed=False,
        scope='Exact native scalar stores cover all65536 bytes before first target instruction; source fence.i unchanged')


def checked_reference(path,symbols):
    exceptions=re.findall(r'exception (\w+), epc (0x[0-9a-f]+)',path.read_text())
    expected=[('trap_supervisor_ecall',bulk.address(p,e)+8) for p in range(3) for e in range(16)]
    require([(kind,int(pc,16)) for kind,pc in exceptions]==expected,
        'Exact48 raw Spike exception kind/PC/order required before trap augmentation')
    ref=bulk.reference_interval(pre.build.parse_spike_commits(path))
    pre.validate(pre.with_ecalls(ref,symbols),symbols)
    return ref,dict(raw_trace=str(path),raw_trace_sha=life.digest(path),trap_count=48,
        kind='trap_supervisor_ecall',ordered_EPCs=[hex(pc) for kind,pc in expected],
        augmentation_only_after_raw_exception_check=True)


pre=SimpleNamespace(**bulk.old.__dict__)
pre.validate=bulk.validate
pre.baseline=baseline
pre.BASE,pre.BASE_SHA=BASE,BASE_SHA


def collect(prepared,seal,output):
    import run_itlb_asid_exec_bulk as runner
    require(not output.exists(),'Fresh offline qualification only')
    r=life.read_bound(prepared,seal);run=Path(r['output']);pp=Path(r['preflight'])
    q=life.read_bound(pp,r['preflight_seal']);pins=life.merge_pins(r['pins'],{str(prepared):seal})
    require(r['command']==runner.command(pp.parent/'input.elf',run) and r['timeout_s']==600 and
        r['schema']=='ITLB_BULK_FROZEN600_AUTOQUALIFY_V1' and r['driver_variant']=='ITLB_BULK_SOURCE_PACKED189_CSR6' and r['preflight_seal']==PREFLIGHT_SHA and r['baseline_seal']==pre.BASE_SHA,
        'Exact prepared command differs')
    runner.validate_record(r)
    require(life.read_bound(run/'manifest.json',life.digest(run/'manifest.json'))==dict(r,pins=pins),'Actual run manifest differs')
    terminal=life.read_bound(run/'simulation-status.json',life.digest(run/'simulation-status.json'))
    require(terminal.get('returncode')==0 and terminal['status']=='SIMULATION_EXITED_NOT_ADMITTED','No successful terminal')
    for p in run.rglob('*'):
        if p.is_file():pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins);output.mkdir()
    try:
        require(bulk.elf_contract(pp.parent/'input.elf')==life.read_bound(pp.parent/'elf-preload-proof.json',
            pins[str(pp.parent/'elf-preload-proof.json')]),'Frozen ELF preload proof differs')
        markers((run/'console.log').read_text())
        ref,exception_ledger=checked_reference(pp.parent/'spike.trace',q['symbols'])
        require(pre.architecture.reference_counts(ref,q['symbols'])==q['counts'],
            'Unaugmented full reference counts differ from frozen preflight')
        life.save(output/'reference-exception-ledger.json',exception_ledger)
        scalar=pre.architecture.spike_trace.compare_commit_prefix(pp.parent/'spike.trace',run/'commit_trace.csv',
            0x80000000,terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
        life.save(output/'scalar-comparison.json',scalar);exact_scalar(scalar,q['counts'])
        with (run/'commit_trace.csv').open() as f:rows=list(csv.DictReader(f))
        life.save(output/'csr-lifecycle.json',csr_lifecycle(rows))
        rows=[r for r in rows if r['event']=='retire']
        traps=support.old.trap_contract(rows,q['symbols'])
        nontrap=[dict(row,order=str(i)) for i,row in enumerate(x for x in rows if not int(x['trap']))]
        commits=reference.native_reference(nontrap)
        require(bulk.reference_interval(commits)==commits,'Native trace must be exactly entry through successful tohost')
        require(len(commits)==len(ref),'Complete native/reference prefix differs')
        for index,(a,b) in enumerate(zip(commits,ref)):
            require((a.pc,a.instruction,a.gpr_writes,a.memory_accesses)==
                (b.pc,b.instruction,b.gpr_writes,b.memory_accesses),'Complete compressed/uncompressed scalar differs at '+str(index))
        pre.validate(pre.with_ecalls(commits,q['symbols']),q['symbols'])
        life.save(output/'code-write-dominance.json',code_write_dominance(commits,q['symbols']))
        with (run/'vector_trace.csv').open() as f:vectors=list(csv.DictReader(f))
        require(all(x['event']=='config' for x in vectors),'Unexpected vector side effect')
        life.save(output/'native-oracle.json',dict(checks=pre.CHECKS,failed=0,traps=traps,
            true_S_mode_instructions=144,full_code_bytes=65536,complete_scalar_including_compressed=True,
            scalar_memory_accesses=sum(bool(c.memory_accesses) for c in commits),vector_writes=0,
            CSR_restored=True,UVM_final_report_claimed=False))
        vpd=run/'itlb-exec.vpd';require(0<vpd.stat().st_size<=64*1024*1024,'Focused waveform64MB cap exceeded')
        require(life.digest(CONVERTER)==CONVERTER_SHA,'Converter drift')
        vcd=output/'itlb-exec.vcd'
        with (output/'convert.log').open('x') as log:
            subprocess.run([str(CONVERTER),'-splitpacked',str(vpd),str(vcd)],stdout=log,stderr=subprocess.STDOUT,
                timeout=120,check=True)
        life.save(output/'itlb-axi-observations.json',waveform(vcd))
        before,ledger,bpins=pre.baseline();pins=life.merge_pins(pins,bpins)
        with (output/'single-inputs.txt').open('x') as f:f.write(ledger[0]+'\n'+str(run/'code.vdb')+'\n')
        single=bitmap.collect(output/'single-inputs.txt');after=full_union(before,single);delta=bitmap.delta(before,after)
        pred,predpins=pre.prediction();require(pred==q['prediction'],'Sealed771 targets changed')
        pins=life.merge_pins(pins,predpins);prior_toggle,pins=pre.toggle_baseline(ledger,pins)
        files=list((run/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files)==1,'Unique new Toggle data required')
        sample,sha=pre.native.rows(files[0],[pre.SCOPE]);require(pins[str(files[0])]==sha,'New Toggle data drift')
        merged=pre.native.union(prior_toggle,sample);gains=pre.native.gains(prior_toggle,merged)[pre.SCOPE]
        oldbits=format(int(prior_toggle[pre.SCOPE]['bits'],16),'0%db'%prior_toggle[pre.SCOPE]['width'])
        targets=[dict(native=t['native'],before_zero=[i for i in t['fresh_positions'] if oldbits[i]=='0'],
            hit_positions=sorted(set(t['fresh_positions'])&set(gains))) for t in pred['targets']]
        gain=dict(baseline=773,scope=pre.SCOPE,before=prior_toggle[pre.SCOPE],single=sample[pre.SCOPE],after=merged[pre.SCOPE],
            new_serialized_positions=gains,new_positions=len(gains),targets=targets,
            target_new_positions=sum(len(t['hit_positions']) for t in targets),
            official_percentage=False,direction_order_calibrated=False)
        for p,h in single['input_hashes'].items():pins=life.merge_pins(pins,{p:h})
        for rel,h in single['design'].items():pins=life.merge_pins(pins,{str(Path(ledger[0])/'snps/coverage/db'/rel):h})
        for name,value in [('single-bits.json',single),('diagnostic-combined-bits.json',after),
            ('raw-delta.json',delta),('toggle-gain.json',gain)]:life.save(output/name,value)
        life.check(pins);life.save(output/'evidence-pins.json',pins)
        life.save(output/'qualification.json',dict(status='ITLB_TRUE_SMODE_ARCHITECTURE_OBSERVATIONS_RAW773_QUALIFIED_NOT_ADMITTED',
            baseline=773,software_checks=pre.CHECKS,raw_delta=delta['metrics'],toggle_new_positions=len(gains),
            target_new_positions=gain['target_new_positions'],coverage_admitted=False,official_percentage=False,
            UVM_final_report_claimed=False,input_pins=pins,
            output_pins={str(p):life.digest(p) for p in output.iterdir() if p.is_file()}))
        print('QUALIFIED_NOT_ADMITTED',life.digest(output/'qualification.json'),gain['target_new_positions'],delta['metrics'],flush=True)
    except Exception as error:
        life.save(output/'failure.json',dict(status='HOLD_NOT_ADMITTED',reason=str(error),
            traceback=traceback.format_exc(),coverage_admitted=False,rerun=False));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared',type=Path,required=True)
    parser.add_argument('--seal',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    collect(args.prepared.absolute(),args.seal,args.output.absolute())
