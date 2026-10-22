"""Exact new688-object/9440-direction qualification; no population apply."""
import argparse
import json
from pathlib import Path
import re
import sys
from types import FunctionType, SimpleNamespace

import qbs_hit128_native780 as local

primitive, life, tools, require = local.primitive, local.life, local.tools, local.require
HERE = Path(__file__).resolve().parent
PROOF = life.OUT / 'qbs-main-side-exact-batch780-agent-20261008-01.json'
PROOF_SHA = 'b3a125456ca92ebef722b83272f33b29333e4f1da488790b55eb2b85108bb600'
LOCAL_SHA = '327830c7102399481f0045d334d81054845e04511e674bb8e00cc0e41a3319bb'
parse_el = local.parse_el


def instances(proof, template, definition):
    require(proof['population'] == 780 and proof['no_EDA'] is True and
            proof['aggregate_application'] is False and proof['new_target_bits'] == 4720
            and proof['new_target_objects'] == 688, 'Source proof authority')
    wanted, qualified, coordinates = {}, set(), set()
    nodes, offsets, offset = {}, {}, 0
    for node in definition.find('tglshape'):
        require(node.tag in ('node', 'vectornode'), 'No array offset guessing')
        name = node.get('name')
        require(name not in nodes, 'Ambiguous compiled declaration')
        nodes[name] = node
        offsets[name] = offset
        offset += 2 * (abs(int(node.get('left', '0')) - int(node.get('right', '0'))) + 1)
    require(len(nodes) == 3193 and offset == 66340 and definition.get('chksum') == '3657545390',
            'Complete frozen typed payload')
    owners = {i['scope']: i for i in template['instances']}
    require(len(owners) == 2, 'Both native bank identities')
    for group in proof['target_groups']:
        scope, name = group['scope'], group['signal']
        require(scope in owners and group['checksum'] == '3657545390', 'Unknown scope/checksum')
        require(name in nodes and nodes[name].tag == 'vectornode'
                and nodes[name].get('portnode') == '0' and nodes[name].get('right') == '0'
                and nodes[name].get('line_num') in ('269', '355', '381'), 'Non-hit compiled object')
        status = group['classification']
        require(status in ('NEW_ZERO_NATIVE_REQUIRED', 'QUALIFIED128_NOT_APPLIED'), 'HOLD cannot become target')
        for text, coords in group['bit_missing_coordinates'].items():
            bit = int(text)
            require(text == str(bit) and 0 <= bit <= int(nodes[name].get('left')),
                    'Exact compiled bit bounds')
            key, slot, side = local.reuse.old.proof.mapping.identity(name, bit)
            require(group['original_writer_slots'][text] == [slot, key[-1]], 'Original writer identity')
            require(coords == [offsets[name] + 2 * bit, offsets[name] + 2 * bit + 1],
                    'Wrong raw coordinates/observed direction')
            identity = scope, name, bit
            require(identity not in coordinates, 'Duplicate source coordinate')
            coordinates.add(identity)
            if status == 'QUALIFIED128_NOT_APPLIED':
                qualified.add(identity)
            else:
                wanted.setdefault(scope, {}).setdefault(name, []).append(bit)
    expected128 = {(local.SCOPE, name, bit) for name, bits in local.target_names().items() for bit in bits}
    require(qualified == expected128 and len(coordinates - qualified) == 4720, 'Exact128 exclusion from9440')
    result = []
    for scope, signals in sorted(wanted.items()):
        prior = owners[scope]
        selected = []
        for name, bits in sorted(signals.items()):
            node = nodes[name]
            left = int(node.get('left'))
            require(left in (15, 31) and 0 < len(bits) < left + 1, 'Only partial hit vectors')
            selected.append(dict(name=name, bits=sorted(bits), scalar=False, left=left, right=0,
                                 native_label=name + '[' + str(left) + ':0]', shape=dict(node.attrib)))
        result.append(dict(scope=scope, design_module_checksum=prior['design_module_checksum'],
            toggle_checksum='3657545390', signals=selected,
            protected=[dict(n.attrib, tag=n.tag) for name, n in nodes.items() if name not in signals],
            retained_target_signal_bits={s['name']: sorted(set(range(s['left'] + 1)) - set(s['bits'])) for s in selected}))
    require(len(result) == 2 and sum(len(i['signals']) for i in result) == 688, 'Exact688 objects')
    return result


def proof_inputs():
    require(life.digest(Path(local.__file__)) == LOCAL_SHA, 'Frozen128 primitive drift')
    proof = life.read_bound(PROOF, PROOF_SHA)
    template = life.read_bound(local.TEMPLATE / 'config.json', local.TEMPLATE_SHA)
    path = next(Path(p) for p in proof['pins'] if p.endswith('/shape/tgl.verilog.shape.xml'))
    shape = primitive.toggle.xml(path)
    defs = [d for d in shape.iter('tgldef') if d.get('name') == 'qbs_payload_buffer'
            and d.get('chksum') == '3657545390']
    require(len(defs) == 1, 'Unique compiled bank definition')
    return proof, template, path, defs[0]


