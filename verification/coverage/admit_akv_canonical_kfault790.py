"""Parent-only sequential790/791 publication; readonly measured raw gains first."""
import argparse
import hashlib
import json
from pathlib import Path

import coverage_bitmap_delta as bitmap
import targeted_toggle_evidence as toggle
import collect_akv_canonical_kfault_epoch_offline as epoch

life, need, runner = epoch.life, epoch.require, epoch.original.runner
BASE = life.OUT/'csr-cause-wlrl-offline-admitted789-agent-20261008-02'
BASE_SHA = '810a9531e1e7a7edaece3fcec19e90e47fee3530e641f824aaed49e8deb3522d'
QUALS = tuple(life.OUT/('akv-canonical-kfault-phase%d-epoch-qualified-parent-20261008-01/qualification.json'%i) for i in (0,1))
QUAL_SHAS = ('60a85808b4287d60d1e968fee7a7e7a8a893531b4918cf10631601b54f3324e2',
             'd0be73155da4cd491fef3425c354bb4c920684c294779e9cbca99a3d1800cc75')
RUNS = tuple(life.OUT/('akv-canonical-kfault-phase%d-old-image-agent-20261008-01'%i) for i in (0,1))
RUN_SHAS = ('ecd7a0d1e182090530b4b8f3086ea83207b5fddc0ff84a07cebcb186ff77387a',
            '5a3c441415f2d897364c21bab2c9851b8b9952f3b5ddbd70cbfaccb93cd76c73')
CACHE = life.OUT/'toggle741-capacity-ranking-agent-20261007-01.json'
CACHE_SHA = '8c9fe15bec6ae5dcd2e5e9dee9c461047db4109464d2c568e3ca5ec9b0bf0865'
COUNTS = dict(line=1892,cond=2023,branch=2155,fsm=92)
ROOT_SCOPE = 'ara_tb.dut.i_ara_soc.i_system'


def union_gate(before,single,population):
    need(len(before['tests'])==len(set(before['tests']))==population and
         len(single['tests'])==1 and single['tests'][0] not in before['tests'], 'Exact unique population append')
    need(set(before['metrics'])==set(single['metrics'])==set(COUNTS), 'Four exact metric families')
    life.merge_pins(before['input_hashes'],single['input_hashes'])
    after=bitmap.combine(before,single)
    for metric,count in COUNTS.items():
        a,b,c=(x['metrics'][metric] for x in (before,single,after))
        need(len(a)==count and set(a)==set(b)==set(c), 'Complete6162 metric instance universe')
        for scope,row in a.items():
            other,final=b[scope],c[scope]
            need(type(row['width']) is int and row['width']>=0 and
                 (row['width'],row['checksum'])==(other['width'],other['checksum'])==(final['width'],final['checksum']), 'Exact metric shape')
            values=[int(r['bits'],16) for r in (row,other,final)]
            need(min(values)>=0 and max(values).bit_length()<=row['width'] and values[2]==values[0]|values[1], 'Bounded exact OR')
    need(after['tests']==before['tests']+single['tests'], 'Exact ordered prefix')
    return after


def toggle_gain(before,after):
    coordinates=toggle.gains(before,after)
    groups=[dict(scope=s,width=before[s]['width'],checksum=before[s]['checksum'],
                 serialized_positions=positions,new_raw_directions=len(positions))
            for s,positions in coordinates.items() if positions]
    return dict(raw_diagnostic_only=True,official_denominator=None,official_percentage=None,
        direction_or_bit_mapping_claimed=False,groups=groups,
        all_scopes=sum(g['new_raw_directions'] for g in groups),
        i_system=sum(g['new_raw_directions'] for g in groups if g['scope']==ROOT_SCOPE or g['scope'].startswith(ROOT_SCOPE+'.')))


