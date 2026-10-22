"""One exact VMFPU4 states/6 handoffs native session; no population application."""
import argparse
import csv
import json
from pathlib import Path
import re
import types

import audit_vmfpu_remaining_fsm762 as proof
import capture_dispatcher_four762 as prior

life, require, tools, native = prior.life, prior.require, prior.tools, prior.native
HERE = Path(__file__).resolve().parent
TCL = Path(__file__).with_suffix('.tcl')
AUDIT = life.OUT / 'vmfpu-remaining-fsm-source-audit762-agent-20261007-01.json'
AUDIT_SHA = '903a2d0cc805d05ef11482c56e3bcee5944dbe571d2f5e30f6af3cc9f0178c5f'
BASE = proof.rank.BASE


def owner_contract(text):
    proof.source_controls(text)
    require(len(re.findall(r'\bvinsn_queue_d\s*=\s*vinsn_queue_q;', text)) == 1,
            'Whole queue default assignment changed')
    require(re.search(r"\bvinsn_queue_q\s*<=\s*vinsn_queue_d;", text) and
            re.search(r"\bvinsn_queue_q\s*<=\s*'0;", text), 'Queue clock/reset binding changed')
    require(text.count('mfpu_state_d = next_mfpu_state(') == 2 and
            "if (vinsn_queue_d.issue_cnt == '0 && !prevent_commit) begin" in text and
            "if (!is_reduction(vfu_operation_i.op) || (vinsn_queue_d.commit_cnt == '0)) begin" in text,
            'Positive-owner entry gates differ')
    return dict(entry='Accept starts active reduction with count0 then increments to1; '
                      'NO_REDUCTION commit and WAIT successor require issue_d_valid/count>0.',
                hold='Only NO_REDUCTION and WAIT decrement queue issue_cnt; active reduction '
                     'cannot decrement. Accept increments after the count==0 override gate.',
                exit='Reduction must visit WAIT before queue ownership retires; reset goes NO_REDUCTION.',
                counter='vinsn_queue.issue_cnt, NOT per-element issue_cnt',
                parameters='Data/SEW/VL/LMUL/mask/FRM/ready-valid arbitrary within legal known queue protocol; '
                           'positive queue depth symbolic, frozen depth4; lane constants0..3.',
                boundary='No arbitrary X, delta, corrupt queue, or internally forced state claim')


def groups(audit, shape, bits):
    wanted = {(p['scope'], p['raw_position']): p for p in audit['points']
              if p['classification'] != 'REACHABLE_EXTERNAL_RESET_MISSING_PROTECTED'}
    require(len(wanted) == 10, 'Source candidate scope differs')
    defs = [d for d in shape.iter('fsmdef') if d.get('chksum') == '3873291691']
    require(len(defs) == 1, 'Ambiguous VMFPU compiled definition')
    machine = list(defs[0].iter('fsmfsm'))
    require(len(machine) == 1 and machine[0].get('name') == 'mfpu_state_q', 'Wrong FSM machine')
    machine = machine[0]
    ids = {s.get('id'): s.get('name') for s in machine.findall('state')}
    result, chosen = [], set()
    for scope in sorted({k[0] for k in wanted}):
        metric = bits['metrics']['fsm'][scope]
        require(metric['width'] == 37 and metric['checksum'] == '3873291691' and
                any(i.get('name') == scope for i in defs[0].findall('fsminst')), 'Wrong compiled instance')
        offset = 0
        for mode, tag in [('State', 'state'), ('Transition', 'transition')]:
            rows = []
            for item in machine.findall(tag):
                src = ids[item.get('fromid')] if tag == 'transition' else None
                dst = ids[item.get('toid')] if src else item.get('name')
                name = src + '->' + dst if src else dst
                key = (scope, offset)
                target = key in wanted
                if target:
                    p = wanted[key]
                    require(p['machine'] == machine.get('name') and p['kind'] == mode and
                            p['name'] == name and p['source_line'] == item.get('line') and
                            not ((int(metric['bits'], 16) >> (36-offset)) & 1), 'Proof/shape/raw target differs')
                    chosen.add(key)
                rows.append(dict(name=name, raw_index=offset, target=target, source=src,
                                 destination=dst, attributes=dict(item.attrib)))
                offset += 1
            result.append(dict(scope=scope, checksum=metric['checksum'], machine=dict(machine.attrib),
                               mode=mode, rows=rows))
        require(offset == 37, 'Incomplete protected FSM inventory')
    require(chosen == set(wanted) and sum(r['target'] for g in result if g['mode'] == 'State'
                                        for r in g['rows']) == 4, 'Target state/transition count changed')
    reset = {(p['scope'], p['name']) for p in audit['points']
             if p['classification'] == 'REACHABLE_EXTERNAL_RESET_MISSING_PROTECTED'}
    protected = {(g['scope'], r['name']) for g in result for r in g['rows'] if not r['target']}
    require(len(reset) == 20 and reset <= protected, 'A reachable reset arc became a candidate')
    return result


