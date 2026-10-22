"""One local native session for exact DWC31 FSM / 32 Toggle objects (168 directions)."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

import fma_product_native as native
import review_dwc_internal_error742 as proof

life, require, tools = native.life, native.require, native.tools
HERE = Path(__file__).resolve().parent
SCRIPT = Path(__file__).resolve()
TCL = SCRIPT.with_suffix('.tcl')
TEST = HERE / 'test_qualify_dwc_points742.py'
REVIEW = life.OUT / 'dwc-internal-error742-source-proof-agent-20261007-01.json'
REVIEW_SHA = '968927e24bd550c938739b9a6bb66eaf9c2c5e1faaacf608fb25495743245e8a'


def atom(value):
    require(not any(c in str(value) for c in '{}\\\n\r'), 'Unsafe Tcl value')
    return '{' + str(value) + '}'


def inventory(review):
    design = proof.t.xml(proof.DB / 'design/verilog.design.xml')
    nodes = {i.get('id'): (i, m) for m in design.findall('srcdef') for i in m.findall('srcinst')}

    def path(key):
        i, _ = nodes[key]
        return (path(i.get('pid')) + '.' if i.get('pid') in nodes else '') + i.get('name')

    modules = {path(k): m.get('chksum') for k, (_, m) in nodes.items()}
    shape = proof.t.xml(proof.DB / 'shape/fsm.verilog.shape.xml')
    definitions = [d for d in shape.iter('fsmdef') if d.get('chksum') == review['compiled_fsm_checksum']
                   and any(i.get('name') == review['scope'] for i in d.findall('fsminst'))]
    require(len(definitions) == 1, 'Ambiguous compiled FSM')
    groups, records = [], []
    for machine in definitions[0].iter('fsmfsm'):
        ids = {s.get('id'): s.get('name') for s in machine.findall('state')}
        for mode, tag in [('State', 'state'), ('Transition', 'transition')]:
            rows = []
            for item in machine.findall(tag):
                name = item.get('name') if tag == 'state' else ids[item.get('fromid')] + '->' + ids[item.get('toid')]
                signature = item.get('id') if tag == 'state' else item.get('fromid') + '->' + item.get('toid')
                points = [p for p in review['fsm_points'] if p['machine'] == machine.get('name') and
                          p['kind'] == tag and (p.get('state') if tag == 'state' else
                          p['from_state'] + '->' + p['to_state']) == name]
                require(len(points) == 1, 'Source/compiled point differs')
                rows.append(dict(name=name, target=points[0]['candidate']))
                if points[0]['candidate']:
                    records.append((review['scope'], modules[review['scope']], review['compiled_fsm_checksum'],
                                    machine.get('name'), machine.get('chksum'), mode, name, signature))
            groups.append(dict(machine=machine.get('name'), mode=mode, rows=rows))
    toggles = []
    for p in review['toggle_candidates']:
        a = p['attributes']
        require(a['portnode'] == '0', 'Interface exclusion forbidden')
        label = p['signal'] + ('[%s:%s]' % (a['left'], a['right']) if 'left' in a else '')
        toggles.append(dict(scope=p['scope'], module=modules[p['scope']], checksum=p['checksum'],
                            signal=p['signal'], label=label, width=p['width']))
    require(len(records) == 31 and len(toggles) == 32 and sum(t['width'] * 2 for t in toggles) == 168,
            'Exact candidate count differs')
    return dict(groups=groups, fsm_records=records, toggles=toggles)


def parse_el(text, config):
    allowed_fsm = {tuple(r) for r in config['fsm_records']}
    allowed_tgl = {(t['scope'], t['module'], t['checksum'], t['signal']): t for t in config['toggles']}
    checksum = scope = machine = machine_sha = None
    found = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('//'):
            continue
        if line.startswith('ANNOTATION:'):
            require(re.fullmatch(r'ANNOTATION: "[^"\r\n]*"', line), 'Malformed annotation')
            continue
        match = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"', line)
        if match:
            checksum = match.groups(); scope = machine = machine_sha = None
            continue
        if line.startswith('INSTANCE: '):
            scope = line[len('INSTANCE: '):]
            require(checksum is not None, 'Unbound instance')
            machine = machine_sha = None
            continue
        match = re.fullmatch(r'Fsm (\w+) "(\d+)"', line)
        if match:
            machine, machine_sha = match.groups()
            continue
        match = re.fullmatch(r'(State|Transition) (\S+) "([0-9]+(?:->[0-9]+)?)"', line)
        if match:
            require(scope is not None and checksum is not None and machine is not None, 'Unbound FSM point')
            key = (scope, *checksum, machine, machine_sha, *match.groups())
            require(key in allowed_fsm, 'Unapproved FSM identity/signature')
            key = ('fsm',) + key
        else:
            match = re.fullmatch(r'Toggle ([\w.]+) "((?:logic|reg|wire) ([\w.]+)(?:\[([0-9]+):([0-9]+)\])?)"', line)
            require(match is not None and scope is not None and checksum is not None,
                    'Unexpected exclusion record: ' + line)
            name, declaration, declared, left, right = match.groups()
            k = (scope, *checksum, name)
            require(k in allowed_tgl and name == declared, 'Unapproved Toggle/interface/scope')
            target = allowed_tgl[k]
            suffix = '[%s:%s]' % (left, right) if left is not None else ''
            require(name + suffix == target['label'], 'Toggle width/bounds differ')
            key = ('tgl',) + k + (declaration,)
        require(key not in found, 'Duplicate native exclusion')
        found.add(key)
    require(len([r for r in found if r[0] == 'fsm']) == 31 and
            len([r for r in found if r[0] == 'tgl']) == 32, 'Missing/extra native candidate')
    return sorted(found)


def prepare(out):
    require(out.parent == life.OUT and not out.exists(), 'Fresh output required')
    review = life.read_bound(REVIEW, REVIEW_SHA)
    life.check(review['input_pins'])
    inv = inventory(review)
    raw = life.read_bound(native.inherited.admission.RAW, native.inherited.admission.RAW_SHA)
    tools.revalidate(raw['tool_identity'])
    manifest = life.read_bound(proof.BASE / 'admission-manifest.json', proof.BASE_SHA)
    vdb = Path(json.loads((proof.BASE / 'combined-bits.json').read_bytes())['tests'][-1])
    tests = list((vdb / 'snps/coverage/db/testdata').iterdir())
    require(len(tests) == 1 and str(vdb) in (proof.BASE / 'combined-inputs.txt').read_text().splitlines(),
            'Not one admitted742 VDB')
    pins = life.merge_pins(review['input_pins'], {str(REVIEW): REVIEW_SHA,
                          str(native.inherited.admission.RAW): native.inherited.admission.RAW_SHA})
    for p in [SCRIPT, TCL, TEST, HERE / 'fsm741_transition_batch.tcl', HERE / 'fsm741_native_singleton.tcl',
              HERE / 'fsm741_native_probe.tcl', HERE / 'discover_ptw_pmp0_fsm_v2.tcl',
              HERE / 'apply_points740_v4.tcl',
              Path(tools.__file__).resolve(), *tests[0].glob('*.data.xml')]:
        pins = life.merge_pins(pins, {str(p): life.digest(p)})
    require(manifest['input_pins'][str(tests[0] / 'fsm.verilog.data.xml')] == pins[str(tests[0] / 'fsm.verilog.data.xml')],
            'Historical FSM input differs')
    out.mkdir()
    lines = ['set dw_groups {}\n', 'set dw_toggles {}\n']
    for group in inv['groups']:
        names = ' '.join(atom(r['name']) for r in group['rows'])
        targets = ' '.join(atom(r['name']) for r in group['rows'] if r['target'])
        values = [review['scope'], str(life.ROOT / 'hardware/deps/axi/src/axi_atop_filter.sv'),
                  group['machine'], group['mode']]
        lines.append('lappend dw_groups [list ' + ' '.join(atom(v) for v in values) +
                     ' [list ' + names + '] [list ' + targets + ']]\n')
    for scope in sorted({t['scope'] for t in inv['toggles']}):
        labels = ' '.join(atom(t['label']) for t in inv['toggles'] if t['scope'] == scope)
        lines.append('lappend dw_toggles [list ' + atom(scope) + ' [list ' + labels + ']]\n')
    values = dict(dw_design=str(life.IMAGE) + '.vdb', dw_vdb=str(vdb),
                  dw_test=str(vdb.with_suffix('') / tests[0].name), dw_python=shutil.which('python3'),
                  dw_helper=str(SCRIPT))
    lines.extend('set ' + k + ' ' + atom(v) + '\n' for k, v in values.items())
    with (out / 'selection.tcl').open('x') as f:
        f.write(''.join(lines))
    pins[str(out / 'selection.tcl')] = life.digest(out / 'selection.tcl')
    life.check(pins)
    c = dict(**inv, pins=pins, identity=raw['tool_identity'], output=str(out), timeout_seconds=900,
             baseline=742, proof_sha256=REVIEW_SHA, local_session_only=True, population_application=False,
             protected_fsm=8, protected_toggle_positions=4188, proof_limit=review['induction']['limitation'],
             source_protection=review['protects'], automatic_retry=False)
    life.save(out / 'config.json', c)
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'config.json'), pins=len(pins))))


def verify(out, seal, prepared=False):
    c = life.read_bound(out / 'config.json', seal)
    life.check(c['pins']); tools.revalidate(c['identity'])
    if prepared:
        print('PREPARED_PINS_PASS'); return
    terminal = json.loads((out / 'terminal.json').read_bytes())
    require(terminal['returncode'] == 0 and not terminal['timeout'] and terminal['actual_dve'], 'Terminal failed')
    require(not (out / 'error.txt').exists(), 'Native failure artifact')
    log = (out / 'DVEfiles/dve_gui.log').read_text()
    require(log.splitlines().count('DWC_POINTS_NATIVE_DONE') == 1 and
            not re.search(r'UCAPI-DLMA|DVCDT136|EK-CMD-|Load Failed|Error:|Fatal:', log), 'Native log failed')
    first = parse_el((out / 'first.el').read_text(), c)
    require(first == parse_el((out / 'second.el').read_text(), c), 'Native semantic reload differs')
    for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el', 'cleanup-empty.el'):
        require((out / name).read_bytes() == b'', 'Global exclusions not empty')
    rows = list(csv.reader((out / 'audit.tsv').open(), delimiter='\t'))
    require(len(rows) == 5 * (39 + 32), 'Incomplete five-stage audit')
    expected_rows = set()
    for stage in ('before', 'selected', 'reset', 'reloaded', 'final'):
        active = stage in ('selected', 'reloaded')
        for g in c['groups']:
            for r in g['rows']:
                expected_rows.add((stage, 'FSM', g['machine'], g['mode'], r['name']))
        for t in c['toggles']:
            expected_rows.add((stage, 'Toggle', t['scope'], '', t['label']))
    require(len({tuple(r[:5]) for r in rows}) == len(rows) and {tuple(r[:5]) for r in rows} == expected_rows,
            'Missing/duplicate native audit identity')
    for r in rows:
        require(r[5] in ('0', '1'), 'Nonboolean native query')
        if r[6] != 'EL_AUTHORITY':
            require(r[5] == r[6], 'Protected/reset/target audit differs')
    for index in range(3):
        def identities(stage):
            return sorted(tuple(r[1:]) for r in csv.reader(
                (out / ('toggle-%s-%d.tsv' % (stage, index))).open(), delimiter='\t'))
        baseline = identities('before')
        require(baseline and len(baseline) == len(set(baseline)), 'Ambiguous native Toggle tree')
        for stage in ('selected', 'reset', 'reloaded', 'final'):
            require(identities(stage) == baseline, 'Protected native tree identity drift')
    result = dict(status='EXACT_DWC31_FSM_168_INTERNAL_TOGGLE_NATIVE_QUALIFIED_NOT_APPLIED',
                  config_seal=seal, fsm_states=7, fsm_arcs=24, toggle_objects=32, toggle_directions=168,
                  protected_fsm=8, protected_toggle_positions=4188, five_stages=True, global_empty=True,
                  source_contract=c['proof_limit'], interfaces_retained=True, population_application=False,
                  EL_records=first, pins={**c['pins'], **{str(p): life.digest(p) for p in out.rglob('*')
                      if p.is_file() and p.name not in ('capture-result.json', 'worker.log')}})
    life.save(out / 'capture-result.json', result)
    print(json.dumps(dict(status=result['status'], seal=life.digest(out / 'capture-result.json'))), flush=True)


def run(out, seal):
    verify(out, seal, True)
    c = life.read_bound(out / 'config.json', seal)
    require(not (out / 'execution.json').exists(), 'One-shot already claimed')
    env = tools.controlled_environment(c['identity'], os.environ)
    env.pop('DVE', None); env['DVE_COVERAGE_OUTPUT'] = str(out)
    command = [shutil.which('xvfb-run'), '-a', '-e', str(out / 'xvfb.log'), '-s', '-screen 0 1280x1024x24',
               c['identity']['roles']['launcher'], '-full64', '-cov', '-script', str(TCL)]
    with (out / 'execution.json').open('x') as f:
        json.dump(dict(command=command, authorization='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL',
                       timeout_seconds=900, retry=False, final_application=False), f)
    process = None; live = None; timeout = False
    try:
        with (out / 'launcher.log').open('x') as log:
            process = subprocess.Popen(command, cwd=out, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            start = tools.process_info(process.pid)['starttime']
            until = time.monotonic() + 60
            while process.poll() is None and time.monotonic() < until:
                for p in Path('/proc').iterdir():
                    if p.name.isdigit():
                        try:
                            if (p / 'exe').resolve() == Path(c['identity']['executable']) and (p / 'cwd').resolve() == out:
                                live = tools.verify_live_executable(int(p.name), c['identity'], process.pid, start)
                                break
                        except (OSError, ValueError):
                            pass
                if live: break
                time.sleep(.25)
            require(live is not None, 'Actual launch-bound DVE missing')
            life.save(out / 'live-identity.json', live)
            (out / 'live-ready').touch()
            print('DWC_NATIVE_LIVE pid=%s' % live['pid'], flush=True)
            try:
                process.wait(timeout=900)
            except subprocess.TimeoutExpired:
                timeout = True
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait()
        life.save(out / 'terminal.json', dict(returncode=process.returncode if process else None,
                                            timeout=timeout, actual_dve=live))
    try:
        verify(out, seal)
    except Exception as exc:
        life.save(out / 'status.json', dict(status='HOLD', reason=str(exc), population_application=False))
        raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'check', 'run', 'inspect', 'el'))
    p.add_argument('--output', type=Path, required=True); p.add_argument('--seal'); p.add_argument('--file')
    a = p.parse_args(); out = a.output.absolute()
    if a.mode == 'prepare': prepare(out)
    elif a.mode == 'el':
        require(a.file in ('first.el', 'second.el'), 'Unapproved EL filename')
        print(json.dumps(dict(records=len(parse_el((out / a.file).read_text(), json.loads((out / 'config.json').read_bytes()))))))
    else:
        require(a.seal, 'Exact config seal required')
        if a.mode == 'run': run(out, a.seal)
        else: verify(out, a.seal, a.mode == 'check')
