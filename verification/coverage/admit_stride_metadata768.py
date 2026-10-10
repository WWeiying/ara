"""Offline exact767+one PASS, including measured Toggle-only gain; no EDA."""
import argparse
import json
from pathlib import Path
import re
import run_stride_metadata767 as case

life,require,OUT=case.life,case.require,case.OUT
RUN=OUT/'stride-metadata-full64-old-image767-agent-20261007-01'
QUAL=RUN.with_name(RUN.name+'-qualified')
QUAL_SHA='e3e4ffb03d0e0941989418898c02f409691a967feadea496a954aba53f2564ec'


def elf_references(value):
    if isinstance(value,dict):
        for v in value.values():yield from elf_references(v)
    elif isinstance(value,list):
        for v in value:yield from elf_references(v)
    elif isinstance(value,str):
        if value.startswith('+PRELOAD='):yield Path(value.split('=',1)[1])
        elif value.startswith('/') and value.endswith('.elf'):yield Path(value)


def dedup(ledger,newhash,evidence=None):
    def is_elf(p):
        with p.open('rb') as f:return f.read(4)==b'\x7fELF'
    pins={};members=[];metadata=None
    for db in ledger[1:]:
        parent=Path(db).parent;found=set();sources=[]
        # Prefer the actual per-run copied ELF/command over a batch-level plan.
        for directory in (parent,parent/'work',*list(parent.parents)[:5]):
            if directory==OUT or OUT not in directory.parents:break
            for p in directory.glob('*.elf'):
                if p.is_file() and is_elf(p):found.add(p.resolve())
            for name in ('manifest.json','started.json','rtl.command.json','coverage.command.json','replay_manifest.json','inputs.json'):
                p=directory/name
                if p.is_file():
                    value=json.loads(p.read_bytes());paths=[x for x in elf_references(value) if x.is_file()]
                    if paths:
                        sources.append(p);found.update(x.resolve() for x in paths)
            if found:break
        if not found and evidence:
            # Parent-run receipts can live beside, rather than inside, their VDB directory.
            if metadata is None:
                metadata=[]
                for name,h in evidence.items():
                    p=Path(name)
                    if p.suffix=='.json' and p.name not in ('combined-bits.json','single-bits.json','candidate-bits.json'):
                        if not p.is_file():continue
                        value=json.loads(p.read_bytes())
                        refs=[x for x in elf_references(value) if x.is_file()]
                        if refs:metadata.append((p,h,value,refs))
            for p,h,value,refs in metadata:
                if str(parent) in json.dumps(value):
                    require(life.digest(p)==h,'Historical command receipt drift')
                    sources.append(p);found.update(x.resolve() for x in refs)
        require(found,'Historical ELF/command missing for '+db)
        for p in sources:pins[str(p)]=life.digest(p)
        hashes={}
        for p in sorted(found):
            require(is_elf(p),'Referenced object is not ELF')
            h=life.digest(p);require(h!=newhash,'Duplicate historical ELF: '+str(p));pins[str(p)]=h;hashes[str(p)]=h
        members.append(dict(vdb=db,ELF_candidates=hashes,command_sources=[str(p) for p in sources]))
    return dict(baseline=767,ledger_members=len(members),members=members,pins=pins,duplicate=False,
                previous_preflight_dedup_scope='Only16 direct .elf pins; this audit resolves actual767 run ELF/commands, superseding that limited scope')


def contract(q,scalar,vector):
    require(q['status']=='STRIDE_FULL64_FULL_ARCHITECTURE_PASS_NOT_ADMITTED' and q['baseline']==767 and
            q['coverage_admitted'] is False and q['qualification_full_scalar_Spike'] is True,'Qualification identity')
    require(q['signature']['checks']==605 and q['signature']['failed_checks']==0 and q['signature']['fullVRF_bytes']==4096,
            'Complete software oracle')
    require(q['lifecycle']['requests']==q['lifecycle']['responses']==94 and q['lifecycle']['exceptions']==0 and
            q['lifecycle']['actual_VL1_strided_operations']==32,'Actual protocol/operations')
    require(scalar['status']=='TERMINAL_TOHOST_MATCH' and scalar['matched_instructions']==9086 and scalar['mismatch'] is None,'Scalar qualification')
    require(vector['status']=='PASS' and vector['compared_instructions']==21 and vector['skipped_unknown_bytes']==0 and
            vector['non_bit_exact_instructions']==0 and vector['first_mismatch'] is None,'Vector qualification')
    require(q['raw_gain']['baseline']==767 and q['raw_gain']['target_new_serialized_directions']==1500 and
            len(q['raw_gain']['targets'])==14 and sum(t['new_directions'] for t in q['raw_gain']['targets'])==1500,'Measured14 Toggle gain')