def check(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    require(c['output'] == str(out) and c['baseline'] == 780 and c['population_application'] is False
            and c['source_proof_sha256'] == PROOF_SHA, 'Output/source owner')
    life.check(c['pins'])
    p, t, path, definition = proof_inputs()
    require(c['instances'] == instances(p, t, definition) and c['shape_path'] == str(path), 'Exact complement differs')
    require(len(primitive.bitset(c)) == 9440 and c['protected_direction_count'] == 123240
            and c['protected_target_vector_bits'] == 13456, 'Exact direction partition')
    parse_el((out / 'candidate.el').read_text(), c)
    tools.revalidate(c['identity'])
    return c


def prepare(out):
    require(out.parent == life.OUT and not out.exists(), 'Fresh output only')
    p, t, shape_path, definition = proof_inputs()
    pins = dict(p['pins'])
    for path, sha in t['pins'].items():
        if path.startswith(t['design'] + '/') or path.startswith(t['vdb'] + '/') or path.endswith(('.py', '.tcl')):
            require(path not in pins or pins[path] == sha, 'Conflicting inherited pin')
            pins[path] = sha
    for path in (PROOF, local.TEMPLATE / 'config.json', Path(local.__file__), Path(__file__).resolve(),
                 HERE / 'test_qbs_hit9440_native780.py', HERE / 'queue_constant_native.tcl'):
        pins[str(path)] = life.digest(path)
    selected = instances(p, t, definition)
    c = dict(output=str(out), baseline=780, source_proof_sha256=PROOF_SHA, pins=pins,
        instances=selected, shape_path=str(shape_path), identity=t['identity'], design=t['design'],
        vdb=t['vdb'], test=t['test'], input_VDB_count=1, physical_bits=4720, bit_directions=9440,
        protected_direction_count=123240, protected_target_vector_bits=13456,
        non_target_compiled_signal_count=5698, timeout_seconds=1800, automatic_retry=False,
        population_application=False, qualified128_included=False, HOLD_included=False)
    tools.revalidate(c['identity'])
    text = primitive.candidate(c)
    parse_el(text, c)
    values = dict(qc_design=c['design'], qc_vdb=c['vdb'], qc_test=c['test'],
                  qc_python=sys.executable, qc_helper=str(Path(__file__).resolve()))
    require(all(v and not any(x in v for x in '{}\\\n\r') for v in values.values()), 'Unsafe Tcl value')
    selection = ''.join('set ' + k + ' {' + v + '}\n' for k, v in values.items()) + 'set qc_instances {}\n'
    for i in selected:
        labels = ' '.join('{' + s['native_label'] + '}' for s in i['signals'])
        selection += 'lappend qc_instances [list {' + i['scope'] + '} [list ' + labels + ']]\n'
    life.check(pins)
    out.mkdir()
    for name, contents in (('candidate.el', text), ('selection.tcl', selection),
                           ('queue_constant_native.tcl', (HERE / 'queue_constant_native.tcl').read_text())):
        primitive.common.common.save(out / name, contents)
        pins[str(out / name)] = life.digest(out / name)
    life.save(out / 'config.json', c)
    seal = life.digest(out / 'config.json')
    check(out, seal)
    print(json.dumps(dict(output=str(out), seal=seal, objects=688, directions=9440, EDA=False)))


def verify(out, seal):
    c = check(out, seal)
    terminal = json.loads((out / 'terminal.json').read_bytes())
    require(type(terminal['returncode']) is int and terminal['returncode'] == 0
            and type(terminal['timeout']) is bool and terminal['timeout'] is False
            and len(terminal['actual_dve']) == 1, 'Strict native terminal')
    actual = terminal['actual_dve'][0]
    require(type(actual['pid']) is int and actual['pid'] > 0 and actual['cwd'] == str(out)
            and actual['exe'] == c['identity']['executable'], 'Actual executable/output identity')
    for name in ('launcher.log', 'DVEfiles/dve_gui.log'):
        require(re.search(r'(?:Error-|Fatal-|Warning-|\b(?:Error|Fatal):)', (out / name).read_text()) is None,
                'Native diagnostic: ' + name)
    counts = [local.audit_inventory(i, {s: (out / ('native_' + s + '_' + str(k) + '.tsv')).read_text()
                                        for s in ('before', 'selected', 'reset', 'reloaded', 'final')})
              for k, i in enumerate(c['instances'])]
    def save(path, value):
        require(path == out / 'capture-result.json', 'Unexpected native write')
        value.update(status='QBS_NEW688_OBJECTS9440_DIRECTIONS_NATIVE_NOT_APPLIED', baseline=780,
            physical_bits=4720, bit_directions=9440, source_proof_sha256=PROOF_SHA,
            native_inventory_counts=counts, protected_target_bits=13456,
            qualified128_included=False, HOLD_included=False, population_application=False)
        if path.exists():
            require(json.loads(path.read_bytes()) == value, 'Existing receipt differs')
        else:
            life.save(path, value)
    ns = dict(vars(primitive), parse_el=parse_el, life=SimpleNamespace(**dict(vars(life), save=save)))
    FunctionType(primitive.verify.__code__, ns)(out, seal)


def run(out, seal):
    check(out, seal)
    FunctionType(primitive.run.__code__, dict(vars(primitive), HERE=out, verify=verify))(out, seal)


if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('mode', choices=('prepare', 'check', 'el', 'run', 'verify'))
    cli.add_argument('--output', type=Path, required=True)
    cli.add_argument('--seal')
    cli.add_argument('--file')
    a = cli.parse_args()
    out = a.output.resolve()
    if a.mode == 'prepare': prepare(out)
    elif a.mode == 'el':
        print(json.dumps(dict(bit_directions=len(parse_el((out / a.file).read_text(), json.loads((out / 'config.json').read_bytes()))))))
    else:
        {'check': check, 'run': run, 'verify': verify}[a.mode](out, a.seal)
        if a.mode == 'check': print('QBS9440_PREPARED_CHECK_PASS_NO_EDA')
