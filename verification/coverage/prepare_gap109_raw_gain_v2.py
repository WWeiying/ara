"""GAP109 v2: exact merged WIDTH32 LZC binding, saved singleton only; no admission."""
import argparse
import json
from pathlib import Path

import qualify_gap109_native as qualifier
import prepare_gap107_raw_gain_v2 as mapping

life, require = qualifier.life, qualifier.require
bitmap, inventory = mapping.bitmap, mapping.inventory
DESIGN = mapping.DESIGN
QUAL = life.OUT/'gap109-native-qualified-731-parent-20261006-01'
BASE = life.OUT/'pure-war-offline-admitted-731-parent-20261006-01'
BASE_SEAL = '79b146c964a009b7185e8f8b90616feab8ebeb8c859d08e0a782daea6e2f5641'
CONFIG = QUAL.with_name(QUAL.name+'.prepared.json')
RUN_PID = qualifier.RUN_PID


def seal_contract(seal):
    require(isinstance(seal, str) and len(seal) == 64 and
            all(c in '0123456789abcdef' for c in seal), 'Explicit SHA256 seal required')
bit, pre_scope = mapping.bit, mapping.pre_scope
LZC_SCOPE = pre_scope()+'.i_fpnew.gen_operation_groups[3].i_opgroup_block.gen_merged_slice.i_multifmt_slice.gen_num_lanes[0].active_lane.lane_instance.i_fpnew_cast_multi.i_lzc'
LZC_NAME = 'lzc ( parameter WIDTH=32,MODE=0,CNT_WIDTH=5,gen_lzc.NumLevels=5 + WIDTH=32,MODE=1,CNT_WIDTH=5,gen_lzc.NumLevels=5 )'
SAVED_SINGLE = life.OUT/'gap109-raw-gain-731-parent-20261006-01/single-bits.json'
SAVED_SHA = 'ec63b9f9a59bf91f5f023f0266c36c02ab107a0eb1e01ad7a8c5816abd435a8c'


def native_definition(shape, module, scope, row, info_checksum, tgl_definition=None, metric='cond'):
    if scope != LZC_SCOPE:
        return mapping.native_definition(shape,module,scope,row,info_checksum,tgl_definition,metric)
    require(metric == 'cond' and row['width'] == 217 and row['checksum'] is None and
            info_checksum is None, 'Exact LZC metric identity differs')
    require(dict(module.attrib) == dict(id='-30',name='lzc',type='module',chksum='3250293308'),
            'Exact LZC compiled module differs')
    require(tgl_definition is not None and dict(tgl_definition.attrib) ==
            dict(id='-30',name=LZC_NAME+' ',chksum='1427877459'),
            'Exact LZC full parameter/tgl identity differs')
    nodes = [n for n in shape if n.get('id') == '-30' and n.get('name','').strip() == LZC_NAME]
    require(len(nodes) == 1 and nodes[0].get('chksum') == '4070328312',
            'Ambiguous/missing exact LZC condition variant')
    require(len(inventory.points('cond',nodes[0],217)) == 217, 'Incomplete LZC shape')
    return nodes[0], 'exact_scope_merged_lzc_width32_modes01_sealed_tgl_full_parameters'


