"""One explicit742 report: approved66 FSM transitions plus four observer leaves."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

import audit_fsm741_exact as native
import fsm741_transition_native as capture
import observer_scope_741 as observer

life, require, tools = capture.life, capture.require, capture.tool
HERE = Path(__file__).resolve().parent
BASE = life.OUT / 'gap113-full8-cached-offline-admitted-742-agent-20261007-01'
BASE_SHA = 'f07f7ccdcfc7257faad21aabdc45a48008658c70ee26abda275065f1e204a730'
FSM = life.OUT / 'fsm741-exact66-full-report-20261007-02'
FSM_SHA = 'dd6dbf0c3a1d670fd0296aa392139d3ab3733be0682ba23a1bfbf381a23462ce'
OBS = life.OUT / 'observer-only-rooted-741-agent-20261007-04'
OBS_SHA = '5cb735aa8a46b42051b38784992bdeb432e5950559ab695c5be5b748c7a8a3a3'
OBS_EL_SHA = 'e6cce50e01716e4d07c95b5247917dfa543a8be6e53ad2a76f272b81cc92cd28'
OBS_QUAL_SHA = '89f34505d6650340851c46c983e95b0672803b6fd4949d2ac7c6b2ac05207c9c'
PTW_PROOF = life.OUT / 'ptw-rvh0-disabled-fsm-review-741-agent-20261007-01.json'
PTW_SHA = 'f21c4f28689fc4e68176463551343e9e4e9c86e053d223df8620ee020bea001c'
ANNOTATION = 'Integration scope: observation-only, not an unreachability waiver'


def combined_records(text):
    fsm, scopes = [], {}
    blocks = re.split(r'(?m)(?=^CHECKSUM:)', text)
    for block in blocks:
        if not block:
            continue
        header = block.splitlines()[0]
        if re.fullmatch(r'CHECKSUM: "[0-9]+ [0-9]+"', header):
            fsm.extend(native.native_records(block))
        else:
            entries = observer.native_entries(block)
            annotations = re.findall(r'(?m)^ANNOTATION: "([^"\r\n]*)"$', block)
            require(len(entries) == 1 and annotations == [ANNOTATION], 'Observer native attributes differ')
            require(not set(entries) & set(scopes), 'Duplicate observer scope')
            scopes.update(entries)
    require(len(fsm) == len(set(fsm)), 'Duplicate FSM native identity')
    return sorted(fsm), scopes


def exact_population(book, bits, state, ledger):
    require(state['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and state['coverage_admitted'] is True and
            state['aggregate_passed'] == 742 and state['exact741_prefix'] and state['unique_new_vdb'], 'Not formal742')
    prior_path = capture.report.BASE / 'admission-manifest.json'
    prior = life.read_bound(prior_path, capture.report.SEAL)
    before_path = capture.report.BASE / 'combined-bits.json'
    before = life.read_bound(before_path, prior['output_pins'][str(before_path)])
    require(book['baseline_seal'] == capture.report.SEAL and bits['tests'][:-1] == before['tests'] and
            len(bits['tests']) == len(set(bits['tests'])) == 742 and bits['design'] == before['design'] and
            ledger == [str(capture.BUILD / 'sim/simv.vdb'), *bits['tests']], '742 prefix/design/ledger differs')


def add_ptw(groups, proof, bits):
    require(proof['status'] == 'SOURCE_APPROVED_EXACT_DISABLED_MACHINE_NATIVE_CAPTURE_PENDING_NOT_APPLIED' and
            proof['scope'] == capture.PTW and proof['machine']['chksum'] == '158773701', 'Wrong PTW proof')
    stage = [g for g in groups if g['scope'] == capture.PTW and g['machine']['name'] == 'ptw_stage_q']
    require(len(stage) == 2 and all(g['machine'] == proof['machine'] for g in stage), 'PTW machine differs')
    approved = {(o['kind'], o['name']): o for o in proof['objects']}
    for g in stage:
        for row in g['rows']:
            obj = approved[(g['mode'], row['name'])]
            require(row['attributes'] == obj['shape_attributes'] and row['raw_index'] == obj['raw_index'] and
                    not obj['raw741_hit'] and not (int(bits['metrics']['fsm'][capture.PTW]['bits'], 16) &
                    (1 << (34 - row['raw_index']))), 'PTW compiled identity or zero differs')
            row['target'] = g['mode'] == 'Transition'
    require(sum(r['target'] for g in stage for r in g['rows']) == 6, 'Exact six PTW transitions required')


def prepare(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh output required')
    book = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    pins = life.merge_pins(book['input_pins'], book['output_pins'])
    bits = life.read_bound(BASE / 'combined-bits.json', pins[str(BASE / 'combined-bits.json')])
    state = life.read_bound(BASE / 'status.json', pins[str(BASE / 'status.json')])
    ledger = (BASE / 'combined-inputs.txt').read_text().splitlines()
    exact_population(book, bits, state, ledger)
    fsm = life.read_bound(FSM / 'qualification.json', FSM_SHA)
    require(fsm['status'] == 'FULL741_EXACT_FSM_ADJUSTED_REPORT_VERIFIED' and fsm['targets'] == 66,
            'Missing approved FSM qualification')
    oc = life.read_bound(OBS / 'config.json', OBS_SHA)
    oq = life.read_bound(OBS / 'qualification.json', OBS_QUAL_SHA)
    require(oq['status'] == 'QUALIFIED_EFFECTIVE_FOUR_OBSERVER_741_INTEGRATION_SCOPE' and
            oq['config_seal'] == OBS_SHA, 'Observer qualification differs')
    proof = life.read_bound(PTW_PROOF, PTW_SHA)
    pins = life.merge_pins(pins, fsm['input_pins'])
    pins = life.merge_pins(pins, oc['pins'])
    pins = life.merge_pins(pins, {str(BASE / 'admission-manifest.json'): BASE_SHA,
                                str(FSM / 'qualification.json'): FSM_SHA, str(OBS / 'config.json'): OBS_SHA,
                                str(OBS / 'observers.el'): OBS_EL_SHA,
                                str(OBS / 'qualification.json'): OBS_QUAL_SHA, str(PTW_PROOF): PTW_SHA})
    for record in [*proof['source_pins'], proof['shape'], proof['frozen_source_ledger'], proof['compile_command']]:
        pins = life.merge_pins(pins, {str(life.ROOT / record['path']): record['sha256']})
    life.check(pins)
    design = Path(ledger[0])
    targets = observer.compiled_targets(design / 'snps/coverage/db/design/verilog.design.xml')
    require(targets == oc['targets'], 'Observer compiled bindings differ')
    expected_observers = {s: v[1] for s, v in observer.TARGETS.items()}
    groups = capture.groups_from_shape(native.read_xml(design / 'snps/coverage/db/shape/fsm.verilog.shape.xml'), bits)
    add_ptw(groups, proof, bits)
    plan = dict(groups=groups, targets=72, protected=315, strategy='direct-transition-only-72',
                point_query_authority='saved-native-identity', no_other_waivers=True)
    expected = native.expected_records(plan, native.Design(design))
    original = [tuple(r) for r in fsm['native_records']]
    require(set(original) <= set(expected) and len(expected) == 72, 'Approved66 changed')
    extra = sorted(set(expected) - set(original))
    require(len(extra) == 6 and all(r[2] == capture.PTW and r[3] == 'ptw_stage_q' and r[4] == '158773701'
                                  and r[-3] == 'Transition' for r in extra), 'Foreign PTW addition')
    extra_el = ''.join('CHECKSUM: "%s %s"\nINSTANCE: %s\nFsm %s "%s"\nANNOTATION: "%s"\n%s %s "%s"\n' % r
                       for r in extra)
    combined = (FSM / 'first.el').read_text() + extra_el + (OBS / 'observers.el').read_text()
    require(combined_records(combined) == (expected, expected_observers), 'Approved native union differs')
    selected = []
    for vdb in ledger:
        testroot = Path(vdb) / 'snps/coverage/db/testdata'
        if testroot.is_dir():
            for test in sorted(testroot.iterdir()):
                if test.is_dir():
                    selected.append(str(Path(vdb).with_suffix('') / test.name))
    require(len(selected) == len(set(selected)) == 742, 'Ambiguous742 selected tests')
    raw = life.read_bound(capture.report.admission.RAW, capture.report.admission.RAW_SHA)
    tools.revalidate(raw['tool_identity'])
    dependencies = [Path(__file__).resolve(), HERE / 'report_fsm_observers742.tcl',
                    HERE / 'test_report_fsm_observers742.py', Path(native.__file__).resolve(),
                    Path(capture.__file__).resolve(), Path(observer.__file__).resolve(),
                    HERE / 'fsm741_transition_native.tcl', HERE / 'fsm741_transition_batch.tcl',
                    HERE / 'fsm741_native_singleton.tcl', HERE / 'fsm741_native_probe.tcl',
                    HERE / 'discover_ptw_pmp0_fsm_v2.tcl', HERE / 'apply_points740_v4.tcl',
                    HERE / 'export_dve_coverage.tcl', Path(tools.__file__).resolve()]
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in dependencies})
    life.check(pins)
    out.mkdir()
    with (out / 'inputs.txt').open('x') as stream:
        stream.write('\n'.join(ledger) + '\n')
    with (out / 'combined.el').open('x') as stream:
        stream.write(combined)
    with (out / 'selection.tcl').open('x') as stream:
        stream.write('set fx_groups {}\n')
        for group in groups:
            source = life.ROOT / group['source'] if group['scope'] != capture.DISPATCH else life.ROOT.parent / 'ara_dsa' / group['source']
            values = [group['scope'], str(source), group['machine']['name'], group['mode']]
            names = ' '.join(capture.tcl_atom(r['name']) for r in group['rows'])
            selected_names = ' '.join(capture.tcl_atom(r['name']) for r in group['rows'] if r['target'])
            stream.write('lappend fx_groups [list ' + ' '.join(capture.tcl_atom(v) for v in values) +
                         ' [list ' + names + '] [list ' + selected_names + ']]\n')
    for name in ('inputs.txt', 'combined.el', 'selection.tcl'):
        pins[str(out / name)] = life.digest(out / name)
    config = dict(schema='EXACT742_APPROVED72_FSM_FOUR_OBSERVER_REPORT', output=str(out), pins=pins,
                  input_ledger=ledger, expected_selected=selected, native_fsm=[list(r) for r in expected],
                  observers=expected_observers, plan=plan, tool_identity=raw['tool_identity'],
                  admission_seal=BASE_SHA, fsm_qualification_seal=FSM_SHA, observer_config_seal=OBS_SHA,
                  new_PTW_candidates_included=True, ptw_source_proof_seal=PTW_SHA, other_waivers_included=False)
    life.save(out / 'config.json', config)
    print(json.dumps(dict(status='PREPARED_NO_DVE', output=str(out), seal=life.digest(out / 'config.json'),
                          tests=742, inputs=743, fsm_transitions=72, observer_leaves=4, pins=len(pins))))


def verify(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    life.check(c['pins'])
    require((out / 'inputs.txt').read_text().splitlines() == c['input_ledger'] and
            (out / 'selected_tests.txt').read_text().splitlines() == c['expected_selected'], '742 native population differs')
    expected = ([tuple(r) for r in c['native_fsm']], c['observers'])
    for name in ('applied.el', 'reloaded.el'):
        require(combined_records((out / name).read_text()) == expected, 'Foreign/missing native identity or attribute')
    for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el', 'cleanup-empty.el'):
        require((out / name).read_bytes() == b'', 'Nonempty global reset')
    # Reuse the sealed projection protocol; the exact72 selectors remain unchanged.
    native.audit_points(list(csv.reader((out / 'exact-audit.tsv').open(), delimiter='\t')),
                        dict(c['plan'], strategy='direct-transition-only-66'))
    reports = {}
    for stage in ('raw', 'applied', 'reset', 'reloaded', 'final'):
        rows = list(csv.DictReader((out / ('rooted_' + stage + '.csv')).open()))
        require(len(rows) == 1 and rows[0]['Scope'] == rows[0]['Token'] == observer.SYSTEM and
                rows[0]['Name'] == rows[0]['GUIPath'] == 'i_system' and rows[0]['Stage'] == stage,
                'Rooted system identity differs')
        reports[stage] = {m: rows[0][m] for m in native.METRICS}
    require(reports['raw'] == reports['reset'] == reports['final'] and reports['applied'] == reports['reloaded'],
            'Rooted reset/reload differs')
    gui = (out / 'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('EXACT742_FSM_OBSERVERS_DONE') == 1 and
            gui.splitlines().count('DVE_COVERAGE_EXPORT_DONE') == 1 and
            not re.search(r'EXPORT_FAILED|EXACT742_FAILED|Error:|Fatal:|EK-CMD-|DVTC[0-9]+|UCAPI-DLMA|DVCDT136', gui),
            'Incomplete/failed native report')
    require(gui.splitlines().count('DVE_SELECTED_TESTS: ' + ' '.join(c['expected_selected'])) == 1,
            'GUI742 selected identity differs')
    life.check(c['pins'])
    result = dict(status='FULL742_EXACT72_FSM_FOUR_OBSERVER_REPORT_VERIFIED', population=742,
                  admission_seal=BASE_SHA, config_seal=seal, system=reports, native_fsm_transitions=72,
                  nonrecursive_observers=c['observers'], new_PTW_candidates_included=True,
                  input_pins=c['pins'], output_pins={str(out / n): life.digest(out / n) for n in
                  ('applied.el', 'reloaded.el', 'exact-audit.tsv', 'selected_tests.txt', 'DVEfiles/dve_gui.log',
                   'rooted_raw.csv', 'rooted_applied.csv', 'rooted_reset.csv', 'rooted_reloaded.csv', 'rooted_final.csv',
                   'initial-empty.el', 'reset-empty.el', 'final-empty.el', 'cleanup-empty.el')})
    life.save(out / 'qualification.json', result)
    print(json.dumps(dict(status=result['status'], seal=life.digest(out / 'qualification.json'), system=reports)))


def run(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    life.check(c['pins'])
    tools.revalidate(c['tool_identity'])
    require(not (out / 'launcher.log').exists(), 'No repeated DVE attempt')
    env = tools.controlled_environment(c['tool_identity'], os.environ)
    env.pop('DVE', None)
    env.update(DVE_COVERAGE_OUTPUT=str(out), FSM_PROBE_OUTPUT=str(out),
               DVE_REVIEWED_WAIVERS=str(HERE / 'report_fsm_observers742.tcl'))
    process = None
    try:
        with (out / 'launcher.log').open('x') as stream:
            process = subprocess.Popen(tools.launch_command(c['tool_identity'], HERE / 'export_dve_coverage.tcl'),
                                       cwd=out, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            start = tools.process_info(process.pid)['starttime']
            deadline = time.monotonic() + 60
            live = None
            while process.poll() is None and time.monotonic() < deadline:
                for p in Path('/proc').iterdir():
                    if not p.name.isdigit():
                        continue
                    try:
                        if (p / 'exe').resolve() == Path(c['tool_identity']['executable']):
                            live = tools.verify_live_executable(int(p.name), c['tool_identity'], process.pid, start)
                            break
                    except (OSError, ValueError):
                        pass
                if live:
                    break
                time.sleep(.2)
            require(live is not None, 'No launch-bound DVE')
            life.save(out / 'live-identity.json', live)
            (out / 'live-ready').touch()
            print('EXACT742_LIVE pid=%s launch=%s' % (live['pid'], process.pid), flush=True)
            code = process.wait(timeout=900)
            require(code == 0, 'DVE nonzero exit')
        verify(out, seal)
    except Exception as exc:
        life.save(out / 'failure.json', dict(reason=str(exc), no_retry=True))
        raise
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'run', 'verify'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal')
    a = p.parse_args()
    if a.mode != 'prepare':
        require(a.seal, 'Exact config seal required')
    (prepare(a.output.absolute()) if a.mode == 'prepare' else
     (run if a.mode == 'run' else verify)(a.output.absolute(), a.seal))
