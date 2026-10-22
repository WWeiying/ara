"""Actual-EL successor: encoded FSM states and paired scalar Toggle directions.

Original failed session is immutable. No offline promotion of its missing stages.
"""
import contextlib
import io
import json
from pathlib import Path
import re

import qualify_dwc_points742 as base

OLD_SCRIPT, OLD_TCL, OLD_TEST = base.SCRIPT, base.TCL, base.TEST
FAILED = base.life.OUT / 'dwc31-fsm168-toggle-native742-agent-20261007-01'
original_inventory, original_prepare = base.inventory, base.prepare


def inventory(review):
    c = original_inventory(review)
    shape = base.proof.t.xml(base.proof.DB / 'shape/fsm.verilog.shape.xml')
    definition = next(d for d in shape.iter('fsmdef') if any(
        i.get('name') == review['scope'] for i in d.findall('fsminst')))
    values = {(m.get('name'), s.get('name')): str(int(s.get('value'), 16))
              for m in definition.iter('fsmfsm') for s in m.findall('state')}
    records = []
    for r in c['fsm_records']:
        r = list(r)
        names = r[6].split('->')
        r[7] = '->'.join(values[(r[3], n)] for n in names)
        records.append(r)
    c['fsm_records'] = records
    complete = []
    scope, module, checksum = records[0][:3]
    for m in definition.iter('fsmfsm'):
        ids = {s.get('id'): s.get('name') for s in m.findall('state')}
        for s in m.findall('state'):
            complete.append((scope, module, checksum, m.get('name'), m.get('chksum'),
                             'State', s.get('name'), values[(m.get('name'), s.get('name'))]))
        for a in m.findall('transition'):
            names = [ids[a.get('fromid')], ids[a.get('toid')]]
            complete.append((scope, module, checksum, m.get('name'), m.get('chksum'), 'Transition',
                             '->'.join(names), '->'.join(values[(m.get('name'), n)] for n in names)))
    base.require(len(complete) == 39 and len(set(complete) - {tuple(r) for r in records}) == 8,
                 'Complete protected FSM graph differs')
    c['fsm_complete_records'] = complete
    c['native_format'] = 'OBSERVED_SCALAR_DIRECTION_PAIRS_AND_ENCODED_STATE_SIGNATURES'
    return c


def parse_el(text, c):
    wanted_fsm = {tuple(r) for r in c['fsm_records']}
    wanted_tgl = {(t['scope'], t['module'], t['checksum'], t['signal']): t for t in c['toggles']}
    found_fsm, found_tgl = set(), {}
    scope = checksum = machine = machine_sha = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('//'): continue
        if line.startswith('ANNOTATION:'):
            base.require(re.fullmatch(r'ANNOTATION: "[^"\r\n]*"', line), 'Malformed annotation')
            continue
        m = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"', line)
        if m:
            checksum = m.groups(); scope = machine = machine_sha = None; continue
        if line.startswith('INSTANCE: '):
            base.require(checksum is not None, 'Unbound instance')
            scope = line[len('INSTANCE: '):]; machine = machine_sha = None; continue
        m = re.fullmatch(r'Fsm (\w+) "(\d+)"', line)
        if m: machine, machine_sha = m.groups(); continue
        m = re.fullmatch(r'(State|Transition) (\S+) "([0-9]+(?:->[0-9]+)?)"', line)
        if m:
            base.require(checksum and scope and machine, 'Unbound FSM')
            record = (scope, *checksum, machine, machine_sha, *m.groups())
            base.require(record in wanted_fsm and record not in found_fsm, 'Wrong/duplicate FSM signature')
            found_fsm.add(record); continue
        m = re.fullmatch(r'Toggle (?:(0to1|1to0) )?([\w.]+) "((?:logic|reg|wire) ([\w.]+)(?:\[([0-9]+):([0-9]+)\])?)"', line)
        base.require(m is not None and checksum and scope, 'Unexpected exclusion record: ' + line)
        direction, name, declaration, declared, left, right = m.groups()
        key = (scope, *checksum, name)
        base.require(key in wanted_tgl and name == declared, 'Unapproved Toggle/interface identity')
        target = wanted_tgl[key]
        suffix = '[%s:%s]' % (left, right) if left is not None else ''
        base.require(name + suffix == target['label'], 'Wrong Toggle bounds')
        base.require(direction is None or (target['width'] == 1 and left is None),
                     'Unobserved vector partial-direction format')
        for d in ((direction,) if direction else ('0to1', '1to0')):
            k = key + (d,)
            base.require(k not in found_tgl, 'Duplicate/overlapping Toggle direction')
            found_tgl[k] = declaration
    # DVE compresses selected states plus incident transitions into State directives.
    # Expand only within this exact compiled graph; any extra protected point rejects.
    closure = set(found_fsm)
    for state in found_fsm:
        if state[5] != 'State': continue
        for raw_arc in c['fsm_complete_records']:
            arc = tuple(raw_arc)
            if arc[:5] == state[:5] and arc[5] == 'Transition' and state[6] in arc[6].split('->'):
                closure.add(arc)
    base.require(closure == wanted_fsm, 'Missing/extra FSM state/arc closure')
    base.require(set(found_tgl) == {k + (d,) for k in wanted_tgl for d in ('0to1', '1to0')},
                 'Missing/extra Toggle direction')
    per_bit = []
    for k, declaration in found_tgl.items():
        target = wanted_tgl[k[:4]]
        bounds = re.search(r'\[(\d+):(\d+)\]$', target['label'])
        bits = range(min(map(int, bounds.groups())), max(map(int, bounds.groups())) + 1) if bounds else (0,)
        per_bit.extend(('tgl',) + k + (str(bit), declaration) for bit in bits)
    base.require(len(per_bit) == len(set(per_bit)) == 168, 'Not exact168 per-bit directions')
    return sorted([('fsm',) + r for r in closure] + per_bit)


