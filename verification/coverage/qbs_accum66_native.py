"""Frozen-config QBS partial-range native qualification, not population application."""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

import capture_cva6_parent_rvfi457 as host
import qualify_csr_pmp0_native765 as labels
import review_qbs_accum_config_constants767 as source
import audit_qbs_engine_residual766 as q

life, tools, require = host.life, host.tools, host.require
HERE = Path(__file__).resolve().parent
ENTRY = HERE / 'qbs_accum66_native.tcl'
REVIEW = source.OUT
REVIEW_SHA = '910fb3a7b8a8647a80f9b7d774b01b196bef0abcf6ee4a3b8d23db4fd9290288'
STAGES = ('before', 'selected', 'reset', 'reloaded', 'final')
EL_FILES = dict(before='initial-empty.el', selected='first.el', reset='reset-empty.el',
                reloaded='second.el', final='final-empty.el')
BOUNDARY = 'Frozen FP32 QBS disabled-format and padded-result configuration constants only; no flags rounding control handshake or active-result exclusions'


def proof():
    r = life.read_bound(REVIEW, REVIEW_SHA)
    life.check(r['pins'])
    require(r['already_qualified766_canonical_overlap'] == 0 and not r['native_qualified']
            and r['candidate_objects'] == 66 and r['candidate_source_bits'] == 2112,
            'Exact independent source candidate contract')
    require(source.source_contract({p.name: p.read_text() for p in source.SOURCE_PATHS})
            == r['source_legal_domain'], 'Frozen source domain changed')
    all_objects = r['candidates'] + r['protected_full_complement'] + r['protected_arrays']
    scopes = sorted({p['scope'] for p in all_objects})
    instances = []
    for scope in scopes:
        local = [p for p in all_objects if p['scope'] == scope]
        summary = local[0]
        require(all((p['checksum'], p['design_checksum']) ==
                    (summary['checksum'], summary['design_checksum']) for p in local), 'Scope identity drift')
        nodes = [dict(kind=p['kind'], **p['attributes']) for p in local]
        byname = {n['name']: n for n in nodes}
        targets = []
        for p in r['candidates']:
            if p['scope'] != scope: continue
            n = byname[p['name']]
            require(n['kind'] == 'vectornode' and n['type'] == '1' and n['excluded'] == '0'
                    and n['left'] == '31' and n['right'] == '0' and n['portnode'] == '0'
                    and p['name'].endswith('.result'), 'Exact internal result shape required')
            targets.append(dict(signal=p['name'], source_bits=list(range(32)),
                                retained_source_bits=[], attributes=p['attributes']))
        require(len(nodes) == len(byname), 'Duplicate compiled name')
        instances.append(dict(scope=scope, nodes=nodes, targets=targets,
                              design_checksum=summary['design_checksum'], toggle_checksum=summary['checksum']))
    require(len(instances) == 38 and sum(len(i['nodes']) for i in instances) == 2425
            and sum(len(i['targets']) for i in instances) == 66
            and sum(len(t['source_bits']) for i in instances for t in i['targets']) == 2112
            and sum(len(t['retained_source_bits']) for i in instances for t in i['targets']) == 0,
            'Exact source-approved66/2112/2359 complement partition')
    return r, r, instances


def contract(c):
    _, _, instances = proof()
    require(c['instances'] == instances and c['timeout_seconds'] == 900
            and c['population_application'] is False and c['automatic_retry'] is False
            and c['boundary'] == BOUNDARY, 'Frozen qualification contract changed')
    require(c['source_domain'] == proof()[0]['source_legal_domain'], 'Source domain binding drift')


def candidate(c):
    lines = []
    for i in c['instances']:
        if not i['targets']: continue
        lines += ['CHECKSUM: "%s %s"' % (i['design_checksum'], i['toggle_checksum']),
                  'INSTANCE: ' + i['scope'], 'ANNOTATION: "' + BOUNDARY + '"']
        nodes = {n['name']: n for n in i['nodes']}
        for t in i['targets']:
            n = nodes[t['signal']]
            for bit in t['source_bits']:
                lines.append('Toggle %s [%d] "logic %s%s"' %
                             (n['name'], bit, n['name'], labels.bounds(n)))
    return '\n'.join(lines) + '\n'


