"""Exact51 upper-half native qualification; immutable existing five-stage primitive."""
import argparse
import json
from pathlib import Path
import re
import shutil
import inventory_operand_debug
from types import FunctionType, SimpleNamespace
import cva6_fixed_fields_native768 as native
import prove_vlsu_address_padding770 as proof

life, require, tools = native.life, native.require, native.tools
HERE = Path(__file__).resolve().parent
TEMPLATE = life.OUT / 'cva6-fixed120-native768-agent-20261007-01/config.json'
TEMPLATE_SHA = '1a34f949b9d89a1a7403c067a1d3c56228df3d72d9d4527b36d6c33c2604858c'


def parse_el(text, config):
    instances = {i['scope']: i for i in config['instances']}
    found, scope, checks = set(), None, None
    for line in map(str.strip, text.splitlines()):
        if not line or line.startswith('//'): continue
        if re.fullmatch(r'ANNOTATION: "[^"\n]*"', line): continue
        m = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"', line)
        if m: checks = list(m.groups()); scope = None; continue
        if line.startswith('INSTANCE:'):
            scope = line.split(':', 1)[1].strip()
            require(scope in instances and checks == [instances[scope]['design_module_checksum'],
                                                     instances[scope]['toggle_checksum']], 'Unknown scope/checksum')
            continue
        m = re.fullmatch(r'Toggle(?: (0to1|1to0))? ([\w.]+(?:\[\d+\]\.[\w.]+)?)\s*(?:\[(\d+)(?::(\d+))?\])?(?: "([^"\n]+)")?', line)
        require(scope is not None and m is not None, 'Unknown metric/EL grammar')
        direction, name, left, right, sig = m.groups()
        signal = next((s for s in instances[scope]['signals'] if s['name'] == name), None)
        require(signal is not None and left is not None, 'Protected object or whole-field exclusion')
        hi, lo = int(left), int(right or left)
        require(127 >= hi >= lo >= 64, 'Low64 or out-of-bounds exclusion')
        if sig is not None:
            require(sig in ('logic ' + signal['native_label'], 'reg ' + signal['native_label']), 'Declaration/type/bounds mismatch')
        for bit in range(lo, hi + 1):
            for d in (direction,) if direction else ('0to1', '1to0'):
                key = (scope, name, bit, d)
                require(key not in found, 'Duplicate direction'); found.add(key)
    require(found == native.primitive.bitset(config), 'Missing/extra exact directions')
    return sorted(found)


def label(node):
    name = node.get('name')
    if node.tag == 'node': return name
    if node.tag == 'vectornode': return name + '[' + node.get('left') + ':' + node.get('right') + ']'
    require(node.tag == 'arrays', 'Unknown shape kind')
    dims = (node.get('unpackedrange', '') + ' ' + node.get('packedrange', '')).split()
    require(len(dims) % 2 == 0, 'Invalid array dimensions')
    return name + ''.join('[' + dims[j] + ':' + dims[j+1] + ']' for j in range(0, len(dims), 2))


def definition_name(scope, module):
    if scope.endswith('.i_addrgen_req_queue'):
        require(module == 'fifo_v3', 'Request storage module changed')
        return 'fifo_v3 ( parameter FALL_THROUGH=0,DATA_WIDTH=32,DEPTH=4,ADDR_DEPTH=2,FifoDepth=4,dtype=addrgen_axi_req_t ) '
    if scope.endswith('.i_store_b_metadata'):
        require(module == 'fifo_v3', 'Metadata storage module changed')
        return 'fifo_v3 ( parameter FALL_THROUGH=0,DATA_WIDTH=32,DEPTH=16,ADDR_DEPTH=4,FifoDepth=16,dtype=b_meta_t ) '
    require(module in ('addrgen', 'vstu'), 'Producer module changed')
    return module


