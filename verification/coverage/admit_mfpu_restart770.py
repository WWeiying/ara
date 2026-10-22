"""Exact formal769 plus one independently qualified MFPU restart; no EDA."""
import argparse
import hashlib
import json
from pathlib import Path

import run_mfpu_restart_word_boundary769 as case
from admit_stride_metadata768 import dedup

life,require=case.life,case.require
QUAL=case.QUAL
QUAL_SHA='17283ab5ea53fd91e6077d3aa08e58e4fd96b3b53034e1ddf25378860fa454af'
REPLAY=life.OUT/'mfpu-restart-word-boundary-parent-replay-20261007-01'
REPLAY_SHA='3ea2f60559ea985dd8c95749231944a8ea73574e26641e5bc9b33455c527b511'
DESIGN=Path(str(life.IMAGE)+'.vdb')


def contract(q):
    require(q['status']=='MFPU_RESTART_FULL_ARCHITECTURE_QUALIFIED_NOT_ADMITTED' and
            q['coverage_admitted'] is False and q['official_percentage'] is False,'Qualified only')
    require((q['software_checks'],q['full_VRF_snapshot_bytes'],q['source_guard_bytes'],q['CSR_words'])==
            (6264,12288,3200,60),'Complete native software oracle')
    require(q['full_scalar_retirements']==53077 and
            q['lifecycle']==dict(requests=225,responses=225,backend_uops=146),'Exact lifecycle')
    p=q['protocol']
    require(p['status']=='EXACT_HANDSHAKE_LASTDRAIN_PASS' and p['requests']==p['responses']==225 and
            p['cycle_offset']==5 and p['last']['after']==0 and p['last']['before']==1<<p['last']['sid'],
            'Complete protocol lastdrain')
    case.vector_gate(q['vector'])
    require(q['vector']['compared_instructions']==50 and q['vector']['compared_bytes']==14376,
            'Complete vector extent')
    require(len(q['per_instruction_FMA_oracles'])==12 and
            [r['start'] for r in q['per_instruction_FMA_oracles']]==list(case.gold.STARTS) and
            all(r['defined_bytes']==2*(512-r['start']) for r in q['per_instruction_FMA_oracles']),
            'Independent12 FMA byte contracts')
    g=q['raw_gain']
    require(g['baseline']==769 and g['baseline_seal']==case.BASE_SHA and
            g['target_new_serialized_positions']==726 and
            sum(len(t['new_serialized_positions']) for t in g['target_objects'])==726,
            'Qualified measured769 target gain')


def union(before,single):
    require(len(before['tests'])==len(set(before['tests']))==769 and
            single['tests']==[str(case.OUT/'code.vdb')],'Exact769 plus exact single VDB')
    after=case.bitmap.combine(before,single);count=0
    for metric,rows in before['metrics'].items():
        for scope,r in rows.items():
            n=single['metrics'][metric][scope];a=after['metrics'][metric][scope]
            require(int(a['bits'],16)==int(r['bits'],16)|int(n['bits'],16),'Independent OR')
            count+=1
    require(count==6162 and after['tests']==before['tests']+single['tests'] and
            len(set(after['tests']))==770,'Full6162 OR exact769 prefix/770unique')
    return after


def replay_equal(original,replay):
    require(set(original)==set(replay),'Complete replay schema')
    require({k:v for k,v in original.items() if k!='pins'} ==
            {k:v for k,v in replay.items() if k!='pins'},'Complete parent architecture/raw replay differs')
    contract(replay)


