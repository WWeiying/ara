"""One bank/plane/slot/row partial native qualification, never aggregate apply."""
import argparse
import csv
import io
import json
from pathlib import Path
import re
import sys
from types import FunctionType, SimpleNamespace

import qbs_even_hit_native762 as reuse

primitive, life, tools, require = reuse.primitive, reuse.life, reuse.tools, reuse.require
HERE = Path(__file__).resolve().parent
PROOF = life.OUT / 'qbs-main-hit-congruence780-bank0-p2-slot1-row0-agent-20261008-02.json'
PROOF_SHA = '23e6d07d94580fb63025509708a37104f78b5cfb5f191214cb27aae1128375fe'
TEMPLATE = life.OUT / 'qbs-even-hit19328-native762-agent-20261007-01'
TEMPLATE_SHA = 'f4f88c4ec1650881dc04858cc24b8950bf96d3241210a887aae41370a159c720'
RECEIPT_SHA = 'bf06c26430b00c7201916f564531c6860ee431bee1c0cf5dc151384a323760c7'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.i_compute_engine.i_block_adapter_bank0.i_payload_buffer'
PREFIX = 'gen_write_merge[1].gen_bank_plane[2].gen_bank_row[0].gen_byte_merge'
parse_el = reuse.parse_el


def target_names():
    return {PREFIX + '[' + str(lane) + '].hit': [2, 6, 10, 14] for lane in range(1, 32, 2)}


def instances(proof, template, definition):
    require(proof['population'] == 780 and proof['no_EDA'] is True and
            proof['native_qualification'] is False, 'Proof authority')
    selected = [(r['signal'], r['bit']) for r in proof['records']
                if r['classification'] == 'SOURCE_MAPPING_ZERO_NATIVE_REQUIRED']
    wanted = target_names()
    require(len(selected) == len(set(selected)) == 64 and
            set(selected) == {(n, b) for n, bits in wanted.items() for b in bits}, 'Exact64 proof bits')
    require(all(r['scope'] == SCOPE and r['checksum'] == '3657545390' and
                len(r['raw_coordinates']) == 2 and r['mapping_witness'] is None
                for r in proof['records'] if r['classification'] == 'SOURCE_MAPPING_ZERO_NATIVE_REQUIRED'),
            'Target source/scope/zero binding')
    nodes = {n.get('name'): n for n in definition.find('tglshape')}
    require(len(nodes) == len(list(definition.find('tglshape'))) == 3193, 'Complete compiled complement')
    prior = [i for i in template['instances'] if i['scope'] == SCOPE]
    require(len(prior) == 1 and prior[0]['toggle_checksum'] == '3657545390', 'Exact prior native owner')
    signals = []
    for name, bits in sorted(wanted.items()):
        n = nodes[name]
        require(n.tag == 'vectornode' and n.get('left') == '15' and n.get('right') == '0'
                and n.get('line_num') == '269' and n.get('portnode') == '0', 'Hit source declaration')
        signals.append(dict(name=name, bits=bits, scalar=False, left=15, right=0,
                            native_label=name + '[15:0]', shape=dict(n.attrib)))
    return [dict(scope=SCOPE, design_module_checksum=prior[0]['design_module_checksum'],
        toggle_checksum='3657545390', signals=signals,
        protected=[dict(n.attrib, tag=n.tag) for name, n in nodes.items() if name not in wanted],
        retained_target_signal_bits={n: sorted(set(range(16)) - set(b)) for n, b in wanted.items()})]


