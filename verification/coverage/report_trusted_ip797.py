"""Independent trusted execution-IP report; preserve the qualified raw797 corpus."""
import argparse
import csv
import io
import json
import os
from pathlib import Path
from types import FunctionType

import report_global777_compact as s
import review_trusted_execution797_system_v2 as policy

HERE = Path(__file__).resolve().parent
BASE = s.OUT / 'current-population797-masku-zero3-prepared-agent-20261008-01'
BASE_CONFIG = '170c663a862aa530540f186eb1d04101d4b14046647cf14e5a894a5ab8343e1b'
BASE_QUAL = '9db76c7b52ba428dba02057575bd68cf1ae4c2d25340bd1e00e5025a1ec5b771'
REVIEW = s.OUT / 'trusted-execution797-isystem-review-agent-20261008-02.json'
REVIEW_SHA = '7089a39a78818e9abf5e420aef5b5b4e61a196e8743983654ed19be6cf104769'
TCL = Path(__file__).with_suffix('.tcl')
need, life = s.need, s.life


def owned(scope, roots):
    return any(scope == r or scope.startswith(r + '.') for r in roots)


def normalized(text, roots):
    other, masks = s.semantic(text)
    # Native save may retain redundant child points or omit them under a whole IP.
    return ({x for x in other if not owned(x[0], roots)},
            {k: v for k, v in masks.items() if not owned(k[0], roots)})


def whole_gate(text, c):
    other, _ = s.semantic(text)
    expected = c['trusted_roots']
    actual = {scope: checks for scope, checks, _, directive in other
              if directive == 'WHOLE_SCOPE' and owned(scope, expected)}
    need(actual == expected, 'Exact approved whole-IP roots/checksums; no extra descendants')
    need(s.semantic_seal(normalized(text, expected)) == c['retained_EL_seal'],
         'Every inherited exclusion outside trusted IP must be preserved')


def prepare(out, unit):
    need(out.parent == s.OUT and not out.exists(), 'Fresh independent report')
    need(s.re.fullmatch(r'ara-[a-zA-Z0-9-]+\.service', unit), 'Explicit owning unit')
    reader = s.Reader()
    base = reader.read(BASE / 'config.json', BASE_CONFIG, True)
    q = reader.read(BASE / 'qualification.json', BASE_QUAL, True)
    need(q['population'] == q['actual_selected_tests'] == 797 and q['config_seal'] == BASE_CONFIG,
         'Qualified exact797 baseline')
    review = reader.read(REVIEW, REVIEW_SHA, True)
    policy.validate(review)
    roots = review['minimal_recommended_roots']
    by_scope = {t['scope']: t for t in review['candidates']}
    expected = {r: by_scope[r]['design_checksum'] for r in roots}
    need(len(expected) == 577 and all(policy.inside(r) and
         by_scope[r]['decision'] == 'RECOMMEND' for r in roots), 'Approved577 roots')
    baseline_el = reader.read(BASE / 'applied.el', q['output_pins'][str(BASE / 'applied.el')]).decode('ascii')
    pins = dict(review['pins'])
    pins.update(reader.pins)
    # Bind actual coverage inputs, not merely manifests declaring a population.
    for path, sha in base['pins'].items():
        if any(path.startswith(db + '/') for db in base['input_ledger']):
            pins[path] = sha
    for path in (Path(__file__).resolve(), TCL, HERE / 'test_report_trusted_ip797.py',
                 s.EXPORT, s.ROOT_HELPER, s.TCL, Path(s.__file__).resolve(), Path(policy.__file__).resolve()):
        pins[str(path)] = life.digest(path)
    reader.finish(pins)
    s.tools.revalidate(base['tool_identity'])
    out.mkdir()
    files = {
        'inputs.txt': '\n'.join(base['input_ledger']) + '\n',
        'combined.el': baseline_el,
        'root-selection.tcl': s.selection(base['hierarchy_roots']),
        'trusted-scopes.tcl': 'set trusted_scopes {\n' + ''.join(' {' + r + '}\n' for r in roots) + '}\n',
    }
    for name, text in files.items():
        with (out / name).open('x') as stream:
            stream.write(text)
        pins[str(out / name)] = life.digest(out / name)
    c = dict(schema='TRUSTED_IP_INTEGRATION797_V1', population=797, output=str(out), pins=pins,
        trusted_roots=expected, retained_EL_seal=s.semantic_seal(normalized(baseline_el, expected)),
        baseline_EL_seal=s.semantic_seal(s.semantic(baseline_el)),
        input_ledger=base['input_ledger'], expected_selected=base['expected_selected'],
        hierarchy_roots=base['hierarchy_roots'], tool_identity=base['tool_identity'],
        baseline_qualification=BASE_QUAL, timeout_seconds=3600, owner_uid=os.getuid(),
        owning_service_unit=unit,
        expected_cgroup='/user.slice/user-%d.slice/user@%d.service/app.slice/%s' % (os.getuid(), os.getuid(), unit),
        historical_PASS_only_no_new_RTL_signoff=True, unreachability_claim=False)
    life.save(out / 'config.json', c)
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'config.json'), roots=len(expected))))