def qualification_contract(record, audit):
    qualifier.runner.exact(record, dict(status='GAP109_SOFTWARE_NATIVE_QUALIFIED_NOT_ADMITTED',
        full_scalar_isa_verified=False, spike_custom_isa_pass=False, coverage_admitted=False,
        coverage_increment_measured=False, gain_requires_latest_formal_baseline=True,
        simulation_rerun=False, rtl_changed=False), 'Qualification differs')
    qualifier.runner.exact(audit, dict(status='GAP109_COMPLETE_SOFTWARE_NATIVE_PASS_NOT_FULL_SCALAR_ISA',
        custom_write_bytes=256, custom_active_bytes=8, custom_zero_tail_bytes=248,
        full_vrf_bytes=8192, initial_vrf_bytes=8192, csr_values=24, source_guard_bytes=6880,
        checks=41, full_scalar_isa_verified=False, spike_custom_isa_pass=False,
        coverage_admitted=False), 'Native audit differs')
    require([(b['phase'],b['pc'],b['backend_vl'],b['software_vl'],b['native_total_write_bytes'])
             for b in audit['bindings']]==[(0,0x8000017a,32,1,128),(1,0x80000252,32,1,128)],
            'Exact native sites differ')
    c = audit['contract']
    require(type(c['requests']) is int and c['requests']>0 and c['requests']==c['responses'] and all(c[k]==0 for k in
        ('exceptions','protocol_errors','outstanding','req_stalled','resp_stalled')),
        'Terminal native conservation differs')


    expected = [{k:v[k] for k in ('result_bits','integer_dot','integer_correction','fflags','stage_bits','stage_flags')}
                for v in qualifier.independent_native()]
    require(audit['numeric_oracles'] == expected, 'Independent GAP109 numeric audit differs')