def prepare(out, proof_path, proof_sha):
    require(out.parent == life.OUT and not out.exists(), 'Fresh output required')
    p = life.read_bound(proof_path, proof_sha); life.check(p['pins'])
    require(p['schema'] == 'VLSU_ADDRESS_PADDING770_SOURCE_PROOF_V1' and p['baseline'] == 770 and
            p['bits'] == 3264 and p['directions'] == 6528 and p['old_EL_overlap_count'] == 0, 'Proof boundary')
    proof.source_contract({r: (proof.ROOT / r).read_text() for r in proof.SOURCES})
    for old in p['old_EL_inventory']:
        require(life.digest(old['path']) == old['sha256'], 'Old EL drift')
        proof.duplicates(Path(old['path']).read_text(), proof.names())
    base = life.read_bound(proof.BASE / 'admission-manifest.json', proof.BASE_SHA)
    ledger = proof.BASE / 'combined-inputs.txt'
    require(life.digest(ledger) == base['output_pins'][str(ledger)], '770 ledger drift')
    paths = ledger.read_text().splitlines()
    require(len(paths) == len(set(paths)) == 771, 'Not exact770 population')
    db = Path(paths[0]); design = native.Design(db)
    shape = native.primitive.toggle.xml(db / 'snps/coverage/db/shape/tgl.verilog.shape.xml')
    info = native.primitive.toggle.xml(db / 'snps/coverage/db/shape/tgl.verilog.info.xml')
    info_checks = {n.get('name'): n.get('chksum') for n in info.iter('instance_data')}
    instances = []
    for scope, fields in sorted(proof.names().items()):
        candidates = [c for c in p['candidates'] if c['scope'] == scope]
        require({c['name'] for c in candidates} == fields and len(candidates) == len(fields), 'Exact source target names')
        check = candidates[0]['checksum']
        module = design.hierarchy[scope]
        expected_name = definition_name(scope, module.get('name'))
        defs = [d for d in shape.findall('tgldef') if d.get('chksum') == check and d.get('name') == expected_name]
        require(len(defs) == 1 and info_checks.get(scope) == check, 'Actual scope/module/checksum')
        nodes = list(defs[0].find('tglshape')); signals = []
        for c in candidates:
            matches = [n for n in nodes if n.get('name') == c['name']]
            require(len(matches) == 1, 'Unique actual target')
            n = matches[0]
            require(n.tag == 'vectornode' and n.get('left') == '127' and n.get('right') == '0' and
                    n.get('portnode') == '0' and all(c['shape'].get(k) == v for k, v in n.attrib.items()), 'Complete compiled declaration')
            signals.append(dict(name=c['name'], scalar=False, left=127, right=0, bits=list(range(64, 128)),
                                native_label=label(n), shape=dict(n.attrib)))
        instances.append(dict(scope=scope, toggle_checksum=check, design_module_checksum=module.get('chksum'),
                              signals=signals, all_typed_labels=[label(n) for n in nodes],
                              protected_shape=[dict(n.attrib, tag=n.tag) for n in nodes if n.get('name') not in fields],
                              retained_target_bits={name:list(range(64)) for name in fields}))
    template = life.read_bound(TEMPLATE, TEMPLATE_SHA)
    tools.revalidate(template['identity'])
    pins = dict(p['pins']); pins[str(proof_path)] = proof_sha; pins[str(TEMPLATE)] = TEMPLATE_SHA
    pins[str(ledger)] = base['output_pins'][str(ledger)]
    vdb = Path(paths[-1]); samples = list((vdb / 'snps/coverage/db/testdata').iterdir())
    require(len(samples) == 1, 'Single admitted sample')
    for path in samples[0].iterdir():
        if path.is_file():
            sha = life.digest(path)
            if str(path) in base['input_pins']: require(sha == base['input_pins'][str(path)], 'Admitted sample drift')
            else: require(path.name in ('siminfo.xml', 'vcmArguments.xml'), 'Unpinned sample artifact')
            pins[str(path)] = sha
    for module in (native, native.primitive, native.primitive.common, native.primitive.common.common,
                   inventory_operand_debug, native.primitive.toggle, life, tools, proof):
        path = Path(module.__file__).resolve(); pins[str(path)] = life.digest(path)
    for name in ('vlsu_address_padding_native770.py', 'test_vlsu_address_padding_native770.py',
                 'cva6_fixed_fields_native768.tcl'):
        path = HERE / name; pins[str(path)] = life.digest(path)
    config = dict(schema='VLSU_PADDING51_NATIVE770_PREPARED_V1', baseline=770, output=str(out),
                  instances=instances, design=str(db), vdb=str(vdb), test=str(vdb.with_suffix('') / samples[0].name),
                  pins=pins, identity=template['identity'], timeout_seconds=900, launch_authorized=False,
                  population_application=False, proof_seal=proof_sha, old_EL_inventory=p['old_EL_inventory'],
                  audit_low64_method='Exact global exported EL physical ranges; whole target row percentages may change',
                  official_denominator_verified=False)
    require(len(native.primitive.bitset(config)) == 6528, 'Not exact51 upper halves')
    text = native.primitive.candidate(config); parse_el(text, config); life.check(pins)
    out.mkdir()
    native.primitive.common.common.save(out / 'candidate.el', text)
    native.primitive.common.common.save(out / 'queue_constant_native.tcl', (HERE / 'cva6_fixed_fields_native768.tcl').read_text())
    selection = ''.join('set qc_' + k + ' {' + config[k] + '}\n' for k in ('design', 'vdb', 'test'))
    selection += 'set qc_python {' + shutil.which('python3') + '}\nset qc_helper {' + str(Path(__file__).resolve()) + '}\nset qc_instances {}\n'
    for i in instances:
        selection += 'lappend qc_instances [list {' + i['scope'] + '} [list ' + ' '.join('{' + s['native_label'] + '}' for s in i['signals']) + ']]\n'
    native.primitive.common.common.save(out / 'selection.tcl', selection)
    for name in ('candidate.el', 'selection.tcl', 'queue_constant_native.tcl'): pins[str(out / name)] = life.digest(out / name)
    life.save(out / 'config.json', config)
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'config.json'), objects=51, directions=6528, launch_authorized=False)))