def measured_toggle(q,ledger,pins):
    cachepath=life.OUT/'toggle741-capacity-ranking-agent-20261007-01.json'
    cache=life.read_bound(cachepath,'8c9fe15bec6ae5dcd2e5e9dee9c461047db4109464d2c568e3ca5ec9b0bf0865')
    review=life.read_bound(case.gold.REVIEW,case.gold.REVIEW_SHA)
    prefix=next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    require(life.digest(prefix)==cache['input_pins'][str(prefix)] and
            prefix.read_text().splitlines()==ledger[:742],'Exact741 reusable prefix')
    scopes=sorted({t['scope'] for t in review['targets']})
    before={s:cache['instances'][s] for s in scopes}
    for name in ledger[742:]:
        paths=list((Path(name)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(paths)==1,'Unique769 Toggle member')
        rows,sha=case.toggle.rows(paths[0],scopes)
        require(pins.get(str(paths[0]))==sha,'Sealed769 Toggle source')
        before=case.toggle.union(before,rows)
    path=case.OUT/'code.vdb/snps/coverage/db/testdata'/case.NAME/'tgl.verilog.data.xml'
    sample,sha=case.toggle.rows(path,scopes)
    require(pins.get(str(path))==sha,'Exact sealed MFPU Toggle')
    after=case.toggle.union(before,sample);targets=[]
    for t in review['targets']:
        old,new=before[t['scope']],after[t['scope']]
        require(old['checksum']==new['checksum']==t['checksum'] and
                old['width']==new['width']==t['serialized_width'],'Typed target checksum/width')
        positions=[i for i in t['exact_missing_serialized_positions'] if
            not(int(old['bits'],16)>>(old['width']-1-i)&1) and int(new['bits'],16)>>(new['width']-1-i)&1]
        targets.append(dict(scope=t['scope'],name=t['name'],new_serialized_positions=positions))
    require(targets==q['raw_gain']['target_objects'] and
            case.toggle.gains(before,after)==q['raw_gain']['scoped_toggle'],
            'Exact actual Toggle identities and incremental positions')
    # Global binary encoding compatibility, not a full-design incremental claim.
    allbinary,sha2=case.toggle.rows(path,list(cache['instances']))
    require(sha2==sha,'Native Toggle changed');case.toggle.union(cache['instances'],allbinary)
    return len(allbinary)


def evaluate(qualified,seal):
    path=qualified/'qualification.json';q=life.read_bound(path,seal);contract(q)
    original=life.read_bound(QUAL/'qualification.json',QUAL_SHA)
    replay=life.read_bound(REPLAY/'qualification.json',REPLAY_SHA)
    replay_equal(original,replay);replay_equal(original,q)
    pins=life.merge_pins(life.merge_pins(q['pins'],original['pins']),replay['pins'])
    pins=life.merge_pins(pins,{str(path):seal,str(QUAL/'qualification.json'):QUAL_SHA,
                             str(REPLAY/'qualification.json'):REPLAY_SHA});life.check(pins)
    for name,embedded in [('scalar-comparison.json',q['scalar']),('vector-comparison.json',q['vector']),
                          ('raw-gain769.json',q['raw_gain'])]:
        p=qualified/name
        require(str(p) in pins and life.read_bound(p,pins[str(p)])==embedded,'Sealed qualification output mismatch')
    pre=life.read_bound(case.gold.OUT/'preflight.json',case.precheck.PREFLIGHT_SHA)
    case.shared.scalar_exact(q['scalar'],pre['counts'])
    base,ledger=case.baseline()
    pins=life.merge_pins(pins,life.merge_pins(base['input_pins'],base['output_pins']))
    pins=life.merge_pins(pins,{str(case.BASE/'admission-manifest.json'):case.BASE_SHA})
    before=life.read_bound(case.BASE/'combined-bits.json',base['output_pins'][str(case.BASE/'combined-bits.json')])
    require(ledger==[str(DESIGN),*before['tests']],'Exact formal769 ledger')
    inputfile=qualified/'candidate-inputs.txt'
    require(str(inputfile) in pins and life.digest(inputfile)==pins[str(inputfile)] and
            inputfile.read_text().splitlines()==[ledger[0],str(case.OUT/'code.vdb')],'Exact sealed singleton ledger')
    single=case.bitmap.collect(inputfile)
    require(all(pins.get(p)==h for p,h in single['input_hashes'].items()),'Sealed singleton four metrics')
    require(all(pins.get(str(DESIGN/'snps/coverage/db'/p))==h for p,h in single['design'].items()),
            'Sealed design/shape compatibility')
    after=union(before,single);delta=case.bitmap.delta(before,after)
    require(delta==q['raw_gain']['raw_delta'],'Exact qualified raw delta')
    compatible=measured_toggle(q,ledger,pins)
    elf_audit=dedup(ledger,life.digest(case.gold.OUT/'input.elf'),pins)
    require(elf_audit['ledger_members']==769 and not elf_audit['duplicate'],'Unique sealed ELF')
    elf_audit['baseline']=769;pins=life.merge_pins(pins,elf_audit['pins'])
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_mfpu_restart770.py')):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins)
    values={'combined-bits.json':after,'single-bits.json':single,'raw-delta.json':delta,
        'mfpu-toggle-gain.json':q['raw_gain'],'elf-ledger-dedup.json':elf_audit,'evidence-pins.json':pins,
        'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',coverage_admitted=True,aggregate_passed=770,
            baseline=769,new_passed=1,exact769_prefix=True,full_OR_instances=6162,unique_new_vdb=True,
            duplicate_ELF=False,full_scalar_ISA_verified=True,full_vector_verified=True,
            complete_native_protocol_oracle=True,software_checks=6264,full_VRF_snapshot_bytes=12288,
            source_guard_bytes=3200,CSR_words=60,per_instruction_FMA_oracles=12,
            target_new_serialized_toggle_positions=726,compatible_binary_Toggle_instances=compatible,
            raw_delta=delta['metrics'],official_percentage_claimed=False,RTL_changed=False,new_simulation=False,
            qualification=str(path),qualification_seal=seal,parent_replay=str(REPLAY/'qualification.json'),
            parent_replay_seal=REPLAY_SHA)}
    return values,'\n'.join([ledger[0],*after['tests']])+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['prepare','verify','admit']);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--qualification',type=Path,default=QUAL);p.add_argument('--qualification-seal',default=QUAL_SHA)
    p.add_argument('--seal');a=p.parse_args();out=a.output.absolute()
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh formal770 output')
    values,text=evaluate(a.qualification.absolute(),a.qualification_seal)
    outputs={str(out/n):hashlib.sha256((json.dumps(v,indent=2)+'\n').encode()).hexdigest() for n,v in values.items()}
    outputs[str(out/'combined-inputs.txt')]=hashlib.sha256(text.encode()).hexdigest()
    proposal=dict(output=str(out),baseline=str(case.BASE),baseline_seal=case.BASE_SHA,
        qualification=str(a.qualification.absolute()/'qualification.json'),qualification_seal=a.qualification_seal,
        input_pins=values['evidence-pins.json'],output_pins=outputs,coverage_admitted=False)
    record=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':life.save(record,proposal);print('PREPARED',str(record),life.digest(record),flush=True);return
    require(a.seal and life.read_bound(record,a.seal)==proposal,'Exact prepared contract')
    if a.mode=='verify':print('VERIFY_PASS_NO_ADMISSION',flush=True);return
    out.mkdir()
    for n,v in values.items():life.save(out/n,v)
    with (out/'combined-inputs.txt').open('x') as f:f.write(text)
    life.check(proposal['input_pins']);life.check(outputs)
    life.save(out/'admission-manifest.json',dict(proposal,coverage_admitted=True,prepared=str(record),
        prepared_seal=a.seal,authorization_source='PARENT_REPLAY_PASS_REQUIRED_BEFORE_AGENT_ADMIT'))
    print('ADMITTED770',str(out),life.digest(out/'admission-manifest.json'),flush=True)


if __name__=='__main__':main()
