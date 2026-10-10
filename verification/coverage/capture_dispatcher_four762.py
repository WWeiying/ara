"""Four source-proven transitions, one historical sample, native qualification only."""
import argparse
import csv
import io
import json
from pathlib import Path
import re
import types

import qualify_dwc_points742 as runner
import audit_fsm741_exact as native

life, require, tools = runner.life, runner.require, runner.tools
HERE = Path(__file__).resolve().parent
TCL = Path(__file__).with_suffix('.tcl')
AUDIT = life.OUT / 'dispatcher17-static-reachability-762-agent-20261007-01.json'
AUDIT_SHA = 'f2ea39ba3f4563f02d65844b1cf3afa74400d7e581c1ea593589494db1be5166'
BASE = life.OUT / 'load-ni-tlb-offline-admitted-762-agent-20261007-01'
TARGETS = {31, 32, 34, 37}


def groups(shape, bits, scope):
    metric = bits['metrics']['fsm'][scope]
    require(metric['width'] == 92 and metric['checksum'] == '1099616778', 'Wrong module identity')
    defs = [d for d in shape.iter('fsmdef') if d.get('chksum') == metric['checksum']
            and any(i.get('name') == scope for i in d.findall('fsminst'))]
    require(len(defs) == 1, 'Ambiguous compiled instance')
    result, offset, chosen = [], 0, set()
    for machine in defs[0].iter('fsmfsm'):
        ids = {s.get('id'): s.get('name') for s in machine.findall('state')}
        for mode, nodes in [('State', machine.findall('state')), ('Transition', machine.findall('transition'))]:
            rows = []
            for item in nodes:
                source = ids[item.get('fromid')] if mode == 'Transition' else None
                dest = ids[item.get('toid')] if mode == 'Transition' else item.get('name')
                target = offset in TARGETS
                if target:
                    require(machine.get('name') == 'state_q' and mode == 'Transition' and
                            source == 'OVERLAP_ISSUE_ORIGINAL' and not
                            ((int(metric['bits'], 16) >> (91-offset)) & 1), 'Wrong/hit target')
                    chosen.add(offset)
                rows.append(dict(name=source+'->'+dest if source else dest, raw_index=offset,
                                 target=target, source=source, destination=dest, attributes=dict(item.attrib)))
                offset += 1
            require(len({r['name'] for r in rows}) == len(rows), 'Duplicate native selector')
            result.append(dict(scope=scope, checksum=metric['checksum'], machine=dict(machine.attrib),
                               mode=mode, rows=rows))
    require(offset == 92 and chosen == TARGETS, 'Incomplete exact inventory')
    return result


