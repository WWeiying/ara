#!/usr/bin/env python3
"""One-scope vector UI discovery, not exclusion qualification; no implicit launch."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import tkinter

import c910_lane23_padding1424_launcher_v2 as base

life, need, tools = base.life, base.need, base.tools
core = base.core
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_c910_vector_discovery_v3.py')
TCL = SCRIPT.with_suffix('.tcl')
ORIGIN = life.OUT / 'c910-lane23-padding1424-launcher-v2-prepared796-agent-20261008-03/config.json'
ORIGIN_SEAL = '54333111b2206676dbeadea33de7e2840b2db6d01a1f2c0ece0e7b36c13e1265'
AUTH = life.OUT / 'akv-canonical-alias-offline-admitted796-parent-20261008-01/admission-manifest.json'
AUTH_SEAL = '1aa18b04d4b1f3a4a2d8182c0457e240f43e0538bbeabe1b0385724e5a56400d'
STAGES = ('initial', 'selected', 'detail_clicked')
P740 = TCL.with_name('apply_points740_v4.tcl')
COLUMN_SCHEMAS = {
    'tglListView': ['Variable', ' ', '  ', '   ', 'Type', 'Coverage', 'Display'],
    'tglDetailListView': ['Variable', ' ', '  ', '   ', '0->1', '1->0'],
}
PREDECESSORS = {
    str(SCRIPT.with_name('c910_vector_discovery_v2.py')): '831ab3aade2819063449f78b549b6e7453515d8cdfeb2c1dc38142575d92a0b4',
    str(SCRIPT.with_name('c910_vector_discovery_v2.tcl')): 'bb5d51b327ddf25c71c93a9f21b278ba574757f565eb42723011ebb416a46368',
    str(SCRIPT.with_name('test_c910_vector_discovery_v2.py')): '0e7b7215905affbc942475ae71801d71bdbe6fd5ed30c75fef09cfbd9eeff44b',
    str(SCRIPT.with_name('c910_vector_discovery.py')): 'dd37c005ffc0d8d69998025ac383718feaa24fd24facc15ce0c00c335d655b02',
    str(SCRIPT.with_name('c910_vector_discovery.tcl')): '6a274be066a94c7b1432035df66c29d70f6dec0850db9b964d187733dec01580',
    str(SCRIPT.with_name('test_c910_vector_discovery.py')): '37c16862980b0afaa4bc48f00013a5112517d0023c8811b4240c35ac993cd5ee',
}
approved, cgroup_gate, proc_cgroup, observe = base.approved, base.cgroup_gate, base.proc_cgroup, base.observe


def contract(out):
    h = base.contract(out)
    h.update(schema='C910_VECTOR_DISCOVERY_ONE_SHOT', timeout_seconds=300,
             unit='c910-vector-discovery-' + core.hashlib.sha256(str(out).encode()).hexdigest()[:20])
    return h


def selection(c):
    return ''.join('set vd_%s {%s}\n' % (key, c[key]) for key in ('scope', 'test', 'design', 'vdb'))


def authority():
    origin = life.read_bound(ORIGIN, ORIGIN_SEAL)
    auth = life.read_bound(AUTH, AUTH_SEAL)
    need(auth['coverage_admitted'] is True, 'Admitted796 authority')
    status_path, ledger_path = AUTH.parent / 'status.json', AUTH.parent / 'combined-inputs.txt'
    status = life.read_bound(status_path, auth['output_pins'][str(status_path)])
    need(status['aggregate_passed'] == 796 and status['new_passed'] == 1 and
         status['coverage_admitted'] is True, 'One authoritative admitted PASS addition')
    life.check({str(ledger_path): auth['output_pins'][str(ledger_path)]})
    ledger = ledger_path.read_text().splitlines()
    need(ledger[-1] == origin['vdb'] and ledger[0] == origin['design'], 'Exact admitted single PASS sample')
    pins = {str(ORIGIN): ORIGIN_SEAL, str(AUTH): AUTH_SEAL,
            str(status_path): auth['output_pins'][str(status_path)],
            str(ledger_path): auth['output_pins'][str(ledger_path)]}
    pins.update({p: sha for p, sha in origin['pins'].items()
                 if p.startswith(origin['vdb'] + '/') or p.startswith(origin['design'] + '/')})
    return origin, pins


def prepare(out):
    need(out.parent == life.OUT and not out.exists(), 'Fresh independent discovery only')
    origin, pins = authority()
    pins = life.merge_pins(pins, PREDECESSORS)
    c = dict(schema='C910_VECTOR_UI_DISCOVERY_V3', output=str(out), timeout_seconds=300,
        automatic_retry=False, read_only=True, qualification=False, column_schemas=COLUMN_SCHEMAS, instances=[origin['instances'][0]],
        scope=origin['instances'][0]['scope'], identity=origin['identity'],
        **{k: origin[k] for k in ('design', 'vdb', 'test')})
    c['launch_contract'] = contract(out)
    for module in list(sys.modules.values()):
        p = getattr(module, '__file__', None)
        if p and Path(p).resolve().parent == SCRIPT.parent:
            pins[str(Path(p).resolve())] = life.digest(Path(p).resolve())
    for p in (SCRIPT, TEST, TCL, P740):
        pins[str(p)] = life.digest(p)
    for row in c['launch_contract']['host_tools']:
        pins[row['path']] = row['sha256']
    tools.revalidate(c['identity'])
    life.check(pins)
    out.mkdir()
    (out / 'selection.tcl').write_text(selection(c))
    (out / 'native-bind.tcl').write_bytes(TCL.read_bytes())
    for name in ('selection.tcl', 'native-bind.tcl'):
        pins[str(out / name)] = life.digest(out / name)
        core.ptw.primitive.check_generated_tcl.check(out / name)
    c['pins'] = pins
    life.save(out / 'config.json', c)
    return dict(output=str(out), seal=life.digest(out / 'config.json'), EDA_started=False,
                status='PREPARED_READONLY_DISCOVERY_PARENT_REVIEW_REQUIRED', timeout_seconds=300)


def check(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    life.check(c['pins'])
    need(c['schema'] == 'C910_VECTOR_UI_DISCOVERY_V3' and c['output'] == str(out) and
         type(c['timeout_seconds']) is int and c['timeout_seconds'] == 300 and
         c['automatic_retry'] is False and c['read_only'] is True and c['qualification'] is False,
         'Closed300 read-only discovery')
    need(c['column_schemas'] == COLUMN_SCHEMAS, 'Exact proven7/6 schemas')
    need(all(c['pins'].get(p) == sha for p, sha in PREDECESSORS.items()), 'Frozen predecessor source pins')
    origin = life.read_bound(ORIGIN, ORIGIN_SEAL)
    need(c['instances'] == [origin['instances'][0]] and c['scope'] == origin['instances'][0]['scope'] and
         all(c[k] == origin[k] for k in ('test', 'design', 'vdb', 'identity')), 'One exact scope/PASS/native identity')
    need(c['launch_contract'] == contract(out), 'Exact persistent interpreter/systemd environment')
    for p in (SCRIPT, TEST, TCL, P740, ORIGIN, AUTH):
        expected = ORIGIN_SEAL if p == ORIGIN else AUTH_SEAL if p == AUTH else life.digest(p)
        need(c['pins'].get(str(p)) == expected, 'Required discovery pin')
    need((out / 'selection.tcl').read_text() == selection(c) and
         (out / 'native-bind.tcl').read_bytes() == TCL.read_bytes(), 'Exact discovery driver')
    tools.revalidate(c['identity'])
    return c


def service_command(c, out, seal):
    cmd = base.service_command(c, out, seal)
    # 290 seconds runtime plus the inherited 10-second stop bound stays within 300.
    return ['--property=RuntimeMaxSec=290' if x == '--property=RuntimeMaxSec=900'
            else str(SCRIPT) if x == str(base.SCRIPT) else x for x in cmd]


def launch(out, seal, reviewed):
    approved(seal, reviewed)
    c = check(out, seal)
    need(not any((out / n).exists() for n in ('service-request.json', 'execution.json', 'terminal.json',
         'worker-error.json')), 'One shot only; no retries')
    cmd = service_command(c, out, seal)
    life.save(out / 'service-request.json', dict(config_seal=seal, reviewed_seal=reviewed,
        command=cmd, unit=c['launch_contract']['unit'], uid=os.getuid(), timeout_seconds=300))
    r = subprocess.run(cmd, cwd=out, capture_output=True, text=True, timeout=30)
    life.save(out / 'service-launch-receipt.json', dict(returncode=r.returncode, stdout=r.stdout,
                                                       stderr=r.stderr, command=cmd))
    need(type(r.returncode) is int and r.returncode == 0, 'Submission failure is not native completion')
    return dict(status='DISCOVERY_SUBMITTED_NOT_QUALIFIED', unit=c['launch_contract']['unit'])


def frames(path):
    data = path.read_bytes()
    records = []
    tcl = tkinter.Tcl()
    while data:
        prefix, sep, tail = data.partition(b'\n')
        need(sep and prefix.isdigit(), 'Length-framed raw record')
        size = int(prefix)
        need(len(tail) >= size + 1 and tail[size:size + 1] == b'\n', 'Complete raw payload')
        records.append(list(tcl.splitlist(tail[:size].decode('utf-8'))))
        data = tail[size + 1:]
    need(records, 'Nonempty snapshot')
    return records


def header_gate(records):
    tcl = tkinter.Tcl()
    probes = [r for r in records if r[0] == 'column_probe']
    need([int(r[1]) for r in probes] == list(range(8)), 'Fixed eight raw header probes')
    results = [tcl.splitlist(r[2]) for r in probes]
    need(all(len(r) == 3 and r[0] == '0' for r in results), 'Actual successful header queries')
    header = [r[1] for r in results]
    matches = [name for name, labels in COLUMN_SCHEMAS.items()
               if header == labels + [''] * (8 - len(labels))]
    need(len(matches) == 1, 'Unknown or changed full column header; whitespace exact')
    name = matches[0]
    schema = [r for r in records if r[0] == 'schema']
    need(schema == [['schema', name, str(len(COLUMN_SCHEMAS[name]))]], 'Exact selected schema')
    cols = [r for r in records if r[0] == 'column']
    n = len(COLUMN_SCHEMAS[name])
    need(cols == [['column', str(i), probes[i][2]] for i in range(n)], 'Every proven column return')
    return n


def capture_gate(out, c):
    need(not (out / 'discovery-error.txt').exists(), 'Native discovery failure recorded')
    need((out / 'discovery-done.txt').read_text().strip() ==
         'C910_SINGLE_SCOPE_DISCOVERY_DONE_NOT_QUALIFICATION', 'Explicit gated three-stage completion')
    tcl = tkinter.Tcl()
    counts = {}
    for stage in STAGES:
        records = frames(out / (stage + '.frames'))
        need(records[0] == ['snapshot', stage, c['scope'], c['test']], 'Exact stage/scope/sample')
        need(records[-1][0] == 'end' and records[-1][1] == '0', 'Complete raw tree traversal')
        rows = [r for r in records if r[0] == 'rawrow']
        need(len(rows) == int(records[-1][3]), 'Every raw row preserved')
        need(len({r[3] for r in rows}) == len(rows), 'Raw handle uniqueness')
        column_count = header_gate(records)
        contexts = [r for r in records if r[0] == 'context']
        need(len(contexts) == 11 and len([r for r in records if r[0] == 'action']) == 1,
             'View/selection/layout/currentview context and action returns')
        expected_context = {
            ('gui_covdetail_query', '-id', 'CovDetail.1', '-name', 'type'),
            ('gui_list_get_selected', '-id', 'CovDetail.1', '-flat'),
            ('gui_list_get_selected', '-id', 'CovDetail.1', '-count'),
            ('gui_list_get_selected', '-id', 'CoverageTable.1', '-flat'),
            ('gui_get_current_view',),
        }
        expected_context.update(('gui_get_state_value', '-category', 'Layout_CovDetail_' + view, '-key', key)
                                for view in COLUMN_SCHEMAS for key in ('names', 'orders', 'widths'))
        need({tcl.splitlist(r[1]) for r in contexts} == expected_context and
             all(len(tcl.splitlist(r[2])) == 3 for r in contexts), 'All exact context queries and returns')
        action = tcl.splitlist(next(r[1] for r in records if r[0] == 'action'))
        if stage == 'initial':
            need(action == ('setup_only',), 'Initial snapshot before any click')
        elif stage == 'selected':
            steps = [tcl.splitlist(x) for x in action]
            for step in steps:
                need(len(step) == 3 and len(tcl.splitlist(step[2])) == 3 and
                     tcl.splitlist(step[2])[0] == '0', 'Every selection operation must succeed')
            need([s[0] for s in steps][-5:] == ['cleared_count', 'select', 'selection_events', 'selected_count', 'selected_readback'],
                 'Strict selection terminal sequence')
            need(steps[0][0] == 'selected_before', 'Initial grouped selection recorded')
            old = []
            for group in tcl.splitlist(tcl.splitlist(steps[0][2])[1]):
                members = tcl.splitlist(group)
                need(members, 'Nonempty selected group')
                for wrapped in members:
                    tokens = tcl.splitlist(wrapped)
                    need(len(tokens) == 1 and tokens[0], 'Strict grouped old token')
                    old.append(tokens[0])
            need([(s[0], s[1]) for s in steps[1:-5]] == [('unselect', token) for token in old],
                 'Every exact old token unselected once')
            need(steps[-4][1] == 'initial_divisor_in[55:0]', 'Exact selected target')
            need(tcl.splitlist(steps[-5][2])[1] == '0' and tcl.splitlist(steps[-2][2])[1] == '1',
                 'Actual cleared0 and singleton1')
            groups = tcl.splitlist(tcl.splitlist(steps[-1][2])[1])
            need(len(groups) == 1, 'One selected group')
            members = tcl.splitlist(groups[0])
            need(len(members) == 1, 'One selected member')
            tokens = tcl.splitlist(members[0])
            need(tokens == ('initial_divisor_in[55:0]',), 'Exact grouped singleton')
            need(column_count == 6, 'Selection must actually expose detail schema')
        else:
            steps = [tcl.splitlist(x) for x in action]
            need([s[0] for s in steps] == ['double_click', 'events'] and
                 all(len(s) == 3 and tcl.splitlist(s[2])[0] == '0' for s in steps),
                 'One successful detail-token click only')
            selected_rows = frames(out / 'selected.frames')
            candidates = []
            for row in selected_rows:
                if row[0] != 'rawrow' or row[1] != '0':
                    continue
                fields = [tcl.splitlist(f) for f in tcl.splitlist(row[4])]
                path, name = tcl.splitlist(fields[0][-1]), tcl.splitlist(fields[2][-1])
                if path[0] == name[0] == '0' and name[1] == 'initial_divisor_in[55:0]':
                    tokens = tcl.splitlist(path[1])
                    if len(tokens) == 1 and tokens[0]:
                        candidates.append(tokens[0])
            need(candidates == [steps[0][1]], 'Click exact unique captured detail path token')
        for row in rows:
            need(len(row) == 7, 'Raw handle/depth/parent/fields/navigation returns')
            fields = [tcl.splitlist(x) for x in tcl.splitlist(row[4])]
            need([f[0] for f in fields[:3]] == ['path', 'meta', 'name'] and
                 [int(f[1]) for f in fields[3:]] == list(range(column_count)) and
                 all(f[0] == 'text' for f in fields[3:]), 'All raw identity and column return values')
            need(all(len(tcl.splitlist(f[-1])) == 3 for f in fields), 'Every raw query rc/value/errorInfo')
        counts[stage] = len(rows)
    return counts


def verify(out, seal):
    c = check(out, seal)
    need(not (out / 'worker-error.json').exists(), 'Worker failure is not completed discovery')
    terminal = json.loads((out / 'terminal.json').read_text())
    e = json.loads((out / 'execution.json').read_text())
    live = json.loads((out / 'live-identity.json').read_text())
    need(type(terminal['returncode']) is int and terminal['returncode'] == 0 and
         terminal['timeout'] is False and terminal['actual_dve'] == live and len(live) == 1,
         'Actual terminal0/non-timeout/native identity')
    need(e['command'] == core.ptw.command(c, out) and e['config_seal'] == seal and
         e['cwd'] == str(out) and e['timeout_seconds'] == 300, 'Exact measured execution')
    base.live_gate(live[0], c, e)
    request = json.loads((out / 'service-request.json').read_text())
    receipt = json.loads((out / 'service-launch-receipt.json').read_text())
    need(request == dict(config_seal=seal, reviewed_seal=seal, command=service_command(c, out, seal),
         unit=c['launch_contract']['unit'], uid=os.getuid(), timeout_seconds=300), 'Exact parent request')
    need(type(receipt['returncode']) is int and receipt['returncode'] == 0 and
         receipt['command'] == request['command'], 'Actual submission receipt')
    counts = capture_gate(out, c)
    paths = [out / (s + '.frames') for s in STAGES]
    paths += [out / n for n in ('terminal.json', 'execution.json', 'live-identity.json',
              'service-request.json', 'service-launch-receipt.json', 'discovery-done.txt',
              'launcher.log', 'worker.log', 'DVEfiles/dve_gui.log', 'DVEfiles/dve_history.log')]
    result = dict(status='READONLY_DISCOVERY_COMPLETE_NOT_QUALIFICATION', config_seal=seal,
        raw_row_counts=counts, pins={str(p): life.digest(p) for p in paths},
        hypothesis='STRICT_SINGLE_SELECTION_THEN_DETAIL_TOKEN',
        qualification=False, EL_applied=False, timeout_seconds=300)
    dest = out / 'discovery-result.json'
    if dest.exists():
        need(json.loads(dest.read_text()) == result, 'Existing result must match')
    else:
        life.save(dest, result)
    return result


def worker(out, seal, reviewed):
    proc, live, timeout, rc = None, [], False, 1
    c, group, phase = None, None, 'precheck'
    deadline = time.monotonic() + 280
    need(not any((out / n).exists() for n in ('worker-error.json', 'terminal.json', 'execution.json')),
         'One worker attempt only; preserve earlier evidence')
    try:
        approved(seal, reviewed)
        c = check(out, seal)
        need(os.environ.get('C1424_CONFIG_SEAL') == seal, 'Exact C1424 environment seal')
        group = cgroup_gate(proc_cgroup(os.getpid()), c['launch_contract'])
        request = json.loads((out / 'service-request.json').read_bytes())
        need(request['command'] == service_command(c, out, seal) and request['reviewed_seal'] == seal,
             'Exact independent parent authorization')
        need(not (out / 'execution.json').exists(), 'One native attempt only')
        env = tools.controlled_environment(c['identity'], os.environ)
        env.pop('DVE', None)
        env.update(DVE_COVERAGE_OUTPUT=str(out), C1424_CONFIG_SEAL=seal,
                   PYTHONPATH=c['launch_contract']['pythonpath'])
        cmd = core.ptw.command(c, out)
        execution = dict(command=cmd, cwd=str(out), config_seal=seal, timeout_seconds=300,
            service_unit=c['launch_contract']['unit'], worker_pid=os.getpid(), worker_cgroup=group)
        phase = 'native'
        with (out / 'launcher.log').open('x') as log, (out / 'worker.log').open('x') as worker_log:
            worker_log.write('Persistent systemd worker owns and waits for sealed DVE child\n')
            worker_log.flush()
            proc = subprocess.Popen(cmd, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            start = tools.process_info(proc.pid)['starttime']
            execution.update(launch_pid=proc.pid, launch_starttime=start)
            life.save(out / 'execution.json', execution)
            probe_deadline = min(deadline - 10, time.monotonic() + 60)
            while time.monotonic() < probe_deadline:
                live = observe(c, out, proc, start, execution)
                if live or proc.poll() is not None:
                    break
                time.sleep(0.5)
            life.save(out / 'live-identity.json', live)
            need(len(live) == 1, 'Actual sealed native child not found in worker cgroup')
            try:
                proc.wait(timeout=max(0, deadline - 10 - time.monotonic()))
            except subprocess.TimeoutExpired:
                timeout = True
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=5)
            rc = proc.returncode
    except Exception as error:
        life.save(out / 'worker-error.json', dict(error=str(error), phase=phase,
            EDA_started=proc is not None, returncode=rc if proc is None else proc.returncode))
        if proc is not None:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)
            rc = proc.returncode
        raise
    finally:
        life.save(out / 'terminal.json', dict(returncode=rc, timeout=timeout, actual_dve=live,
                  service_unit=c['launch_contract']['unit'] if c else None, worker_cgroup=group,
                  phase=phase, EDA_started=proc is not None))
    # The submitter may still be writing its real returncode receipt.
    receipt_deadline = time.monotonic() + 5
    while not (out / 'service-launch-receipt.json').exists() and time.monotonic() < receipt_deadline:
        time.sleep(0.1)
    try:
        return verify(out, seal)
    except Exception as error:
        life.save(out / 'worker-error.json', dict(error=str(error), phase='verify',
                  EDA_started=True, returncode=1, native_returncode=rc))
        raise

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'check', 'launch-reviewed', 'worker', 'verify'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal')
    p.add_argument('--parent-reviewed-seal')
    a = p.parse_args()
    out = a.output.resolve()
    if a.mode == 'prepare':
        need(a.seal is None and a.parent_reviewed_seal is None, 'Prepare cannot authorize EDA')
        result = prepare(out)
    elif a.mode == 'check':
        check(out, a.seal)
        result = dict(status='CHECK_PASS_NO_EDA')
    elif a.mode == 'launch-reviewed':
        result = launch(out, a.seal, a.parent_reviewed_seal)
    elif a.mode == 'worker':
        result = worker(out, a.seal, a.parent_reviewed_seal)
    else:
        result = verify(out, a.seal)
    print(json.dumps(result, indent=2), flush=True)

