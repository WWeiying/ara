"""Exact formal787 + qualified entropy64; offline prepare, explicit parent publication only."""
import argparse
import hashlib
import json
from pathlib import Path

import scalar_entropy64_reviewed as case
from admit_stride_metadata768 import dedup

run, life, need = case.runner, case.life, case.need
QUAL = run.OUT/'scalar-entropy64-qualified786-parent-20261008-01'
Q_SHA = '797b412536fc0235cb511b631a9c01db48af0793060d68366bef9879739fc0e9'
RUN = run.OUT/'scalar-entropy64-reviewed786-agent-20261008-01'
BASE = run.OUT/'csr-satp-sepc-offline-admitted787-parent-20261008-01'
PREPARED_SHA = '1f999e25e41f7501129fdcabf9e5f2f1c1c30aeb3913884aed2e5d0db597f5e8'
COUNTS = dict(line=1892,cond=2023,branch=2155,fsm=92)
GAIN_SCOPE = run.PREFIX+'.ex_stage_i.i_mult.i_div.i_lzc_b'
SCALAR = dict(matched_instructions=3326,matched_scalar_writes=1646,
              matched_floating_writes=0,matched_scalar_memory_accesses=903)


def ledger_gate(ledger,before,status,original):
    need(len(ledger) == len(set(ledger)) == 788 and ledger == [str(life.IMAGE)+'.vdb',*before['tests']] and
         ledger[:-1] == original and status['aggregate_passed'] == 787 and
         status['coverage_admitted'] is True, 'Formal787 must exactly retain frozen786 prefix')


def architecture(q,docs):
    need(q['status'] == 'SCALAR_ENTROPY64_ARCHITECTURE_AND_RAW_DIAGNOSTIC_NOT_ADMITTED' and
         q['baseline'] == 786 and q['architecture_pass'] is True and q['coverage_admitted'] is False and
         q['MDA_direction_gain_qualified'] is False and q['official_DVE_percentage'] is False and
         q['scalar_counts'] == SCALAR, 'Exact parent entropy qualification required')
    run.architecture.scalar_exact(docs['scalar-comparison.json'],SCALAR)
    native = docs['native-frame.json']
    for key,value in dict(checks=390,result_bytes=1536,memory_and_guard_bytes=512,csr_bytes=96,
                          vector_writes_expected=0).items():
        need(type(native.get(key)) is int and native[key] == value, 'Native obligation differs: '+key)
    need(native['csr_before'] == native['csr_after'] and len(native['csr_before']) == 6, 'Six CSR guards')
    initial = docs['ELF-native-initialization.json']
    need(initial['ELF_initial_zero_verified'] is True and initial['native_first_read_store_dominance'] is True and
         initial['ELF_initialization_not_assumed_to_initialize_hardware'] is True and initial['frame_reads'] == 252,
         'Native initialization/ELF first-read proof required')
    control = docs['lifecycle.json']
    need(control['requests'] == control['responses'] == 4 and control['no_vector_writes'] is True and
         control['trap_events'] == 0, 'Four readonly CSR conservation')
    typed = docs['typed-toggle.json']
    need(set(typed['new_serialized_positions']) == set(run.SCOPES) and
         all(not v for v in typed['new_serialized_positions'].values()) and typed['MDA_gain_not_counted'] is True,
         'Zero measured target binary Toggle; MDA is not measured gain')
    for scope in run.SCOPES:
        old,new = typed['before'][scope],typed['single'][scope]
        need((old['width'],old['checksum']) == (new['width'],new['checksum']) and
             int(new['bits'],16)&~int(old['bits'],16) == 0, 'Candidate not subset of previous target Toggle')
    delta = docs['raw-delta.json']
    need(delta['metrics'] == dict(line=0,cond=7,branch=0,fsm=0) and len(delta['instances']) == 1 and
         delta['instances'][0]['instance'] == GAIN_SCOPE and delta['instances'][0]['metric'] == 'cond' and
         delta['instances'][0]['new_bits'] == 7, 'Exact original divider LZC gain')