def evaluate():
    q=life.read_bound(QUAL/'qualification.json',QUAL_SHA);life.check(q['pins'])
    scalar=json.loads((QUAL/'scalar-comparison.json').read_bytes());vector=json.loads((QUAL/'vector-comparison.json').read_bytes())
    contract(q,scalar,vector)
    prepath=OUT/'stride-metadata-full64-preflight767-agent-20261007-02/preflight-manifest.json'
    pre=case.verify(prepath,'96bab5dadca1608b030585707166126ccebd12dc733e9395216610f052542cd0')
    case.common.scalar_exact(scalar,pre['reference_counts'])
    case.vector_gate(vector,case.shared.parse_spike_commits(prepath.parent/'spike.trace'))
    ledger,evidence=case.baseline();before=json.loads((case.BASE/'combined-bits.json').read_bytes())
    single=json.loads((QUAL/'candidate-bits.json').read_bytes())
    require(ledger==[str(case.life.IMAGE)+'.vdb',*before['tests']] and len(before['tests'])==767,'Exact767 prefix')
    require(single['tests']==[str(RUN/'code.vdb')] and str(RUN/'code.vdb') not in ledger,'One distinct new VDB')
    after=case.bitmap.combine(before,single);delta=case.bitmap.delta(before,after)
    require(delta==q['raw_gain']['raw_delta'] and len(after['tests'])==768 and after['tests'][:767]==before['tests'],'OR/prefix/delta')
    # Check all binary local Toggle shapes; packed-array native data is retained untouched for DVE.
    cache=life.read_bound(OUT/'toggle741-capacity-ranking-agent-20261007-01.json','8c9fe15bec6ae5dcd2e5e9dee9c461047db4109464d2c568e3ca5ec9b0bf0865')
    tglfiles=list((RUN/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'));require(len(tglfiles)==1,'One native Toggle data file')
    allbinary,sha=case.toggle.rows(tglfiles[0],list(cache['instances']));case.toggle.union(cache['instances'],allbinary)
    elf_audit=dedup(ledger,life.digest(prepath.parent/'input.elf'),evidence)
    pins=life.merge_pins(q['pins'],evidence);pins=life.merge_pins(pins,elf_audit['pins'])
    pins=life.merge_pins(pins,single['input_hashes'])
    manifest=life.read_bound(case.BASE/'admission-manifest.json',case.BASE_SHA)
    pins=life.merge_pins(pins,manifest['output_pins'])
    paths=[QUAL/'qualification.json',Path(__file__).resolve(),Path(__file__).with_name('test_admit_stride_metadata768.py')]
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in paths});life.check(pins)
    outputs={'combined-bits.json':after,'single-bits.json':single,'raw-delta.json':delta,
        'stride-toggle-gain.json':q['raw_gain'],'elf-ledger-dedup.json':elf_audit,'evidence-pins.json':pins,
        'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',aggregate_passed=768,baseline=767,new_passed=1,
            exact767_prefix=True,unique_new_vdb=True,duplicate_ELF=False,full_scalar_ISA_verified=True,
            full_vector_verified=True,complete_native_protocol_oracle=True,source_guard_CSR_fullVRF_verified=True,
            native_five_metrics_retained=True,compatible_binary_Toggle_instances=len(allbinary),
            raw_delta=delta['metrics'],target_queue_objects=14,target_new_serialized_toggle_positions=1500,
            official_percentage_claimed=False,coverage_admitted=True,RTL_changed=False,new_simulation=False,
            interpretation='VL1 full64 stride metadata, not a huge-address traversal',qualification_seal=QUAL_SHA)}
    return outputs,'\n'.join([ledger[0],*after['tests']])+'\n'


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','verify','admit'));p.add_argument('--output',type=Path,required=True);p.add_argument('--seal')
    a=p.parse_args();out=a.output.resolve();require(out.parent==OUT and not out.exists(),'Fresh formal output')
    values,text=evaluate();outputs={}
    import hashlib
    for name,value in values.items():outputs[str(out/name)]=hashlib.sha256((json.dumps(value,indent=2)+'\n').encode()).hexdigest()
    outputs[str(out/'combined-inputs.txt')]=hashlib.sha256(text.encode()).hexdigest()
    proposal=dict(output=str(out),baseline=str(case.BASE),baseline_seal=case.BASE_SHA,qualification=str(QUAL/'qualification.json'),
                  qualification_seal=QUAL_SHA,input_pins=values['evidence-pins.json'],output_pins=outputs,coverage_admitted=False)
    record=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':life.save(record,proposal);print('PREPARED',str(record),life.digest(record));return
    require(a.seal and life.read_bound(record,a.seal)==proposal,'Prepared seal drift')
    if a.mode=='verify':print('VERIFY_PASS exact767+1 fullISA/fullVRF/605checks/1500Toggle NO_ADMISSION');return
    out.mkdir()
    for name,value in values.items():life.save(out/name,value)
    with (out/'combined-inputs.txt').open('x') as f:f.write(text)
    life.check(proposal['input_pins']);life.check(outputs)
    life.save(out/'admission-manifest.json',dict(proposal,coverage_admitted=True,prepared=str(record),prepared_seal=a.seal,
        authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'))
    print('ADMITTED',str(out),life.digest(out/'admission-manifest.json'))


if __name__=='__main__':main()
