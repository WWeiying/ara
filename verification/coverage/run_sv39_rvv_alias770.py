"""Frozen600s foreground worker; prepare/verify only until parent authorization."""
import argparse
import json
from pathlib import Path
from types import FunctionType,SimpleNamespace
import run_pure_war_simulation as frozen
import preflight_sv39_rvv_alias_smode770 as reference
import run_gap115_axi_capture as capture
from ara_verify.spike_trace import compare_commit_prefix

life,require=frozen.life,frozen.require
ROOT,OUT=life.ROOT,life.OUT
NAME='vsv39_rvv_alias_smode_ring'
PRE=OUT/'sv39-rvv-alias-smode-ring-preflight770-agent-20261007-02'
PRE_SEAL='2c5a419eddde4de7b8750ffed7b48b34918216af283ef8c8cee018094f2305f8'
ELF_SEAL='b48502b66dd1fc0a41db30f5a3d7c23a45f56e3b328155be6a6917f2199328f2'
BASE=OUT/'mfpu-restart-word-boundary-offline-admitted-770-agent-20261007-01'
TCL=Path(__file__).with_name('sv39_alias_metadata_capture.tcl').resolve()
BUDGET=600


def command(out):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
        '+PRELOAD='+str(PRE/'input.elf'),'+TESTCASE='+NAME,'+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(out/'commit_trace.csv'),'+VECTOR_TRACE='+str(out/'vector_trace.csv'),
        '+ARA_UVM_TRACE_AXI_WRITE','-cm','line+cond+fsm+tgl+branch','-cm_dir',str(out/'code.vdb'),
        '-cm_name',NAME,'-ucli','-do',str(TCL)]


def trap_contract(rows,symbols):
    retired=[r for r in rows if r['event']=='retire']
    traps=[i for i,r in enumerate(retired) if int(r['trap'])]
    require(len(traps)==48,'Exactly48 scalar supervisor traps, never silently skip extras')
    returns=[]
    for i in traps:
        row=retired[i]
        require(int(row['pc'],16)==symbols['alias_s_ecall'] and int(row['insn'],16)==0x73
                and int(row['rd'])==0 and int(row['mem_rmask'])==int(row['mem_wmask'])==0,
                'Exact ECALL PC/insn/no memory or destination effect')
        require(i+1<len(retired),'Missing handler')
        handler=retired[i+1];word=int(handler['insn'],16)
        require(not int(handler['trap']) and int(handler['pc'],16)==symbols['alias_machine_return']
                and word>>20==0x342 and word&0x707f==0x2073 and int(handler['rd_wdata'],16)==9,
                'Immediate untouched mcause9 handler read')
        end=next((j for j in range(i+2,len(retired)) if int(retired[j]['pc'],16)==symbols['alias_resume']),None)
        require(end is not None and not any(int(r['trap']) for r in retired[i+1:end]),'Exact handler return')
        epc=[r for r in retired[i+1:end] if int(r['insn'],16)>>20==0x341
             and int(r['insn'],16)&0x707f==0x2073]
        require(len(epc)==1 and int(epc[0]['rd_wdata'],16)==symbols['alias_s_ecall'],'Actual mepc attestation')
        require(int(retired[end-1]['insn'],16)==0x30200073,'Machine MRET before exact resume')
        returns.append((int(row['order']),int(retired[end]['order'])))
    require(len({a for a,b in returns})==len({b for a,b in returns})==48,'Unique trap/return binding')
    return dict(supervisor_ecalls=48,exact_cause_pc_handler_return=True,unexpected_traps=0)


def scalar_compare(commit_csv,pre):
    import csv
    with commit_csv.open() as f:rows=list(csv.DictReader(f))
    traps=trap_contract(rows,pre['symbols'])
    result=compare_commit_prefix(PRE/'spike.trace',commit_csv,0x80000000,
        terminal_tohost_address=pre['symbols']['tohost'],rvfi_store_data_layout='unshifted')
    require(result['status']=='TERMINAL_TOHOST_MATCH' and result['ara_trap_events']==48
            and result['mismatch'] is None and result['skipped_unobservable_register_values']==0,
            'Full instruction/GPR/memory comparison, no permissive trap or unknown-value skip')
    return dict(traps=traps,scalar=result)


