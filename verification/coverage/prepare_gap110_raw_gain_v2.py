"""GAP110 v2 sealed compiled-input read gate; exact saved singleton, no recollect/admission."""
import argparse
import json
from pathlib import Path
from types import ModuleType

import qualify_gap110_native_v2 as qualifier
import prepare_gap109_raw_gain_v2 as mapping

life, require = qualifier.life, qualifier.require
bitmap, inventory = mapping.bitmap, mapping.inventory
DESIGN = mapping.DESIGN
QUAL = life.OUT/'gap110-native-v2-qualified-parent-20261006-01'
BASE = life.OUT/'store-fault-flush-offline-admitted-733-parent-20261006-01'
BASE_SEAL = 'ff12f5b191546e814fde60a4e71e1112e07c769ece72bdb9a0706d512ce83a81'
CONFIG = QUAL.with_name(QUAL.name+'.prepared.json')
QUAL_SEAL='de367a7367c8d5b01956da47588c8e3e8d5d493a1038eea2d5edd35feabe1404'
CONFIG_SEAL='ef748a418b36d1e8532d833b7888950dcf18451680fc71689fec60df941d70e8'
RUN_PID = qualifier.RUN_PID
SAVED_SINGLE=life.OUT/'gap110-raw-gain-733-parent-20261006-01/single-bits.json'
SAVED_SHA='9081836e52bda2f0a7c5e7508caeb0b1532a779f233676b94fb717fa758dd766'
ORIGINAL_SHA='cee6ddf097de7826f64a3427e362ad63c5396b28c2a28ca9836e44f28f223e02'
ORIGINAL_TEST_SHA='e79a7e820f8e29375ad011222103e6b4d616b800b2f7767521bbd87023040961'


def seal_contract(seal):
    require(isinstance(seal, str) and len(seal) == 64 and
            all(c in '0123456789abcdef' for c in seal), 'Explicit SHA256 seal required')
bit, native_definition, pre_scope = mapping.bit, mapping.native_definition, mapping.pre_scope


def bind_reused_helpers(pins, ancestor_book):
    # GAP109 delegates through GAP107 to GAP106 v4. 733's inventory omitted
    # the re-exporting GAP107 module; recover only required pins from sealed732.
    pending=[mapping,bitmap,inventory,qualifier]
    seen=set()
    roots=(life.ROOT/'verification/coverage',life.ROOT/'verification/ara_verify')
    while pending:
        module=pending.pop()
        name=getattr(module,'__file__',None)
        if not name:
            continue
        path=Path(name).absolute()
        if path.suffix!='.py' or not any(root in path.parents for root in roots):
            continue
        if str(path) in seen:
            continue
        seen.add(str(path))
        require(path.resolve()==path and not path.is_symlink(),'Aliased reused helper: '+str(path))
        key=str(path)
        if key in ancestor_book:
            pins=life.merge_pins(pins,{key:ancestor_book[key]})
        require(key in pins,'Unbound reused helper: '+key)
        life.check({key:pins[key]})
        pending.extend(value for value in vars(module).values() if isinstance(value,ModuleType))
    return pins

def qualification_contract(record, audit):
    qualifier.runner.exact(record, dict(status='GAP110_SOFTWARE_NATIVE_QUALIFIED_NOT_ADMITTED',
        full_scalar_isa_verified=False, spike_custom_isa_pass=False, coverage_admitted=False,
        coverage_increment_measured=False, gain_requires_latest_formal_baseline=True,
        simulation_rerun=False, rtl_changed=False), 'Qualification differs')
    qualifier.runner.exact(audit, dict(status='GAP110_COMPLETE_SOFTWARE_NATIVE_PASS_NOT_FULL_SCALAR_ISA',
        custom_write_bytes=240, custom_active_bytes=240, custom_preserved_vrf_bytes=7952,
        full_vrf_bytes=8192, initial_vrf_bytes=8192, csr_values=24, source_guard_bytes=7328,
        checks=41, full_scalar_isa_verified=False, spike_custom_isa_pass=False,
        coverage_admitted=False), 'Native audit differs')
    require([(b['phase'],b['pc'],b['backend_vl'],b['software_vl'],b['native_total_write_bytes'])
             for b in audit['bindings']]==[(0,0x8000017a,160,7,140),(1,0x80000252,160,5,100)],
            'Exact native sites differ')
    c = audit['contract']
    require(type(c['requests']) is int and c['requests']>0 and c['requests']==c['responses'] and all(c[k]==0 for k in
        ('exceptions','protocol_errors','outstanding','req_stalled','resp_stalled')),
        'Terminal native conservation differs')


    expected = [{k:v[k] for k in ('result_bits','integer_dots','fflags','n')}
                for v in qualifier.independent_native()]
    require(audit['numeric_oracles'] == expected, 'Independent GAP110 numeric audit differs')