def records(text, c):
    instances = {i['scope']: i for i in c['instances']}
    expected = {(i['scope'], t['signal'], bit, direction)
                for i in c['instances'] for t in i['targets'] for bit in t['source_bits']
                for direction in ('0to1', '1to0')}
    found = set(); scopes = set(); scope = None; check = None; pending = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('//'):
            continue
        m = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"', line)
        if m:
            require(not pending, 'Orphan/duplicate checksum'); check = m.groups(); scope = None; pending = True
            continue
        if line.startswith('INSTANCE:'):
            scope = line.split(':', 1)[1].strip()
            require(pending and scope in instances and scope not in scopes, 'Foreign/duplicate scope')
            i = instances[scope]
            require(check == (i['design_checksum'], i['toggle_checksum']), 'Scope/checksum mismatch')
            scopes.add(scope); pending = False; continue
        if line.startswith('ANNOTATION:'):
            require(scope is not None and line == 'ANNOTATION: "' + BOUNDARY + '"', 'Unknown annotation')
            continue
        m = re.fullmatch(r'Toggle (?:(0to1|1to0) )?([^\s"]+)(?: \[(\d+)(?::(\d+))?\])? "logic ([^"\r\n]+)"', line)
        require(scope is not None and m is not None, 'Unknown typed partial Toggle directive: ' + line)
        direction, name, left, right, declaration = m.groups()
        i = instances[scope]; targets = {t['signal']: t for t in i['targets']}
        require(name in targets, 'Protected/foreign EL object')
        n = next(n for n in i['nodes'] if n['name'] == name)
        require(declaration == name + labels.bounds(n), 'Full source type/name/bounds differ')
        bits = set(range(int(right or left), int(left) + 1)) if left is not None else set(range(int(n['left']) + 1))
        require(bits and bits <= set(targets[name]['source_bits']), 'Protected low/retained bits included')
        for bit in bits:
            for d in ((direction,) if direction else ('0to1', '1to0')):
                key = (scope, name, bit, d)
                require(key not in found, 'Duplicate/mixed whole or split direction'); found.add(key)
    require(not pending and scopes == {s for s, i in instances.items() if i['targets']}
            and found == expected and len(found) == 4224,
            'Exact2112 both directions and scope union required')
    return sorted(found)


def inventory(out, c, stage, index):
    require(stage in STAGES and 0 <= index < len(c['instances']), 'Invalid scope/stage')
    i = c['instances'][index]
    with (out / ('native_%s_%d.tsv' % (stage, index))).open(newline='') as f:
        rows = list(csv.reader(f, delimiter='\t'))
    require(rows and rows[0] == ['handle', 'path', 'meta', 'name', 'excluded']
            and len(rows) - 1 == len(i['nodes']), 'Exact full local inventory schema/count')
    aliases = {alias: n for n in i['nodes'] for alias in labels.aliases(n)}
    require(len(aliases) == sum(len(labels.aliases(n)) for n in i['nodes']), 'Ambiguous compiled aliases')
    targets = {t['signal'] for t in i['targets']}; found = {}; handles = set()
    for row in rows[1:]:
        require(len(row) == 5 and all(row), 'Native row encoding')
        handle, path, meta, name, flag = row
        require(handle not in handles and path == meta == name and name in aliases and flag in ('0', '1'),
                'Native actual identity/aggregate flag mismatch')
        n = aliases[name]; require(n['name'] not in found, 'Duplicate whole-object alias')
        if stage in ('before', 'reset', 'final') or n['name'] not in targets:
            require(flag == '0', 'Non-target object/array/port or reset excluded')
        else:
            require(flag == '1', 'Exact whole target not excluded')
        handles.add(handle); found[n['name']] = (path, meta, name)
    require(set(found) == {n['name'] for n in i['nodes']}, 'Missing full complement')
    return sorted(found.items())


