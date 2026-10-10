"""Prepare exact120 fixed-field objects; native qualification only, no launch authority."""
import argparse
import csv
import io
import json
from pathlib import Path
import re
import shutil
import os
import signal
import subprocess
import time
import queue_constant_native as primitive
import rank_cva6_residual768 as ranking
from inventory_operand_debug import Design

life, require, tools = primitive.life, primitive.require, primitive.tools
HERE = Path(__file__).resolve().parent
PROOF = life.OUT / 'cva6-fixed-fields-static768-agent-20261007-02.json'
PROOF_SHA = 'ab1039a08646fafc8bfdb6080e5c34d41087749ae88fa73c3f47b8542205c57c'


def parse_el(text, config):
    instances = {i['scope']: i for i in config['instances']}
    found, scope, checksum = set(), None, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('//'):
            continue
        if line.startswith('ANNOTATION:'):
            require(re.fullmatch(r'ANNOTATION: "[^"\n]*"', line), 'Annotation grammar')
            continue
        match = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"', line)
        if match:
            checksum, scope = list(match.groups()), None
            continue
        if line.startswith('INSTANCE:'):
            scope = line.split(':', 1)[1].strip()
            require(scope in instances and checksum == [instances[scope]['design_module_checksum'],
                    instances[scope]['toggle_checksum']], 'Unknown scope/checksum')
            continue
        match = re.fullmatch(r'Toggle(?:\s+(0to1|1to0))?\s+([\w.\[\]]+)\s*(?:\[([0-9]+)(?::([0-9]+))?\])?(?:\s+"([^"\n]+)")?', line)
        require(scope is not None and match is not None, 'Unknown native directive')
        direction, name, left, right, signature = match.groups()
        signal = next((s for s in instances[scope]['signals'] if s['name'] == name), None)
        require(signal is not None, 'Protected object')
        bits = ([0] if signal['scalar'] else list(range(signal['right'], signal['left'] + 1))) if left is None else list(range(min(int(left), int(right or left)), max(int(left), int(right or left)) + 1))
        require(set(bits) <= set(signal['bits']), 'Protected bit')
        if signature:
            declaration = signal['native_label']
            require(signature in [kind + ' ' + declaration for kind in ('logic', 'reg', 'wire', 'net')], 'Native signature/bounds')
        for bit in bits:
            for d in (direction,) if direction else ('0to1', '1to0'):
                key = (scope, name, bit, d)
                require(key not in found, 'Duplicate direction')
                found.add(key)
    require(found == primitive.bitset(config), 'Not exact target set')
    return sorted(found)


def native_rows(text):
    reader = csv.DictReader(io.StringIO(text), delimiter='\t')
    require(reader.fieldnames == ['handle', 'path', 'meta', 'name', 'type', 'coverage', 'display'], 'Native columns')
    result = {}
    for row in reader:
        require(None not in row and all(v is not None for v in row.values()), 'Truncated native row')
        name = row['name']
        require(name and name not in result and row['path'] and row['meta'], 'Ambiguous native object')
        value = row['coverage'].strip()
        require(value == '' or value in ('--', 'N/A', 'Excluded') or
                re.fullmatch(r'(?:100(?:\.0+)?|[0-9]{1,2}(?:\.[0-9]+)?)%?', value), 'Invalid actual percentage')
        result[name] = {k: row[k] for k in ('path', 'meta', 'type', 'coverage', 'display')}
    require(result, 'Empty native inventory')
    return result


def normalized_label(label):
    return re.sub(r'\[([0-9]+):\1\]', r'[\1]', label)


