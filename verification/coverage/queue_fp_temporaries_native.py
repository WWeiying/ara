"""One local typed-object qualification of only16 compiled FPU0 queues."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import re
from types import FunctionType
import capture_cast168_native as lifecycle
import queue_fp_temporaries_static as source

life, require, tools = lifecycle.life, lifecycle.require, lifecycle.tools
HERE = Path(__file__).resolve().parent
REVIEW = life.OUT/'queue-disabled-fp-temporaries-static-parent-20261007-01.json'
REVIEW_SHA = '684da514eab370b59d98764c86ac6a6fb4466808f9c6aff47aa199eee19cf2ee'
STAGES = lifecycle.STAGES
NAME = r'[A-Za-z_]\w*(?:\[\d+\])?\.[A-Za-z_]\w*'


def label(target):
    return target['name'] + ('[%s:%s]' % (target['left'],target['right'])
                             if target['kind'] == 'vectornode' else '')


def instances(review):
    require(review['unambiguous_compiled_scopes'] == 16 and review['held_merged_scopes'] == 8,
            'Exact static clear/HOLD population')
    result = []
    for i in review['instances']:
        if not i['compiled_all_variants_FPU_disabled']: continue
        require(i['decision'] == 'STATIC_DISABLED_CANDIDATE_NATIVE_PENDING' and
                i['logical_bits'] == 96 and len(i['targets']) == 21 and
                {t['name'] for t in i['targets']} == source.fields(), 'Wrong whole21 source fields')
        targets = [dict(t,native_name=label(t)) for t in i['targets']]
        protected = [label(t) for t in i['all_other_objects_protected']]
        require(len(protected) == 43 and len(set(protected+[t['native_name'] for t in targets])) == 64,
                'Full64 compiled complement')
        result.append(dict(scope=i['scope'],toggle_checksum=i['checksum'],
            design_module_checksum='1532764271',targets=targets,protected=protected,
            protected_compiled=i['all_other_objects_protected'],compiled_parameters=i['compiled_parameters']))
    allowed = {'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.i_operand_queues.i_operand_queue_%s' % (l,k)
               for l in range(4) for k in ('st_mask_a','slide_addrgen_a','mask_b','mask_m')}
    require(len(result) == 16 and {i['scope'] for i in result} == allowed, 'Only16 exact FPU0 scopes')
    return result


def contract(c):
    review = life.read_bound(REVIEW,REVIEW_SHA)
    require(c['instances'] == instances(review), 'Source/compiled scope or full-object drift')
    require(c['population_application'] is False and c['timeout_seconds'] == 900, 'Local bounded qualification only')


def typed(meta, target):
    name = target['name']
    bounds = ('[%s:%s]' % (target['left'],target['right']) if target['kind'] == 'vectornode' else '')
    require(meta in ('logic '+name+bounds, 'logic '+bounds+name), 'Exact logic full bounds/name required')
    return 'logic '+name+bounds


def parse_el(text,c,native_meta=None):
    expected = {i['scope']:i for i in c['instances']}
    found = defaultdict(list); scope = checksum = None; blocks = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('//'): continue
        if line.startswith('ANNOTATION:'):
            require(re.fullmatch(r'ANNOTATION: "[^"\r\n]*"',line), 'Malformed annotation')
        elif line.startswith('CHECKSUM:'):
            m = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"',line)
            require(m is not None, 'Typed checksum syntax')
            checksum = m.groups(); scope = None
        elif line.startswith('INSTANCE:'):
            scope = line.split(':',1)[1].strip()
            require(scope in expected and scope not in blocks and checksum ==
                    (expected[scope]['design_module_checksum'],expected[scope]['toggle_checksum']),
                    'Unapproved/duplicate scope/checksum')
            blocks.add(scope)
        else:
            m = re.fullmatch(r'Toggle (?:(0to1|1to0) )?('+NAME+r') "([^"\r\n]+)"',line)
            require(scope is not None and m is not None, 'Typed whole-object syntax only: '+line)
            direction,name,meta = m.groups()
            target = next((t for t in expected[scope]['targets'] if t['name'] == name),None)
            require(target is not None, 'Protected/extra object')
            signature = typed(meta,target)
            if native_meta is not None:
                require(typed(native_meta[scope,name],target) == signature, 'Native metadata drift')
            found[scope,name,checksum,signature].append(direction)
    wanted = {(i['scope'],t['name']) for i in c['instances'] for t in i['targets']}
    require(blocks == set(expected) and len(found) == 336 and {(k[0],k[1]) for k in found} == wanted,
            'Exact complete336 union required')
    for key,directions in found.items():
        require(directions == [None] or (len(directions) == 2 and set(directions) == {'0to1','1to0'}),
                'Incomplete/duplicate/mixed directions: '+key[1])
    return sorted(found)


def inventory(out,c,stage,index):
    require(stage in STAGES and 0 <= index < 16, 'Stage/scope selector')
    with (out/('native_%s_%d.tsv' % (stage,index))).open(newline='') as stream:
        table = list(csv.reader(stream,delimiter='\t'))
    require(table and table[0] == ['handle','path','meta','name'] and
            all(len(r) == 4 and all(r) for r in table[1:]), 'Complete legal native rows')
    rows = [tuple(r[1:]) for r in table[1:]]
    require(rows and len(rows) == len(set(rows)), 'Duplicate native identity')
    names = [r[2] for r in rows]; i = c['instances'][index]
    require(all(names.count(n) == 1 for n in i['protected']+[t['native_name'] for t in i['targets']]),
            'Missing/ambiguous full target/protection inventory')
    byname = {r[2]:r[1] for r in rows}
    for t in i['targets']: typed(byname[t['native_name']],t)
    return sorted(rows)


def check_file(out,c,name):
    if name in ('initial-empty.el','reset-empty.el','final-empty.el'):
        require((out/name).read_bytes() == b'', 'Global exclusion must be empty')
        return 0
    require(name in ('first.el','second.el'), 'EL filename')
    meta = {}
    for idx,i in enumerate(c['instances']):
        byname = {r[2]:r[1] for r in inventory(out,c,'before',idx)}
        meta.update({(i['scope'],t['name']):byname[t['native_name']] for t in i['targets']})
    return len(parse_el((out/name).read_text(),c,meta))


def inspect(out,seal):
    c = life.read_bound(out/'config.json',seal); contract(c); life.check(c['pins'])
    terminal = json.loads((out/'terminal.json').read_bytes())
    require(terminal['returncode'] == 0 and not terminal['timeout'] and len(terminal['actual_dve']) == 1,
            'Actual DVE executable/terminal')
    gui = (out/'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('QUEUE_FP_TEMP_NATIVE_DONE') == 1 and
            'QUEUE_FP_TEMP_NATIVE_FAILED' not in gui and not (out/'error.txt').exists(), 'Five stages incomplete')
    for index in range(16):
        before = inventory(out,c,'before',index)
        for stage in STAGES[1:]:
            require(inventory(out,c,stage,index) == before, 'Full local identity/protection drift')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el','first.el','second.el'):
        check_file(out,c,name)
    require(parse_el((out/'first.el').read_text(),c) == parse_el((out/'second.el').read_text(),c),
            'Exact typed semantic reload')
    pins = life.merge_pins(c['pins'],{str(p):life.digest(p) for p in out.rglob('*') if p.is_file()
        and p.name not in ('worker.log','capture-result.json')})
    result = dict(status='FPU0_QUEUE336_TYPED_FIVE_STAGE_NATIVE_QUALIFIED_NOT_APPLIED',
        scopes=16,objects=336,logical_bits=1536,nominal_direction_slots=3072,
        protected_local_objects=688,ALU_merged_scopes_held=8,source_constant_rationale=True,
        trusted_IEEE_rationale=False,initial_X_excluded=False,population_application=False,
        global_final_reset_empty=True,all_other_metrics_and_scopes_protected=True,pins=pins)
    life.save(out/'capture-result.json',result)
    print(json.dumps(dict(status=result['status'],seal=life.digest(out/'capture-result.json'))),flush=True)


def prepare(out):
    require(out.parent == life.OUT and not out.exists(), 'Fresh local native output')
    review = life.read_bound(REVIEW,REVIEW_SHA); life.check(review['input_pins'])
    source.source_contract((life.ROOT/'hardware/src/lane/operand_queue.sv').read_text())
    config_path = lifecycle.inherited.PRODUCT/'config.json'
    inherited = json.loads(config_path.read_bytes())
    tools.revalidate(inherited['identity'])
    test = Path(inherited['test']); vdb = test.parent.with_suffix('.vdb')
    require(vdb.is_dir() and (vdb/'snps/coverage/db/testdata'/test.name).is_dir(), 'Existing exact native test')
    d = source.Design(source.DESIGN); selected = instances(review)
    require(all(d.hierarchy[i['scope']].get('chksum') == i['design_module_checksum'] for i in selected),
            'Actual compiled module checksum')
    pins = life.merge_pins(review['input_pins'],{str(REVIEW):REVIEW_SHA})
    for p in [config_path,source.BUILD,Path(__file__),HERE/'test_queue_fp_temporaries_native.py',
              HERE/'queue_fp_temporaries_native.tcl',HERE/'fma_datapath_native.tcl',
              Path(lifecycle.__file__),Path(source.__file__),Path(life.__file__),Path(tools.__file__),
              *vdb.rglob('*')]:
        if p.is_file(): pins = life.merge_pins(pins,{str(p.resolve()):life.digest(p)})
    c = dict(output=str(out),instances=selected,pins=pins,identity=inherited['identity'],
        timeout_seconds=900,automatic_retry=False,population_application=False,
        source_review=str(REVIEW),source_review_seal=REVIEW_SHA)
    contract(c); life.check(pins)
    out.mkdir()
    values = dict(fma_design=str(source.DESIGN),fma_vdb=str(vdb),fma_test=str(test),
        fma_python=str(life.ROOT/'verification/tools/soc-venv/bin/python'),
        fma_helper=str(Path(__file__).resolve()),qfp_primitives=str(HERE/'fma_datapath_native.tcl'))
    require(all(not any(ch in v for ch in '{}\\\r\n') for v in values.values()), 'Safe Tcl paths')
    lines = ['set %s {%s}\n' % item for item in values.items()]+['set fma_instances {}\n']
    for index,i in enumerate(selected):
        lines.append('lappend fma_instances [list {%s} {%s} {%s} %d]\n' %
            (i['scope'],' '.join(t['native_name'] for t in i['targets']),' '.join(i['protected']),index))
    with (out/'selection.tcl').open('x') as f: f.write(''.join(lines))
    pins[str(out/'selection.tcl')] = life.digest(out/'selection.tcl')
    life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),pins=len(pins))),flush=True)


class TclRoute:
    def __truediv__(self,name):
        require(name == 'capture_cast168_native.tcl', 'Only inherited runner script entry')
        return HERE/'queue_fp_temporaries_native.tcl'


def run(out,seal):
    # Reuse the established bounded foreground lifecycle without editing it.
    namespace = dict(vars(lifecycle),contract=contract,inspect=inspect,HERE=TclRoute())
    FunctionType(lifecycle.run.__code__,namespace)(out,seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','verify','run','inspect','el','inventory'))
    p.add_argument('--output',type=Path,required=True); p.add_argument('--seal')
    p.add_argument('--file'); p.add_argument('--stage'); p.add_argument('--index',type=int)
    a = p.parse_args(); out = a.output.resolve()
    if a.mode == 'prepare': prepare(out)
    elif a.mode in ('el','inventory'):
        c = json.loads((out/'config.json').read_bytes())
        print(check_file(out,c,a.file) if a.mode == 'el' else len(inventory(out,c,a.stage,a.index)))
    else:
        require(a.seal,'Exact config seal')
        if a.mode == 'verify':
            c = life.read_bound(out/'config.json',a.seal); contract(c); life.check(c['pins'])
            print('VERIFY_PASS')
        else: (run if a.mode == 'run' else inspect)(out,a.seal)