def el(out, c, stage):
    text = (out / EL_FILES[stage]).read_text()
    if stage in ('before', 'reset', 'final'):
        require(text == '', 'Global reset EL not empty'); return []
    result = records(text, c)
    retained = {(i['scope'], t['signal'], bit, direction) for i in c['instances']
                for t in i['targets'] for bit in t['retained_source_bits'] for direction in ('0to1', '1to0')}
    require(len(retained) == 0 and not retained.intersection(result), 'Exact retained-bit complement violated')
    return result


def bind(out, c):
    actual = {i['scope']: inventory(out, c, 'before', index) for index, i in enumerate(c['instances'])}
    life.save(out / 'actual-binding.json', dict(config_seal=life.digest(out / 'config.json'),
        inventory=actual, inventory_pins={str(out / ('native_before_%d.tsv' % n)):
            life.digest(out / ('native_before_%d.tsv' % n)) for n in range(38)}, actual_objects=2425,
        targets=66, protected_objects=2359, protected_target_bits=0))


def atom(value):
    require(not any(ch in str(value) for ch in '{}\\\n\r'), 'Unsafe Tcl atom')
    return '{' + str(value) + '}'


def selection(c):
    text = ''.join('set ::qc_' + k + ' ' + atom(c[k]) + '\n'
                   for k in ('design', 'sample', 'test', 'python', 'helper'))
    scopes = [i['scope'] for i in c['instances']]
    text += 'set ::qc_scopes [list ' + ' '.join(atom(s) for s in scopes) + ']\n'
    text += 'set ::p740_scopes $::qc_scopes\n'
    for s in scopes:
        text += 'set ' + atom('::p740_root_names(' + s + ')') + ' ' + atom(s.split('.')[-1]) + '\n'
    return text


def metrics(out, c, stage):
    with (out / ('rooted_' + stage + '.csv')).open(newline='') as f:
        reader = csv.DictReader(f)
        require(reader.fieldnames == ['Stage', 'Scope', 'Token', 'Handle', 'GUIPath', 'Name',
            'Score', 'Line', 'Toggle', 'FSM', 'Condition', 'Branch'], 'Exact rooted metric schema')
        rows = list(reader)
    require(len(rows) == 38, 'Exactly38 rooted native metric rows')
    values = {}
    for row in rows:
        s = row['Scope']
        require(s in {i['scope'] for i in c['instances']} and s not in values and row['Stage'] == stage
                and row['Token'] == s and row['GUIPath'] == row['Name'] == s.split('.')[-1]
                and row['Handle'].isdigit(), 'Rooted identity differs')
        values[s] = {m: row[m] for m in ('Score', 'Line', 'Toggle', 'FSM', 'Condition', 'Branch')}
        for metric, value in values[s].items():
            if value == 'NA':
                require(metric not in ('Score', 'Toggle'), 'Toggle unavailable'); continue
            require(re.fullmatch(r'(?:0|[1-9][0-9]?|100)\.[0-9]{2}%', value), 'Actual native percent encoding required')
            number = float(value[:-1]); require(math.isfinite(number) and 0 <= number <= 100, 'Metric invalid')
    return values


