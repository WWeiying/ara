"""Prepare/check a bounded actual-native discovery command; never launch EDA here."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import prepare_qbs_payload_side1792_732 as proof
import verify_qbs_payload_side1792_732_json as canonical
import dve_tool_identity as tool
from lzc_selector_native_prepare import tcl_word

HERE = Path(__file__).resolve().parent
SCRIPT = Path(__file__).resolve()
TCL = HERE / 'qbs_side1792_native_discovery.tcl'
TEST = HERE / 'test_qbs_side1792_native_discovery.py'
PARENT = proof.OUT / 'qbs-payload-side1792-proof-native-plan-732-parent-20261006-01'
PROOF_SEAL = 'bf1651bbae82cfc82db2695595b5d88f71ee26525bf482afca30b4626b9072e3'
ALLOWED = {'gui_list_get_selected', 'gui_list_select', 'gui_cov_show_cond_ids',
           'gui_list_action', 'gui_covdetail_query', 'gui_open_cov', 'gui_list_expand', 'gui_exit'}
require, sha = proof.require, proof.digest
SCOPE_BOUNDARY = dict(configuration='frozen732 integrated two-bank configuration',
    reset='valid reset followed by settled legal-known control and metadata',
    boolean_checks=768, boolean_checks_are_four_state_proof=False,
    excludes_X_and_delta=True,
    limitation='valid/mask X with plane2 and another remaining byte1 may recapture X. Oldside X is not known1 reachability; no DUT-bug claim.',
    candidate_annotation='Exact1792 known-vector source proof only; no X/delta unreachable claim; native HOLD')


def safe_tcl(text):
    require(set(re.findall(r'\bgui_\w+', text)) == ALLOWED, 'Unexpected GUI API')
    require(not re.search(r'\b(exec|eval|uplevel|after)\b|\-columns|\.el\b', text), 'Unsafe query/callback')
    require(text.count('source ') == 1 and 'source $env(QBS_SIDE1792_SELECTION)' in text,
            'Only sealed generated selection may be sourced')
    require('-unselect [list $name]' in text and '-select [list $expression]' in text,
            'Only actual expression selections permitted')


def check_pins(pins):
    for name, expected in pins.items():
        require(re.fullmatch('[0-9a-f]{64}', expected) and sha(Path(name)) == expected,
                'Input pin drift: ' + name)


def selection(artifact, database, test):
    groups = artifact['native_groups']
    require(len(groups) == 1344 and sum(len(g['targets']) for g in groups) == 1792 and
            sum(len(g['retained']) for g in groups) == 1792, 'Exact partial group population required')
    scopes = sorted(artifact['scope_protection'])
    require(len(scopes) == 2, 'Two exact payload scopes required')
    text = 'set qsd_design ' + tcl_word(proof.DESIGN) + '\n'
    text += 'set qsd_testdir ' + tcl_word(database) + '\nset qsd_test ' + tcl_word(test) + '\n'
    text += 'set qsd_scopes [list\n'
    for scope in scopes:
        rows = [g for g in groups if g['scope'] == scope]
        require(len(rows) == 672 and len({g['expression'] for g in rows}) == 672, 'Duplicate/foreign expression')
        text += ' [list ' + tcl_word(scope) + ' [list\n'
        for g in rows:
            require(sorted(g['targets'] + g['retained']) == sorted(g['names']) and
                    g['retained'] and 2 <= len(g['names']) <= 3, 'Whole/invalid group')
            text += '  [list ' + tcl_word(g['expression']) + ' [list ' + ' '.join(map(tcl_word, g['names'])) + ']]\n'
        text += ' ]]\n'
    return text + ']\n'


def write(path, value):
    with path.open('x') as stream:
        if isinstance(value, str):
            stream.write(value)
        else:
            json.dump(value, stream, indent=2, sort_keys=True); stream.write('\n')


def inspect_rows(raw, artifact):
    """Parse Tcl lists only, never execute captured commands or infer native IDs."""
    import tkinter
    require(len(raw) <= 32 * 1024 * 1024 and raw.endswith(b'\n') and b'\x00' not in raw,
            'Incomplete/oversized capture')
    text = raw.decode('ascii')
    interp = tkinter.Tcl()
    interp.tk.wantobjects(False)
    split = interp.splitlist
    expected = {(g['scope'], g['expression']): g for g in artifact['native_groups']}
    seen, inventory, completed, displays = set(), {}, set(), set()
    terminal = False
    # Reuse the exact bounded wrapper semantics from the pinned capture script.
    interp.eval(TCL.read_text().split('if {![info exists qsd_test_only]}')[0])
    for line in text.splitlines():
        require(not terminal, 'Data after completion')
        fields = split(line)
        require(fields, 'Empty record')
        kind = fields[0]
        if kind == 'inventory':
            require(len(fields) == 3 and fields[1] in artifact['scope_protection'] and fields[1] not in inventory,
                    'Foreign/duplicate inventory')
            names = [interp.call('qsd_name', x) for x in split(fields[2])]
            require(0 < len(names) <= 8192 and len(names) == len(set(names)), 'Native inventory ambiguity')
            inventory[fields[1]] = set(names)
        elif kind == 'group':
            require(len(fields) == 5, 'Group shape differs')
            key = fields[1], fields[2]
            require(key in expected and key not in seen and key[0] in inventory and key[1] in inventory[key[0]],
                    'Foreign/duplicate/absent actual expression')
            require(interp.call('qsd_name', fields[3]) == key[1], 'Actual selected expression drift')
            names = [interp.call('qsd_name', x) for x in split(fields[4])]
            require(sorted(names) == sorted(expected[key]['names']), 'Actual vector names drift')
            seen.add(key)
        elif kind == 'ids_display':
            require(len(fields) == 3 and fields[1] in inventory and fields[1] not in displays, 'Invalid IDs-display scope')
            require(len(split(fields[2])) <= 8192, 'IDs display bound')
            displays.add(fields[1])
        elif kind == 'scope_complete':
            require(len(fields) == 3 and fields[1] in inventory and fields[1] not in completed and fields[2] == '672',
                    'Incomplete/foreign scope')
            completed.add(fields[1])
        elif kind == 'complete':
            require(fields == ('complete', '1344', 'NATIVE_SIGNATURE_HOLD'), 'False qualification marker')
            terminal = True
        elif kind == 'selected_before_clear':
            require(len(fields) == 3, 'Clear record shape')
            normalized = [interp.call('qsd_name', x) for x in split(fields[1])]
            require([x for x in normalized if x != ''] == list(split(fields[2])), 'Empty-token filtering drift')
        elif kind == 'input':
            require(len(fields) == 4 and fields[1] == str(proof.DESIGN), 'Foreign input')
        else:
            raise ValueError('Unknown native record: ' + kind)
    require(terminal and seen == set(expected) and completed == displays == set(artifact['scope_protection']),
            'Incomplete native discovery')
    return dict(status='ACTUAL_NAMES_OBSERVED_NUMERIC_SIGNATURE_HOLD', groups=len(seen),
                scope_boundary=SCOPE_BOUNDARY, native_qualified=False)


def prepare(output):
    require(output.parent == proof.OUT and output.resolve() == output and not output.exists(), 'Fresh direct output required')
    path = PARENT / 'proof-native-plan.json'
    canonical.verify(path, PROOF_SEAL)
    artifact = json.loads(path.read_bytes())
    check_pins(artifact['pins'])
    safe_tcl(TCL.read_text())
    bitmap_path = proof.BASE / 'combined-bits.json'
    bitmap = json.loads(bitmap_path.read_bytes())
    database = Path(bitmap['tests'][0])
    testroot = database / 'snps/coverage/db/testdata'
    children = sorted(p for p in testroot.iterdir() if p.is_dir())
    require(len(children) == 1, 'Ambiguous sample testdata')
    test = str(database.with_suffix('') / children[0].name)
    identity = tool.prepare(shutil.which('dve'), shutil.which('xvfb-run'))
    generated = selection(artifact, database, test)
    output.mkdir()
    write(output / 'selection.tcl', generated)
    pins = dict(artifact['pins'])
    for p in (path, SCRIPT, TCL, TEST, Path(canonical.__file__), Path(tool.__file__),
              HERE / 'lzc_selector_native_prepare.py', bitmap_path, output / 'selection.tcl'):
        pins[str(p)] = sha(p)
    # Seal the selected read-only sample, not all732 run data: no coverage claim is made.
    for p in sorted(database.rglob('*')):
        if p.is_file():
            pins[str(p)] = sha(p)
    record = dict(schema='QBS_SIDE1792_NATIVE_DISCOVERY_V1', status='PREPARED_NOT_LAUNCHED_NATIVE_HOLD',
        proof=str(path), proof_seal=PROOF_SEAL, baseline=str(proof.BASE), baseline_seal=proof.BASE_SHA,
        sample_database=str(database), sample_test=test, sample_not_732_coverage_merge=True,
        pins=pins, tool_identity=identity, budget_seconds=300,
        command=['/usr/bin/timeout', '--kill-after=10s', '300s'] + tool.launch_command(identity, TCL),
        environment=dict(QBS_SIDE1792_SELECTION=str(output/'selection.tcl'), QBS_SIDE1792_OUTPUT=str(output)),
        target_groups=1344, target_vectors=1792, retained_neighbor_vectors=1792, protected_condition_points=41214,
        scope_protection=artifact['scope_protection'],
        source_proof_scope_boundary=SCOPE_BOUNDARY,
        parent_provenance='PARENT_AGENT_INDEPENDENT_EXECUTION',
        identity_policy='Actual expression/vector names and observed IDs-display bytes only. No XML IDs, list-order mapping, hidden columns or inferred native checksum. Numeric signatures remain HOLD.',
        protections='Condition view selection only in2 exact scopes. No exclusions/reset/import/saveEL, other metrics/scopes untouched.',
        native_qualified=False, application_approval=False, launched=False)
    write(output/'discovery-plan.json', record)
    seal = sha(output/'discovery-plan.json')
    write(output/'seal.json', dict(seal=seal, launched=False, native_qualified=False))
    print(json.dumps(dict(output=str(output), seal=seal, pins=len(pins), native_qualified=False)))


def verify(output, seal):
    path = output/'discovery-plan.json'
    require(output.parent == proof.OUT and output.resolve() == output and sha(path) == seal, 'External discovery seal drift')
    plan = json.loads(path.read_bytes())
    check_pins(plan['pins']); tool.revalidate(plan['tool_identity']); safe_tcl(TCL.read_text())
    require(plan['proof'] == str(PARENT/'proof-native-plan.json') and plan['proof_seal'] == PROOF_SEAL and
            sha(Path(plan['proof'])) == PROOF_SEAL, 'Proof binding drift')
    artifact = json.loads(Path(plan['proof']).read_bytes())
    require((output/'selection.tcl').read_text() == selection(artifact, Path(plan['sample_database']), plan['sample_test']),
            'Generated selections differ')
    require(plan['command'] == ['/usr/bin/timeout', '--kill-after=10s', '300s'] + tool.launch_command(plan['tool_identity'], TCL) and
            plan['environment'] == dict(QBS_SIDE1792_SELECTION=str(output/'selection.tcl'), QBS_SIDE1792_OUTPUT=str(output)) and
            not plan['launched'] and not plan['native_qualified'] and not plan['application_approval'], 'Scope/command drift')
    require(plan['source_proof_scope_boundary'] == SCOPE_BOUNDARY, 'Known-control scope boundary drift')
    print('VERIFY_PASS_PREPARED_NO_LAUNCH_NATIVE_HOLD')
    return plan


def authorization(path, seal):
    receipt = json.loads(path.read_bytes())
    require(receipt == dict(source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL',
        plan_seal=seal, action='ONE_READ_ONLY_NATIVE_DISCOVERY', budget_seconds=300,
        exclusions=False, application=False), 'Explicit exact parent discovery authorization required')
    return dict(path=str(path), sha256=sha(path))


def capture(output, seal, receipt):
    # This entry is inert without a separately supplied parent authorization receipt.
    approved = authorization(receipt, seal)
    plan = verify(output, seal)
    require(not (output/'launch.json').exists(), 'Single launch only; preserve old directory')
    env = tool.controlled_environment(plan['tool_identity'], os.environ)
    env.update(plan['environment'])
    started = time.monotonic()
    status = dict(status='HOLD', native_qualified=False, application=False, authorization=approved)
    with (output/'dve.log').open('xb') as log:
        process = subprocess.Popen(plan['command'], cwd=output, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        launch_start = tool.process_info(process.pid)['starttime']
        write(output/'launch.json', dict(pid=process.pid, starttime=launch_start,
            command=plan['command'], plan_seal=seal, authorization=approved))
        try:
            # Startup identity handshake only; after confirmation wait without polling.
            live = None
            deadline = time.monotonic() + 20
            while live is None and time.monotonic() < deadline:
                for entry in Path('/proc').iterdir():
                    if not entry.name.isdigit():
                        continue
                    try:
                        if (entry/'exe').resolve(strict=True) == Path(plan['tool_identity']['executable']):
                            live = tool.verify_live_executable(int(entry.name), plan['tool_identity'], process.pid, launch_start)
                            break
                    except (OSError, ValueError):
                        pass
                if live is None:
                    time.sleep(0.5)
            require(live is not None, 'Actual DVE executable not confirmed')
            write(output/'actual-executable.json', live)
            print(json.dumps(live), flush=True)
            code = process.wait(timeout=max(1, 320-(time.monotonic()-started)))
            status['returncode'] = code
            require(code == 0, 'DVE nonzero terminal')
            check_pins(plan['pins']); tool.revalidate(plan['tool_identity'])
            require(not list(output.rglob('*.el')), 'Unexpected exclusion artifact')
            rows = (output/'native-rows.tcllist').read_bytes()
            status.update(inspect_rows(rows, json.loads(Path(plan['proof']).read_bytes())))
        except Exception as error:
            status['error'] = str(error)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL); process.wait()
            status['elapsed_seconds'] = round(time.monotonic()-started, 3)
    # Preserve raw bytes even on decoding/API failure, never errors=ignore.
    status['artifacts'] = {str(p): sha(p) for p in output.rglob('*') if p.is_file()}
    write(output/'capture-status.json', status)
    print(json.dumps(dict(status=status['status'], native_qualified=False)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'verify', 'capture-readonly'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    parser.add_argument('--authorization', type=Path)
    args = parser.parse_args()
    output = args.output.absolute()
    if args.command == 'prepare':
        prepare(output)
    elif args.command == 'verify':
        verify(output, args.seal)
    else:
        require(args.authorization is not None, 'Parent authorization required before launch')
        capture(output, args.seal, args.authorization.absolute())


if __name__ == '__main__':
    main()