def full_union(before,single):
    need(len(before['tests']) == len(set(before['tests'])) == 787 and
         single['tests'] == [str(RUN/'code.vdb')] and single['tests'][0] not in before['tests'],
         'Exact787 plus distinct entropy VDB')
    need(before['design'] == single['design'] and set(before['metrics']) == set(single['metrics']) == set(COUNTS),
         'Compiled design/four metrics differ')
    need(all(len(before['metrics'][m]) == n for m,n in COUNTS.items()), 'Full6162 metric instances')
    life.merge_pins(before['input_hashes'],single['input_hashes'])
    after = run.bitmap.combine(before,single)
    for metric,scopes in before['metrics'].items():
        need(set(scopes) == set(single['metrics'][metric]) == set(after['metrics'][metric]), 'Metric scope set differs')
        for scope,old in scopes.items():
            new,merged = single['metrics'][metric][scope],after['metrics'][metric][scope]
            need((old['width'],old['checksum']) == (new['width'],new['checksum']) and
                 type(old['width']) is int and old['width'] >= 0, 'Native metric identity differs')
            need(int(merged['bits'],16) == int(old['bits'],16)|int(new['bits'],16) and
                 int(merged['bits'],16).bit_length() <= old['width'], 'Independent OR/bounds differs')
    need(after['tests'] == before['tests']+single['tests'] and len(set(after['tests'])) == 788, 'Exact788 append lost')
    delta = run.bitmap.delta(before,after)
    need(delta['metrics']['line'] == delta['metrics']['branch'] == delta['metrics']['fsm'] == 0 and
         0 < delta['metrics']['cond'] <= 7 and all(r['instance'] == GAIN_SCOPE and r['metric'] == 'cond'
         for r in delta['instances']), 'No positive rebased divider gain or foreign gain')
    return after,delta


def historical_elf_gate(elf,ledger,authority):
    need(elf['ledger_members'] == 787 and elf['duplicate'] is False and
         [r['vdb'] for r in elf['members']] == ledger[1:] and
         all(authority.get(p) == h for p,h in elf['pins'].items()), 'Historical-only787 ELF dedup authority')