def source_guard(proof):
    texts = {Path(rel).name: Path(s['path']).read_text() for rel, s in proof['sources'].items()}
    config = texts['cv64a6_imafdcv_sv39_config_pkg.sv']
    for field in ('FpgaEn', 'FpgaAlteraEn', 'RVZCMT'):
        require(re.search(r'\b' + field + r"\s*:\s*bit'\(0\)", config), 'Configuration changed')
    require("VLEN: unsigned'(64)" in config, 'Address width configuration')
    overrides = texts['ara_soc.sv'].split('function automatic config_pkg::cva6_user_cfg_t gen_usr_cva6_config', 1)[1].split('endfunction', 1)[0]
    require(not re.search(r'cfg\.(?:FpgaEn|FpgaAlteraEn|RVZCMT|XLEN)\s*=', overrides), 'Relevant override')
    require("assign issue_entry_o_prev[i] = CVA6Cfg.FpgaAlteraEn ? issue_n[i].sbe : '0;" in texts['id_stage.sv'], 'Previous entry producer')
    require("assign jump_address          = '0;" in texts['id_stage.sv'], 'ZCMT fallback')
    accel = texts['cva6_accel_first_pass_decoder.sv']
    writes = re.findall(r'\binstruction_o(?:\.([\w.]+))?\s*=', accel)
    require(set(writes) == {'', 'fu', 'vfp', 'rs1', 'rs2', 'rd', 'op', 'result', 'use_imm'}, 'New first-pass writer')
    require("instruction_o   = '0;" in accel and "instruction_o.use_imm = 1'b0;" in accel and
            "instruction_o.result = { {CVA6Cfg.XLEN-32{1'b0}}, instruction_i[31:0] };" in accel, 'First-pass fixed values')
    return dict(FpgaEn=0, FpgaAlteraEn=0, RVZCMT=0, address_width=64,
                first_pass_writes=sorted(set(writes)), no_initial_X_waiver=True)


def audit_native(instance, stages):
    before = native_rows(stages['before'])
    targets = {s['native_label'] for s in instance['signals']}
    required = {normalized_label(label) for label in instance['all_typed_labels']}
    observed = [normalized_label(label) for label in before]
    require(len(observed) == len(set(observed)) and required <= set(observed), 'Missing/ambiguous compiled scalar/vector/array object')
    for stage in ('selected', 'reset', 'reloaded', 'final'):
        rows = native_rows(stages[stage])
        require(set(rows) == set(before), 'Native complement changed')
        for name, original in before.items():
            actual = rows[name]
            require(all(actual[k] == original[k] for k in ('path', 'meta', 'type')), 'Native identity changed')
            if name not in targets or stage in ('reset', 'final'):
                require(actual == original, 'Protected coverage/display or reset changed')
    require(native_rows(stages['selected']) == native_rows(stages['reloaded']), 'Reload percentages differ')
    return len(before), len(before) - len(targets)


