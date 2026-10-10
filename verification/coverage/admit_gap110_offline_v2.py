"""Exact formal733 + reviewed GAP110 native/raw candidate; explicit offline734 only."""
import argparse
import hashlib
import json
from pathlib import Path

import prepare_gap110_raw_gain_v2 as candidate

life, require = candidate.life, candidate.require
BASE, BASE_SEAL = candidate.BASE, candidate.BASE_SEAL
PRIOR = life.OUT/'gap109-offline-admitted-732-parent-20261006-01'
PRIOR_SEAL = 'badbcc7aad21ce6dab6c8c0eeabc7f85b2c13226bbe893a56c88995eab149794'
CONFIG = candidate.CONFIG
CANDIDATE = life.OUT/'gap110-raw-gain-v2-733-parent-20261006-01'

PRODUCTS = {'single-inputs.txt','single-bits.json','combined-bits.json','raw-delta.json',
            'gained-compiled-points.json','target-hits.json','evidence-pins.json'}
SCHEMA = 'GAP110_HISTORICAL734_SOFTWARE_NATIVE_ADMISSION_V1'


def candidate_contract(record, directory, qualification_seal, config_seal):
    candidate.seal_contract(qualification_seal);candidate.seal_contract(config_seal)
    require(qualification_seal==candidate.QUAL_SEAL and config_seal==candidate.CONFIG_SEAL,
            'Only actual parent v2 qualification/config allowed')
    require(directory == CANDIDATE and directory.parent == life.OUT and directory.resolve() == directory, 'Direct candidate required')
    candidate.qualifier.runner.exact(record,dict(status='GAP110_EXPLICIT_BASE_PLUS_ONE_CANDIDATE_NOT_ADMITTED',
        baseline=str(BASE),baseline_seal=BASE_SEAL,
        qualification=str(candidate.QUAL),qualification_seal=qualification_seal,baseline_population=733,proposed_population=734,
        config=str(CONFIG),config_seal=config_seal,exact_baseline_prefix=True,coverage_admitted=False,full_scalar_isa_verified=False,
        spike_custom_isa_pass=False,rtl_changed=False,simulations_started=False,
        ), 'Exact qualified candidate differs')
    delta = record['raw_delta']
    require(set(delta) == {'line','cond','branch','fsm'} and all(type(v) is int and v >= 0 for v in delta.values()) and
            sum(delta.values()) > 0, 'No valid measured product gain')
    require(set(record['output_pins'])=={str(directory/n) for n in PRODUCTS},
            'Incomplete/foreign candidate products')


def singleton_contract(pins,record,directory):
    require(pins.get(str(candidate.SAVED_SINGLE))==candidate.SAVED_SHA and
            record['output_pins'].get(str(directory/'single-bits.json'))==candidate.SAVED_SHA,
            'Not exact preserved failed-attempt singleton')


