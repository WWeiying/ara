"""One sealed matrix, foreground old-image lifecycle; prepare/verify do not run EDA."""
import argparse
import csv
import json
from pathlib import Path
from types import SimpleNamespace

import preflight_queue_mask_source_lifetime_tail as software
import run_pure_war_simulation as frozen

p=software.prior
life,require=p.life,p.require
PRE=life.OUT/'queue-mask-source-lifetime-tail-preflight-738-agent-20261006-01'
PRE_SEAL='7b5cae18f99f755a4a4488e4aeb9859d05f0d937cd5f489c4ba0fc89f29fa9b4'
ELF=PRE/'input.elf'
ELF_SHA='93649e806ef6d39d79cbd6ff0e457ef7a5a59bce699e5a81ce63324e16a03209'
IMAGE_SHA='2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
FROZEN_SHA='2e7ded5ac7c1caeff20a0d1febbb7123dbd30973a9fdef0435ad051673e11626'
NAME='vqueue_mask_source_lifetime'
BUDGET=600
RETIREMENTS=96979
FREEZE={str(software.APP):'d76204ef8fd3efae4644d794518ceffb2e58e08369c26cf04070810bc324a1f4',
        str(Path(software.__file__).resolve()):'9cc242729a721ed26bbe09fa3ca2b927662851d03029e60815a71209a3fd7c15',
        str(Path(software.__file__).with_name('test_preflight_queue_mask_source_lifetime_tail.py').resolve()):
        '52c432851c5522052a7db78730f2c04ab7caa2c8d6fae8309f1fa4fc970ceabb'}

def reference_counts(commits,tohost):
    terminals=[i for i,c in enumerate(commits) if any(a==tohost and v is not None for a,v in c.memory_accesses)]
    require(len(terminals)==1 and commits[terminals[0]].memory_accesses==((tohost,1),),
            'One exact successful terminal store required')
    prefix=commits[:terminals[0]+1]
    return dict(matched_instructions=len(prefix),scalar_writes=sum(len(c.gpr_writes) for c in prefix),
        memory_accesses=sum(len(c.memory_accesses) for c in prefix),
        vector_destination_instructions=sum(bool(c.vector_writes) for c in prefix),
        total_spike_records=len(commits),post_terminal_records=len(commits)-len(prefix))

def verify_preflight():
    pre=life.read_bound(PRE/'preflight-manifest.json',PRE_SEAL)
    require(pre['schema']=='QUEUE_MASK_LIFETIME_TAIL_SOFTWARE_PREFLIGHT_V2' and
            pre['baseline']==str(p.BASE) and pre['baseline_seal']==p.BASE_SHA and
            pre['checks']==6936 and pre['elf_sha256']==ELF_SHA and
            pre['native_qualification'] is False and pre['application_approval'] is False,
            'Exact software-only preflight contract differs')
    pins=life.merge_pins(pre['pins'],pre['outputs'])
    pins=life.merge_pins(pins,FREEZE);life.check(pins)
    require(pre['outputs'].get(str(ELF))==ELF_SHA,'ELF ownership differs')
    symbols=life.read_bound(PRE/'symbols.json',pins[str(PRE/'symbols.json')])
    require(symbols['tohost']==0x80001000,'Terminal address differs')
    commits=p.shared.parse_spike_commits(PRE/'spike.log')
    result=software.namespace()['validate'](commits,symbols,(PRE/'spike.log').read_text())
    counts=reference_counts(commits,symbols['tohost'])
    require(counts==dict(matched_instructions=96979,scalar_writes=64700,memory_accesses=21387,
            vector_destination_instructions=32,total_spike_records=100000,post_terminal_records=3021),
            'Exact terminal-prefix reference counts differ')
    require(result==life.read_bound(PRE/'validation.json',
            pins[str(PRE/'validation.json')]),'Complete software oracle/retirement replay differs')
    require(pre['tail_policy']==software.tail_policy(),'Exact defined/agnostic boundary differs')
    require(len({c.pc for c in commits if c.instruction&127 in (0x57,0x07,0x27)})==60 and
            sum(bool(c.vector_writes) for c in commits)==32,'All executed RVV PCs/writers differ')
    targets,sourcepins=p.binding()
    require(pre['targets']==targets and all(pins.get(k)==v for k,v in sourcepins.items()),
            'Exact738 four-lane zero/source binding differs')
    return pre,pins,counts

def budget_evidence():
    rows=[];pins={}
    for name in ('narrow-source-group-old-image-parent-20261006-01',
                 'narrow-clip-reject-450-old-image-parent-20261006-01'):
        root=life.OUT/name;status=root/'simulation-status.json';trace=root/'commit_trace.csv'
        data=json.loads(status.read_bytes())
        require(data['returncode']==0 and data['timeout'] is False and data['wall_seconds']>0,
                'Historical budget context is not terminal success')
        with trace.open() as f:
            count=sum(row['event']=='retire' for row in csv.DictReader(f))
        require(count>0,'Empty budget trace')
        rows.append(dict(run=str(root),retirements=count,wall_seconds=data['wall_seconds'],
            linear_context_estimate_s=RETIREMENTS*data['wall_seconds']/count,
            context_only_not_performance_guarantee=True))
        pins.update({str(x):life.digest(x) for x in (status,trace)})
    require(BUDGET>max(r['linear_context_estimate_s'] for r in rows)*1.15,
            'Budget lacks context allowance')
    return rows,pins