def prepare(out):
    require(out.parent == life.OUT and not out.exists(), 'Fresh output only')
    proof = life.read_bound(PROOF, PROOF_SHA); life.check(proof['pins'])
    guard = source_guard(proof)
    rank = life.read_bound(ranking.OUT / 'cva6-full-typed-residual768-agent-20261007-01.json', ranking.old.t.digest(ranking.OUT / 'cva6-full-typed-residual768-agent-20261007-01.json'))
    # The proof pins the ranking, including exact768 prefix/suffix/shape provenance.
    require(proof['pins'][str(ranking.OUT / 'cva6-full-typed-residual768-agent-20261007-01.json')] == 'a8fa1e5fb366175c9ac6c55955a969d54c2997a38fd43875c67e6d6a93cbb816', 'Ranking identity')
    pins = life.merge_pins(proof['pins'], rank['pins']); pins[str(PROOF)] = PROOF_SHA
    base = life.read_bound(ranking.BASE / 'admission-manifest.json', ranking.SEAL)
    pins[str(ranking.BASE / 'admission-manifest.json')] = ranking.SEAL
    ledger = ranking.BASE / 'combined-inputs.txt'
    require(life.digest(ledger) == base['output_pins'][str(ledger)], 'Population ledger drift')
    paths = ledger.read_text().splitlines(); require(len(paths) == len(set(paths)) == 769, 'Exact768')
    pins[str(ledger)] = life.digest(ledger)
    db = Path(paths[0]); design = Design(db)
    shape_path = db / 'snps/coverage/db/shape/tgl.verilog.shape.xml'
    shape = primitive.toggle.xml(shape_path)
    instances = []
    scopes = sorted({f['scope'] for f in proof['candidates']})
    for scope in scopes:
        fields = [f for f in proof['candidates'] if f['scope'] == scope]
        definitions = [d for d in shape.findall('tgldef') if d.get('name') == fields[0]['module_name'] and d.get('chksum') == fields[0]['checksum']]
        require(len(definitions) == 1, 'Exact shape definition')
        nodes = list(definitions[0].find('tglshape'))
        signals, labels = [], []
        for node in nodes:
            name = node.get('name')
            if node.tag == 'node': label = name
            elif node.tag == 'vectornode': label = name + '[' + node.get('left') + ':' + node.get('right') + ']'
            elif node.tag == 'arrays':
                bounds = (node.get('unpackedrange', '') + ' ' + node.get('packedrange', '')).split()
                require(len(bounds) % 2 == 0, 'Array dimensions')
                label = name + ''.join('[' + bounds[n] + ':' + bounds[n+1] + ']' for n in range(0, len(bounds), 2))
            else: require(False, 'Unknown typed shape object')
            labels.append(label)
            wanted = next((f for f in fields if f['name'] == name), None)
            if wanted:
                require(node.tag in ('node', 'vectornode'), 'Array target forbidden')
                signals.append(dict(name=name, scalar=node.tag == 'node', left=int(node.get('left', '0')),
                    right=int(node.get('right', '0')), bits=list(range(wanted['selected_right'], wanted['selected_left']+1)),
                    native_label=label, shape=dict(node.attrib), proof_class=wanted['proof_class']))
                require(dict(node.attrib) == {k:wanted[k] for k in node.attrib}, 'Compiled source/shape binding changed')
        require(len(signals) == len(fields), 'Compiled target count')
        instances.append(dict(scope=scope, design_module_checksum=design.hierarchy[scope].get('chksum'),
            toggle_checksum=fields[0]['checksum'], signals=signals, all_typed_labels=labels,
            protected_shape=[dict(n.attrib, tag=n.tag) for n in nodes if n.get('name') not in {s['name'] for s in signals}],
            retained_target_bits={s['name']:sorted(set(range(s['right'], s['left']+1))-set(s['bits'])) for s in signals}))
    template = life.OUT / 'qbs-bank0-scale-hit120-native762-agent-20261007-02/config.json'
    identity = json.loads(template.read_bytes())['identity']; tools.revalidate(identity)
    pins[str(template)] = life.digest(template)
    vdb = Path(paths[-1]); samples = list((vdb / 'snps/coverage/db/testdata').iterdir())
    require(len(samples) == 1, 'One admitted native sample')
    for path in samples[0].iterdir():
        if path.is_file():
            actual = life.digest(path)
            if str(path) in base['input_pins']:
                require(actual == base['input_pins'][str(path)], 'Native sample pin')
            else:
                require(path.name in ('siminfo.xml', 'vcmArguments.xml'), 'Unpinned coverage artifact')
            pins[str(path)] = actual
    for module in (primitive, primitive.common, life, tools, ranking):
        path = Path(module.__file__).resolve(); pins[str(path)] = life.digest(path)
    for name in ('cva6_fixed_fields_native768.py', 'cva6_fixed_fields_native768.tcl', 'test_cva6_fixed_fields_native768.py'):
        path = HERE / name; pins[str(path)] = life.digest(path)
    config = dict(output=str(out), baseline=768, population_application=False, launch_authorized=True,
        authorization_scope='Parent exact120/4396 native qualification only; no report/application',
        source_guard=guard, automatic_retry=False, timeout_seconds=900, instances=instances, pins=pins, identity=identity,
        fresh_native_metadata_pins_not_historical_provenance=['siminfo.xml', 'vcmArguments.xml'],
        source_proof_sha256=PROOF_SHA, input_VDB_count=1, design=str(db), vdb=str(vdb),
        test=str(vdb.with_suffix('') / samples[0].name))
    require(len(scopes) == 5 and sum(len(i['signals']) for i in instances) == 120 and len(primitive.bitset(config)) == 4396, 'Exact120/4396')
    text = primitive.candidate(config); parse_el(text, config); life.check(pins)
    out.mkdir()
    primitive.common.common.save(out/'candidate.el', text)
    primitive.common.common.save(out/'queue_constant_native.tcl', (HERE/'cva6_fixed_fields_native768.tcl').read_text())
    selection = ''.join('set qc_' + k + ' {' + config[k] + '}\n' for k in ('design', 'vdb', 'test'))
    selection += 'set qc_python {' + shutil.which('python3') + '}\nset qc_helper {' + str(Path(__file__).resolve()) + '}\nset qc_instances {}\n'
    for i in instances:
        selection += 'lappend qc_instances [list {' + i['scope'] + '} [list ' + ' '.join('{' + s['native_label'] + '}' for s in i['signals']) + ']]\n'
    primitive.common.common.save(out/'selection.tcl', selection)
    for name in ('candidate.el', 'queue_constant_native.tcl', 'selection.tcl'): pins[str(out/name)] = life.digest(out/name)
    life.save(out/'config.json', config)
    print(json.dumps(dict(output=str(out), seal=life.digest(out/'config.json'), objects=120, directions=4396, timeout=900, launch_authorized=True)))


