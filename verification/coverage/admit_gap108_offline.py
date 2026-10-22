"""Exact formal729 + externally sealed qualified GAP108 candidate; explicit offline730."""
import argparse
import hashlib
import json
from pathlib import Path

import prepare_gap108_raw_gain as candidate

life, require = candidate.life, candidate.require
BASE, BASE_SEAL = candidate.BASE, candidate.BASE_SEAL
PRIOR = life.OUT/'fence-t-u-padding-offline-admitted-728-parent-20261006-01'
PRIOR_SEAL = 'db371b3e126a4739117de8501daab2c149306acf0e4446b3eb64d69c65ec6add'
CONFIG, CONFIG_SEAL = candidate.CONFIG, candidate.CONFIG_SEAL

PRODUCTS = {'single-inputs.txt','single-bits.json','combined-bits.json','raw-delta.json',
            'gained-compiled-points.json','target-hits.json','evidence-pins.json'}
SCHEMA = 'GAP108_HISTORICAL730_SOFTWARE_NATIVE_ADMISSION_V1'


def candidate_contract(record, directory, qualification_seal):
    candidate.seal_contract(qualification_seal)
    require(directory.parent == life.OUT and directory.resolve() == directory, 'Direct candidate required')
    candidate.qualifier.runner.exact(record,dict(status='GAP108_EXPLICIT_BASE_PLUS_ONE_CANDIDATE_NOT_ADMITTED',
        baseline=str(BASE),baseline_seal=BASE_SEAL,
        qualification=str(candidate.QUAL),qualification_seal=qualification_seal,baseline_population=729,proposed_population=730,
        config=str(CONFIG),config_seal=CONFIG_SEAL,exact_baseline_prefix=True,coverage_admitted=False,full_scalar_isa_verified=False,
        spike_custom_isa_pass=False,rtl_changed=False,simulations_started=False,
        ), 'Exact qualified candidate differs')
    delta = record['raw_delta']
    require(set(delta) == {'line','cond','branch','fsm'} and all(type(v) is int and v >= 0 for v in delta.values()) and
            sum(delta.values()) > 0, 'No valid measured product gain')
    require(set(record['output_pins'])=={str(directory/n) for n in PRODUCTS},
            'Incomplete/foreign candidate products')