def prepare(out):
    out=out.absolute();require(out.parent==OUT and out.resolve()==out and not out.exists(),'Fresh independent run')
    pre=life.read_bound(PRE/'preflight.json',PRE_SEAL);life.check(pre['input_pins'])
    require(pre['status']=='S_MODE_INDEPENDENT_SPIKE_FULL_VRF_MEMORY_PTE_CSR_PREFLIGHT_PASS_NOT_DUT'
            and pre['baseline']==770 and pre['hard_budget_seconds']==600 and not pre['VCS_launched'],
            'Exact S-mode preflight')
    require(life.digest(PRE/'input.elf')==ELF_SEAL and pre['counts']['expected_supervisor_ecalls']==48
            and pre['counts']['checks']==3113 and pre['counts']['target_stores']==pre['counts']['target_loads']==48,
            'No trap-free/MPRV predecessor or reduced fixture')
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(image['simv']==str(life.IMAGE) and len(image['image'])==66
            and image['image'][str(life.IMAGE)]==frozen.IMAGE_SEAL,'Exact frozen simv66')
    baseline=json.loads((BASE/'admission-manifest.json').read_bytes())
    require(baseline['coverage_admitted'] is True,'Formal770 baseline')
    ledger=(BASE/'combined-inputs.txt').read_text().splitlines()
    require(len(ledger)==len(set(ledger))==771 and str(out/'code.vdb') not in ledger,'Exact770/new candidate')
    pins=life.merge_pins(pre['input_pins'],image['image'])
    files=[PRE/'preflight.json',Path(__file__).resolve(),Path(__file__).with_name('test_run_sv39_rvv_alias770.py'),
           Path(frozen.__file__),Path(reference.__file__),Path(life.__file__),TCL,life.PLAN,
           capture.DOC,capture.CONVERTER,Path(capture.__file__),BASE/'admission-manifest.json']
    import ara_verify.spike_trace as scalar
    files.append(Path(scalar.__file__))
    files.extend(sorted((ROOT/'verification/ara_verify').glob('*.py')))
    fifo=ROOT/'hardware/deps/common_cells/src/fifo_v3.sv'
    book=life.read_bound(reference.prior.old.SOURCE,reference.prior.old.SOURCE_SHA)
    require(life.digest(fifo)==book[str(fifo)],'Frozen FIFO source identity')
    fifo_text=fifo.read_text()
    require('mem_n[write_pointer_q] = data_i;' in fifo_text and 'if (push_i && ~full_o)' in fifo_text,
            'Exact accepted push/slot write mapping')
    files.append(fifo)
    for name in ('combined-inputs.txt','combined-bits.json'):
        p=BASE/name;require(life.digest(p)==baseline['output_pins'][str(p)],'Formal770 baseline drift');files.append(p)
    for p in files:pins=life.merge_pins(pins,{str(p):life.digest(p)})
    require(pins[str(capture.CONVERTER)]==capture.CONVERTER_SHA and pins[str(capture.DOC)]==capture.DOC_SHA,
            'Existing successful/documented read-only UCLI dump API')
    life.check(pins)
    return out,dict(case=NAME,preflight=str(PRE/'preflight.json'),preflight_seal=PRE_SEAL,
        command=command(out),output=str(out),pins=pins,timeout_s=BUDGET,baseline_tests=770,
        baseline_manifest_sha256=life.digest(BASE/'admission-manifest.json'),
        image_sha256=frozen.IMAGE_SEAL,elf_sha256=ELF_SEAL,old_image_files_checked=66,
        authorization_source='SEPARATE_PARENT_AGENT_REVIEW_REQUIRED_BEFORE_RUN',
        foreground_lifetime=True,normal_wait_calls=1,start_new_session=True,
        systemd_policy=dict(RuntimeMaxSec=630,TimeoutStopSec=10,KillMode='control-group'),
        coverage_admitted=False,automatic_retry=False,raw_commit=True,raw_vector=True,no_FSDB=True,
        focused_readonly_VPD=True,wave_byte_limit=64*1024*1024,
        scalar_trap_gate='Exact48 cause9/PC/ECALL/untouched-handler CSR/MRET/resume; full nontrap instruction/GPR/memory compare with zero skips',
        functional_gate='tohost1/3113checks/0fails; full scalar/vector/CSR/PTE/samePA4096byte page perphase, full3 VRF/sourceguards; protocol0 and complete native lifecycle',
        metadata_gate='Actual VPD push&&!full, flush0, known vaddr/data_i and write_pointer_q; filter exact samePA target;48 target pushes,16 each low/high/low and all16 slots perphase. No software-only inferred pushes.',
        raw_gain_gate='Compatible complete raw5metric OR against pinned770 plus entire actual candidate VDB; report full scope/position delta. No official Toggle percentage from serialized counts.')


def run(out,manifest):
    namespace=dict(frozen.run.__globals__)
    namespace.update(command=command,PRE=PRE,ELF_SEAL=ELF_SEAL,preflight=SimpleNamespace(NAME=NAME))
    FunctionType(frozen.run.__code__,namespace,'run')(out,manifest)


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','verify','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--prepared-seal');p.add_argument('--parent-authorized',action='store_true')
    a=p.parse_args();require((a.mode!='prepare')==bool(a.prepared_seal),'Verify/run fixed seal required')
    require((a.mode=='run')==a.parent_authorized,'Separate parent run authorization required')
    out,record=prepare(a.output);path=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':
        life.save(path,record);print(json.dumps(dict(prepared=str(path),seal=life.digest(path),pins=len(record['pins']))))
    else:
        require(life.read_bound(path,a.prepared_seal)==record,'Prepared command/pins drift')
        if a.mode=='verify':print('VERIFY_PASS frozen66/770/S-ECALL48/600s/noFSDB/read-only-metadata NO_VCS')
        else:run(out,dict(record,authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'))


if __name__=='__main__':main()