def baseline_contract(manifest, status, before, original, base):
    require(manifest['output'] == str(base) and manifest['schema'].endswith('_ADMISSION_V1') and
            all(Path(p).parent == base for p in manifest['output_pins']),
            'Not an explicitly sealed admission output')
    count = status['aggregate_passed']
    require(type(count) is int and count == 731 and status['coverage_admitted'] is True and
            status['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY',
            'Not an admitted formal baseline')
    require(len(before['tests']) == len(set(before['tests'])) == count and
            len(original['tests']) == len(set(original['tests'])) == 731 and
            before['tests'][:731] == original['tests'], 'Formal731 prefix/population differs')
    require(before['design'] == original['design'], 'Original design differs')
    life.merge_pins(before['input_hashes'], original['input_hashes'])
    return count


def population(before, single):
    require(len(before['tests']) == len(set(before['tests'])) and
            single['tests'] == [str(qualifier.RUN/'code.vdb')] and
            single['tests'][0] not in before['tests'], 'Not unique original singleton')
    life.merge_pins(before['input_hashes'], single['input_hashes'])
    combined = bitmap.combine(before, single)
    require(combined['tests'] == before['tests'] + single['tests'] and
            len(set(combined['tests'])) == len(before['tests']) + 1, 'Exact baseline prefix differs')
    change = bitmap.delta(before, combined)
    require(sum(change['metrics'].values()) > 0, 'No fresh product gain; do not admit')
    return combined, change

def compiled(before, single, combined, pre, read):
    db = DESIGN/'snps/coverage/db'
    design = inventory.read_xml(db/'design/verilog.design.xml')
    nodes = {n.get('id'):(n,d) for d in design.findall('srcdef') for n in d.findall('srcinst')}
    require(len(nodes)==sum(len(d.findall('srcinst')) for d in design.findall('srcdef')), 'Duplicate hierarchy')
    def path(key, seen=()):
        require(key not in seen, 'Hierarchy cycle')
        node,_ = nodes[key]; parent = node.get('pid')
        return (path(parent,seen+(key,))+'.' if parent in nodes else '')+node.get('name')
    hierarchy = {path(k):d for k,(_,d) in nodes.items()}
    require(len(hierarchy)==len(nodes), 'Duplicate scopes')
    files = {n.get('id'):n.get('name') for n in inventory.read_xml(
        db/'auxiliary/verilog.sourceinfo.xml').iter('fileinfo')}
    shapes = {m:inventory.read_xml(db/('shape/'+m+'.verilog.shape.xml')) for m in before['metrics']}
    infos={}
    changed_metrics={metric for metric,rows in before['metrics'].items() if any(
        row['bits']!=combined['metrics'][metric][scope]['bits'] for scope,row in rows.items())}
    for metric in changed_metrics:
        p=db/('shape/'+metric+'.verilog.info.xml');read(p)
        infos[metric]={n.get('name'):n.get('chksum') for n in inventory.read_xml(p).iter('instance_data')}
    tgl_info=db/'shape/tgl.verilog.info.xml';tgl_shape=db/'shape/tgl.verilog.shape.xml'
    read(tgl_info);read(tgl_shape)
    tgl_checksums={n.get('name'):n.get('chksum') for n in inventory.read_xml(tgl_info).iter('instance_data')}
    tgl=inventory.read_xml(tgl_shape)
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
    require(len(pre['targets']) == 1, 'Exact GAP109 target population differs')
    seen = set()
    for target in pre['targets']:
        scope = target['scope']; raw = target['point']['raw_index']
        require(target['metric'] == 'cond' and (scope, raw) not in seen, 'Duplicate/wrong target')
        seen.add((scope, raw))
        old = before['metrics']['cond'][scope]
        require((old['width'], old['checksum']) == (target['width'], target['instance_checksum']),
                'Target width/checksum differs')
        ci_path = db/'shape/cond.verilog.info.xml'; read(ci_path)
        ci = {n.get('name'):n.get('chksum') for n in inventory.read_xml(ci_path).iter('instance_data')}
        td = inventory.definition(tgl, hierarchy[scope], tgl_checksums.get(scope)) if (
            old['checksum'] is None and ci.get(scope) is None) else None
        definition, binding = native_definition(shapes['cond'], hierarchy[scope], scope, old, ci.get(scope), td)
        points = {p['raw_index']:p for p in inventory.points('cond', definition, old['width'])}
        require(points[raw] == target['point'] and definition.get('chksum') ==
                target['compiled_definition_checksum'] and binding == target['binding'],
                'Target compiled identity differs')
        require(files[points[raw]['file_id']] == target['source'], 'Target source identity differs')
        read(Path(target['source']))
        targets.append(dict(scope=scope, point=points[raw], before_hit=bit(old, raw),
                            single_hit=bit(single['metrics']['cond'][scope], raw),
                            after_hit=bit(combined['metrics']['cond'][scope], raw)))
    return gained, targets


def historical_source_pin(path, build):
    path = Path(path)
    allowed = {life.ROOT/'hardware/deps/fpnew/src'/name for name in
               ('fpnew_fma.sv', 'fpnew_classifier.sv', 'fpnew_rounding.sv')}
    allowed.add(life.ROOT/'hardware/deps/common_cells/src/lzc.sv')
    require(path in allowed and path.resolve() == path and not path.is_symlink(),
            'Not exact historical GAP109 target source')
    require(str(path) in build, 'Historical build lacks target source')
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
    require(single_path is not None and Path(single_path).absolute() == SAVED_SINGLE and
            single_seal == SAVED_SHA, 'Only exact sealed failed-attempt singleton allowed')
    seal_contract(qualification_seal)
    require(base == BASE and baseline_seal == BASE_SEAL, 'Only authoritative731 allowed')
    require(qualification == QUAL, 'Only parent qualified GAP109 artifact allowed')
    seal_contract(config_seal)
    require(config_path == CONFIG, 'Only parent GAP109 qualifier config allowed')
    pins = {}
    def expected(path, seal):
        nonlocal pins
        pins = life.merge_pins(pins, {str(path):seal})
        return life.read_bound(path, seal)
    def read(path):
        nonlocal pins
        if Path(path) in ({life.ROOT/'hardware/deps/fpnew/src'/name for name in
                         ('fpnew_fma.sv','fpnew_classifier.sv','fpnew_rounding.sv')} |
                         {life.ROOT/'hardware/deps/common_cells/src/lzc.sv'}):
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
    require(config['run'] == str(qualifier.RUN) and config['run_prepared_seal'] == qualifier.RUN_SEAL and
            config['run_pid'] == RUN_PID and config['backend_derived_not_observed'] ==
                qualifier.runner.backend_contract(qualifier.life.read_bound(
                    qualifier.runner.PRE/'preflight-manifest.json',qualifier.runner.PRE_SEAL)) and
            config['expected_external_request_count'] is None and
            config['status'] == 'GAP109_NATIVE_PREPARED_NOT_COLLECTED', 'Reviewed original run differs')
    require(life.merge_pins(pins, config['pins']) == pins, 'Lost prepared pins')
    manifest = expected(base/'admission-manifest.json', baseline_seal)
    require(manifest['output'] == str(base) and all(Path(p).parent == base for p in manifest['output_pins']),
            'Aliased baseline outputs')
    pins = life.merge_pins(pins, manifest['output_pins'])
    pins = life.merge_pins(pins, json.loads(read(base/'evidence-pins.json')))
    status, before = [json.loads(read(base/name)) for name in ('status.json', 'combined-bits.json')]
    pre = expected(qualifier.runner.PRE/'preflight-manifest.json', qualifier.runner.PRE_SEAL)
    original_base = Path(pre['baseline'])
    require(original_base == BASE and pre['baseline_seal'] == BASE_SEAL, 'Static original731 differs')
    original_manifest = expected(original_base/'admission-manifest.json', pre['baseline_seal'])
    original = expected(original_base/'combined-bits.json',
                        original_manifest['output_pins'][str(original_base/'combined-bits.json')])
    count = baseline_contract(manifest, status, before, original, base)
    require(read(base/'combined-inputs.txt').decode().splitlines() == [str(DESIGN), *before['tests']],
            'Exact formal design/input order differs')
    pins = life.merge_pins(pins, before['input_hashes'])
    pins = life.merge_pins(pins, {str(DESIGN/'snps/coverage/db'/p):h for p,h in before['design'].items()})
    targets = expected(qualifier.runner.PRE/'target-static-contract.json', qualifier.runner.TARGET_SEAL)
    pins = life.merge_pins(pins, targets['pins'])
    for module in (mapping, bitmap, inventory, inventory.score, qualifier):
        path = Path(module.__file__).resolve()
        require(str(path) in pins, 'Unbound reused helper: ' + str(path))
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_prepare_gap109_raw_gain_v2.py')):
        pins = life.merge_pins(pins, {str(path):life.digest(path)})
    life.check(pins)
    symbols, data, sites = qualifier.elf_view()
    require(qualifier.runtime(qualifier.RUN, symbols, data, sites, qualifier.independent_native()) == audit,
            'Actual qualified runtime replay differs')
    # Qualification and replay must pass before collecting any raw evidence.
    output.mkdir()
    try:
        inputs = output/'single-inputs.txt'
        with inputs.open('x') as stream:
            stream.write(str(DESIGN)+'\n'+str(qualifier.RUN/'code.vdb')+'\n')
        if single_path:
            single = expected(Path(single_path).absolute(), single_seal)
        else:
            single = bitmap.collect(inputs)
        require(all(p in pins and pins[p] == h for p,h in single['input_hashes'].items()),
                'Singleton differs from qualified raw pins')
        pins = life.merge_pins(pins, single['input_hashes'])
        life.save(output/'single-bits.json', single)
        combined, change = population(before, single)
        gained, hits = compiled(before, single, combined, targets, read)
        require(len(gained) == sum(change['metrics'].values()), 'Compiled gain ledger incomplete')
        life.check(pins)
        products = dict(combined_bits=combined, raw_delta=change,
                        gained_compiled_points=gained, target_hits=hits, evidence_pins=pins)
        for name,value in products.items():
            life.save(output/(name.replace('_','-')+'.json'), value)
        life.save(output/'candidate.json', dict(status='GAP109_EXPLICIT_BASE_PLUS_ONE_CANDIDATE_NOT_ADMITTED',
            baseline=str(base), baseline_seal=baseline_seal, baseline_population=count,
            qualification=str(qualification), qualification_seal=qualification_seal,
            config=str(config_path), config_seal=config_seal, proposed_population=count+1,
            exact_baseline_prefix=True, coverage_admitted=False, full_scalar_isa_verified=False,
            spike_custom_isa_pass=False, rtl_changed=False, simulations_started=False,
            raw_delta=change['metrics'], output_pins={str(p):life.digest(p) for p in output.iterdir() if p.is_file()}))
    except Exception as error:
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