def check(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    require(c['output'] == str(out) and c['baseline'] == 780 and c['population_application'] is False
            and c['source_proof_sha256'] == PROOF_SHA, 'Configuration owner')
    life.check(c['pins'])
    p = life.read_bound(PROOF, PROOF_SHA)
    t = life.read_bound(TEMPLATE / 'config.json', TEMPLATE_SHA)
    shape = primitive.toggle.xml(Path(c['shape_path']))
    defs = [d for d in shape.iter('tgldef') if d.get('name') == 'qbs_payload_buffer'
            and d.get('chksum') == '3657545390']
    require(len(defs) == 1 and c['instances'] == instances(p, t, defs[0]), 'Exact target/complement changed')
    require(len(primitive.bitset(c)) == 128 and c['protected_direction_count'] == 66212,
            'Full binary complement count')
    parse_el((out / 'candidate.el').read_text(), c)
    tools.revalidate(c['identity'])
    return c


def prepare(out):
    require(out.parent == life.OUT and not out.exists(), 'Fresh independent output required')
    p = life.read_bound(PROOF, PROOF_SHA)
    life.check(p['pins'])
    t = life.read_bound(TEMPLATE / 'config.json', TEMPLATE_SHA)
    q = life.read_bound(TEMPLATE / 'capture-result.json', RECEIPT_SHA)
    require(q['status'] == 'QBS_EVEN_START9664_BITS19328_NATIVE_ROUNDTRIP_NOT_APPLICATION'
            and q['semantic_reload'] is True and q['global_final_empty'] is True, 'Qualified native template')
    shape_path = next(Path(k) for k in p['pins'] if k.endswith('/shape/tgl.verilog.shape.xml'))
    shape = primitive.toggle.xml(shape_path)
    defs = [d for d in shape.iter('tgldef') if d.get('name') == 'qbs_payload_buffer'
            and d.get('chksum') == '3657545390']
    require(len(defs) == 1, 'Compiled bank definition')
    pins = dict(p['pins'])
    # Only consume the template's tool/design/sample identity, not its old targets.
    for path in (PROOF, TEMPLATE / 'config.json', TEMPLATE / 'capture-result.json',
                 Path(__file__).resolve(), HERE / 'test_qbs_hit128_native780.py',
                 Path(reuse.__file__).resolve(), Path(primitive.__file__).resolve(),
                 HERE / 'queue_constant_native.tcl'):
        pins[str(path)] = life.digest(path)
    for path, sha in t['pins'].items():
        if path.startswith(t['design'] + '/') or path.startswith(t['vdb'] + '/') or path.endswith(('.py', '.tcl')):
            require(path not in pins or pins[path] == sha, 'Conflicting source/design pin')
            pins[path] = sha
    c = dict(output=str(out), baseline=780, population_application=False,
             source_proof_sha256=PROOF_SHA, pins=pins, identity=t['identity'],
             design=t['design'], vdb=t['vdb'], test=t['test'], input_VDB_count=1,
             instances=instances(p, t, defs[0]), shape_path=str(shape_path),
             physical_bits=64, bit_directions=128, protected_direction_count=66212,
             protected_target_vector_bits=192, timeout_seconds=1800, automatic_retry=False,
             witness_scope='DIRECT/FILL only; no read start28 claim for context REUSE',
             protection='Exact global EL excludes only128 directions; all3193 rows preserved in5stages')
    tools.revalidate(c['identity'])
    text = primitive.candidate(c)
    parse_el(text, c)
    values = dict(qc_design=c['design'], qc_vdb=c['vdb'], qc_test=c['test'],
                  qc_python=sys.executable, qc_helper=str(Path(__file__).resolve()))
    require(all(v and not any(x in v for x in '{}\\\n\r') for v in values.values()), 'Unsafe Tcl value')
    selection = ''.join('set ' + k + ' {' + v + '}\n' for k, v in values.items())
    selection += 'set qc_instances {}\n'
    labels = ' '.join('{' + s['native_label'] + '}' for s in c['instances'][0]['signals'])
    selection += 'lappend qc_instances [list {' + SCOPE + '} [list ' + labels + ']]\n'
    life.check(pins)
    out.mkdir()
    for name, contents in (('candidate.el', text), ('selection.tcl', selection),
                           ('queue_constant_native.tcl', (HERE / 'queue_constant_native.tcl').read_text())):
        primitive.common.common.save(out / name, contents)
        pins[str(out / name)] = life.digest(out / name)
    life.save(out / 'config.json', c)
    seal = life.digest(out / 'config.json')
    check(out, seal)
    print(json.dumps(dict(output=str(out), seal=seal, physical_bits=64, directions=128,
                         protected_objects=3177, protected_target_bits=192, EDA_started=False)))


def audit_inventory(instance, stages):
    nodes = instance['protected'] + [dict(s['shape'], tag='vectornode') for s in instance['signals']]
    targets = {s['native_label'] for s in instance['signals']}
    baseline = None
    for stage in ('before', 'selected', 'reset', 'reloaded', 'final'):
        reader = csv.DictReader(io.StringIO(stages[stage]), delimiter='\t')
        require(reader.fieldnames == ['handle', 'path', 'meta', 'name', 'column1', 'column2'], 'Native TSV schema')
        rows = {}
        for row in reader:
            require(None not in row and all(v is not None for v in row.values()) and row['name'] not in rows,
                    'Truncated/duplicate native object')
            rows[row['name']] = {k: row[k] for k in ('path', 'meta', 'name', 'column1', 'column2')}
        used = set()
        for n in nodes:
            name = n['name']
            label = name if n['tag'] == 'node' else name + '[' + n['left'] + ':' + n['right'] + ']'
            choices = [label]
            if n['tag'] == 'vectornode' and n['left'] == n['right']:
                choices += [name, name + '[' + n['left'] + ']']
            matches = [x for x in choices if x in rows]
            require(len(matches) == 1 and matches[0] not in used, 'Compiled/native object missing or ambiguous: ' + label)
            used.add(matches[0])
            require(rows[matches[0]]['path'] == rows[matches[0]]['meta'] == matches[0], 'Native signature')
        require(used == set(rows), 'Extra native object')
        if baseline is None:
            baseline = rows
        else:
            require(set(rows) == set(baseline), 'Inventory drift')
            for name in rows:
                keys = ('path', 'meta', 'name') if name in targets and stage in ('selected', 'reloaded') else tuple(rows[name])
                require(all(rows[name][k] == baseline[name][k] for k in keys), 'Protected/reset display drift')
        if stage == 'selected':
            selected = rows
        if stage == 'reloaded':
            require(rows == selected, 'Reload native display differs')
    return [len(baseline), len(baseline) - len(targets)]


def verify(out, seal):
    c = check(out, seal)
    terminal = json.loads((out / 'terminal.json').read_bytes())
    require(type(terminal['returncode']) is int and terminal['returncode'] == 0
            and type(terminal['timeout']) is bool and terminal['timeout'] is False
            and len(terminal['actual_dve']) == 1, 'Strict native terminal')
    actual = terminal['actual_dve'][0]
    require(type(actual['pid']) is int and actual['pid'] > 0 and actual['cwd'] == str(out)
            and actual['exe'] == c['identity']['executable'], 'Actual DVE executable/output')
    for name in ('launcher.log', 'DVEfiles/dve_gui.log'):
        require(re.search(r'(?:Error-|Fatal-|Warning-|\b(?:Error|Fatal):)', (out / name).read_text()) is None,
                'Native diagnostic: ' + name)
    counts = audit_inventory(c['instances'][0], {s: (out / ('native_' + s + '_0.tsv')).read_text()
                                               for s in ('before', 'selected', 'reset', 'reloaded', 'final')})
    def save(path, value):
        value.update(status='QBS_BANK0_P2_SLOT1_ROW0_EXACT128_NATIVE_NOT_APPLIED', baseline=780,
                     physical_bits=64, bit_directions=128, source_proof_sha256=PROOF_SHA,
                     native_inventory_counts=counts, protected_target_bits=192, population_application=False)
        if path.exists():
            require(json.loads(path.read_bytes()) == value, 'Existing qualification differs')
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
    if a.mode == 'el':
        c = json.loads((out / 'config.json').read_bytes())
        print(json.dumps(dict(bit_directions=len(parse_el((out / a.file).read_text(), c)))))
    else:
        if a.mode == 'prepare':
            prepare(out)
        else:
            {'check': check, 'run': run, 'verify': verify}[a.mode](out, a.seal)
        if a.mode == 'check':
            print('QBS128_PREPARED_CHECK_PASS_NO_EDA')
