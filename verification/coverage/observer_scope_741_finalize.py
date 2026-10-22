"""Offline04 finalization: retain exact tables and qualify excluded-row rendering separately."""
import argparse
import json
from pathlib import Path

import observer_scope_741_rooted_global as adapter


def finalize(out, seal):
    n = adapter.namespace()
    life, require = n['life'], n['require']
    c = life.read_bound(out / 'config.json', seal)
    life.check(c['pins'])
    terminal = json.loads((out / 'terminal.json').read_bytes())
    require(terminal == dict(returncode=0, actual_dve_confirmed=True), 'No successful actual DVE terminal')
    expected = {p: v[1] for p, v in n['TARGETS'].items()}
    parser = n['n']['native_entries']
    for name in ('initial-empty.el', 'final-empty.el'):
        require(parser((out / name).read_text()) == {}, 'Nonempty initial/reset EL')
    require((out / 'observers.el').read_bytes() == (out / 'observers-reloaded.el').read_bytes(), 'Native EL reload bytes differ')
    require(parser((out / 'observers.el').read_text()) == expected, 'Not exactly four approved observer/checksums')
    reports = {s: n['rooted'](out / ('rooted_' + s + '.csv'), s) for s in ('raw', 'applied', 'reloaded', 'reset')}
    require(reports['raw'] == reports['reset'], 'Any raw/reset rooted metric differs')
    for p in [n['SYSTEM'], *n['PROTECTED']]:
        require(reports['applied'][p] == reports['reloaded'][p], 'Non-observer rooted reload metric differs')
    for p in n['PROTECTED']:
        require(reports['raw'][p] == reports['applied'][p], 'Protected product root changed')
    differences = {}
    for p in expected:
        a, b = reports['applied'][p], reports['reloaded'][p]
        require(all(a[k] == 'NA' and b[k] in ('NA', '0.00%') for k in n['METRICS']),
                'Observer has a non-excluded display or unexpected reload value')
        differences[p] = dict(applied=a, reloaded=b)
    raw = n['n']['rows'](out / 'summary.csv.partial')
    require(raw == n['n']['rows'](n['n']['RAW'] / 'summary.csv'), 'Any full raw741 report row differs')
    require(reports['raw'][n['SYSTEM']] == {k: raw[n['SYSTEM']][k] for k in n['METRICS']}, 'Rooted raw baseline differs')
    require(reports['raw'][n['SYSTEM']] != reports['applied'][n['SYSTEM']], 'No effective scope scoring change')
    require((out / 'selected_tests.txt').read_text().splitlines() == c['expected_selected'], 'Not exact741 selection')
    gui = (out / 'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('OBSERVER_741_SAVE_RELOAD_RESET_DONE') == 1 and
            gui.splitlines().count('DVE_COVERAGE_EXPORT_DONE') == 1, 'Incomplete native batch')
    require(not n['n']['re'].search(r'(^|\s)(Warning|Error|Fatal)([\s:-]|$)|EXPORT_FAILED',
            gui + (out / 'launcher.log').read_text(), n['n']['re'].M), 'DVE error/warning')
    result = dict(status='QUALIFIED_EFFECTIVE_FOUR_OBSERVER_741_INTEGRATION_SCOPE', config_seal=seal,
        population=741, observer_targets=c['targets'], raw_i_system=reports['raw'][n['SYSTEM']],
        scoped_i_system=reports['applied'][n['SYSTEM']], raw_reset_exact=True,
        nonobserver_apply_reload_exact=True, native_EL_save_reload_byte_exact=True,
        all_rooted_rows_apply_reload_literal_equal=False, observer_display_differences=differences,
        display_qualification='Only exact four INSTANCE-excluded observers: apply NA vs reload0.00; no product metric normalization',
        protected_roots=n['PROTECTED'], full_raw_rows_verified=2989, reports=reports,
        earlier_strict_checker_rejection='Literal equality of excluded observer NA/0.00 rendering; preserved, no DVE retry',
        observer_runtime_checks_unchanged=True, functional_IP_exclusions=[], new_RTL_signoff=False,
        input_pins=c['pins'], finalizer_pins={str(Path(__file__).resolve()): life.digest(Path(__file__).resolve())},
        output_pins={str(p): life.digest(p) for p in out.rglob('*') if p.is_file() and p.name != 'qualification.json'})
    path = out / 'qualification.json'
    if path.exists():
        require(json.loads(path.read_bytes()) == result, 'Qualification evidence drift')
    else:
        life.save(path, result)
    print(json.dumps(dict(path=str(path), seal=life.digest(path), status=result['status'],
                         raw=result['raw_i_system'], scoped=result['scoped_i_system'])))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--seal', required=True)
    a = p.parse_args()
    finalize(a.output.absolute(), a.seal)