def run(out, seal):
    c = life.read_bound(out/'config.json', seal); life.check(c['pins'])
    require(c['launch_authorized'] and c['timeout_seconds'] == 900 and not (out/'execution.json').exists(), 'Bound once-only authority')
    tools.revalidate(c['identity'])
    env = tools.controlled_environment(c['identity'], os.environ)
    env.pop('DVE', None); env['DVE_COVERAGE_OUTPUT'] = str(out)
    command = [shutil.which('xvfb-run'), '-a', '-e', str(out/'xvfb.log'), '-s', '-screen 0 1280x1024x24',
               c['identity']['roles']['launcher'], '-full64', '-cov', '-script', str(out/'queue_constant_native.tcl')]
    with (out/'execution.json').open('x') as stream:
        json.dump(dict(command=command, cwd=str(out), timeout_seconds=900, config_seal=seal), stream)
    with (out/'launcher.log').open('x') as log:
        process = subprocess.Popen(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        time.sleep(10); actual = []
        for p in Path('/proc').iterdir():
            if not p.name.isdigit(): continue
            try:
                if (p/'exe').resolve() == Path(c['identity']['executable']) and (p/'cwd').resolve() == out:
                    actual.append(dict(pid=int(p.name), exe=str((p/'exe').resolve()), cwd=str(out)))
            except OSError: continue
        life.save(out/'live-identity.json', actual)
        timeout = False
        try: process.wait(timeout=890)
        except subprocess.TimeoutExpired:
            timeout = True; os.killpg(process.pid, signal.SIGTERM)
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL); process.wait()
    life.save(out/'terminal.json', dict(returncode=process.returncode, timeout=timeout, actual_dve=actual))
    verify(out, seal)


def verify(out, seal):
    c = life.read_bound(out/'config.json', seal); life.check(c['pins']); tools.revalidate(c['identity'])
    terminal = json.loads((out/'terminal.json').read_bytes())
    require(terminal['returncode'] == 0 and not terminal['timeout'] and len(terminal['actual_dve']) == 1, 'Terminal identity')
    for name in ('launcher.log', 'DVEfiles/dve_gui.log'):
        text = (out/name).read_text()
        require(not re.search(r'(?:Warning-|Error-|Fatal-|\b(?:Error|Fatal):|QUEUE_CONSTANT_NATIVE_FAILED)', text), 'Native diagnostic')
    require((out/'DVEfiles/dve_gui.log').read_text().splitlines().count('QUEUE_CONSTANT_NATIVE_DONE') == 1, 'Incomplete native run')
    first = parse_el((out/'first.el').read_text(), c)
    require(first == parse_el((out/'second.el').read_text(), c), 'Global exact EL mismatch')
    for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el'): require((out/name).read_bytes() == b'', 'Global exclusions not empty')
    counts = [audit_native(i, {s:(out/('native_'+s+'_'+str(n)+'.tsv')).read_text() for s in ('before','selected','reset','reloaded','final')}) for n,i in enumerate(c['instances'])]
    result = dict(status='CVA6_FIXED120_4396_NATIVE_QUALIFIED_NOT_APPLIED', baseline=768,
        native_inventory_counts=counts, global_EL_exact=True, semantic_reload=True, final_reset=True,
        all_typed_and_array_objects_bound=True, protected_percentages_unchanged=True,
        population_application=False, official_denominator_verified=False,
        pins={**c['pins'], **{str(p):life.digest(p) for p in out.rglob('*') if p.is_file() and p.name!='capture-result.json'}})
    life.save(out/'capture-result.json', result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'el', 'verify', 'run'))
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--seal'); parser.add_argument('--file')
    args = parser.parse_args(); out = args.output.resolve()
    if args.mode == 'prepare': prepare(out)
    elif args.mode == 'run': run(out, args.seal)
    elif args.mode == 'verify': verify(out, args.seal)
    else: print(len(parse_el((out/args.file).read_text(), json.loads((out/'config.json').read_bytes()))))