def qualification_gate(q,phase):
    need(type(phase) is int and phase in (0,1), 'Exact phase')
    need(q['status']=='AKV_CANONICAL_KFAULT_EXACT_OWNER_ARCH_CYCLE_PASS_NOT_ADMITTED' and
         q['coverage_admitted'] is False and q['RTL_modified'] is False and
         q['scalar_Spike_instruction_stream_equality'] is False, 'Scoped parent qualification, not full ISA claim')
    a,c=q['architecture'],q['cycles']; proof=c['global_terminal_evidence']
    need(a['retirements']==74627 and a['traps']==2 and len(a['owners'])==1, 'Complete native architecture')
    owner=a['owners'][0]
    need(owner['status']=='PASS' and owner['requests']==owner['responses']==188 and
         owner['full_scalar_compared_words']==5680 and owner['exact_destination_bytes']==384 and
         owner['custom']==[[11870299,1],[11870299,0],[341083,0],[341083,0],[341083,0],[20571,0]], 'Full owner/readback/retry/release contract')
    need(c['status']=='PASS' and c['accepted_AR']==c['accepted_RLAST']==6 and c['sampled_edges']==333
         and len(c['faults'])==len(c['acknowledgements'])==1 and
         int(c['faults'][0]['address'],16)==epoch.original.p.ADDRESSES[phase], 'Exact phase waveform owner')
    need(proof['VCD_units']=='100fs' and proof['first_global_edge']==155000 and proof['global_period']==10000
         and proof['global_last_commit_cycle']==a['last_cycle'] and
         proof['VCD_EOF_timestamp']==155000+a['last_cycle']*10000 and
         proof['reset_events']==[[0,'0'],[100000,'1']] and proof['held_idle_until_EOF'] is True
         and proof['gated_edges_not_global_cycles'] is True, 'Exact ungated epoch closure')
    closure=q['offline_epoch_closure']
    need(closure['clock_proof']==proof and closure['original_collector_sha']==epoch.ORIGINAL_SHA
         and closure['native_VCS_reexecuted'] is False and closure['converter_reexecuted'] is False, 'Existing evidence only')


def baseline(path,seal,population):
    manifest=life.read_bound(path/'admission-manifest.json',seal)
    need(manifest['coverage_admitted'] is True and manifest['output']==str(path), 'Formal admitted baseline')
    pins=life.merge_pins(manifest['input_pins'],manifest['output_pins'])
    pins=life.merge_pins(pins,{str(path/'admission-manifest.json'):seal})
    def doc(name): return life.read_bound(path/name,pins[str(path/name)])
    status=doc('status.json'); before=doc('combined-bits.json')
    ledger=(path/'combined-inputs.txt').read_text().splitlines()
    need(status['aggregate_passed']==population and status['coverage_admitted'] is True and
         ledger==[str(life.IMAGE)+'.vdb',*before['tests']] and len(ledger)==len(set(ledger))==population+1,
         'Exact admitted population ledger')
    if population==789: need(path==BASE and seal==BASE_SHA, 'Only approved789 anchor')
    else:
        need(population==790 and manifest['schema']=='AKV_CANONICAL_KFAULT_HISTORICAL790_ADMISSION_V1'
             and manifest['baseline']==str(BASE) and manifest['baseline_seal']==BASE_SHA
             and manifest['qualification_seal']==QUAL_SHAS[0], 'Only sequential qualified790 predecessor')
        anchor=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
        old=life.read_bound(BASE/'combined-bits.json',anchor['output_pins'][str(BASE/'combined-bits.json')])
        need(before['tests']==old['tests']+[str(RUNS[0]/'code.vdb')], 'Exact789 prefix plusphase0')
    return manifest,before,ledger,pins


