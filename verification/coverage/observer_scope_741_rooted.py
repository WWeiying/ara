"""One authorized Rooted refresh follow-up; unchanged exact four-observer EL."""
import argparse
import csv
import json
from pathlib import Path

import observer_scope_741_v2 as frozen

n = frozen.namespace()
life, require, common = n['life'], n['require'], n['common']
HERE, SYSTEM, TARGETS = n['HERE'], n['SYSTEM'], n['TARGETS']
PREVIOUS = life.OUT / 'observer-only-scoped-741-agent-20261007-02'
SEAL = '0e13e4c1dd059a0a79769c95cfe635771fd4712c1a36fbad60bef3962ca3e7cd'
LIB = HERE / 'apply_points740_v4.tcl'
LIB_SHA = '506d6f5f073ff3294e10f34830da8ba68676491e7265013a016b6063ff58727e'
PROTECTED = [SYSTEM + '.i_ara', SYSTEM + '.i_ara.i_dispatcher', SYSTEM + '.i_ara.i_vlsu']
ROOTS = [SYSTEM, *TARGETS, *PROTECTED]
METRICS = ('Score', 'Line', 'Toggle', 'FSM', 'Condition', 'Branch')
DOCROOT = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1')


def prepare(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh direct output required')
    c = life.read_bound(PREVIOUS / 'config.json', SEAL)
    life.check(c['pins'])
    require(life.digest(LIB) == LIB_SHA and c['targets'] == n['compiled_targets'](
        Path((PREVIOUS / 'inputs.txt').read_text().splitlines()[0]) / 'snps/coverage/db/design/verilog.design.xml'),
        'Rooted library/observer bindings differ')
    files = [Path(__file__).resolve(), HERE / 'observer_scope_741_rooted.tcl',
             HERE / 'test_observer_scope_741_rooted.py', LIB, PREVIOUS / 'config.json',
             PREVIOUS / 'result.json',
             life.OUT / 'point-only-5832-raw740-v4-agent-20261007-01/rooted_raw.csv',
             life.OUT / 'point-only-5832-raw740-v4-agent-20261007-01/rooted_applied.csv',
             DOCROOT / 'doc/UserGuide/pdf/cov_ug_vcsmx.pdf',
             DOCROOT / 'gui/dve/auxx/gui/dve/preferencesCovMainMenu.tcl',
             DOCROOT / 'gui/dve/auxx/gui/dialogs/helpstrings.tcl']
    pins = life.merge_pins(c['pins'], {str(p): life.digest(p) for p in files})
    life.check(pins)
    out.mkdir()
    for name in ('inputs.txt', 'observer-plan.tcl'):
        common.save(out / name, (PREVIOUS / name).read_text())
    roots = 'set p740_scopes {\n' + ''.join(' {' + p + '}\n' for p in ROOTS) + '}\narray set p740_root_names {\n'
    roots += ''.join(' {' + p + '} {' + p.split('.')[-1] + '}\n' for p in ROOTS) + '}\n'
    common.save(out / 'root-selection.tcl', roots)
    for name in ('inputs.txt', 'observer-plan.tcl', 'root-selection.tcl'):
        pins = life.merge_pins(pins, {str(out / name): life.digest(out / name)})
    c = dict(c, output=str(out), pins=pins, predecessor_config=str(PREVIOUS / 'config.json'),
        predecessor_seal=SEAL, roots=ROOTS,
        hypothesis='Expanded-tree text is stale; re-root unique native row as in measured5832point report',
        scoring_evidence='Local GUI menu invokes gui_exclusion -recalculate; no hiding/scoring switch added',
        previous_report_effective_statistics_verified=False)
    life.save(out / 'config.json', c)
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'config.json'), roots=len(ROOTS), pins=len(pins))))


def rooted(path, stage):
    with path.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == len(ROOTS), 'Rooted row count differs')
    result = {}
    for row, scope in zip(rows, ROOTS):
        require(row['Stage'] == stage and row['Scope'] == row['Token'] == scope and
                row['GUIPath'] == row['Name'] == scope.split('.')[-1] and row['Handle'].isdigit(),
                'Rooted native scope identity differs')
        result[scope] = {k: row[k] for k in METRICS}
    return result