def baseline_contract(manifest, status, before, original, base):
    require(manifest['output'] == str(base) and manifest['schema'].endswith('_ADMISSION_V1') and
            all(Path(p).parent == base for p in manifest['output_pins']),
            'Not an explicitly sealed admission output')
    count = status['aggregate_passed']
    require(type(count) is int and count == 733 and status['coverage_admitted'] is True and
            status['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY',
            'Not an admitted formal baseline')
    require(len(before['tests']) == len(set(before['tests'])) == count and
            len(original['tests']) == len(set(original['tests'])) == 732 and
            before['tests'][:732] == original['tests'], 'Formal732 ancestor prefix/population differs')
    require(before['design'] == original['design'], 'Original design differs')
    life.merge_pins(before['input_hashes'], original['input_hashes'])
    return count


def population(before, single):
    require(len(before['tests']) == len(set(before['tests'])) and
            single['tests'] == [str(qualifier.RUN/'code.vdb')] and
            single['tests'][0] not in before['tests'], 'Not unique original singleton')
    require(set(before['metrics'])=={'line','cond','branch','fsm'} and
            sum(len(rows) for rows in before['metrics'].values())==6162,
            'Exact6162 metric instances required')
    life.merge_pins(before['input_hashes'], single['input_hashes'])
    combined = bitmap.combine(before, single)
    require(combined['tests'] == before['tests'] + single['tests'] and
            len(set(combined['tests'])) == len(before['tests']) + 1, 'Exact baseline prefix differs')
    change = bitmap.delta(before, combined)
    require(sum(change['metrics'].values()) > 0, 'No fresh product gain; do not admit')
    return combined, change

def compiled_inputs(before,combined):
    require(set(before['metrics'])=={'line','cond','branch','fsm'},'Exact compiled metric set required')
    changed={metric for metric,rows in before['metrics'].items() if any(
        row['bits']!=combined['metrics'][metric][scope]['bits'] for scope,row in rows.items())}
    relatives=['design/verilog.design.xml','auxiliary/verilog.sourceinfo.xml']
    relatives += ['shape/'+metric+'.verilog.shape.xml' for metric in ('line','cond','branch','fsm','tgl')]
    relatives += ['shape/'+metric+'.verilog.info.xml' for metric in sorted(changed|{'cond','tgl'})]
    return [DESIGN/'snps/coverage/db'/relative for relative in relatives]


def bind_compiled_inputs(pins,ancestor_book,before,combined):
    db=DESIGN/'snps/coverage/db'
    for path in compiled_inputs(before,combined):
        require(path.resolve()==path and not path.is_symlink(),'Aliased compiled design input')
        key=str(path)
        if key in ancestor_book:
            pins=life.merge_pins(pins,{key:ancestor_book[key]})
        relative=str(path.relative_to(db))
        if relative in before['design']:
            pins=life.merge_pins(pins,{key:before['design'][relative]})
        require(key in pins,'Unbound compiled design input: '+key)
        life.check({key:pins[key]})
    return pins


def write_single_inputs(path):
    with Path(path).open('x') as stream:
        stream.write(str(DESIGN)+'\n'+str(qualifier.RUN/'code.vdb')+'\n')


def compiled(before, single, combined, pre, read):
    for path in compiled_inputs(before,combined):
        read(path)
    def checked_xml(path):
        read(path)
        return inventory.read_xml(path)
    db = DESIGN/'snps/coverage/db'
    design = checked_xml(db/'design/verilog.design.xml')
    nodes = {n.get('id'):(n,d) for d in design.findall('srcdef') for n in d.findall('srcinst')}
    require(len(nodes)==sum(len(d.findall('srcinst')) for d in design.findall('srcdef')), 'Duplicate hierarchy')
    def path(key, seen=()):
        require(key not in seen, 'Hierarchy cycle')
        node,_ = nodes[key]; parent = node.get('pid')
        return (path(parent,seen+(key,))+'.' if parent in nodes else '')+node.get('name')
    hierarchy = {path(k):d for k,(_,d) in nodes.items()}
    require(len(hierarchy)==len(nodes), 'Duplicate scopes')
    files = {n.get('id'):n.get('name') for n in checked_xml(
        db/'auxiliary/verilog.sourceinfo.xml').iter('fileinfo')}
    shapes = {m:checked_xml(db/('shape/'+m+'.verilog.shape.xml')) for m in before['metrics']}
    infos={}
    changed_metrics={metric for metric,rows in before['metrics'].items() if any(
        row['bits']!=combined['metrics'][metric][scope]['bits'] for scope,row in rows.items())}
    for metric in changed_metrics:
        p=db/('shape/'+metric+'.verilog.info.xml');read(p)
        infos[metric]={n.get('name'):n.get('chksum') for n in checked_xml(p).iter('instance_data')}
    tgl_info=db/'shape/tgl.verilog.info.xml';tgl_shape=db/'shape/tgl.verilog.shape.xml'
    read(tgl_info);read(tgl_shape)
    tgl_checksums={n.get('name'):n.get('chksum') for n in checked_xml(tgl_info).iter('instance_data')}
    tgl=checked_xml(tgl_shape)
    gained = []
    for metric, rows in before['metrics'].items():
        for scope,old in rows.items():
            new = combined['metrics'][metric][scope]
            changed = [r for r in range(old['width']) if not bit(old,r) and bit(new,r)]
            if not changed: continue
            tgl_definition=None
            if old['checksum'] is None and infos[metric].get(scope) is None:
                tgl_definition=inventory.definition(tgl,hierarchy[scope],tgl_checksums.get(scope))
            definition,binding = native_definition(shapes[metric],hierarchy[scope],scope,old,
                                                  infos[metric].get(scope),tgl_definition,metric)
            points = {p['raw_index']:p for p in inventory.points(metric,definition,old['width'])}
            for raw in changed:
                p = points[raw]; source = Path(files[p['file_id']])
                read(source)
                gained.append(dict(scope=scope,metric=metric,width=old['width'],checksum=old['checksum'],
                    point=p,source=str(source),compiled_definition_checksum=definition.get('chksum'),binding=binding,before_hit=False,single_hit=bit(single['metrics'][metric][scope],raw),
                    after_hit=True))
    targets = []
    require(len(pre['targets']) == 26, 'Exact GAP110 target population differs')
    seen = set()
    for target in pre['targets']:
        scope = target['scope']; raw = target['point']['raw_index']
        require(target['metric'] == 'cond' and (scope, raw) not in seen, 'Duplicate/wrong target')
        seen.add((scope, raw))
        old = before['metrics']['cond'][scope]
        require((old['width'], old['checksum']) == (target['width'], target['checksum']),
                'Target width/checksum differs')
        ci_path = db/'shape/cond.verilog.info.xml'; read(ci_path)
        ci = {n.get('name'):n.get('chksum') for n in checked_xml(ci_path).iter('instance_data')}
        td = inventory.definition(tgl, hierarchy[scope], tgl_checksums.get(scope)) if (
            old['checksum'] is None and ci.get(scope) is None) else None
        definition, binding = native_definition(shapes['cond'], hierarchy[scope], scope, old, ci.get(scope), td)
        points = {p['raw_index']:p for p in inventory.points('cond', definition, old['width'])}
        require(points[raw] == target['point'] and definition.get('chksum') ==
                target['compiled_definition_checksum'],
                'Target compiled identity differs')
        require(files[points[raw]['file_id']] == str(life.ROOT/'hardware/src/vlsu/qbs/qbs_payload_buffer.sv'),
                'Target source identity differs')
        read(Path(files[points[raw]['file_id']]))
        targets.append(dict(scope=scope, point=points[raw], before_hit=bit(old, raw),
                            single_hit=bit(single['metrics']['cond'][scope], raw),
                            after_hit=bit(combined['metrics']['cond'][scope], raw)))
    require(all(not t['before_hit'] and t['single_hit'] and t['after_hit'] for t in targets),
            'Not all26 targets freshly measured against733')
    return gained, targets


SOURCE_RELATIVE=(
    'hardware/include/qbs_pkg.sv',
    'hardware/src/vlsu/qbs/qbs_payload_buffer.sv',
    'hardware/src/vlsu/qbs/qbs_block_adapter.sv',
    'hardware/src/vlsu/qbs/qbs_compute_engine.sv',
    'hardware/src/vlsu/qbs/qbs_engine.sv',
    'hardware/src/vlsu/qbs/qbs_read_engine.sv',
    'hardware/src/vlsu/qbs/qbs_descriptor_decoder.sv',
    'hardware/src/vlsu/qbs/qbs_profile_decoder.sv',
    'hardware/src/vlsu/qbs/qbs_profile_engine_int.sv',
    'hardware/deps/fpnew/src/fpnew_fma.sv',
    'hardware/deps/fpnew/src/fpnew_classifier.sv',
    'hardware/deps/fpnew/src/fpnew_rounding.sv',
    'hardware/deps/common_cells/src/lzc.sv')


def historical_source_pin(path, build):
    path=Path(path)
    require(path in {life.ROOT/r for r in SOURCE_RELATIVE} and
            path.resolve()==path and not path.is_symlink(),
            'Not exact historical GAP110 reviewed source')
    require(str(path) in build,'Historical build lacks target source')
    return {str(path):build[str(path)]}


def prepare(output, base, baseline_seal, qualification, qualification_seal, config_path, config_seal,
            single_path=None, single_seal=None):
    output, base, qualification, config_path = [Path(p).absolute() for p in
                                               (output, base, qualification, config_path)]
    require(output.parent == life.OUT and output.resolve() == output and not output.exists(),
            'Fresh output required')
    require(base.parent == life.OUT and base.resolve() == base and
            qualification.parent == life.OUT and qualification.resolve() == qualification and
            config_path.parent == life.OUT and config_path.resolve() == config_path,
            'Evidence paths outside exact output root')
    require(single_path is not None and Path(single_path).absolute()==SAVED_SINGLE and
            single_seal==SAVED_SHA,'Only exact preserved failed-attempt singleton allowed')
    seal_contract(qualification_seal)
    require(qualification_seal==QUAL_SEAL and config_seal==CONFIG_SEAL,
            'Only actual parent v2 qualification/config allowed')
    require(base == BASE and baseline_seal == BASE_SEAL, 'Only authoritative733 allowed')
    require(qualification == QUAL, 'Only parent qualified GAP110 artifact allowed')
    seal_contract(config_seal)
    require(config_path == CONFIG, 'Only parent GAP110 qualifier config allowed')
    pins = {}
    def expected(path, seal):
        nonlocal pins
        pins = life.merge_pins(pins, {str(path):seal})
        return life.read_bound(path, seal)
    def read(path):
        nonlocal pins
        if Path(path) in {life.ROOT/r for r in SOURCE_RELATIVE}:
            build = expected(qualifier.BUILD, qualifier.BUILD_SHA)
            pins = life.merge_pins(pins, historical_source_pin(path, build))
        require(str(path) in pins, 'Unbound input: ' + str(path))
        life.check({str(path):pins[str(path)]})
        return Path(path).read_bytes()
    record = expected(qualification/'qualification.json', qualification_seal)
    audit = expected(qualification/'runtime-audit.json', record['audit_sha256'])
    qualification_contract(record, audit)
    pins = life.merge_pins(pins, expected(qualification/'evidence-pins.json', record['pins_sha256']))
    config = expected(config_path, config_seal)
    require(config['run']==str(qualifier.RUN) and config['run_prepared_seal']==qualifier.RUN_SEAL and
            config['run_pid']==RUN_PID and config['expected_backend_vl']==[160,160] and
            config['expected_software_vl']==[7,5] and config['native_bytes_per_command']==[140,100] and
            config['preserved_vrf_bytes_per_command']==[3956,3996] and
            config['gain_baseline_required']==733 and config['expected_external_request_count'] is None and
            config['status']=='GAP110_NATIVE_PREPARED_NOT_COLLECTED','Reviewed qualifier config differs')
    require(life.merge_pins(pins, config['pins']) == pins, 'Lost prepared pins')
    manifest = expected(base/'admission-manifest.json', baseline_seal)
    require(manifest['output'] == str(base) and all(Path(p).parent == base for p in manifest['output_pins']),
            'Aliased baseline outputs')
    pins = life.merge_pins(pins, manifest['output_pins'])
    pins = life.merge_pins(pins, json.loads(read(base/'evidence-pins.json')))
    status, before = [json.loads(read(base/name)) for name in ('status.json', 'combined-bits.json')]
    pre = expected(qualifier.runner.PRE/'preflight-manifest.json', qualifier.runner.PRE_SEAL)
    original_base = Path(pre['baseline'])
    require(original_base == qualifier.runner.BASE and pre['baseline_seal'] == qualifier.runner.BASE_SEAL,
            'Static original732 differs')
    original_manifest = expected(original_base/'admission-manifest.json', pre['baseline_seal'])
    original = expected(original_base/'combined-bits.json',
                        original_manifest['output_pins'][str(original_base/'combined-bits.json')])
    ancestor_book_path=original_base/'evidence-pins.json'
    ancestor_book=expected(ancestor_book_path,original_manifest['output_pins'][str(ancestor_book_path)])
    for name in ('gap108-offline-admitted-730-parent-20261006-01',
                 'gap106-offline-admitted-727-parent-20261006-01'):
        path=life.OUT/name/'evidence-pins.json'
        require(str(path) in ancestor_book,'Missing sealed mapping ancestor book: '+str(path))
        ancestor_book=life.merge_pins(ancestor_book,expected(path,ancestor_book[str(path)]))
    count = baseline_contract(manifest, status, before, original, base)
    require(read(base/'combined-inputs.txt').decode().splitlines() == [str(DESIGN), *before['tests']],
            'Exact formal design/input order differs')
    pins = life.merge_pins(pins, before['input_hashes'])
    pins = life.merge_pins(pins, {str(DESIGN/'snps/coverage/db'/p):h for p,h in before['design'].items()})
    targets = expected(qualifier.runner.PRE/'target-static-contract.json', qualifier.runner.TARGET_SEAL)
    pins = life.merge_pins(pins, targets['pins'])
    pins=bind_reused_helpers(pins,ancestor_book)
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_prepare_gap110_raw_gain_v2.py')):
        pins = life.merge_pins(pins, {str(path):life.digest(path)})
    pins=life.merge_pins(pins,{
        str(Path(__file__).with_name('prepare_gap110_raw_gain.py')):ORIGINAL_SHA,
        str(Path(__file__).with_name('test_prepare_gap110_raw_gain.py')):ORIGINAL_TEST_SHA})
    life.check(pins)
    symbols, data, sites = qualifier.elf_view()
    require(qualifier.runtime(qualifier.RUN, symbols, data, sites, qualifier.independent_native()) == audit,
            'Actual qualified runtime replay differs')
    # Complete compiled verification precedes output creation. Never recollect VDB.
    try:
        single=expected(SAVED_SINGLE,SAVED_SHA)
        require(all(p in pins and pins[p]==h for p,h in single['input_hashes'].items()),
                'Singleton differs from qualified raw pins')
        pins=life.merge_pins(pins,single['input_hashes'])
        combined,change=population(before,single)
        pins=bind_compiled_inputs(pins,ancestor_book,before,combined)
        gained,hits=compiled(before,single,combined,targets,read)
        require(len(gained)==sum(change['metrics'].values()),'Compiled gain ledger incomplete')
        life.check(pins)
        output.mkdir()
        inputs=output/'single-inputs.txt'
        write_single_inputs(inputs)
        life.save(output/'single-bits.json',single)
        products = dict(combined_bits=combined, raw_delta=change,
                        gained_compiled_points=gained, target_hits=hits, evidence_pins=pins)
        for name,value in products.items():
            life.save(output/(name.replace('_','-')+'.json'), value)
        life.save(output/'candidate.json', dict(status='GAP110_EXPLICIT_BASE_PLUS_ONE_CANDIDATE_NOT_ADMITTED',
            baseline=str(base), baseline_seal=baseline_seal, baseline_population=count,
            qualification=str(qualification), qualification_seal=qualification_seal,
            config=str(config_path), config_seal=config_seal, proposed_population=count+1,
            exact_baseline_prefix=True, coverage_admitted=False, full_scalar_isa_verified=False,
            spike_custom_isa_pass=False, rtl_changed=False, simulations_started=False,
            raw_delta=change['metrics'], output_pins={str(p):life.digest(p) for p in output.iterdir() if p.is_file()}))
    except Exception as error:
        if output.exists():
            life.save(output/'failure.json',dict(status='REJECTED_NOT_ADMITTED',reason=type(error).__name__+': '+str(error)))
        raise
    return life.digest(output/'candidate.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-seal','qualification-seal','config-seal'):
        parser.add_argument('--'+name, required=True)
    for name in ('baseline','qualification','config','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--single-bits', type=Path)
    parser.add_argument('--single-seal')
    args = parser.parse_args()
    seal = prepare(args.output, args.baseline, args.baseline_seal, args.qualification,
                   args.qualification_seal, args.config, args.config_seal, args.single_bits, args.single_seal)
    print(json.dumps(dict(output=str(args.output), seal=seal)))


if __name__ == '__main__': main()