def baseline_toggle(before,ledger,pins):
    cache=life.read_bound(CACHE,CACHE_SHA)
    cachepins=dict(cache['input_pins']); life.check(cachepins)
    prefix=next(Path(p) for p in cachepins if p.endswith('/inputs.txt'))
    need(ledger[:742]==prefix.read_text().splitlines() and cache['tests']==741, 'Sealed741 cache exact ledger prefix')
    result={s:{k:r[k] for k in ('width','checksum','bits')} for s,r in cache['instances'].items()}
    need(len(result)==2989, 'Complete native Toggle instances')
    extra={str(CACHE):CACHE_SHA}
    for db in ledger[742:]:
        files=list((Path(db)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        need(len(files)==1 and str(files[0]) in pins, 'Bound native suffix Toggle')
        path=files[0]; sample=bitmap.read_metric(path)
        need(life.digest(path)==pins[str(path)], 'Native suffix bytes')
        result=toggle.union(result,sample)
    return result,life.merge_pins(cachepins,extra)


def sample(phase,authority):
    q=life.read_bound(QUALS[phase],QUAL_SHAS[phase]); qualification_gate(q,phase)
    pins=life.merge_pins(q['input_pins'],q['output_pins'])
    pins=life.merge_pins(pins,{str(QUALS[phase]):QUAL_SHAS[phase]})
    pins=life.merge_pins(authority,pins)
    run=RUNS[phase]; prepared=run.with_name(run.name+'.prepared.json')
    manifest=life.read_bound(prepared,RUN_SHAS[phase])
    need(life.read_bound(run/'manifest.json',RUN_SHAS[phase])==manifest and
         manifest['phase']==phase and manifest['command']==runner.command(run,phase)
         and manifest['elf_sha256']==life.digest(runner.elf_path(phase)), 'Exact ELF/native command')
    epoch.original.terminal_gate(life.read_bound(run/'simulation-status.json',pins[str(run/'simulation-status.json')]),
        life.read_bound(run/'started.json',pins[str(run/'started.json')]),manifest,run)
    vdb=run/'code.vdb'; actual={str(p) for p in vdb.rglob('*') if p.is_file()}
    need(actual and actual=={p for p in q['input_pins'] if p.startswith(str(vdb)+'/')}
         and not any(p.is_symlink() for p in vdb.rglob('*')), 'Complete qualified VDB membership')
    design_dir=Path(str(life.IMAGE)+'.vdb')/'snps/coverage/db'
    design_paths=[design_dir/'design/verilog.design.xml',*[design_dir/('shape/'+m+'.verilog.shape.xml') for m in COUNTS]]
    need(all(pins.get(str(p))==life.digest(p) for p in design_paths), 'Sealed same-image compiled design bytes')
    single=dict(design={str(p.relative_to(design_dir)):pins[str(p)] for p in design_paths},
                tests=[str(vdb)],input_hashes={},metrics={})
    folder=vdb/'snps/coverage/db/testdata'/('%s_phase%d'%(runner.NAME,phase))
    need(list(folder.parent.iterdir())==[folder], 'Single exact native test name')
    for metric in (*COUNTS,'tgl'):
        path=folder/(metric+'.verilog.data.xml')
        need(str(path) in pins and life.digest(path)==pins[str(path)], 'Qualified metric bytes')
        rows=bitmap.read_metric(path)
        if metric=='tgl': tgl=rows
        else:
            single['metrics'][metric]=rows;single['input_hashes'][str(path)]=pins[str(path)]
    return q,single,tgl,pins


def elf_dedup(base,ledger,pins,new_sha):
    path=base/'elf-ledger-dedup.json'; audit=life.read_bound(path,pins[str(path)])
    members=audit['members'][:]
    need(audit['duplicate'] is False and len(members)==audit['ledger_members'] and
         [m['vdb'] for m in members]==ledger[1:1+len(members)], 'Historical sealed ELF ownership prefix')
    for db in ledger[1+len(members):]:
        path=Path(db).parent/'manifest.json'; record=life.read_bound(path,pins[str(path)])
        elfs=[s.split('=',1)[1] for s in record['command'] if s.startswith('+PRELOAD=')]
        need(len(elfs)==1 and elfs[0] in pins, 'Exact ELF for ledger suffix')
        members.append(dict(vdb=db,ELF_candidates={elfs[0]:pins[elfs[0]]},command_sources=[str(path)]))
    need(len(members)==len(ledger)-1 and all(m['ELF_candidates'] and
         all(pins.get(p)==h and h!=new_sha for p,h in m['ELF_candidates'].items()) for m in members), 'No missing/drifted/duplicate ELF')
    return dict(ledger_members=len(members),members=members,duplicate=False,new_ELF_sha256=new_sha,
                historical_authority_only=True)


def evaluate(phase,base,seal):
    population=789+phase
    manifest,before,ledger,pins=baseline(base,seal,population)
    q,single,tgl,qpins=sample(phase,pins);pins=life.merge_pins(pins,qpins)
    after=union_gate(before,single,population);delta=bitmap.delta(before,after)
    oldtgl,cachepins=baseline_toggle(before,ledger,pins);pins=life.merge_pins(pins,cachepins)
    newtgl=toggle.union(oldtgl,tgl);gain=toggle_gain(oldtgl,newtgl)
    need(sum(delta['metrics'].values())+gain['i_system']>0, 'Zero integration gain: no admission')
    dedup=elf_dedup(base,ledger,pins,life.digest(runner.elf_path(phase)))
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_akv_canonical_kfault790.py'),
                 Path(bitmap.__file__).resolve(),Path(toggle.__file__).resolve(),Path(epoch.__file__).resolve()):
        pins=life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    retained={Path(p).name:life.read_bound(Path(p),h) for p,h in manifest['output_pins'].items()
        if Path(p).parent==base and p.endswith('.json') and ('toggle-gain' in Path(p).name or Path(p).name.startswith('retained-'))}
    retained.update({'single-bits.json':single,'combined-bits.json':after,'raw-delta.json':delta,
        'combined-toggle-bits.json':newtgl,'akv-phase%d-toggle-gain.json'%phase:gain,
        'elf-ledger-dedup.json':dedup,'evidence-pins.json':pins,
        'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',aggregate_passed=population+1,
            baseline=population,new_passed=1,coverage_admitted=True,exact_prefix=True,
            full_OR_metric_instances=6162,native_toggle_instances=2989,raw_delta=delta['metrics'],
            raw_Toggle_gain=gain['i_system'],qualification_seal=QUAL_SHAS[phase],
            full_scalar_ISA_equality=False,official_percentage_claimed=False,RTL_changed=False,new_simulation=False)})
    return retained,'\n'.join([ledger[0],*after['tests']])+'\n'


