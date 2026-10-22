"""Prepare one local native partial-bit BTB capture; never applies a population."""
import argparse
import csv
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

import prepare_btb_bit0_132 as plan
import dve_tool_identity as tools

HERE = Path(__file__).resolve().parent
HOOK = HERE/'capture_btb_bit0_132.tcl'
STATIC = plan.OUT/'btb-bit0-132-prepared779-agent-20261008-01'
STATIC_SHA = '6f9edc8b0d3cd18a0137f16a5f1b3ddf486158963f946a7e67d1b28d64e181eb'
RUN = plan.OUT/'btb-target-ring-old-image777-agent-20261007-01'
STAGES = ('before', 'applied', 'reset', 'reloaded', 'final')
ELS = dict(before='initial-empty.el', applied='first.el', reset='reset-empty.el',
           reloaded='second.el', final='final-empty.el')
METRICS = ('Score', 'Line', 'Toggle', 'FSM', 'Condition', 'Branch')
HEADER = ['Stage', 'Scope', 'Path', 'Name'] + list(METRICS)
require, digest = plan.require, plan.digest


def save(path, value):
    with Path(path).open('x') as f:
        if isinstance(value, str): f.write(value)
        else: json.dump(value, f, indent=2); f.write('\n')


def bound(path, sha):
    path = Path(path)
    require(path.absolute() == path.resolve(strict=True), 'Aliased bound input')
    data = path.read_bytes()
    require(plan.hashlib.sha256(data).hexdigest() == sha, 'Bound input drift: '+str(path))
    return json.loads(data)


def check(pins):
    require(bool(pins), 'Empty input inventory')
    for name, sha in pins.items():
        require(digest(name) == sha, 'Input drift: '+name)


def native_records(text):
    # Native save may reorder the two scope headers or serialize both directions separately.
    headers, body = {}, []
    in_body = False
    for line in text.splitlines():
        line = line.strip()
        if not line: continue
        m = re.fullmatch(r'(CHECKSUM|INSTANCE|ANNOTATION):\s*(.*)', line)
        if m:
            require(not in_body and m[1] not in headers, 'Mixed/duplicate native header')
            headers[m[1]] = m[2]
        else:
            in_body = True
            body.append(line)
    require(headers == dict(CHECKSUM='"'+plan.CHECKSUM+'"', INSTANCE=plan.SCOPE,
                            ANNOTATION='"'+plan.NOTE+'"'), 'Exact native scope/checksum/annotation')
    normalized = []
    for line in body:
        # [0:0] is the same sole source bit; no other range normalization is allowed.
        m = re.fullmatch(r'Toggle (?:(0to1|1to0) )?(\S+) \[(0(?::0)?)\] "logic (\S+)\[63:0\]"', line)
        require(m is not None, 'Nonpartial/foreign native directive')
        normalized.append('Toggle '+(m[1]+' ' if m[1] else '')+m[2]+' [0] "logic '+m[4]+'[63:0]"')
    return plan.records('\n'.join(plan.el_text().splitlines()[:3]+normalized))


def complement(inventory):
    all_bits = {(n['attrs']['name'], b, d) for n in inventory['all_nodes']
                for b in ([0] if n['kind'] == 'node' else
                    range(min(int(n['attrs']['left']),int(n['attrs']['right'])),
                          max(int(n['attrs']['left']),int(n['attrs']['right']))+1))
                for d in ('0to1', '1to0')}
    targets = {(name, 0, d) for name in plan.NAMES for d in ('0to1', '1to0')}
    require(len(all_bits) == 8992 and targets <= all_bits and len(targets) == 132,
            'Complete typed native source-bit inventory')
    kept = all_bits-targets
    require(len(kept) == 8860 and all(x in kept for x in all_bits if x[0].endswith('.valid')),
            'Exact full complementary bit/direction set')
    return kept


