"""Exact bank0 scale-hit120 native qualification; no population application."""
import argparse
import json
from pathlib import Path
import re
import shutil
from types import FunctionType, SimpleNamespace

import queue_constant_native as primitive
import prove_qbs_activation_scale_hit762 as proof

life, tools, require = primitive.life, primitive.tools, primitive.require
HERE = Path(__file__).resolve().parent
PROOF = life.OUT/'qbs-bank0-scale-hit120-proof762-agent-20261007-01.json'
PROOF_SHA = '2e9c4d179835967bfdf4e2de78aad879add5d3917906de6047799d5bb1bf73ac'
BASE = life.OUT/'load-ni-tlb-offline-admitted-762-agent-20261007-01'
BASE_SHA = '6959f676c022f38f9ee2977252c600cfeb5b89fe50b3c4b22d08bf5de7b95cc5'
PRIMITIVE_SHA = '1686e5f9cb896530648eefd3aca8b0f4a273b4f24c89337dd36ed2e1d8bbb8c1'


def parse_el(text, config):
    instances = {i['scope']:i for i in config['instances']}
    found, scope, checksum = set(), None, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('//'): continue
        if line.startswith('ANNOTATION:'):
            require(re.fullmatch(r'ANNOTATION: "[^"\n]*"',line), 'Malformed annotation')
            continue
        if line.startswith('CHECKSUM:'):
            m = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"',line)
            require(m is not None, 'Checksum grammar')
            checksum, scope = list(m.groups()), None
            continue
        if line.startswith('INSTANCE:'):
            scope = line.split(':',1)[1].strip()
            require(scope in instances and checksum == [instances[scope]['design_module_checksum'],
                                                       instances[scope]['toggle_checksum']], 'Scope/checksum')
            continue
        m = re.fullmatch(r'Toggle(?:\s+(0to1|1to0))?\s+([\w.\[\]]+)\s*(?:\[([0-9]+)(?::([0-9]+))?\])?(?:\s+"([^"\n]+)")?',line)
        require(scope is not None and m is not None, 'Unknown native EL directive: '+line)
        direction, name, left, right, signature = m.groups()
        signal = next((s for s in instances[scope]['signals'] if s['name'] == name),None)
        require(signal is not None, 'Protected signal')
        bits = list(range(32)) if left is None else list(range(min(int(left),int(right or left)),
                                                              max(int(left),int(right or left))+1))
        require(set(bits) <= set(signal['bits']), 'Protected hit bit / whole-vector exclusion')
        if signature:
            require(signature in ('net '+name+'[31:0]', 'wire '+name+'[31:0]'), 'Native wire declaration mismatch')
        for bit in bits:
            for d in (direction,) if direction else ('0to1','1to0'):
                key = scope,name,bit,d
                require(key not in found, 'Duplicate native bit-direction')
                found.add(key)
    require(found == primitive.bitset(config), 'Incomplete/extra native bit-direction set')
    return sorted(found)


def checked_config(out, seal):
    c = life.read_bound(out/'config.json',seal)
    require(c['baseline'] == 762 and c['output'] == str(out) and not c['population_application'], 'Config identity')
    life.check(c['pins'])
    require(len(primitive.bitset(c)) == 240 and len(c['instances']) == 2, 'Exact120 both-bank protection contract')
    require(len(c['instances'][0]['signals']) == 15 and c['instances'][1]['signals'] == [], 'Bank1 cannot have targets')
    parse_el((out/'candidate.el').read_text(),c)
    return c