def prepare(out):
    c = inventory(json.loads(base.REVIEW.read_bytes()))
    first = (FAILED / 'first.el').read_bytes()
    parse_el(first.decode('utf-8'), c)
    extra = {str(p): base.life.digest(p) for p in [OLD_SCRIPT, OLD_TCL, OLD_TEST,
             FAILED / 'config.json', FAILED / 'first.el', FAILED / 'terminal.json', FAILED / 'error.txt']}
    save = base.life.save

    def bound_save(path, data):
        if path == out / 'config.json':
            with (out / 'candidate.el').open('xb') as stream:
                stream.write(first)
            extra[str(out / 'candidate.el')] = base.life.digest(out / 'candidate.el')
            data = dict(data, pins=base.life.merge_pins(data['pins'], extra),
                        predecessor_status='HOLD_PARSER_FORMAT_MISSING_FIVE_STAGES',
                        state_arc_authority='Exact complete39 compiled incident graph; normal8 retained',
                        candidate_reused_native_export=True, GUI_point_selection_repeated=False)
        save(path, data)

    base.life.save = bound_save
    try:
        with contextlib.redirect_stdout(io.StringIO()): original_prepare(out)
    finally: base.life.save = save
    c = json.loads((out / 'config.json').read_bytes())
    print(json.dumps(dict(output=str(out), seal=base.life.digest(out / 'config.json'), pins=len(c['pins']))))


base.inventory, base.parse_el, base.prepare = inventory, parse_el, prepare
base.SCRIPT = Path(__file__).resolve()
base.TCL = base.SCRIPT.with_suffix('.tcl')
base.TEST = base.SCRIPT.with_name('test_qualify_dwc_points742_v2.py')

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'check', 'run', 'inspect', 'el'))
    p.add_argument('--output', type=Path, required=True); p.add_argument('--seal'); p.add_argument('--file')
    a = p.parse_args(); out = a.output.absolute()
    if a.mode == 'prepare': prepare(out)
    elif a.mode == 'el':
        base.require(a.file in ('first.el', 'second.el'), 'Unapproved EL')
        print(json.dumps(dict(semantic_records=len(parse_el((out / a.file).read_text(),
                                                           json.loads((out / 'config.json').read_bytes()))))))
    else:
        base.require(a.seal, 'Exact seal required')
        if a.mode == 'run': base.run(out, a.seal)
        else: base.verify(out, a.seal, a.mode == 'check')