def contract(c):
    require(c['schema'] == 'BTB_BIT0_132_LOCAL_NATIVE_PREPARED' and c['static_seal'] == STATIC_SHA and
            c['baseline_seal'] == plan.BASE_SHA and c['population'] == 779 and
            c['scope'] == plan.SCOPE and c['timeout_seconds'] == 600 and
            c['automatic_retry'] is False and c['population_application'] is False,
            'Exact local scope/budget/source contract')
    require(c['design'] == str(plan.OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb') and
            c['vdb'] == str(RUN/'code.vdb') and
            c['selected_test'] == str(RUN/'code/btb_target_ring_sv39'), 'Exact admitted selected test')
    require(len(complement(c['inventory'])) == 8860, 'Complement contract')
    require({t['attrs']['name'] for t in c['inventory']['targets']} == plan.NAMES,
            'Exact approved targets')


def read_config(out, seal):
    c = bound(out/'config.json', seal)
    contract(c); check(c['pins'])
    require(c['output'] == str(out), 'Output identity')
    require(str(STATIC/'inventory.json') in c['pins'] and
            bound(STATIC/'inventory.json',c['pins'][str(STATIC/'inventory.json')]) == c['inventory'],
            'Exact sealed typed inventory binding')
    return c


def check_stage(out, c, stage):
    require(stage in STAGES, 'Unknown stage')
    text = (out/ELS[stage]).read_text()
    if stage in ('before', 'reset', 'final'):
        require(text == '', 'Global native reset is not empty')
        return set()
    actual = native_records(text)
    require(not actual & complement(c['inventory']), 'Protected bit/direction excluded')
    return actual


def percent(value):
    require(re.fullmatch(r'(?:0|[1-9]\d*)(?:\.\d+)?%?', value) is not None,
            'Strict native percentage encoding')
    number = Decimal(value[:-1] if value.endswith('%') else value)
    require(0 <= number <= 100, 'Native percentage bounds')
    return number


def metrics(out, stage):
    with (out/('rooted_'+stage+'.csv')).open(newline='') as f:
        reader = csv.DictReader(f)
        require(reader.fieldnames == HEADER, 'Exact native metrics schema')
        rows = list(reader)
    require(len(rows) == 1, 'Exactly one local root')
    row = rows[0]
    require(row['Stage'] == stage and row['Scope'] == plan.SCOPE and
            row['Path'] == row['Name'] == 'i_btb', 'Exact rooted BTB identity')
    return {m: None if row[m] == 'NA' and m not in ('Score','Toggle') else percent(row[m]) for m in METRICS}


def inventory_rows(out, c, stage):
    with (out/('objects_'+stage+'.tsv')).open(newline='') as f:
        rows = list(csv.reader(f, delimiter='\t'))
    require(rows and rows[0] == ['path','meta','name'], 'Object identity schema')
    aliases = {}
    for n in c['inventory']['all_nodes']:
        name = n['attrs']['name']
        rendered = name if n['kind'] == 'node' else name+'[%s:%s]'%(n['attrs']['left'],n['attrs']['right'])
        for alias in {name, rendered}:
            require(alias not in aliases or aliases[alias] == name, 'Ambiguous compiled alias')
            aliases[alias] = name
    found = {}
    for row in rows[1:]:
        require(len(row) == 3 and all(x in aliases for x in row), 'Unknown native object identity')
        names = {aliases[x] for x in row}
        require(len(names) == 1, 'Path/metadata/name disagree')
        name = names.pop()
        require(name not in found, 'Duplicate native object')
        found[name] = row
    require(set(found) == {n['attrs']['name'] for n in c['inventory']['all_nodes']},
            'Complete143 compiled objects required')
    return found


def verify(out, seal):
    c = read_config(out, seal); tools.revalidate(c['identity'])
    terminal = json.loads((out/'terminal.json').read_bytes())
    require(type(terminal['returncode']) is int and terminal['returncode'] == 0 and
            terminal['timeout'] is False and len(terminal['actual_dve']) == 1,
            'Actual successful DVE executable terminal required')
    live=json.loads((out/'live-identity.json').read_bytes())
    require(live == terminal['actual_dve'] and (out/'live-ready').read_text() == 'LIVE_EXECUTABLE_VERIFIED\n',
            'Bound verified launch child record')
    record=live[0]
    require(record['executable_verified'] is True and record['executable'] == c['identity']['executable'] and
            all(type(record[k]) is int and record[k] > 0 for k in
                ('pid','starttime','launch_pid','launch_starttime')) and
            record['pid'] != record['launch_pid'] and record['starttime'] >= record['launch_starttime'],
            'Exact live executable/launch ancestry identity')
    gui = (out/'DVEfiles/dve_gui.log').read_text().splitlines()
    require(gui.count('BTB132_NATIVE_DONE') == 1 and not (out/'error.txt').exists() and
            not any(re.match(r'^(?:BTB132_NATIVE_FAILED|Error(?:[:\[]|-)|ERROR\b)', line) for line in gui),
            'Five-stage GUI completion/error contract')
    require((out/'selected_tests.txt').read_text().splitlines() == [c['selected_test']] and
            gui.count('BTB132_SELECTED '+c['selected_test']) == 1, 'Exact one selected native test')
    first = check_stage(out,c,'applied')
    require(first == check_stage(out,c,'reloaded'), 'Exact semantic native reload')
    for stage in ('before','reset','final'): check_stage(out,c,stage)
    require((out/'cleanup-empty.el').read_bytes() == b'', 'Independent final cleanup empty')
    require(inventory_rows(out,c,'before') == inventory_rows(out,c,'final'), 'Typed object identity drift')
    values = {stage:metrics(out,stage) for stage in STAGES}
    require(values['before'] == values['reset'] == values['final'], 'Raw/reset/final metrics differ')
    require(values['applied'] == values['reloaded'], 'Applied/reloaded metrics differ')
    require(all(values['before'][m] == values['applied'][m] for m in ('Line','FSM','Condition','Branch')),
            'Non-Toggle metric changed')
    require(values['applied']['Toggle'] > values['before']['Toggle'], 'Native partial application had no effect')
    result = dict(status='BTB_BIT0_132_LOCAL_NATIVE_QUALIFIED_NOT_POPULATION_APPLIED',
        config_seal=seal, source_bit_targets=66, direction_targets=132, protected_directions=8860,
        exact_global_EL_membership=True, per_bit_GUI_flags_read=False,
        protection_authority='Complete global native EL has exactly the approved partial-bit direction set; no aggregate vector flags are used.',
        population_application=False, official_percentage=None,
        local_metrics={s:{k:str(v) if v is not None else 'NA' for k,v in vals.items()} for s,vals in values.items()},
        pins=dict(c['pins'], **{str(p):digest(p) for p in out.rglob('*') if p.is_file() and
                               p.name not in ('capture-result.json','launcher.log','xvfb.log')}))
    check(result['pins'])
    path = out/'capture-result.json'
    if path.exists(): require(json.loads(path.read_bytes()) == result, 'Existing qualification differs')
    else: save(path,result)
    return digest(path)


def prepare(out):
    require(out.parent == plan.OUT and not out.exists(), 'Fresh independent local output')
    static = bound(STATIC/'prepare-manifest.json',STATIC_SHA)
    require(static['status'] == 'STATIC_PREPARED_NOT_NATIVE_APPROVED' and
            static['population'] == 779 and static['baseline_seal'] == plan.BASE_SHA,
            'Approved static plan only')
    check(static['input_pins']); check(static['output_pins'])
    pins = dict(static['input_pins'], **static['output_pins'])
    pins[str(STATIC/'prepare-manifest.json')] = STATIC_SHA
    def static_output(name):
        expected = STATIC/name
        matches = [(path, sha) for path, sha in static['output_pins'].items()
                   if Path(os.path.abspath(path)) == expected]
        require(len(matches) == 1 and expected.resolve(strict=True) == expected,
                'Unique ordinary static output identity')
        sha = matches[0][1]
        pins[str(expected)] = sha
        return bound(expected,sha)
    prior = bound(plan.PRIOR,plan.PRIOR_SHA)
    prior_config = plan.PRIOR.parent/'config.json'
    source = bound(prior_config,prior['config_seal'])
    identity = source['tool_identity']; tools.revalidate(identity)
    pins[str(prior_config)] = prior['config_seal']
    admitted = bound(plan.BASE, plan.BASE_SHA)
    ledger = Path(admitted['output'])/'combined-inputs.txt'
    require(digest(ledger) == admitted['output_pins'][str(ledger)] and
            ledger.read_text().splitlines()[-1] == str(RUN/'code.vdb'), 'Selected VDB is admitted779 member')
    vdb = RUN/'code.vdb'
    dirs = list((vdb/'snps/coverage/db/testdata').iterdir())
    require(len(dirs) == 1 and dirs[0].name == 'btb_target_ring_sv39', 'One exact selected test')
    # Actual DVE read closure: fixed compiled database and selected admitted test only.
    design = plan.OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb'
    for folder in (design, vdb):
        for p in folder.rglob('*'):
            if p.is_file():
                require(p.resolve(strict=True) == p and str(p) in admitted['input_pins'], 'Unbound native database input: '+str(p))
                pins[str(p)] = admitted['input_pins'][str(p)]
    for p in (Path(__file__).resolve(),HOOK,HERE/'test_capture_btb_bit0_132.py',
              Path(tools.__file__).resolve(), plan.PRIOR, STATIC/'inventory.json'):
        sha = digest(p)
        require(str(p) not in pins or pins[str(p)] == sha, 'Dependency pin conflicts')
        pins[str(p)] = sha
    for item in identity['files']:
        pins[item['path']] = item['sha256']
    c = dict(schema='BTB_BIT0_132_LOCAL_NATIVE_PREPARED', output=str(out), population=779,
        baseline_seal=plan.BASE_SHA, static_seal=STATIC_SHA, scope=plan.SCOPE,
        inventory=static_output('inventory.json'),
        identity=identity, pins=pins, timeout_seconds=600, automatic_retry=False,
        population_application=False, design=str(design), vdb=str(vdb),
        selected_test=str(RUN/'code/btb_target_ring_sv39'))
    contract(c); check(pins)
    vals = dict(btb_design=c['design'],btb_vdb=c['vdb'],btb_test=c['selected_test'],
        btb_scope=plan.SCOPE,btb_python=str(plan.ROOT/'verification/tools/soc-venv/bin/python'),
        btb_helper=str(Path(__file__).resolve()))
    require(all(not any(ch in v for ch in '{}\\\r\n') for v in vals.values()), 'Unsafe Tcl literal')
    out.mkdir()
    save(out/'selection.tcl',''.join('set ::%s {%s}\n'%item for item in vals.items()))
    candidate_path=STATIC/'candidate.el'
    expected_sha=next(sha for path,sha in static['output_pins'].items()
                      if Path(os.path.abspath(path)) == candidate_path)
    candidate=candidate_path.read_bytes()
    require(plan.hashlib.sha256(candidate).hexdigest() == expected_sha,'Static candidate drift')
    require(native_records(candidate.decode()) == plan.records(plan.el_text()),'Exact prepared partial candidate')
    save(out/'candidate.el',candidate.decode())
    for name in ('selection.tcl','candidate.el'): pins[str(out/name)] = digest(out/name)
    save(out/'config.json',c)
    return digest(out/'config.json')


def run(out,seal):
    c = read_config(out,seal)
    require(not (out/'execution.json').exists(), 'One-shot native capture')
    env = tools.controlled_environment(c['identity'],os.environ);env.pop('DVE',None)
    env['DVE_COVERAGE_OUTPUT'] = str(out)
    env['BTB132_CONFIG_SEAL'] = seal
    cmd = tools.launch_command(c['identity'],HOOK)
    save(out/'execution.json',dict(command=cmd,timeout_seconds=600,automatic_retry=False))
    actual, timed = [], False
    with (out/'launcher.log').open('x') as log:
        proc = subprocess.Popen(cmd,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        start = tools.process_info(proc.pid)['starttime'];deadline=time.monotonic()+600
        live_deadline = min(deadline, time.monotonic()+30)
        try:
            while time.monotonic() < live_deadline and not actual:
                require(proc.poll() is None, 'Launcher exited before live identity gate')
                for path in Path('/proc').iterdir():
                    if not path.name.isdigit(): continue
                    try:
                        if (path/'exe').resolve() == Path(c['identity']['executable']) and (path/'cwd').resolve() == out:
                            actual.append(tools.verify_live_executable(int(path.name),c['identity'],proc.pid,start))
                    except (OSError,ValueError): continue
                if not actual: time.sleep(0.2)
            require(len(actual) == 1, 'Exactly one verified DVE child')
            save(out/'live-identity.json',actual);save(out/'live-ready','LIVE_EXECUTABLE_VERIFIED\n')
            proc.wait(timeout=max(0.1,deadline-time.monotonic()))
        except subprocess.TimeoutExpired:
            timed=True
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid,signal.SIGTERM)
                try: proc.wait(timeout=10)
                except subprocess.TimeoutExpired: os.killpg(proc.pid,signal.SIGKILL);proc.wait()
            save(out/'terminal.json',dict(returncode=proc.returncode,timeout=timed,actual_dve=actual))
    return verify(out,seal)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','check','stage','verify','run'))
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--seal')
    parser.add_argument('--stage',choices=STAGES)
    args=parser.parse_args();out=args.output.absolute()
    if args.mode == 'prepare': print(prepare(out))
    else:
        require(args.seal,'Exact config seal required')
        if args.mode == 'stage':
            print(len(check_stage(out,read_config(out,args.seal),args.stage)))
        elif args.mode == 'check': read_config(out,args.seal);print('BTB132_PREPARED_PINS_PASS_NO_EDA')
        else: print((verify if args.mode == 'verify' else run)(out,args.seal))