def evaluate(base,base_sha):
    need(base == BASE and base == base.resolve(), 'Only exact parent CSR787 baseline is authorized')
    manifest = life.read_bound(base/'admission-manifest.json',base_sha)
    need(manifest['coverage_admitted'] is True and manifest['output'] == str(base) and
         manifest['baseline'] == str(run.BASE) and manifest['baseline_seal'] == run.BASE_SHA,
         'Must be admitted CSR787, not alternate786 branch')
    authority = life.merge_pins(manifest['input_pins'],manifest['output_pins'])
    def prior(name):
        return life.read_bound(base/name,manifest['output_pins'][str(base/name)])
    before,status = prior('combined-bits.json'),prior('status.json')
    ledger_path = base/'combined-inputs.txt'
    need(run.toggle.digest(ledger_path) == manifest['output_pins'][str(ledger_path)], 'Baseline ledger seal')
    ledger = ledger_path.read_text().splitlines()
    ancestor = life.read_bound(run.BASE/'admission-manifest.json',run.BASE_SHA)
    original_path = run.BASE/'combined-inputs.txt'
    need(run.toggle.digest(original_path) == ancestor['output_pins'][str(original_path)], 'Original786 ledger seal')
    ledger_gate(ledger,before,status,original_path.read_text().splitlines())
    q = life.read_bound(QUAL/'qualification.json',Q_SHA)
    run.check(q['input_pins']);run.check(q['output_pins'])
    docs = {Path(p).name:life.read_bound(Path(p),h) for p,h in q['output_pins'].items() if p.endswith('.json')}
    architecture(q,docs)
    pins = life.merge_pins(authority,life.merge_pins(q['input_pins'],q['output_pins']))
    prepared = Path(str(RUN)+'.prepared.json')
    runtime = life.read_bound(prepared,PREPARED_SHA)
    case.verify_receipt(RUN,runtime)
    identity = case.read_native_identity(RUN,runtime)
    need(identity == docs['native-runtime-identity.json'] and
         json.loads((RUN/'manifest.json').read_bytes()) == runtime, 'Actual executed/native identity differs')
    case.collector.terminal(json.loads((RUN/'simulation-status.json').read_bytes()))
    db = RUN/'code.vdb'
    need(not any(p.is_symlink() for p in db.rglob('*')) and {str(p) for p in db.rglob('*') if p.is_file()} ==
         {p for p in q['input_pins'] if p.startswith(str(db)+'/')}, 'Complete immutable singleton VDB')
    native = db/'snps/coverage/db/testdata/scalar_entropy64'
    design = Path(ledger[0])/'snps/coverage/db'
    need(all(run.toggle.digest(design/rel) == h == pins[str(design/rel)] for rel,h in before['design'].items()),
         'Frozen design fingerprint mismatch')
    single = dict(design=before['design'],tests=[str(db)],input_hashes={},metrics={})
    for metric in run.bitmap.METRICS:
        path = native/(metric+'.verilog.data.xml')
        need(run.toggle.digest(path) == pins[str(path)], 'Native data seal differs')
        single['metrics'][metric] = run.bitmap.read_metric(path)
        single['input_hashes'][str(path)] = pins[str(path)]
    # collect() records additional design/data inputs; require every such hash,
    # while comparing metric contents independently from freshly read native XML.
    sealed = docs['single-bits.json']
    need(single['design'] == sealed['design'] and single['tests'] == sealed['tests'] and
         single['metrics'] == sealed['metrics'] and all(pins.get(p) == h for p,h in sealed['input_hashes'].items()),
         'Qualified singleton/native contents differ')
    single['input_hashes'] = sealed['input_hashes']
    after,delta = full_union(before,single)
    elf_sha = pins[str(run.PRE/'input.elf')]
    elf = dedup(ledger,elf_sha,authority)
    historical_elf_gate(elf,ledger,authority)
    pins = life.merge_pins(pins,elf['pins'])
    fixed = {str(base/'admission-manifest.json'):base_sha,str(QUAL/'qualification.json'):Q_SHA,
             str(prepared):PREPARED_SHA,str(run.BASE/'admission-manifest.json'):run.BASE_SHA}
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_scalar_entropy788.py'),
                 Path(dedup.__code__.co_filename).resolve()):
        fixed[str(path)] = run.toggle.digest(path)
    pins = life.merge_pins(pins,fixed)
    run.check(pins)
    products = {Path(p).name:prior(Path(p).name) for p in manifest['output_pins']
                if Path(p).parent == base and p.endswith('.json') and
                ('toggle-gain' in Path(p).name or Path(p).name.startswith('retained-'))}
    products.update({'single-bits.json':single,'combined-bits.json':after,'raw-delta.json':delta,
        'scalar-entropy-runtime-identity.json':identity,'elf-ledger-dedup.json':dict(elf,baseline=787),
        'scalar-entropy-target-toggle-diagnostic.json':docs['typed-toggle.json'],'evidence-pins.json':pins,
        'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',baseline=787,aggregate_passed=788,
            new_passed=1,coverage_admitted=True,exact787_prefix=True,unique_new_vdb=True,duplicate_ELF=False,
            full_OR_metric_instances=6162,raw_delta=delta['metrics'],qualification_seal=Q_SHA,
            scalar_counts=SCALAR,software_checks=390,measured_target_binary_Toggle_gain=0,
            MDA_direction_gain_qualified=False,official_percentage_claimed=False,RTL_changed=False,new_simulation=False,
            similar_regfile_entropy_campaign_stopped=True)})
    return products,'\n'.join([ledger[0],*after['tests']])+'\n'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','verify','admit'))
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--baseline-seal',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seal')
    p.add_argument('--parent-authorized',action='store_true')
    a = p.parse_args()
    need(a.parent_authorized == (a.mode == 'admit') and bool(a.seal) == (a.mode != 'prepare'),
         'Explicit reviewed publication only')
    out = a.output.absolute()
    need(out.parent == run.OUT and out == out.resolve() and not out.exists(), 'Fresh direct output required')
    products,text = evaluate(a.baseline.absolute(),a.baseline_seal)
    hashes = {str(out/n):hashlib.sha256((json.dumps(v,indent=2)+'\n').encode()).hexdigest() for n,v in products.items()}
    for name in ('combined-inputs.txt','generic-coverage-inputs.txt'):
        hashes[str(out/name)] = hashlib.sha256(text.encode()).hexdigest()
    proposal = dict(output=str(out),baseline=str(a.baseline.absolute()),baseline_seal=a.baseline_seal,
        qualification=str(QUAL/'qualification.json'),qualification_seal=Q_SHA,
        input_pins=products['evidence-pins.json'],output_pins=hashes,coverage_admitted=False)
    record = Path(str(out)+'.prepared.json')
    if a.mode == 'prepare':
        need(not record.exists(),'Preserve previous preparation')
        life.save(record,proposal)
        print('PREPARED788_NOT_ADMITTED',run.toggle.digest(record))
        return
    need(life.read_bound(record,a.seal) == proposal,'Exact reviewed788 equality')
    if a.mode == 'verify':
        print('VERIFY_PASS_NO_ADMISSION')
        return
    out.mkdir()
    for name,value in products.items():
        life.save(out/name,value)
    for name in ('combined-inputs.txt','generic-coverage-inputs.txt'):
        with (out/name).open('x') as stream:
            stream.write(text)
    run.check(proposal['input_pins']);run.check(hashes)
    life.save(out/'admission-manifest.json',dict(proposal,coverage_admitted=True,
        prepared=str(record),prepared_seal=a.seal,authorization_source='PARENT_EXPLICIT_AUTHORIZATION'))
    print('ADMITTED788',run.toggle.digest(out/'admission-manifest.json'))


if __name__ == '__main__':
    main()