def verify(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    life.check(c['pins'])
    expected = {p: v[1] for p, v in TARGETS.items()}
    for name in ('initial-empty.el', 'final-empty.el'):
        require(n['native_entries']((out / name).read_text()) == {}, 'Nonempty initial/reset EL')
    for name in ('observers.el', 'observers-reloaded.el'):
        require(n['native_entries']((out / name).read_text()) == expected, 'Foreign scope/checksum/point exclusion')
    reports = {s: rooted(out / ('rooted_' + s + '.csv'), s) for s in ('raw', 'applied', 'reloaded', 'reset')}
    require(reports['raw'] == reports['reset'] and reports['applied'] == reports['reloaded'], 'Rooted reset/reload mismatch')
    require(all(reports['raw'][p] == reports['applied'][p] for p in PROTECTED), 'Protected product root changed')
    raw = n['rows'](out / 'summary.csv.partial')
    require(raw == n['rows'](n['RAW'] / 'summary.csv'), 'Full raw741 hierarchy changed')
    require(reports['raw'][SYSTEM] == {k: raw[SYSTEM][k] for k in METRICS}, 'Rooted raw741 baseline differs')
    require(reports['raw'][SYSTEM] != reports['applied'][SYSTEM], 'HOLD: no effective observer scoring change')
    gui = (out / 'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('OBSERVER_741_SAVE_RELOAD_RESET_DONE') == 1 and
            gui.splitlines().count('DVE_COVERAGE_EXPORT_DONE') == 1, 'Incomplete native batch')
    require((out / 'selected_tests.txt').read_text().splitlines() == c['expected_selected'], '741 selected identities differ')
    require(not n['re'].search(r'(^|\s)(Warning|Error|Fatal)([\s:-]|$)|EXPORT_FAILED',
            gui + (out / 'launcher.log').read_text(), n['re'].M), 'DVE diagnostics')
    result = dict(status='VERIFIED_EFFECTIVE_OBSERVER_ONLY_741_INTEGRATION_SCOPE', population=741,
        config_seal=seal, raw_i_system=reports['raw'][SYSTEM], scoped_i_system=reports['applied'][SYSTEM],
        exact4_nonrecursive_observers=c['targets'], protected_roots=PROTECTED,
        full_raw_rows=len(raw), native_EL_exclusive=True, raw_reset_parity=True, save_reload_parity=True,
        observer_runtime_PASS_checks_unchanged=True, new_RTL_signoff=False, functional_IP_exclusions=[],
        reports=reports, input_pins=c['pins'],
        output_pins={str(p): life.digest(p) for p in out.rglob('*') if p.is_file() and p.name != 'result.json'})
    if (out / 'result.json').exists():
        require(json.loads((out / 'result.json').read_bytes()) == result, 'Result drift')
    else:
        life.save(out / 'result.json', result)
    print(json.dumps(dict(seal=life.digest(out / 'result.json'), raw=result['raw_i_system'], scoped=result['scoped_i_system'])))


def run(out, seal):
    # Private frozen lifecycle: only entry Tcl and final verifier are substituted.
    function = n['run']
    scope = dict(function.__globals__)
    scope['verify'] = verify
    code = frozen.SOURCE.read_text()
    old = "DVE_REVIEWED_WAIVERS=str(HERE / 'observer_scope_741.tcl')"
    require(code.count(old) == 1, 'Entry substitution not exact')
    # Compile only the run function, leaving the sealed source and shared globals intact.
    import ast
    tree = ast.parse(code.replace(old, "DVE_REVIEWED_WAIVERS=str(HERE / 'observer_scope_741_rooted.tcl')"))
    runnode = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == 'run')
    exec(compile(ast.Module(body=[runnode], type_ignores=[]), str(frozen.SOURCE), 'exec'), scope)
    scope['run'](out, seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'run', 'verify'))
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--seal')
    a = p.parse_args()
    if a.mode == 'prepare':
        prepare(a.output.absolute())
    else:
        require(a.seal, 'Exact prepared seal required')
        (run if a.mode == 'run' else verify)(a.output.absolute(), a.seal)