def check(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    need(c['schema'] == 'TRUSTED_IP_INTEGRATION797_V1' and c['output'] == str(out), 'Exact successor')
    life.check(c['pins'])
    s.tools.revalidate(c['tool_identity'])
    review = life.read_bound(REVIEW, REVIEW_SHA)
    policy.validate(review)
    selected = {t['scope']: t['design_checksum'] for t in review['candidates']
                if t['scope'] in review['minimal_recommended_roots']}
    need(c['trusted_roots'] == selected and len(selected) == 577, 'Exact reviewed source scopes')
    need(s.semantic_seal(s.semantic((out / 'combined.el').read_text())) == c['baseline_EL_seal'],
         'Exact inherited797+MaskU EL')
    return c


def verify(out, seal):
    c = check(out, seal)
    terminal = json.loads((out / 'terminal.json').read_text())
    s.terminal_gate(terminal, c)
    need(terminal['config_seal'] == seal, 'Exact executed config seal')
    q = life.read_bound(BASE / 'qualification.json', BASE_QUAL)
    reports = {}
    for stage in s.STAGES:
        ep = out / s.EL_FILES[stage]
        if stage in ('raw', 'reset', 'final'):
            need(ep.read_bytes() == b'', 'Reset must remove all exclusions')
        else:
            whole_gate(ep.read_text(), c)
        reports[stage] = s.summary((out / ('modules_' + stage + '.csv')).read_bytes(), stage, c['hierarchy_roots'])
    s.summaries_gate(reports)
    for stage in ('raw', 'reset', 'final'):
        need(reports[stage] == q['module_reports'][stage], 'Same797 raw/reset/final native metrics')
    for scope in reports['applied']:
        affected = owned(scope, c['trusted_roots']) or any(r.startswith(scope + '.') for r in c['trusted_roots'])
        if not affected:
            need(reports['applied'][scope] == q['module_reports']['applied'][scope], 'Protected scope changed: ' + scope)
    selected = (out / 'selected_tests.txt').read_text().splitlines()
    s.membership(c['input_ledger'], selected, 797)
    need(selected == c['expected_selected'], 'Exact ordered historical797 PASS selection')
    s.raw_summary_gate((out / 'raw.csv').read_bytes(), c['hierarchy_roots'], reports['raw'])
    raw_reference = BASE / 'raw.csv'
    need(life.digest(raw_reference) == q['output_pins'][str(raw_reference)], 'Sealed raw baseline')
    def metric_rows(path):
        rows = csv.DictReader(io.StringIO(path.read_text()))
        return [tuple(row[k] for k in ('Name', 'Depth', *s.METRICS)) for row in rows]
    need(metric_rows(out / 'raw.csv') == metric_rows(raw_reference), 'Complete raw2989 metrics unchanged')
    for name in ('launcher.log', 'DVEfiles/dve_gui.log'):
        s.diagnostics((out / name).read_text())
    need('TRUSTED797_FIVE_PHASE_DONE' in (out / 'DVEfiles/dve_gui.log').read_text(), 'Native completion marker')
    need((out / 'cleanup-empty.el').read_bytes() == b'', 'Final cleanup empty')
    result = dict(status='TRUSTED_IP_INTEGRATION797_NATIVE_VERIFIED', population=797,
        config_seal=seal, trusted_roots=c['trusted_roots'], reports=reports,
        coverage_scope_changed_not_stimulus_gain=True, unreachability_claim=False,
        historical_PASS_only_no_new_RTL_signoff=True,
        output_pins={str(p): life.digest(p) for p in out.iterdir() if p.is_file() and p.name != 'qualification.json'})
    life.save(out / 'qualification.json', result)
    print(json.dumps(dict(status=result['status'], metrics=reports['applied'][policy.SCOPE])))


def run(out, seal, reviewed):
    need(not (out / 'execution.json').exists(), 'One attempt; preserve failed outputs')
    ns = dict(s.run.__globals__, check=check, verify=verify, TCL=TCL)
    FunctionType(s.run.__code__, ns)(out, seal, reviewed)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=('prepare', 'check', 'run-reviewed', 'verify'))
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--seal')
    ap.add_argument('--service-unit')
    ap.add_argument('--parent-reviewed-seal')
    a = ap.parse_args()
    out = a.output.resolve()
    if a.mode == 'prepare': prepare(out, a.service_unit)
    elif a.mode == 'check': check(out, a.seal); print('TRUSTED797_CHECK_PASS')
    elif a.mode == 'verify': verify(out, a.seal)
    else: run(out, a.seal, a.parent_reviewed_seal)