def expected_query(stage, mode, target):
    if stage not in ('applied', 'reloaded'): return '0'
    if target: return 'NATIVE_EL_AUTHORITY'
    return 'STATE_DISPLAY_OBSERVATION' if mode == 'State' else '0'


def audit_points(rows, plan):
    expected = {(stage, g['scope'], g['machine']['name'], g['mode'], r['name']):
                expected_query(stage, g['mode'], r['target'])
                for stage in ('initial', 'applied', 'reset', 'reloaded', 'final')
                for g in plan['groups'] for r in g['rows']}
    found = set()
    for row in rows:
        require(len(row) == 7, 'Native point audit schema')
        key = tuple(row[:5])
        require(key in expected and key not in found and row[6] == expected[key] and
                row[5] in ('0', '1'), 'Missing/duplicate/foreign audit identity')
        if row[6] == '0': require(row[5] == '0', 'Protected/reset arc or state excluded')
        found.add(key)
    require(found == set(expected), 'Five-stage protected inventory incomplete')


def assert_el(text, c):
    require(native.native_records(text) == [tuple(r) for r in c['expected_records']],
            'State expansion or native checksum/value/name/annotation differs')


def prepare(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh output required')
    a = life.read_bound(AUDIT, AUDIT_SHA)
    life.check(a['pins'])
    require(proof.collect() == a, 'Source proof and raw762 changed')
    owner = owner_contract(proof.SOURCE.read_text())
    book = life.read_bound(BASE/'admission-manifest.json', proof.rank.BASE_SHA)
    bits_path = BASE/'combined-bits.json'
    bits = life.read_bound(bits_path, book['output_pins'][str(bits_path)])
    ledger_path = BASE/'combined-inputs.txt'
    ledger = ledger_path.read_text().splitlines()
    require(life.digest(ledger_path) == book['output_pins'][str(ledger_path)] and
            ledger[1:] == bits['tests'] and len(ledger) == len(set(ledger)) == 763, 'Exact762 membership differs')
    design, sample = Path(ledger[0]), Path(ledger[1])
    pins = life.merge_pins(a['pins'], {str(AUDIT): AUDIT_SHA, str(ledger_path): life.digest(ledger_path)})
    inherited = life.merge_pins(book['input_pins'], book['output_pins'])
    membership = {}
    for root in (design, sample):
        require(root.resolve() == root and root.is_dir() and not
                any(p.is_symlink() for p in root.rglob('*')), 'Aliased VDB')
        files = sorted(p for p in root.rglob('*') if p.is_file())
        require(files, 'Empty VDB')
        membership[str(root)] = [str(p.relative_to(root)) for p in files]
        for p in files:
            digest = life.digest(p)
            require(str(p) not in inherited or inherited[str(p)] == digest, 'Historical VDB pin drift')
            pins[str(p)] = digest
    tests = list((sample/'snps/coverage/db/testdata').iterdir())
    require(len(tests) == 1 and tests[0].is_dir(), 'Not one historical sample')
    selected = str(sample.with_suffix('') / tests[0].name)
    shape = design/'snps/coverage/db/shape/fsm.verilog.shape.xml'
    require(pins[str(shape)] == bits['design']['shape/fsm.verilog.shape.xml'], 'FSM design drift')
    plan = dict(groups=groups(a, native.read_xml(shape), bits), targets=10, protected=138,
                point_query_authority='saved-native-identity', reachable_reset_arcs_protected=20)
    expected = native.expected_records(plan, native.Design(design))
    rawpath, rawsha = prior.runner.native.inherited.admission.RAW, prior.runner.native.inherited.admission.RAW_SHA
    raw = life.read_bound(rawpath, rawsha)
    tools.revalidate(raw['tool_identity'])
    dependencies = [Path(__file__).resolve(), TCL, HERE/'test_capture_vmfpu_ten762.py',
                    Path(prior.__file__), Path(prior.runner.__file__), Path(native.__file__),
                    Path(tools.__file__), Path(life.__file__), HERE/'fsm741_transition_batch.tcl',
                    HERE/'fsm741_native_singleton.tcl', HERE/'fsm741_native_probe.tcl',
                    HERE/'discover_ptw_pmp0_fsm_v2.tcl', HERE/'apply_points740_v4.tcl',
                    HERE/'inventory_operand_debug.py', HERE/'closure_point_inventory.py', rawpath]
    for p in dependencies: pins[str(p.resolve())] = life.digest(p)
    lines = ['set fx_groups {}\n']
    atom = prior.runner.atom
    for g in plan['groups']:
        fields = [g['scope'], str(proof.SOURCE), g['machine']['name'], g['mode']]
        lines.append('lappend fx_groups [list '+' '.join(map(atom, fields))+' [list '+
                     ' '.join(atom(r['name']) for r in g['rows'])+'] [list '+
                     ' '.join(atom(r['name']) for r in g['rows'] if r['target'])+']]\n')
    lines += ['set '+k+' '+atom(v)+'\n' for k,v in
              dict(v10_design=design, v10_sample=sample, v10_selected=selected).items()]
    life.check(pins)
    out.mkdir()
    (out/'selection.tcl').write_text(''.join(lines))
    pins[str(out/'selection.tcl')] = life.digest(out/'selection.tcl')
    c = dict(schema='EXACT_VMFPU10_NATIVE_762', output=str(out), plan=plan, pins=pins,
             source_proof_sha256=AUDIT_SHA, queue_owner_contract=owner,
             expected_records=expected, identity=raw['tool_identity'], input_membership=membership,
             sample_inputs=[str(design), str(sample)], selected=selected, baseline=762,
             sample_population=1, timeout_seconds=900, population_application=False,
             automatic_retry=False, annotation=native.ANNOTATION,
             state_expansion_forbidden=True, protected_reset_arcs=20,
             non_target_states='EL direct membership authority; GUI inheritance observation only')
    life.save(out/'config.json', c)
    print(json.dumps(dict(output=str(out), seal=life.digest(out/'config.json'), pins=len(pins))), flush=True)


def verify(out, seal, prepared=False):
    c = life.read_bound(out/'config.json', seal)
    require(c['schema'] == 'EXACT_VMFPU10_NATIVE_762' and c['output'] == str(out) and
            c['source_proof_sha256'] == AUDIT_SHA and c['protected_reset_arcs'] == 20 and
            c['plan']['targets'] == 10 and c['plan']['protected'] == 138 and
            c['state_expansion_forbidden'] and not c['population_application'], 'Exact capture contract differs')
    life.check(c['pins']); tools.revalidate(c['identity'])
    require(c['queue_owner_contract'] == owner_contract(proof.SOURCE.read_text()), 'Owner proof drift')
    for root, names in c['input_membership'].items():
        require(sorted(str(p.relative_to(root)) for p in Path(root).rglob('*') if p.is_file()) == names,
                'VDB membership changed')
    if prepared:
        print('PREPARED_PINS_PASS'); return
    terminal = json.loads((out/'terminal.json').read_bytes())
    require(terminal['returncode'] == 0 and not terminal['timeout'] and terminal['actual_dve'], 'Terminal failure')
    require(not (out/'error.txt').exists() and not (out/'cleanup-error.txt').exists(), 'Native failure')
    log = (out/'DVEfiles/dve_gui.log').read_text()
    require(log.splitlines().count('VMFPU_TEN_NATIVE_DONE') == 1 and not
            re.search(r'VMFPU_TEN_FAILED|UCAPI-DLMA|DVCDT136|EK-CMD-|Load Failed|Error:|Fatal:', log), 'Native log failure')
    require("The design '%s' was loaded successfully." % c['sample_inputs'][0] in log, 'Design not loaded')
    for name in ('first.el', 'second.el'): assert_el((out/name).read_text(), c)
    for name in ('initial.el', 'reset.el', 'final-empty.el', 'cleanup-empty.el'):
        require((out/name).read_bytes() == b'', 'Global reset not empty')
    audit_points(list(csv.reader((out/'exact-audit.tsv').open(), delimiter='\t')), c['plan'])
    output_pins = {str(p):life.digest(p) for p in out.rglob('*') if p.is_file() and
                   p.name not in ('capture-result.json', 'worker.log')}
    life.save(out/'capture-result.json', dict(status='EXACT_VMFPU4_STATES_6_HANDOFFS_NATIVE_QUALIFIED_NOT_APPLIED',
        config_seal=seal, baseline=762, sample_population=1, targets=10, protected=138,
        protected_reachable_reset_arcs=20, native_records=c['expected_records'],
        queue_owner_contract=c['queue_owner_contract'], source_proof_sha256=AUDIT_SHA,
        five_stages=True, semantic_reload=True, global_empty=True, state_expansion_rejected=True,
        population_application=False, input_pins=c['pins'], output_pins=output_pins))
    print('QUALIFIED seal='+life.digest(out/'capture-result.json'), flush=True)


def run(out, seal):
    ns = dict(prior.runner.run.__globals__, verify=verify, TCL=TCL)
    types.FunctionType(prior.runner.run.__code__, ns)(out, seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'check', 'run', 'verify'))
    p.add_argument('--output', type=Path, required=True); p.add_argument('--seal')
    a = p.parse_args(); out = a.output.absolute()
    if a.mode == 'prepare': prepare(out)
    else:
        require(a.seal, 'Exact config seal required')
        if a.mode == 'run': run(out, a.seal)
        else: verify(out, a.seal, a.mode == 'check')
