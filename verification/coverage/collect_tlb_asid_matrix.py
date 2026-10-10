"""One terminal matrix: strict scalar/PTE/CSR/guards, raw768 OR and optional769 admission."""
import argparse
import csv
from pathlib import Path
import re
import sys

import run_tlb_asid_matrix as runner
import coverage_bitmap_delta as bitmap
from check_gap100_runtime import scalar_memory
from seal_gap101_failure import scalar_store
from admit_stride_metadata768 import dedup

pre,life,require = runner.pre,runner.life,runner.require
RUN = life.OUT/'tlb-asid-vpn-rsw-old-image-768-agent-20261007-02'
PRE = life.OUT/'tlb-asid-vpn-rsw-preflight-768-agent-20261007-02'
PRE_SEAL = 'f9c45fbe5209b312d897e8c8573a1b22628175600e26679aea1b76df0da7fd19'
RUN_SEAL = '0a2753ef95251dd27deede3abf9d02e51d302f625d66af82ab16ca5a67216f41'
BASE_SEAL = '1add5889916fd9cfe2bb6e95368a2a86d43f1d0ac27ac4cf89786639cb6f4198'
DESIGN = life.OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb'


def native_reference(rows):
    require(rows and all(r['event'] == 'retire' and not int(r['trap']) for r in rows) and
            [int(r['order']) for r in rows] == list(range(len(rows))), 'Incomplete native retire/no-trap prefix')
    commits = []
    for r in rows:
        word = int(r['insn'],16);addr = int(r['mem_addr'],16)
        read,write = int(r['mem_rmask'],16),int(r['mem_wmask'],16)
        require(not (read and write),'Unexpected atomic/read-write activity')
        access=scalar_memory(word)
        if access:
            kind,size=access;mask=((1 << size)-1) << (addr&7)
            require(addr%size == 0 and read == (mask if kind == 'read' else 0) and
                    write == (mask if kind == 'write' else 0),'Missing/extra native memory mask')
        else:require(not (read or write),'Foreign native memory effect')
        accesses = ()
        if write:
            a,data = scalar_store(r)
            accesses = ((a,int.from_bytes(data,'little')),)
        elif read:
            require(access and access[0] == 'read' and addr%access[1] == 0 and
                    read == ((1 << access[1])-1) << (addr&7), 'Native load address/mask/encoding differs')
            accesses = ((addr,None),)
        rd = int(r['rd']);gpr = {}
        if rd:
            require(re.fullmatch(r'(?:0x)?[0-9a-fA-F]+',r['rd_wdata']) is not None,'Unknown native GPR write')
            gpr[rd] = int(r['rd_wdata'],16)
        commits.append(pre.architecture.spike_trace.SpikeCommit(
            pc=int(r['pc'],16),instruction=word,gpr_writes=gpr,fpr_writes={},vector_writes={},
            csr_writes={},memory_accesses=accesses))
    return commits


def full_union(before,single):
    require(len(before['tests']) == len(set(before['tests'])) == 768 and
            single['tests'] == [str(RUN/'code.vdb')], 'Exact768 plus one member required')
    after = bitmap.combine(before,single);count=0
    for metric,rows in before['metrics'].items():
        for scope,r in rows.items():
            n=single['metrics'][metric][scope];a=after['metrics'][metric][scope]
            require(int(a['bits'],16) == int(r['bits'],16) | int(n['bits'],16),'Independent full OR differs')
            count+=1
    require(count == 6162 and after['tests'] == before['tests']+single['tests'] and
            len(set(after['tests'])) == 769,'Full6162 OR/prefix/unique769 differs')
    return after


def console_gate(text):
    lines=text.splitlines()
    require(lines.count('Core Test *** SUCCESS ***') == 1,'Exact terminal software success missing')
    require(re.findall(r'\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+).*?protocol_errors=(\d+) outstanding=(\d+)',text)
            == [('0','0','0','0','0')], 'Zero-vector contract differs')
    require(not any(re.match(r'^\s*(?:UVM_ERROR|UVM_FATAL|Error-|Fatal:|Exception @)',l) for l in lines),
            'Actual error/exception marker')