def verify(out, seal):
    c = life.read_bound(out / 'config.json', seal); life.check(c['pins']); tools.revalidate(c['identity'])
    terminal = json.loads((out / 'terminal.json').read_bytes())
    require(terminal['returncode'] == 0 and not terminal['timeout'] and len(terminal['actual_dve']) == 1, 'Terminal identity')
    for name in ('launcher.log', 'DVEfiles/dve_gui.log'):
        require(not re.search(r'(?:Warning-|Error-|Fatal-|\b(?:Error|Fatal):|QUEUE_CONSTANT_NATIVE_FAILED)', (out / name).read_text()), 'Native diagnostic')
    require((out / 'DVEfiles/dve_gui.log').read_text().splitlines().count('QUEUE_CONSTANT_NATIVE_DONE') == 1, 'Incomplete five stages')
    require(parse_el((out / 'first.el').read_text(), c) == parse_el((out / 'second.el').read_text(), c), 'Exact native reload')
    for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el'): require((out / name).read_bytes() == b'', 'Global exclusion reset not empty')
    counts = [native.audit_native(i, {s:(out / ('native_' + s + '_' + str(k) + '.tsv')).read_text()
                                      for s in ('before', 'selected', 'reset', 'reloaded', 'final')}) for k,i in enumerate(c['instances'])]
    result = dict(status='VLSU_PADDING51_6528_NATIVE_QUALIFIED_NOT_APPLIED', config_seal=seal,
                  native_inventory_counts=counts, exact_global_EL=True, semantic_reload=True, finalreset=True,
                  low64_and_interfaces_protected=True, official_denominator_verified=False, population_application=False,
                  pins={**c['pins'], **{str(p):life.digest(p) for p in out.rglob('*') if p.is_file() and p.name != 'capture-result.json'}})
    life.save(out / 'capture-result.json', result)


def run(out, seal, authorization):
    require(authorization == seal and seal is not None, 'Explicit parent-reviewed config seal required')
    c = life.read_bound(out / 'config.json', seal)
    require(c['schema'] == 'VLSU_PADDING51_NATIVE770_PREPARED_V1' and not c['launch_authorized'], 'Wrong frozen entry')
    # Private read adapter conveys one explicit CLI authorization, never mutates sealed config.
    def read_bound(path, sha):
        value = life.read_bound(path, sha)
        if Path(path) == out / 'config.json': value = dict(value, launch_authorized=True)
        return value
    private_life = SimpleNamespace(**{**vars(life), 'read_bound':read_bound})
    FunctionType(native.run.__code__, {**vars(native), 'life':private_life, 'verify':verify})(out, seal)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'el', 'verify', 'run'))
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--seal')
    parser.add_argument('--proof', type=Path); parser.add_argument('--proof-seal'); parser.add_argument('--file')
    parser.add_argument('--parent-reviewed-seal')
    args = parser.parse_args(); out = args.output.resolve()
    if args.mode == 'prepare': prepare(out, args.proof.resolve(), args.proof_seal)
    elif args.mode == 'el': print(len(parse_el((out / args.file).read_text(), json.loads((out / 'config.json').read_bytes()))))
    elif args.mode == 'verify': verify(out, args.seal)
    else: run(out, args.seal, args.parent_reviewed_seal)