def command(out):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
        '+PRELOAD='+str(ELF),'+TESTCASE='+NAME,'+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(out/'commit_trace.csv'),'+VECTOR_TRACE='+str(out/'vector_trace.csv'),
        '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(out/'code.vdb'),'-cm_name',NAME]

def manifest(out):
    require(out.parent==life.OUT and out.resolve()==out,'Direct independent output required')
    pre,pins,counts=verify_preflight()
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(image['simv']==str(life.IMAGE) and len(image['image'])==66 and
            image['image'].get(str(life.IMAGE))==IMAGE_SHA,'Exact image66 contract differs')
    rows,contextpins=budget_evidence()
    require(life.digest(Path(frozen.__file__))==FROZEN_SHA,'Frozen foreground lifecycle changed')
    deps=[Path(__file__).resolve(),Path(__file__).with_name('test_run_queue_mask_source_lifetime_simulation.py'),
          Path(life.__file__).resolve()]+sorted((life.ROOT/'verification/ara_verify').rglob('*.py'))
    pins=life.merge_pins(pins,image['image']);pins=life.merge_pins(pins,contextpins)
    pins=life.merge_pins(pins,{str(x):life.digest(x) for x in deps})
    pins=life.merge_pins(pins,{str(PRE/'preflight-manifest.json'):PRE_SEAL,
        str(life.PLAN):life.PLAN_SEAL,str(Path(frozen.__file__).resolve()):FROZEN_SHA})
    life.check(pins)
    return dict(case=NAME,output=str(out),command=command(out),pins=pins,timeout_s=BUDGET,
        preflight=str(PRE/'preflight-manifest.json'),preflight_seal=PRE_SEAL,
        input_elf=str(ELF),elf_sha256=ELF_SHA,image_sha256=IMAGE_SHA,old_image_files_checked=66,
        baseline_tests=738,targets=pre['targets'],spike_terminal_prefix_retirements=RETIREMENTS,
        reference_counts=counts,budget_context=rows,software_checks=6936,
        strictly_defined_memory_snapshot_bytes=6912,csr_values=24,tail_policy=pre['tail_policy'],
        full_scalar_instruction_diff_required=True,full_vector_diff_required=True,
        all_memory_accesses_required=True,backend_and_VRF_activity_required=True,
        signature_alone_is_not_qualification=True,primary_cond665_hit_requires_actual_raw_measurement=True,
        native_stall_measured=False,native_cycle_qualified=False,foreground_lifetime=True,
        automatic_retry=False,no_FSDB=True,raw_commit=True,raw_vector=True,rtl_changed=False,
        coverage_admitted=False,admission_performed=False,terminal_oracle_verified=False,
        systemd_policy=dict(RuntimeMaxSec=660,TimeoutStopSec=10,KillMode='control-group'))

def prepare(out):
    require(not out.exists(),'Fresh run only; retries forbidden')
    return manifest(out)

def invoke_run(out,record):
    require(prepare(out)==record,'Reviewed execution drift')
    lifecycle_namespace()['run'](out,record)

def lifecycle_namespace():
    path=Path(frozen.__file__).resolve()
    require(life.digest(path)==FROZEN_SHA,'Frozen lifecycle drift')
    namespace=dict(__name__='queue_mask_private_fixed600_lifecycle',__file__=str(path))
    exec(compile(path.read_bytes(),str(path),'exec'),namespace)
    namespace.update(PRE=PRE,ELF_SEAL=ELF_SHA,IMAGE_SEAL=IMAGE_SHA,BUDGET=BUDGET,
                     preflight=SimpleNamespace(NAME=NAME),command=command)
    return namespace

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode',choices=('prepare','verify','run'));ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--prepared-seal');ap.add_argument('--parent-authorized',action='store_true')
    a=ap.parse_args(argv)
    require((a.mode!='prepare')==bool(a.prepared_seal),'Verify/run need exact reviewed seal')
    require((a.mode=='run')==a.parent_authorized,'Run requires separate explicit parent authorization')
    out=a.output.absolute();record=prepare(out);sidecar=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':
        require(not sidecar.exists(),'Existing sidecar retained; no overwrite')
        life.save(sidecar,record)
        print(json.dumps(dict(prepared=str(sidecar),seal=life.digest(sidecar),pins=len(record['pins']),
                             timeout_s=BUDGET,VCS_started=False)))
    else:
        require(life.read_bound(sidecar,a.prepared_seal)==record,'Reviewed sidecar mismatch')
        if a.mode=='run':invoke_run(out,record)
        else:print('VERIFY_PASS_NO_EDA')

if __name__=='__main__':main()