def collect(output):
    require(not output.exists(),'Fresh offline qualification only')
    prepared=RUN.with_name(RUN.name+'.prepared.json');record=life.read_bound(prepared,RUN_SEAL)
    q=life.read_bound(PRE/'preflight.json',PRE_SEAL)
    pins=life.merge_pins(record['pins'],{str(prepared):RUN_SEAL})
    require(record['command'] == runner.command(PRE/'input.elf',RUN) and record['timeout_s'] == 600 and
            record['case'] == 'tlb_asid_vpn_rsw_matrix' and record['preflight_seal'] == PRE_SEAL,
            'Actual bounded command/preflight differs')
    require(life.read_bound(RUN/'manifest.json',life.digest(RUN/'manifest.json')) == dict(record,pins=pins),
            'Actual run manifest differs')
    terminal=life.read_bound(RUN/'simulation-status.json',life.digest(RUN/'simulation-status.json'))
    require(terminal['status'] == 'SIMULATION_EXITED_NOT_ADMITTED' and terminal['returncode'] == 0 and
            terminal['coverage_admitted'] is False,'Successful terminal required, no retry')
    for p in RUN.rglob('*'):
        if p.is_file():pins=life.merge_pins(pins,{str(p):life.digest(p)})
    for module in tuple(sys.modules.values()):
        p=getattr(module,'__file__',None)
        if p and str(life.ROOT/'verification') in p and Path(p).is_file():
            pins=life.merge_pins(pins,{str(Path(p).resolve()):life.digest(Path(p).resolve())})
    test=Path(__file__).with_name('test_collect_tlb_asid_matrix.py')
    pins=life.merge_pins(pins,{str(test):life.digest(test)})
    life.check(pins);output.mkdir()
    try:
        console_gate((RUN/'console.log').read_text())
        ref=pre.build.parse_spike_commits(PRE/'spike.trace')
        require(pre.validate(ref,q['symbols']) == q['counts'],'Reference107 oracle changed')
        scalar=pre.architecture.spike_trace.compare_commit_prefix(PRE/'spike.trace',RUN/'commit_trace.csv',
            0x80000000,terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
        life.save(output/'scalar-comparison.json',scalar)
        pre.architecture.scalar_exact(scalar,q['counts'])
        with (RUN/'commit_trace.csv').open() as f:rows=list(csv.DictReader(f))
        native= native_reference(rows)
        require(pre.validate(native,q['symbols']) == q['counts'],'Native PTE/CSR/guards/96 reads differ')
        with (RUN/'vector_trace.csv').open() as f:vec=list(csv.DictReader(f))
        require(all(r['event'] == 'config' for r in vec),'Unexpected vector modification')
        life.save(output/'native-oracle.json',dict(checks=107,failed=0,target_reads=96,page_table_words=1536,
            all_three_RSW_write_phases_verified=True,CSR_restored=True,guards_verified=True,
            vector_writes=0,unshifted_native_store_bytes=True,full_scalar_Spike=True,
            UVM_final_report_claimed=False,independent_AXI_waveform_claimed=False))
        base=life.read_bound(pre.BASE/'admission-manifest.json',BASE_SEAL)
        pins=life.merge_pins(pins,life.merge_pins(base['input_pins'],base['output_pins']))
        pins=life.merge_pins(pins,{str(pre.BASE/'admission-manifest.json'):BASE_SEAL})
        before=life.read_bound(pre.BASE/'combined-bits.json',pins[str(pre.BASE/'combined-bits.json')])
        ledger=(pre.BASE/'combined-inputs.txt').read_text().splitlines()
        require(ledger == [str(DESIGN),*before['tests']],'Exact768 ledger/prefix differs')
        with (output/'single-inputs.txt').open('x') as f:f.write(str(DESIGN)+'\n'+str(RUN/'code.vdb')+'\n')
        single=bitmap.collect(output/'single-inputs.txt');after=full_union(before,single)
        delta=bitmap.delta(before,after)
        pred,predpins=pre.prediction();require(pred == q['prediction'],'Exact768 typed prediction changed')
        pins=life.merge_pins(pins,predpins)
        cache=life.read_bound(pre.CACHE,pre.CACHE_SHA)
        old={pre.SCOPE:cache['instances'][pre.SCOPE]}
        for vdb in ledger[742:]:
            paths=list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
            require(len(paths) == 1,'Ambiguous suffix Toggle')
            sample,sha=pre.native.rows(paths[0],[pre.SCOPE]);require(sha == pins[str(paths[0])],'Suffix Toggle drift')
            old=pre.native.union(old,sample)
        files=list((RUN/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files) == 1,'One new Toggle file required')
        sample,sha=pre.native.rows(files[0],[pre.SCOPE]);pins=life.merge_pins(pins,{str(files[0]):sha})
        new=pre.native.union(old,sample);gains=pre.native.gains(old,new)[pre.SCOPE]
        hits=[dict(name=t['native']['name'],native=t['native'],positions=t['fresh_positions'],
                   hit_positions=[i for i in t['fresh_positions'] if i in set(gains)]) for t in pred['targets']]
        gain=dict(baseline=768,scope=pre.SCOPE,checksum=old[pre.SCOPE]['checksum'],width=old[pre.SCOPE]['width'],
            before=old[pre.SCOPE],single=sample[pre.SCOPE],after=new[pre.SCOPE],new_positions=gains,
            new_directions=len(gains),targets=hits,target_new_directions=sum(len(t['hit_positions']) for t in hits),
            predicted_target_directions=984,official_percentage=False,direction_order_calibrated=False)
        require(gain['target_new_directions'] > 0,'No measured targeted gain: architecture PASS is not improvement')
        # Check every cached binary scope against the singleton's compiled encoding, not only DTLB.
        allbinary,sha2=pre.native.rows(files[0],list(cache['instances']))
        require(sha2 == sha,'Toggle file drift');pre.native.union(cache['instances'],allbinary)
        for p,h in single['input_hashes'].items():pins=life.merge_pins(pins,{p:h})
        for rel,h in single['design'].items():pins=life.merge_pins(pins,{str(DESIGN/'snps/coverage/db'/rel):h})
        elfcheck=dedup(ledger,life.digest(PRE/'input.elf'),pins)
        require(elfcheck['ledger_members'] == 768 and not elfcheck['duplicate'],'Full ELF uniqueness differs')
        elfcheck['baseline']=768;pins=life.merge_pins(pins,elfcheck['pins'])
        for name,value in [('single-bits.json',single),('combined-bits.json',after),('raw-delta.json',delta),
                           ('toggle-gain.json',gain),('elf-dedup.json',elfcheck)]:life.save(output/name,value)
        life.check(pins);life.save(output/'evidence-pins.json',pins)
        life.save(output/'qualification.json',dict(status='TLB_MATRIX_FULL_SCALAR_NATIVE107_RAW768_QUALIFIED_NOT_ADMITTED',
            baseline=768,software_checks=107,scalar_counts=q['counts'],measured_toggle_gain=len(gains),
            measured_target_gain=gain['target_new_directions'],raw_delta=delta['metrics'],coverage_admitted=False,
            full_scalar_ISA=True,full_vector_modified=False,UVM_final_report_claimed=False,
            independent_AXI_waveform_claimed=False,official_percentage=False,input_pins=pins,
            output_pins={str(p):life.digest(p) for p in output.iterdir() if p.is_file()}))
        print('QUALIFIED',life.digest(output/'qualification.json'),gain['target_new_directions'],delta['metrics'],flush=True)
    except Exception as e:
        life.save(output/'failure.json',dict(reason=str(e),coverage_admitted=False,rerun=False));raise


def admit(qualified,seal,output):
    require(not output.exists(),'Fresh formal769 only')
    q=life.read_bound(qualified/'qualification.json',seal)
    require(q['status'] == 'TLB_MATRIX_FULL_SCALAR_NATIVE107_RAW768_QUALIFIED_NOT_ADMITTED' and
            q['measured_target_gain'] > 0 and q['software_checks'] == 107,'Qualified measured PASS required')
    pins=life.merge_pins(q['input_pins'],q['output_pins'])
    pins=life.merge_pins(pins,{str(qualified/'qualification.json'):seal});life.check(pins)
    base=life.read_bound(pre.BASE/'admission-manifest.json',BASE_SEAL)
    before=life.read_bound(pre.BASE/'combined-bits.json',base['output_pins'][str(pre.BASE/'combined-bits.json')])
    single=life.read_bound(qualified/'single-bits.json',q['output_pins'][str(qualified/'single-bits.json')])
    after=full_union(before,single);delta=bitmap.delta(before,after)
    gain=life.read_bound(qualified/'toggle-gain.json',q['output_pins'][str(qualified/'toggle-gain.json')])
    require(gain['target_new_directions'] == q['measured_target_gain'] and delta['metrics'] == q['raw_delta'],
            'Qualified gain/delta differs')
    output.mkdir()
    for name,value in [('combined-bits.json',after),('single-bits.json',single),('raw-delta.json',delta),
                       ('tlb-toggle-gain.json',gain),('evidence-pins.json',pins),
                       ('status.json',dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',coverage_admitted=True,
                         aggregate_passed=769,baseline=768,exact768_prefix=True,full_OR_instances=6162,
                         full_scalar_ISA_verified=True,software_checks=107,raw_delta=delta['metrics'],
                         target_new_toggle_directions=q['measured_target_gain'],official_percentage_claimed=False,
                         UVM_final_report_claimed=False,independent_AXI_waveform_claimed=False,RTL_changed=False))]:
        life.save(output/name,value)
    with (output/'combined-inputs.txt').open('x') as f:f.write('\n'.join([str(DESIGN),*after['tests']])+'\n')
    life.check(pins)
    life.save(output/'admission-manifest.json',dict(schema='TLB_ASID_MATRIX_FORMAL769_V1',baseline=str(pre.BASE),
        baseline_seal=BASE_SEAL,qualification=str(qualified/'qualification.json'),qualification_seal=seal,
        input_pins=pins,output_pins={str(p):life.digest(p) for p in output.iterdir()},coverage_admitted=True,
        authorization_source='PARENT_EXPLICIT_SINGLE_RUN_STRICT_ADMISSION'))
    print('ADMITTED769',life.digest(output/'admission-manifest.json'),flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['collect','admit'])
    p.add_argument('--output',type=Path,required=True);p.add_argument('--qualification',type=Path);p.add_argument('--seal')
    a=p.parse_args()
    if a.mode == 'collect':collect(a.output.absolute())
    else:
        require(a.qualification is not None and a.seal,'Qualification/seal required')
        admit(a.qualification.absolute(),a.seal,a.output.absolute())