def prepare(out):
    require(out.parent == life.OUT and not out.exists(), 'Fresh independent output required')
    require(life.digest(Path(primitive.__file__)) == PRIMITIVE_SHA, 'Frozen native primitive drift')
    p = life.read_bound(PROOF,PROOF_SHA)
    life.check(p['pins'])
    require(p['status'] == 'SOURCE_PROVEN_EXACT120_BITS_NATIVE_QUALIFICATION_REQUIRED' and
            p['direction_count'] == 240 and len(p['targets']) == 120 and not p['native_receipt'], 'Wrong source certificate')
    manifest = life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    bits = life.read_bound(BASE/'combined-bits.json',manifest['output_pins'][str(BASE/'combined-bits.json')])
    require(len(bits['tests']) == len(set(bits['tests'])) == 762, 'Exact formal762 population')
    identity = json.loads((life.OUT/'fma-product-native-fp32-agent-20261007-01/config.json').read_bytes())['identity']
    tools.revalidate(identity)
    design = Path(str(life.IMAGE)+'.vdb')
    d = primitive.Design(design)
    db = design/'snps/coverage/db'
    shape = primitive.toggle.xml(db/'shape/tgl.verilog.shape.xml')
    info = primitive.toggle.xml(db/'shape/tgl.verilog.info.xml')
    info_checks = {n.get('name'):n.get('chksum') for n in info.iter('instance_data')}
    defs = [x for x in shape.iter('tgldef') if x.get('name') == 'qbs_payload_buffer']
    require(len(defs) == 1 and defs[0].get('chksum') == '3657545390', 'Compiled definition')
    nodes = {n.get('name'):n for n in defs[0].find('tglshape')}
    require(len(nodes) == 3193, 'Compiled complete signal inventory')
    scopes = sorted(p['missing_direction_accounting'])
    instances = []
    for scope in scopes:
        wanted = {}
        for t in p['targets']:
            if t['scope'] == scope: wanted.setdefault(t['signal'],[]).append(t['bit'])
        signals = []
        for name, selected in sorted(wanted.items()):
            n = nodes[name]
            require(n.tag == 'vectornode' and n.get('left') == '31' and n.get('right') == '0' and
                    n.get('line_num') == '381' and len(selected) == len(set(selected)), 'Target native shape')
            signals.append(dict(name=name,bits=sorted(selected),scalar=False,left=31,right=0,
                                native_label=name+'[31:0]',shape=dict(n.attrib)))
        require(scope in d.hierarchy and info_checks.get(scope) == '3657545390', 'Exact compiled scope/checksum missing')
        instances.append(dict(scope=scope,design_module_checksum=d.hierarchy[scope].get('chksum'),
            toggle_checksum='3657545390',signals=signals,
            protected=[dict(n.attrib) for name,n in nodes.items() if name not in wanted],
            retained_target_signal_bits={name:sorted(set(range(32))-set(selected)) for name,selected in wanted.items()}))
    pins = dict(p['pins'])
    pins[str(PROOF)] = PROOF_SHA
    pins[str(BASE/'admission-manifest.json')] = BASE_SHA
    pins[str(BASE/'combined-bits.json')] = manifest['output_pins'][str(BASE/'combined-bits.json')]
    for rel in ('design/verilog.design.xml','shape/tgl.verilog.shape.xml','shape/tgl.verilog.info.xml'):
        path = db/rel
        sha = life.digest(path)
        expected = bits['design'].get(rel,pins.get(str(path)))
        if rel != 'shape/tgl.verilog.info.xml':
            require(expected is not None and expected == sha, 'Formal/source compiled design mismatch')
        pins[str(path)] = sha
    vdb = life.OUT/'qbs-affine-min-slot15-old-image-agent-20261007-02/code.vdb'
    require(str(vdb) in bits['tests'], 'Representative is not admitted historical PASS')
    tests = list((vdb/'snps/coverage/db/testdata').iterdir())
    require(len(tests) == 1, 'One representative test required')
    for path in vdb.rglob('*'):
        if path.is_file(): pins[str(path)] = life.digest(path)
    for path in (Path(__file__).resolve(),HERE/'test_qbs_scale_hit_native762.py',
                 Path(primitive.__file__),HERE/'queue_constant_native.tcl'):
        pins[str(path)] = life.digest(path)
    c = dict(output=str(out),baseline=762,pins=pins,identity=identity,instances=instances,
        timeout_seconds=1800,population_application=False,automatic_retry=False,
        input_VDB_count=1,design=str(design),vdb=str(vdb),test=str(vdb.with_suffix('')/tests[0].name),
        source_certificate_sha256=PROOF_SHA,non_target_compiled_signal_count=6371,
        protected_direction_count=132440,
        protected_target_vector_bits=360,native_binding_required=True)
    candidate = primitive.candidate(c)
    parse_el(candidate,c)
    life.check(pins)
    out.mkdir()
    primitive.common.common.save(out/'candidate.el',candidate)
    # Identical sealed primitive, copied into the private runner's script root.
    primitive.common.common.save(out/'queue_constant_native.tcl',(HERE/'queue_constant_native.tcl').read_text())
    values = dict(qc_design=c['design'],qc_vdb=c['vdb'],qc_test=c['test'],
                  qc_python=shutil.which('python3'),qc_helper=str(Path(__file__).resolve()))
    require(all(v and not any(x in v for x in '{}\\\n\r') for v in values.values()), 'Unsafe Tcl binding')
    lines = ['set '+k+' {'+v+'}\n' for k,v in values.items()]+['set qc_instances {}\n']
    for i in instances:
        labels = ' '.join('{'+s['native_label']+'}' for s in i['signals'])
        lines.append('lappend qc_instances [list {'+i['scope']+'} [list '+labels+']]\n')
    primitive.common.common.save(out/'selection.tcl',''.join(lines))
    for name in ('candidate.el','selection.tcl','queue_constant_native.tcl'):
        pins[str(out/name)] = life.digest(out/name)
    life.save(out/'config.json',c)
    checked_config(out,life.digest(out/'config.json'))
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),bits=120,directions=240)))