def prepare(out):
    require(out.parent == life.OUT and not out.exists(), 'Fresh independent output required')
    r, _, instances = proof()
    pins = {**r['pins'], str(REVIEW): REVIEW_SHA}
    for module in list(sys.modules.values()):
        file = getattr(module, '__file__', None)
        if file and Path(file).resolve().parent == HERE and Path(file).suffix == '.py':
            pins[str(Path(file).resolve())] = life.digest(file)
    for p in (ENTRY, HERE / 'capture_csr_reserved1193.tcl', HERE / 'apply_points740_v4.tcl',
              HERE / 'test_qbs_accum66_native.py'):
        pins[str(p)] = life.digest(p)
    identity = tools.prepare('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/dve', '/usr/bin/xvfb-run')
    pins.update({p['path']: p['sha256'] for p in identity['files']})
    sample = life.OUT / 'gap84-div32-old-image-20261006-01/code.vdb'
    ledger = q.BASE / 'combined-inputs.txt'
    require(str(sample) in ledger.read_text().splitlines(), 'Representative sample not admitted766')
    dirs = list((sample / 'snps/coverage/db/testdata').iterdir())
    require(len(dirs) == 1 and dirs[0].is_dir(), 'Representative test ambiguity')
    for p in sample.rglob('*'):
        if p.is_file(): pins[str(p)] = life.digest(p)
    c = dict(instances=instances, identity=identity, pins=pins, output=str(out),
        design=str(q.f.BUILD / 'sim/simv.vdb'), sample=str(sample),
        test=str(sample.with_suffix('') / dirs[0].name), python=sys.executable,
        helper=str(Path(__file__).resolve()), timeout_seconds=900, boundary=BOUNDARY,
        population_application=False, automatic_retry=False, source_domain=r['source_legal_domain'])
    contract(c); records(candidate(c), c)
    out.mkdir()
    for name, text in [('selection.tcl', selection(c)), ('candidate.el', candidate(c))]:
        (out / name).write_text(text); pins[str(out / name)] = life.digest(out / name)
    life.check(pins); life.save(out / 'config.json', c)
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'config.json'),
        scopes=38, objects=2425, target_objects=66, target_bits=2112, retained_bits=0)), flush=True)


def verify(out, seal):
    c = life.read_bound(out / 'config.json', seal); contract(c); life.check(c['pins']); tools.revalidate(c['identity'])
    terminal = json.loads((out / 'terminal.json').read_bytes())
    require(terminal['returncode'] == 0 and not terminal['timeout'] and len(terminal['actual_dve']) == 1,
            'Actual native terminal failed')
    log = (out / 'DVEfiles/dve_gui.log').read_text()
    require(log.splitlines().count('QBS_ACCUM66_NATIVE_DONE') == 1
            and not re.search(r'Error:|Fatal:|EK-CMD-|DVTC[0-9]+|UCAPI-DLMA|DVCDT136|QBS_ACCUM66_FAILED', log)
            and not (out / 'error.txt').exists(), 'Native session failed')
    actual = json.loads((out / 'actual-binding.json').read_bytes())
    require(actual['config_seal'] == seal and actual['actual_objects'] == 2425, 'Actual binding seal differs')
    life.check(actual['inventory_pins'])
    values = {}
    for stage in STAGES:
        for index, i in enumerate(c['instances']):
            require(json.loads(json.dumps(inventory(out, c, stage, index))) == actual['inventory'][i['scope']],
                    'Actual full inventory drift')
        el(out, c, stage); values[stage] = metrics(out, c, stage)
    require(el(out, c, 'selected') == el(out, c, 'reloaded'), 'Exact EL roundtrip differs')
    require(values['before'] == values['reset'] == values['final']
            and values['selected'] == values['reloaded'], 'Native metric reset/reload drift')
    for s in values['before']:
        require(all(values['before'][s][m] == values['selected'][s][m]
                    for m in ('Line', 'FSM', 'Condition', 'Branch')), 'Non-Toggle metric changed')
    require((out / 'cleanup-empty.el').read_bytes() == b'', 'Cleanup not empty')
    result = dict(status='QBS_ACCUM66_CONFIG2112_NATIVE_QUALIFIED_NOT_POPULATION_APPLIED',
        config_seal=seal, source_review_sha256=REVIEW_SHA,
        actual_inventory_scopes=[i['scope'] for i in c['instances']], actual_inventory_objects=2425,
        target_objects=66, source_bits=2112, canonical_EL_direction_members=4224,
        protected_objects=2359, protected_target_bits=0, protected_arrays=108,
        native_membership_authority='Exact full typed saved EL members, not per-bit GUI flags',
        global_saved_EL_has_no_foreign_objects_or_scopes=True,
        other_QBS_scopes_not_claimed_as_GUI_inventoried=True,
        metrics=values, boundary=BOUNDARY, source_domain=c['source_domain'],
        population_application=False, official_denominator=None,
        pins={**c['pins'], **{str(p): life.digest(p) for p in out.rglob('*')
            if p.is_file() and p.name not in ('service.log', 'capture-result.json')}})
    life.check(result['pins']); destination = out / 'capture-result.json'
    if destination.exists():
        require(json.loads(destination.read_bytes()) == result, 'Existing qualification seal differs')
    else:
        life.save(destination, result)
    print('QUALIFIED ' + life.digest(destination), flush=True)