def evaluate(base_seal, qualification_seal, candidate_seal, directory):
    require(base_seal == BASE_SEAL, 'Only authoritative729 allowed')
    candidate.seal_contract(qualification_seal); candidate.seal_contract(candidate_seal)
    directory = Path(directory).absolute()
    require(directory.parent == life.OUT and directory.resolve() == directory, 'Direct candidate required')
    pins = {}
    def expected(path, seal):
        nonlocal pins
        path = Path(path)
        require(path.is_absolute() and path.resolve()==path and not path.is_symlink(), 'Aliased evidence')
        pins = life.merge_pins(pins,{str(path):seal})
        return life.read_bound(path,seal)
    def read(path):
        require(str(path) in pins, 'Missing expected pin: '+str(path))
        life.check({str(path):pins[str(path)]})
        return Path(path).read_bytes()
    record = expected(directory/'candidate.json',candidate_seal)
    candidate_contract(record, directory, qualification_seal)
    delta = record['raw_delta']
    pins = life.merge_pins(pins,record['output_pins'])
    pins = life.merge_pins(pins,json.loads(read(directory/'evidence-pins.json')))
    qualification = expected(candidate.QUAL/'qualification.json',qualification_seal)
    audit = expected(candidate.QUAL/'runtime-audit.json',qualification['audit_sha256'])
    candidate.qualification_contract(qualification,audit)
    qpins = expected(candidate.QUAL/'evidence-pins.json',qualification['pins_sha256'])
    require(life.merge_pins(pins,qpins)==pins, 'Candidate dropped qualification pins')
    config = expected(CONFIG,CONFIG_SEAL)
    require(config['status']=='GAP108_NATIVE_PREPARED_NOT_COLLECTED' and
            life.merge_pins(pins,config['pins'])==pins and config['run']==str(candidate.qualifier.RUN) and
            config['run_prepared_seal']==candidate.qualifier.RUN_SEAL, 'Prepared original run differs')
    manifest = expected(BASE/'admission-manifest.json',base_seal)
    require(manifest['schema']=='GAP107_HISTORICAL729_SOFTWARE_NATIVE_ADMISSION_V1' and
            manifest['output']==str(BASE) and manifest['baseline']==str(PRIOR) and
            manifest['baseline_seal']==PRIOR_SEAL and
            all(Path(p).parent==BASE for p in manifest['output_pins']), 'Wrong authoritative729')
    pins = life.merge_pins(pins,manifest['output_pins'])
    pins = life.merge_pins(pins,json.loads(read(BASE/'evidence-pins.json')))
    status = json.loads(read(BASE/'status.json'))
    require(status['status']=='PASS_RAW_UNION_HISTORICAL_ONLY' and status['coverage_admitted'] is True and
            status['aggregate_passed']==729 and status['new_passed']==1, 'Not formally admitted729')
    previous = expected(PRIOR/'admission-manifest.json',PRIOR_SEAL)
    prior = expected(PRIOR/'combined-bits.json',previous['output_pins'][str(PRIOR/'combined-bits.json')])
    before = json.loads(read(BASE/'combined-bits.json'))
    require(read(BASE/'combined-inputs.txt').decode().splitlines()==[str(candidate.DESIGN),*before['tests']],
            'Baseline design/input order differs')
    require(len(prior['tests']) == len(set(prior['tests'])) == 728 and before['tests'][:728] == prior['tests'] and
            before['design'] == prior['design'], 'Exact prior728 prefix differs')
    life.merge_pins(before['input_hashes'], prior['input_hashes'])
    require(candidate.baseline_contract(manifest,status,before,before,BASE)==729,
            'Exact formal729 population differs')
    single = json.loads(read(directory/'single-bits.json'))
    require(read(directory/'single-inputs.txt').decode().splitlines()==
            [str(candidate.DESIGN),str(candidate.qualifier.RUN/'code.vdb')], 'Singleton design/input differs')
    require(all(p in pins and pins[p]==h for p,h in single['input_hashes'].items()), 'Lost singleton raw pins')
    for path in (Path(candidate.__file__).resolve(),Path(candidate.qualifier.__file__).resolve(),
                 Path(candidate.bitmap.__file__).resolve(),Path(candidate.inventory.__file__).resolve()):
        require(str(path) in pins, 'Unbound reused helper')
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_gap108_offline.py')):
        pins = life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    run = candidate.qualifier.RUN
    prepared = expected(run.with_name(run.name+'.prepared.json'),candidate.qualifier.RUN_SEAL)
    require(json.loads(read(run/'manifest.json'))==prepared and prepared['old_image_files_checked']==66 and
            prepared['command']==candidate.qualifier.runner.command(run) and
            prepared['timeout_s']==600 and prepared['preflight']['expected_csr_fflags']==[8,11], 'Fixed original image/ELF run differs')
    terminal = json.loads(read(run/'simulation-status.json'))
    require(terminal['status']=='SIMULATION_EXITED_NOT_ADMITTED' and type(terminal['returncode']) is int and terminal['returncode']==0 and
            terminal['coverage_admitted'] is False, 'Not clean terminal runtime')
    symbols,data,sites = candidate.qualifier.elf_view()
    replay = candidate.qualifier.runtime(run,symbols,data,sites,candidate.qualifier.independent_native())
    require(replay==audit, 'Complete software/native replay differs')
    combined,change = candidate.population(before,single)
    require(change['metrics']==delta and combined==json.loads(read(directory/'combined-bits.json')) and
            change==json.loads(read(directory/'raw-delta.json')), 'Actual729 union/delta differs')
    pre = expected(candidate.qualifier.runner.PRE/'target-static-contract.json',candidate.qualifier.runner.TARGET_SEAL)
    gained,targets = candidate.compiled(before,single,combined,pre,read)
    require(gained==json.loads(read(directory/'gained-compiled-points.json')) and
            targets==json.loads(read(directory/'target-hits.json')) and len(gained)==sum(delta.values()) and
            len(targets)==7 and all(not t['before_hit'] and t['single_hit'] and t['after_hit'] for t in targets),
            'Exact gained/native targets differ')
    life.check(pins)
    outputs = {'combined-bits.json':combined,'single-bits.json':single,'raw-delta.json':change,
        'gained-compiled-points.json':gained,'target-hits.json':targets,'native-runtime-audit.json':replay,
        'evidence-pins.json':pins,'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',
            baseline=729,aggregate_passed=730,new_passed=1,coverage_admitted=True,exact729_prefix=True,
            qualification_seal=qualification_seal,candidate_seal=candidate_seal,raw_delta=delta,
            gained_compiled_points=len(gained),targets_hit=7,full_scalar_isa_verified=False,spike_custom_isa_pass=False,
            complete_software_native_qualified=True,whole_VRF_CSR_source_guards_qualified=True,
            checks=41,custom_commands=2,custom_active_write_bytes=8,custom_write_bytes=256,
            singleton_bitmap_recollected=False,inherited729_replayed=False,inherited729_pins_rechecked=True,
            historical_old_image_only=True,official_DVE_report=False,rtl_changed=False,simulations_started=False)}
    return outputs,'\n'.join([str(candidate.DESIGN),*combined['tests']])+'\n'