def prepare(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh output required')
    a = life.read_bound(AUDIT, AUDIT_SHA)
    pins = {str(life.ROOT / p): sha for p, sha in a['pins'].items()}
    pins[str(AUDIT)] = AUDIT_SHA
    life.check(pins)
    require(a['population'] == 762 and set(a['summary']['proved_unreachable_candidates']) == TARGETS,
            'Static approval scope differs')
    book = json.loads((BASE / 'admission-manifest.json').read_bytes())
    bits = life.read_bound(BASE / 'combined-bits.json', book['output_pins'][str(BASE / 'combined-bits.json')])
    ledger_path = BASE / 'combined-inputs.txt'
    pins[str(ledger_path)] = book['output_pins'][str(ledger_path)]
    ledger = ledger_path.read_text().splitlines()
    require(ledger[1:] == bits['tests'] and len(ledger) == len(set(ledger)) == 763, 'Not exact762 membership')
    design, sample = Path(ledger[0]), Path(ledger[1])
    roots = [design, sample]
    membership = {}
    for root in roots:
        require(root.resolve() == root and root.is_dir(), 'Aliased VDB root')
        files = sorted(p for p in root.rglob('*') if p.is_file())
        require(files and not any(p.is_symlink() for p in root.rglob('*')), 'Empty/aliased VDB')
        membership[str(root)] = [str(p.relative_to(root)) for p in files]
        inherited = life.merge_pins(book['input_pins'], book['output_pins'])
        for p in files:
            sha = life.digest(p)
            require(str(p) not in inherited or inherited[str(p)] == sha, 'Historical sample/design pin differs')
            pins[str(p)] = sha
    tests = sorted(p for p in (sample/'snps/coverage/db/testdata').iterdir() if p.is_dir())
    require(len(tests) == 1, 'Not one sample')
    selected = str(sample.with_suffix('') / tests[0].name)
    shape_path = design/'snps/coverage/db/shape/fsm.verilog.shape.xml'
    require(pins[str(shape_path)] == bits['design']['shape/fsm.verilog.shape.xml'], 'Design shape pin differs')
    gs = groups(native.read_xml(shape_path), bits, a['scope'])
    actual = {r['raw_index']: r for g in gs for r in g['rows'] if r['target']}
    for r in a['remaining']:
        if r['raw_position'] in TARGETS:
            require(actual[r['raw_position']]['name'] == r['name'] and
                    actual[r['raw_position']]['attributes']['fromid'] == r['native_fromid'] and
                    actual[r['raw_position']]['attributes']['toid'] == r['native_toid'], 'Proof/native identity differs')
    plan = dict(groups=gs, targets=4, protected=88, strategy='direct-transition-only-66',
                point_query_authority='saved-native-identity')
    expected = native.expected_records(plan, native.Design(design))
    rawpath, rawsha = runner.native.inherited.admission.RAW, runner.native.inherited.admission.RAW_SHA
    raw = life.read_bound(rawpath, rawsha); pins[str(rawpath)] = rawsha
    tools.revalidate(raw['tool_identity'])
    dependencies = [Path(__file__).resolve(), TCL, HERE/'test_capture_dispatcher_four762.py',
                    HERE/'fsm741_transition_native.tcl', HERE/'fsm741_transition_batch.tcl',
                    HERE/'fsm741_native_singleton.tcl', HERE/'fsm741_native_probe.tcl',
                    HERE/'discover_ptw_pmp0_fsm_v2.tcl', HERE/'apply_points740_v4.tcl',
                    Path(runner.__file__).resolve(), Path(native.__file__).resolve(), Path(tools.__file__).resolve(),
                    Path(life.__file__).resolve(), HERE/'inventory_operand_debug.py', HERE/'closure_point_inventory.py']
    for p in dependencies: pins[str(p)] = life.digest(p)
    source = life.OUT/'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
    lines = ['set fx_groups {}\n']
    for g in gs:
        fields = [g['scope'], str(source), g['machine']['name'], g['mode']]
        names = ' '.join(runner.atom(r['name']) for r in g['rows'])
        targets = ' '.join(runner.atom(r['name']) for r in g['rows'] if r['target'])
        lines.append('lappend fx_groups [list '+' '.join(map(runner.atom, fields))+
                     ' [list '+names+'] [list '+targets+']]\n')
    lines += ['set '+k+' '+runner.atom(v)+'\n' for k,v in
              dict(d4_design=design, d4_sample=sample, d4_selected=selected).items()]
    life.check(pins)
    out.mkdir()
    (out/'selection.tcl').write_text(''.join(lines))
    pins[str(out/'selection.tcl')] = life.digest(out/'selection.tcl')
    c = dict(schema='DISPATCHER_EXACT4_NATIVE_762_V1', output=str(out), pins=pins, plan=plan,
             expected_records=expected, identity=raw['tool_identity'], input_membership=membership,
             sample_inputs=[str(p) for p in roots], selected=selected, baseline=762,
             sample_population=1, population_application=False, automatic_retry=False,
             remaining13_protected=True, states_explicitly_excluded=False,
             query_projection='Applied/reloaded state display inheritance is observation only; EL must contain only four direct transitions.',
             annotation=native.ANNOTATION, timeout_seconds=900)
    life.save(out/'config.json', c)
    print(json.dumps(dict(status='PREPARED_NO_DVE', output=str(out), seal=life.digest(out/'config.json'))), flush=True)


def verify(out, seal, prepared=False):
    c = life.read_bound(out/'config.json', seal)
    require(c['schema'] == 'DISPATCHER_EXACT4_NATIVE_762_V1' and c['output'] == str(out), 'Wrong capture binding')
    life.check(c['pins']); tools.revalidate(c['identity'])
    for root, members in c['input_membership'].items():
        require(sorted(str(p.relative_to(root)) for p in Path(root).rglob('*') if p.is_file()) == members,
                'VDB membership changed')
    if prepared: return
    terminal = json.loads((out/'terminal.json').read_bytes())
    require(terminal['returncode'] == 0 and not terminal['timeout'] and terminal['actual_dve'], 'Failed terminal')
    require(not (out/'error.txt').exists() and not (out/'cleanup-error.txt').exists(), 'Native failure')
    log = (out/'DVEfiles/dve_gui.log').read_text()
    require(log.splitlines().count('DISPATCHER_FOUR_NATIVE_DONE') == 1 and not
            re.search(r'DISPATCHER_FOUR_FAILED|UCAPI-DLMA|DVCDT136|EK-CMD-|Load Failed|Error:|Fatal:', log), 'Native log failure')
    require("The design '%s' was loaded successfully." % c['sample_inputs'][0] in log, 'Design not loaded')
    expected = [tuple(r) for r in c['expected_records']]
    for name in ('first.el', 'second.el'):
        require(native.native_records((out/name).read_text()) == expected, 'Missing/extra/native signature differs')
    for name in ('initial.el', 'reset.el', 'final-empty.el', 'cleanup-empty.el'):
        require((out/name).read_bytes() == b'', 'Global reset not empty')
    native.audit_points(list(csv.reader(io.StringIO((out/'exact-audit.tsv').read_text()), delimiter='\t')), c['plan'])
    pins = {str(p):life.digest(p) for p in out.rglob('*') if p.is_file() and
            p.name not in ('capture-result.json', 'worker.log', 'service.log')}
    life.save(out/'capture-result.json', dict(status='EXACT_DISPATCHER4_NATIVE_ROUNDTRIP_NOT_APPLICATION_APPROVAL',
              config_seal=seal, baseline=762, sample_population=1, targets=4, protected=88,
              native_records=expected, five_stages=True, semantic_reload=True, finalreset=True,
              remaining13_protected=True, state_display_observation_only=True,
              population_application=False, input_pins=c['pins'], output_pins=pins))
    print('QUALIFIED seal='+life.digest(out/'capture-result.json'), flush=True)


def run(out, seal):
    # Reuse the reviewed managed one-shot launcher without altering its module globals.
    ns = dict(runner.run.__globals__, verify=verify, TCL=TCL)
    types.FunctionType(runner.run.__code__, ns)(out, seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'check', 'run', 'verify'))
    p.add_argument('--output', type=Path, required=True); p.add_argument('--seal')
    a = p.parse_args(); out = a.output.absolute()
    if a.mode == 'prepare': prepare(out)
    else:
        require(a.seal, 'Exact seal required')
        if a.mode == 'run': run(out, a.seal)
        else: verify(out, a.seal, a.mode == 'check')