def run(out, seal):
    c = life.read_bound(out / 'config.json', seal); contract(c); life.check(c['pins']); tools.revalidate(c['identity'])
    require(os.environ.get('INVOCATION_ID') and c['output'] == str(out), 'Direct-owning systemd required')
    env = tools.controlled_environment(c['identity'], os.environ); env.pop('DVE', None)
    env.update(DVE_COVERAGE_OUTPUT=str(out), QBS_ACCUM66_SEAL=seal)
    command = [c['identity']['roles']['xvfb_run'], '-a', '-e', str(out / 'xvfb.log'), '-s',
               '-screen 0 1280x1024x24', c['identity']['roles']['launcher'], '-full64', '-cov', '-script', str(ENTRY)]
    life.save(out / 'execution.json', dict(command=command, automatic_retry=False,
        systemd_invocation=os.environ['INVOCATION_ID'], timeout_seconds=900))
    started = time.monotonic()
    with (out / 'launcher.log').open('x') as log:
        process = subprocess.Popen(command, cwd=out, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        start = tools.process_info(process.pid)['starttime']; time.sleep(10); actual = []
        for p in Path('/proc').iterdir():
            if not p.name.isdigit(): continue
            try:
                if (p / 'exe').resolve() == Path(c['identity']['executable']) and (p / 'cwd').resolve() == out:
                    tools.verify_live_executable(int(p.name), c['identity'], process.pid, start)
                    actual.append(dict(pid=int(p.name), exe=str((p / 'exe').resolve()), cwd=str(out),
                                       cgroup=(p / 'cgroup').read_text()))
            except (OSError, ProcessLookupError): pass
        life.save(out / 'live-identity.json', actual); print(json.dumps(dict(actual_dve=actual)), flush=True)
        timeout = False
        try: process.wait(timeout=max(1, 900 - (time.monotonic() - started)))
        except subprocess.TimeoutExpired:
            timeout = True; os.killpg(process.pid, signal.SIGTERM)
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL); process.wait()
    life.save(out / 'terminal.json', dict(returncode=process.returncode, timeout=timeout, actual_dve=actual))
    try: verify(out, seal)
    except Exception as error:
        life.save(out / 'qualification-reject.json', dict(status='REJECTED_NOT_QUALIFIED', reason=str(error),
            config_seal=seal, captures_preserved=True, automatic_retry=False)); raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'run', 'verify', 'inventory', 'bind', 'el'))
    p.add_argument('--output', type=Path, required=True); p.add_argument('--seal')
    p.add_argument('--stage', choices=STAGES); p.add_argument('--index', type=int)
    args = p.parse_args(); out = args.output.absolute()
    if args.mode == 'prepare': prepare(out)
    else:
        seal = args.seal or os.environ.get('QBS_ACCUM66_SEAL')
        require(seal, 'Config seal required'); c = life.read_bound(out / 'config.json', seal)
        contract(c); life.check(c['pins'])
        if args.mode == 'bind': bind(out, c); print('EXACT_ACTUAL2425_BINDING')
        elif args.mode == 'inventory': print('FULL_LOCAL ' + str(len(inventory(out, c, args.stage, args.index))))
        elif args.mode == 'el': print('EXACT_EL_MEMBERS ' + str(len(el(out, c, args.stage))))
        else: (run if args.mode == 'run' else verify)(out, seal)