def fingerprints(output, outputs, text):
    pins = {str(output/n):hashlib.sha256((json.dumps(v,indent=2)+'\n').encode()).hexdigest()
            for n,v in outputs.items()}
    pins[str(output/'combined-inputs.txt')] = hashlib.sha256(text.encode()).hexdigest()
    return pins


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','admit','verify'))
    parser.add_argument('--base-seal',required=True);parser.add_argument('--qualification-seal',required=True)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--candidate-seal',required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seal');args = parser.parse_args(argv)
    directory = args.candidate.absolute()
    output = args.output.absolute();record = output.with_name(output.name+'.prepared.json')
    require(output.parent==life.OUT and output.resolve()==output, 'Direct independent output required')
    require((args.mode!='prepare')==bool(args.seal), 'Admit/verify require external seal')
    manifest = None
    if args.mode=='verify':
        manifest = life.read_bound(output/'admission-manifest.json',args.seal)
        require(manifest['schema']==SCHEMA and manifest['output']==str(output) and
                manifest['baseline']==str(BASE) and manifest['qualification']==str(candidate.QUAL) and
                manifest['candidate']==str(directory) and
                manifest['baseline_seal']==args.base_seal and manifest['qualification_seal']==args.qualification_seal and
                manifest['candidate_seal']==args.candidate_seal, 'Formal730 identity differs')
        require(all(Path(p).parent==output for p in manifest['output_pins']), 'Foreign output')
        life.check(manifest['output_pins'])
    else:
        require(not output.exists(), 'Fresh output required')
        if args.mode=='prepare':require(not record.exists(), 'Fresh prepared record required')
    outputs,text = evaluate(args.base_seal,args.qualification_seal,args.candidate_seal,directory)
    hashes = fingerprints(output,outputs,text)
    if args.mode=='verify':
        require(hashes==manifest['output_pins'], 'Formal products differ from strict replay')
        print('GAP108_HISTORICAL730_SOFTWARE_NATIVE_OFFLINE_REVERIFIED '+args.seal);return
    proposal = dict(schema='GAP108_HISTORICAL730_PREPARED_V1',output=str(output),
        baseline=str(BASE),baseline_seal=args.base_seal,qualification=str(candidate.QUAL),
        qualification_seal=args.qualification_seal,candidate=str(directory),candidate_seal=args.candidate_seal,
        input_pins=outputs['evidence-pins.json'],output_pins=hashes,raw_delta=outputs['raw-delta.json']['metrics'],
        full_scalar_isa_verified=False,spike_custom_isa_pass=False)
    if args.mode=='prepare':
        life.save(record,proposal);print(json.dumps(dict(prepared=str(record),seal=life.digest(record))));return
    require(life.read_bound(record,args.seal)==proposal, 'Reviewed730 proposal differs')
    require(not output.exists(), 'Output appeared during replay');output.mkdir()
    for n,v in outputs.items():life.save(output/n,v)
    with (output/'combined-inputs.txt').open('x') as stream:stream.write(text)
    life.check(outputs['evidence-pins.json']);life.check(hashes)
    life.save(output/'admission-manifest.json',dict(schema=SCHEMA,output=str(output),baseline=str(BASE),
        baseline_seal=args.base_seal,qualification=str(candidate.QUAL),qualification_seal=args.qualification_seal,
        candidate=str(directory),candidate_seal=args.candidate_seal,prepared=str(record),prepared_seal=args.seal,
        output_pins=hashes))
    print(json.dumps(dict(output=str(output),seal=life.digest(output/'admission-manifest.json'))))


if __name__=='__main__':main()
