"""Frozen-image RVH direct-if compiled candidates; no native capture or EL."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from inventory_operand_debug import Design, ROOT
from closure_point_inventory import points

OUT = ROOT / 'verification/out'
BUILD = OUT / 'repaired-aligned-build-20260930-01'
BASE = OUT / 'gap105-offline-admitted-725-parent-20261006-01'
BASE_SHA = '0f49638e8cea36b28b5832e7eaeea39ee9b5249a162de3f3732c0fcd13a5a397'
BUILD_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
SIX = OUT / 'branch-combo-six-policy-population-724-parent-20261006-01/config.json'
SIX_SHA = '32d8deca7e562af7e5e0f8f28768d386772ecfc1c9f3908c193f9d2e5ce0d7cd'
CORE = 'ara_tb.dut.i_ara_soc.i_system.i_ariane'
HERE = Path(__file__).resolve().parent


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def uncomment(text):
    return re.sub(r'/\*.*?\*/|//[^\n]*', lambda m: '\n' * m[0].count('\n'), text, flags=re.S)


def direct_sites(text):
    clean = uncomment(text)
    return {i: line.strip() for i, line in enumerate(clean.splitlines(), 1)
            if re.search(r'\bif\s*\(\s*CVA6Cfg\.RVH\s*\)', line)}


def config_chain(config, build, soc):
    config, build, soc = map(uncomment, (config, build, soc))
    require(re.search(r'localparam\s+CVA6ConfigHExtEn\s*=\s*0\s*;', config)
            and "RVH: bit'(CVA6ConfigHExtEn)" in config, 'Frozen H extension value differs')
    writes = re.findall(r'cfg\.RVH\s*=\s*([^;]+);', build)
    require(writes == ['CVA6Cfg.RVH'], 'RVH build propagation differs')
    fn = re.search(r'function automatic config_pkg::cva6_user_cfg_t gen_usr_cva6_config\b(.*?)endfunction', soc, re.S)
    require(fn and not re.search(r'cfg\.RVH\s*=', fn[1]) and 'return cfg;' in fn[1],
            'SoC RVH override/return differs')
    for anchor in ('gen_usr_cva6_config(cva6_config_pkg::cva6_cfg)',
                   'build_config_pkg::build_config(CVA6AraConfig_user)',
                   '.CVA6Cfg           (CVA6AraConfig        )'):
        require(anchor in soc, 'SoC config connection differs')
    require(re.search(r'cfg\.NrPMPEntries\s*=\s*0\s*;', fn[1]), 'SoC PMP context differs')
    return dict(RVH=0, NrPMPEntries=0, anchors=[
        'CVA6ConfigHExtEn=0', "RVH: bit'(CVA6ConfigHExtEn)",
        'gen_usr_cva6_config has no RVH assignment and returns cfg',
        'cfg.RVH = CVA6Cfg.RVH', '.CVA6Cfg(CVA6AraConfig)'])


def matched_expressions(group, sites, file_id):
    result = []
    for expr in group:
        if expr.tag not in ('branch_expr', 'branch_cexpr'):
            continue
        line = int(expr.get('id', '0'))
        if line not in sites:
            continue
        require(group.get('file_id') == file_id and expr.get('file_id') == file_id,
                'Compiled source file binding differs')
        require(expr.get('exprstr') == "1'b0" and int(expr.get('index', '0')) > 0,
                'Direct RVH compiled constant/index differs')
        result.append(dict(expr.attrib, source_direct_if=sites[line]))
    return result


def true_pattern(pattern, expressions):
    require(bool(expressions), 'No exact direct RVH source binding')
    indices = [int(e['index']) for e in expressions]
    require(all(0 < i < len(pattern) for i in indices) and set(pattern) <= set('01-'),
            'Invalid compiled branch vector')
    # VCS branch_expr index counts from the right; do not use left indexing.
    return any(pattern[-i] == '1' for i in indices)


def partition(mapped, expressions, record):
    require(record['width'] > 0 and int(record['bits'], 16).bit_length() <= record['width'],
            'Bitmap width overflow')
    targets, protected = [], []
    for point in mapped:
        hit = bool(int(record['bits'], 16) & (1 << (record['width'] - 1 - point['raw_index'])))
        row = dict(point=point, hit725=hit)
        if true_pattern(point['native_vector']['vector'], expressions):
            require(not hit, 'Source-unreachable true pattern already hit; HOLD')
            targets.append(row)
        else:
            protected.append(row)
    return targets, protected


def prepare(output):
    require(output.parent == OUT and output.resolve() == output and not output.exists(), 'Fresh direct output required')
    pins = {}
    def pin(path, expected=None):
        path = Path(path).absolute()
        h = digest(path)
        require(expected is None or h == expected, 'Input drift: ' + str(path))
        require(str(path) not in pins or pins[str(path)] == h, 'Conflicting input pin')
        pins[str(path)] = h
        return path
    manifest = json.loads(pin(BASE / 'admission-manifest.json', BASE_SHA).read_bytes())
    require(manifest['schema'] == 'GAP105_HISTORICAL725_SOFTWARE_NATIVE_ADMISSION_V1', 'Foreign admission')
    for path, h in manifest['output_pins'].items():
        require(Path(path).parent == BASE, 'Foreign admission output')
        pin(path, h)
    state = json.loads((BASE / 'status.json').read_bytes())
    bits = json.loads((BASE / 'combined-bits.json').read_bytes())
    require(state['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and state['coverage_admitted']
            and state['aggregate_passed'] == 725 and len(bits['tests']) == len(set(bits['tests'])) == 725,
            'Not formally admitted725')
    source_pins = json.loads(pin(BUILD / 'build-source-pins.json', BUILD_SHA).read_bytes())
    config_paths = [ROOT / 'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
                    ROOT / 'hardware/deps/cva6/core/include/build_config_pkg.sv', ROOT / 'hardware/src/ara_soc.sv']
    chain = config_chain(*(pin(p, source_pins[str(p)]).read_text() for p in config_paths))
    six = json.loads(pin(SIX, SIX_SHA).read_bytes())
    require(not any(s == CORE or s.startswith(CORE + '.') for s in six['scope_owners']),
            'Six-policy core overlap needs exact separate review')
    d = Design(BUILD / 'sim/simv.vdb')
    for rel, h in bits['design'].items():
        pin(d.db / rel, h)
    for rel in ('auxiliary/verilog.sourceinfo.xml', 'shape/branch.verilog.info.xml'):
        pin(d.db / rel)
    sites_cache, groups, holds, outside = {}, [], [], []
    for scope, record in sorted(bits['metrics']['branch'].items()):
        if not (scope == CORE or scope.startswith(CORE + '.')) or not record['width']:
            continue
        source = d.source(scope)
        path = Path(source['resolved_path'])
        require(str(path) in source_pins, 'Core source not build-bound')
        if path not in sites_cache:
            sites_cache[path] = direct_sites(pin(path, source_pins[str(path)]).read_text())
        sites = sites_cache[path]
        if not sites:
            continue
        definition = d.definition(scope, 'branch')
        require(definition.get('id') == d.hierarchy[scope].get('id')
                and definition.get('chksum') == record['checksum'], 'Compiled module/metric identity differs')
        mapped = points('branch', definition, record['width'])
        matched, used = set(), set()
        for group in definition.iter('branch_spec'):
            expressions = matched_expressions(group, sites, source['file_id'])
            if not expressions:
                continue
            matched.update(int(e['id']) for e in expressions)
            local = [p for p in mapped if p['native_id'] == group.get('id')]
            targets, protected = partition(local, expressions, record)
            used.update(p['raw_index'] for p in local)
            groups.append(dict(scope=scope, source=source, source_sha256=source_pins[str(path)],
                module_checksum=d.hierarchy[scope].get('chksum'), metric_checksum=record['checksum'],
                metric_width=record['width'], group=dict(group.attrib), direct_expressions=expressions,
                targets=targets, protected=protected, decision='STATIC_CANDIDATE_NATIVE_IDENTITY_PENDING'))
        holds.extend(dict(scope=scope, source=str(path), line=line, source_direct_if=sites[line],
                          reason='NO_EXACT_COMPILED_DECISION_DO_NOT_INFER_OPTIMIZED') for line in sorted(set(sites)-matched))
        outside.append(dict(scope=scope, metric_checksum=record['checksum'], metric_width=record['width'],
                            protected_outside_matching_groups=[p for p in mapped if p['raw_index'] not in used]))
    counts = dict(direct_decisions=sum(len(g['direct_expressions']) for g in groups),
                  targets=sum(len(g['targets']) for g in groups), protected=sum(len(g['protected']) for g in groups),
                  groups=len(groups), scopes=len({g['scope'] for g in groups}))
    require((counts['direct_decisions'], counts['targets'], counts['protected']) == (131, 247, 1126),
            'Reviewed mapping/protection population differs')
    for p in (Path(__file__).resolve(), HERE / 'test_rvh_direct_native_candidates_725.py',
              HERE / 'inventory_operand_debug.py', HERE / 'closure_point_inventory.py',
              HERE / 'closure_scorecard.py', HERE / 'reviewed_20261004/audit_readonly.py'):
        pin(p)
    for p, h in pins.items():
        require(digest(p) == h, 'Final input drift: ' + p)
    evidence = dict(schema='RVH_DIRECT_COMPILED725_CANDIDATES_V1', status='PREPARED_STATIC_NOT_NATIVE_QUALIFIED',
        admission=str(BASE), admission_seal=BASE_SHA, configuration=chain, counts=counts, groups=groups,
        protected_outside_matching_groups=outside, source_only_hold=holds,
        six_policy_scope_overlap=False, historical_descriptor_skew='HOLD',
        native_identity_qualified=False, native_ids_are_only_compiled_XML=True, exclusions_generated=False,
        application_approval=False, simulations_started=False,
        future_native_gates=['Exact scope/module checksum/file/line/expr and measured GUI IDs; no XML ID transplant',
            'Full same-session before gate, singleton exact difference, save/reload and final reset',
            'Keep all1126 local protection and outside-group/all-other-metric protection; no false/X waiver'],
        input_pins=pins)
    output.mkdir()
    artifact = output / 'inventory.json'
    artifact.write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')
    seal = output / 'seal.json'
    seal.write_text(json.dumps(dict(input_pins=pins, output_pins={str(artifact):digest(artifact)}), indent=2, sort_keys=True)+'\n')
    print(json.dumps(dict(output=str(output), seal=digest(seal), pins=len(pins), counts=counts)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    args = parser.parse_args()
    output = args.output.absolute()
    if args.mode == 'prepare':
        require(args.seal is None, 'Prepare does not accept a guessed seal')
        prepare(output)
    else:
        require(args.seal and digest(output/'seal.json') == args.seal, 'Wrong evidence seal')
        seal = json.loads((output/'seal.json').read_bytes())
        for p, h in {**seal['input_pins'], **seal['output_pins']}.items():
            require(digest(p) == h, 'Evidence drift: ' + p)
        print('VERIFY_PASS STATIC_ONLY_NO_NATIVE_APPROVAL')


if __name__ == '__main__':
    main()