def verify(out, seal):
    c = checked_config(out,seal)
    tools.revalidate(c['identity'])
    require(not (out/'error.txt').exists(), 'Native diagnostic failure')
    for name in ('launcher.log','DVEfiles/dve_gui.log'):
        text = (out/name).read_text()
        require(re.search(r'(?:Error-|Fatal-|Warning-|\b(?:Error|Fatal):)',text) is None,
                'Native launcher/GUI diagnostic: '+name)
    def save(path, value):
        if path == out/'capture-result.json':
            value.update(status='QBS_BANK0_SCALE_HIT120_EXACT_NATIVE_ROUNDTRIP_NOT_APPLICATION',
                baseline=762,physical_bits=120,bit_directions=240,bank1_protected=True,
                source_certificate_sha256=PROOF_SHA,protected_target_vector_bits=360)
            if path.exists():
                require(life.read_bound(path,life.digest(path)) == value, 'Existing native receipt differs')
                return
        life.save(path,value)
    namespace = dict(vars(primitive),parse_el=parse_el)
    namespace['life'] = SimpleNamespace(**dict(vars(life),save=save))
    FunctionType(primitive.verify.__code__,namespace)(out,seal)


def run(out, seal):
    checked_config(out,seal)
    namespace = dict(vars(primitive),HERE=out,verify=verify)
    FunctionType(primitive.run.__code__,namespace)(out,seal)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode',choices=('prepare','check','run','verify','el'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seal')
    parser.add_argument('--file')
    args = parser.parse_args()
    out = args.output.resolve()
    if args.mode == 'prepare': prepare(out)
    elif args.mode == 'check':
        checked_config(out,args.seal)
        print('QBS_SCALE_HIT120_NATIVE_PREPARED_CHECK_PASS_NO_EDA')
    elif args.mode == 'el':
        c = json.loads((out/'config.json').read_bytes())
        print(json.dumps(dict(bit_directions=len(parse_el((out/args.file).read_text(),c)))))
    else: (run if args.mode == 'run' else verify)(out,args.seal)


if __name__ == '__main__': main()