def measure(output):
    _,before,ledger,pins=baseline(BASE,BASE_SHA,789)
    oldtgl,cpins=baseline_toggle(before,ledger,pins);pins=life.merge_pins(pins,cpins)
    rows=[]
    for phase in (0,1):
        _,single,tgl,qpins=sample(phase,pins);pins=life.merge_pins(pins,qpins)
        after=union_gate(before,single,789+phase);newtgl=toggle.union(oldtgl,tgl)
        rows.append(dict(phase=phase,qualification=str(QUALS[phase]),qualification_seal=QUAL_SHAS[phase],
            diagnostic_baseline=789+phase,baseline_is_prospective=(phase==1),
            four_metrics=bitmap.delta(before,after),toggle=toggle_gain(oldtgl,newtgl)))
        before,oldtgl=after,newtgl
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_akv_canonical_kfault790.py')):
        pins=life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    life.save(output,dict(schema='AKV_TWO_PHASE_RAW_GAIN789_DIAGNOSTIC_V1',baseline=str(BASE),baseline_seal=BASE_SHA,
        phases=rows,input_pins=pins,coverage_admitted=False,official_percentage=None,new_simulation=False))
    print(json.dumps(dict(output=str(output),seal=life.digest(output),gains=[dict(phase=r['phase'],metrics=r['four_metrics']['metrics'],Toggle=r['toggle']['i_system']) for r in rows])),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('measure','prepare','verify','admit'));p.add_argument('--phase',type=int,choices=(0,1))
    p.add_argument('--baseline',type=Path,default=BASE);p.add_argument('--baseline-seal',default=BASE_SHA)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--parent-authorized',action='store_true')
    a=p.parse_args();out=a.output.resolve()
    need(out.parent==life.OUT and not out.exists(), 'Fresh output only')
    need((a.mode=='admit')==a.parent_authorized and (a.mode in ('verify','admit'))==bool(a.seal), 'Explicit parent publication/seal')
    if a.mode=='measure':need(a.phase is None and a.baseline.resolve()==BASE and a.baseline_seal==BASE_SHA,'Only formal789 measurement');measure(out);return
    need(a.phase is not None,'Exact phase required')
    values,text=evaluate(a.phase,a.baseline.resolve(),a.baseline_seal)
    hashes={str(out/n):hashlib.sha256((json.dumps(v,indent=2)+'\n').encode()).hexdigest() for n,v in values.items()}
    for n in ('combined-inputs.txt','generic-coverage-inputs.txt'):hashes[str(out/n)]=hashlib.sha256(text.encode()).hexdigest()
    proposal=dict(schema='AKV_CANONICAL_KFAULT_HISTORICAL%d_ADMISSION_V1'%(790+a.phase),
        output=str(out),baseline=str(a.baseline.resolve()),baseline_seal=a.baseline_seal,
        qualification=str(QUALS[a.phase]),qualification_seal=QUAL_SHAS[a.phase],
        input_pins=values['evidence-pins.json'],output_pins=hashes,coverage_admitted=False)
    sidecar=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':life.save(sidecar,proposal);print('PREPARED_NOT_ADMITTED',life.digest(sidecar));return
    need(life.read_bound(sidecar,a.seal)==proposal, 'Prepared admission drift')
    if a.mode=='verify':print('PREPARED_VERIFY_PASS_NO_ADMISSION');return
    out.mkdir()
    for n,v in values.items():life.save(out/n,v)
    for n in ('combined-inputs.txt','generic-coverage-inputs.txt'):
        with (out/n).open('x') as f:f.write(text)
    life.check(proposal['input_pins']);life.check(hashes)
    life.save(out/'admission-manifest.json',dict(proposal,coverage_admitted=True,prepared=str(sidecar),prepared_seal=a.seal,
        authorization_source='EXPLICIT_PARENT_ADMISSION_AUTHORIZATION'))
    print('ADMITTED',790+a.phase,life.digest(out/'admission-manifest.json'))

if __name__=='__main__':main()