def evaluate(base_seal, qualification_seal, candidate_seal, directory, config_seal):
    require(base_seal == BASE_SEAL and qualification_seal==candidate.QUAL_SEAL and
            config_seal==candidate.CONFIG_SEAL,
            'Only authoritative733 / reviewed parent qualification allowed')
    candidate.seal_contract(qualification_seal); candidate.seal_contract(candidate_seal)
    directory = Path(directory).absolute()
    require(directory == CANDIDATE and directory.parent == life.OUT and directory.resolve() == directory, 'Direct candidate required')
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
    candidate_contract(record, directory, qualification_seal, config_seal)
    delta = record['raw_delta']
    pins = life.merge_pins(pins,record['output_pins'])
    pins = life.merge_pins(pins,json.loads(read(directory/'evidence-pins.json')))
    qualification = expected(candidate.QUAL/'qualification.json',qualification_seal)
    audit = expected(candidate.QUAL/'runtime-audit.json',qualification['audit_sha256'])
    candidate.qualification_contract(qualification,audit)
    qpins = expected(candidate.QUAL/'evidence-pins.json',qualification['pins_sha256'])
    require(life.merge_pins(pins,qpins)==pins, 'Candidate dropped qualification pins')
    config = expected(CONFIG,config_seal)
    require(config['status']=='GAP110_NATIVE_PREPARED_NOT_COLLECTED' and
            life.merge_pins(pins,config['pins'])==pins and config['run']==str(candidate.qualifier.RUN) and
            config['run_prepared_seal']==candidate.qualifier.RUN_SEAL and
            config['run_pid']==candidate.qualifier.RUN_PID and config['expected_external_request_count'] is None, 'Prepared original run differs')
    manifest = expected(BASE/'admission-manifest.json',base_seal)
    require(manifest['schema']=='STORE_FAULT_FLUSH_HISTORICAL_ADMISSION_V1' and
            manifest['output']==str(BASE) and manifest['baseline']==str(PRIOR) and
            manifest['baseline_seal']==PRIOR_SEAL and
            all(Path(p).parent==BASE for p in manifest['output_pins']), 'Wrong authoritative733')
    pins = life.merge_pins(pins,manifest['output_pins'])
    pins = life.merge_pins(pins,json.loads(read(BASE/'evidence-pins.json')))
    status = json.loads(read(BASE/'status.json'))
    require(status['status']=='PASS_RAW_UNION_HISTORICAL_ONLY' and status['coverage_admitted'] is True and
            status['aggregate_passed']==733 and status['new_passed']==1, 'Not formally admitted733')
    previous = expected(PRIOR/'admission-manifest.json',PRIOR_SEAL)
    prior = expected(PRIOR/'combined-bits.json',previous['output_pins'][str(PRIOR/'combined-bits.json')])
    before = json.loads(read(BASE/'combined-bits.json'))
    require(read(BASE/'combined-inputs.txt').decode().splitlines()==[str(candidate.DESIGN),*before['tests']],
            'Baseline design/input order differs')
    require(len(prior['tests']) == len(set(prior['tests'])) == 732 and before['tests'][:732] == prior['tests'] and
            before['design'] == prior['design'], 'Exact prior732 prefix differs')
    life.merge_pins(before['input_hashes'], prior['input_hashes'])
    require(candidate.baseline_contract(manifest,status,before,prior,BASE)==733,
            'Exact formal733 population differs')
    singleton_contract(pins,record,directory)
    expected(candidate.SAVED_SINGLE,candidate.SAVED_SHA)
    single = json.loads(read(directory/'single-bits.json'))
    require(read(directory/'single-inputs.txt').decode().splitlines()==
            [str(candidate.DESIGN),str(candidate.qualifier.RUN/'code.vdb')], 'Singleton design/input differs')
    require(all(p in pins and pins[p]==h for p,h in single['input_hashes'].items()), 'Lost singleton raw pins')
    for path in (Path(candidate.__file__).resolve(),Path(candidate.qualifier.__file__).resolve(),
                 Path(candidate.bitmap.__file__).resolve(),Path(candidate.inventory.__file__).resolve()):
        require(str(path) in pins, 'Unbound reused helper')
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_gap110_offline_v2.py')):
        pins = life.merge_pins(pins,{str(path):life.digest(path)})
    pins=life.merge_pins(pins,{
        str(Path(__file__).with_name('admit_gap110_offline.py')):'864e43fa5729ed67c415152006e814d5da6fc995d88ee63f1ff6d4f8315ea9b6',
        str(Path(__file__).with_name('test_admit_gap110_offline.py')):'1ca14e2864612df56c25567e45d511f334e9e9ea55cb180526fbf1c80c169ce2'})
    life.check(pins)
    run = candidate.qualifier.RUN
    prepared = expected(run.with_name(run.name+'.prepared.json'),candidate.qualifier.RUN_SEAL)
    require(json.loads(read(run/'manifest.json'))==prepared and prepared['old_image_files_checked']==66 and
            prepared['command']==candidate.qualifier.runner.command(run) and
            prepared['timeout_s']==600 and prepared['preflight']['expected_csr_fflags']==[8,8] and
            prepared['expected_backend_vl']==[160,160] and prepared['expected_software_vl']==[7,5] and
            prepared['expected_active_output_bytes']==[140,100] and prepared['preflight_files_checked']==298 and prepared['expected_external_request_count'] is None, 'Fixed original image/ELF run differs')
    terminal = json.loads(read(run/'simulation-status.json'))
    require(terminal['status']=='SIMULATION_EXITED_NOT_ADMITTED' and type(terminal['returncode']) is int and terminal['returncode']==0 and
            terminal['coverage_admitted'] is False, 'Not clean terminal runtime')
    started = json.loads(read(run/'started.json'))
    require(started['pid']==candidate.qualifier.RUN_PID and type(started['pid']) is int and
            started['command']==candidate.qualifier.runner.command(run) and started['budget_s']==600 and
            started['input_elf']==str(candidate.qualifier.runner.ELF) and
            started['elf_sha256']==candidate.qualifier.runner.ELF_SEAL and
            started['image']==str(life.IMAGE) and started['image_sha256']==candidate.qualifier.runner.IMAGE_SEAL,
            'Exact original launch differs')
    symbols,data,sites = candidate.qualifier.elf_view()
    replay = candidate.qualifier.runtime(run,symbols,data,sites,candidate.qualifier.independent_native())
    require(replay==audit, 'Complete software/native replay differs')
    combined,change = candidate.population(before,single)
    require(change['metrics']==delta and combined==json.loads(read(directory/'combined-bits.json')) and
            change==json.loads(read(directory/'raw-delta.json')), 'Actual733 union/delta differs')
    pre = expected(candidate.qualifier.runner.PRE/'target-static-contract.json',candidate.qualifier.runner.TARGET_SEAL)
    gained,targets = candidate.compiled(before,single,combined,pre,read)
    require(gained==json.loads(read(directory/'gained-compiled-points.json')) and
            targets==json.loads(read(directory/'target-hits.json')) and len(gained)==sum(delta.values()) and
            len(targets)==26 and all(not t['before_hit'] and t['single_hit'] and t['after_hit'] for t in targets),
            'Exact gained/native targets differ')
    life.check(pins)
    outputs = {'combined-bits.json':combined,'single-bits.json':single,'raw-delta.json':change,
        'gained-compiled-points.json':gained,'target-hits.json':targets,'native-runtime-audit.json':replay,
        'evidence-pins.json':pins,'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',
            baseline=733,aggregate_passed=734,new_passed=1,coverage_admitted=True,exact733_prefix=True,
            qualification_seal=qualification_seal,candidate_seal=candidate_seal,raw_delta=delta,
            gained_compiled_points=len(gained),targets_hit=26,full_scalar_isa_verified=False,spike_custom_isa_pass=False,
            complete_software_native_qualified=True,whole_VRF_CSR_source_guards_qualified=True,
            checks=41,custom_commands=2,custom_active_write_bytes=240,custom_write_bytes=240,custom_preserved_vrf_bytes=7952,
            singleton_bitmap_recollected=False,inherited733_replayed=False,inherited733_pins_rechecked=True,
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
    parser.add_argument('--config-seal',required=True)
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
                manifest['candidate_seal']==args.candidate_seal and manifest['config_seal']==args.config_seal, 'Formal734 identity differs')
        require(all(Path(p).parent==output for p in manifest['output_pins']), 'Foreign output')
        life.check(manifest['output_pins'])
    else:
        require(not output.exists(), 'Fresh output required')
        if args.mode=='prepare':require(not record.exists(), 'Fresh prepared record required')
    outputs,text = evaluate(args.base_seal,args.qualification_seal,args.candidate_seal,directory,args.config_seal)
    hashes = fingerprints(output,outputs,text)
    if args.mode=='verify':
        require(hashes==manifest['output_pins'], 'Formal products differ from strict replay')
        print('GAP110_HISTORICAL734_SOFTWARE_NATIVE_OFFLINE_REVERIFIED '+args.seal);return
    proposal = dict(schema='GAP110_HISTORICAL734_PREPARED_V1',output=str(output),
        baseline=str(BASE),baseline_seal=args.base_seal,qualification=str(candidate.QUAL),
        qualification_seal=args.qualification_seal,config_seal=args.config_seal,candidate=str(directory),candidate_seal=args.candidate_seal,
        input_pins=outputs['evidence-pins.json'],output_pins=hashes,raw_delta=outputs['raw-delta.json']['metrics'],
        full_scalar_isa_verified=False,spike_custom_isa_pass=False)
    if args.mode=='prepare':
        life.save(record,proposal);print(json.dumps(dict(prepared=str(record),seal=life.digest(record))));return
    require(life.read_bound(record,args.seal)==proposal, 'Reviewed734 proposal differs')
    require(not output.exists(), 'Output appeared during replay');output.mkdir()
    for n,v in outputs.items():life.save(output/n,v)
    with (output/'combined-inputs.txt').open('x') as stream:stream.write(text)
    life.check(outputs['evidence-pins.json']);life.check(hashes)
    life.save(output/'admission-manifest.json',dict(schema=SCHEMA,output=str(output),baseline=str(BASE),
        baseline_seal=args.base_seal,qualification=str(candidate.QUAL),qualification_seal=args.qualification_seal,
        config_seal=args.config_seal,candidate=str(directory),candidate_seal=args.candidate_seal,prepared=str(record),prepared_seal=args.seal,
        output_pins=hashes))
    print(json.dumps(dict(output=str(output),seal=life.digest(output/'admission-manifest.json'))))


if __name__=='__main__':main()



