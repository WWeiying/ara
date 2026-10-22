"""594 trusted roots: inherited577 plus exact17 SRT cores; reviewed native only."""
import argparse
import csv
import io
import json
import os
from pathlib import Path
from types import FunctionType

import report_trusted_ip797 as prior
import verify_trusted_ip797_readonly as native
import verify_trusted_ip797_readonly_v2 as tail
import review_srt_whole_trusted797 as review_tool

s, life, need = prior.s, prior.life, prior.need
HERE = Path(__file__).resolve().parent
BASE = s.OUT / 'trusted-ip797-global-parent-20261008-01'
BASE_CONFIG = native.CONFIG_SHA
BASE_QUAL = tail.QUAL_SHA
REVIEW = s.OUT / 'srt-whole-trusted797-reviewed-parent-20261008-01.json'
REVIEW_SHA = '8ab861afddc0070b26ef071d30af8a3fcdce083f2960bd8748e9872308df662c'
TCL = Path(__file__).with_suffix('.tcl')
SCHEMA = 'TRUSTED_SRT797_594_WHOLE_SCOPE_V1'
MARKER = 'TRUSTED_SRT797_FIVE_PHASE_DONE'


def review_gate(review, base, q):
    need(review['schema'] == 'SRT_WHOLE_TRUSTED797_PROPOSAL_V1' and
         review['status'] == 'RECOMMEND_PENDING_PARENT_AND_NATIVE_WHOLE_SCOPE_QUALIFICATION' and
         review['policy'] == 'TRUSTED_IP_INTEGRATION' and review['native_qualified'] is False and
         review['unreachability_claim'] is False, 'Exact reviewed trusted-IP proposal')
    need(q['status'] == 'TRUSTED_IP_INTEGRATION797_NATIVE_VERIFIED' and
         q['population'] == base['population'] == 797 and q['config_seal'] == BASE_CONFIG and
         q['trusted_roots'] == base['trusted_roots'] and len(base['trusted_roots']) == 577,
         'Qualified577 exact797 baseline')
    need(review['baseline']['path'] == str(BASE) and
         review['baseline']['qualification_sha256'] == BASE_QUAL and
         review['baseline']['Toggle'] == q['reports']['applied'][review_tool.SYSTEM]['Toggle'],
         'Proposal owns this baseline')
    roots = review['trusted_roots']
    review_tool.validate_roots(list(roots), base['trusted_roots'])
    need(set(roots.values()) == {'406590228'} and
         review['counts'] == dict(new_roots=17, scalar=1, vector=16,
                                  owned_descendants=51, proposed_union_roots=594), 'Exact17 inventory')
    rows = review['instances']
    need(len(rows) == 17 and {row['scope']: row['checksum'] for row in rows} == roots and
         all(row['decision'] == 'RECOMMEND' and row['owned_subtree'][0]['scope'] == row['scope'] and
             row['owned_subtree'][0]['definition_checksum'] == roots[row['scope']] and
             row['owned_subtree'][0]['toggle_checksum'] == '3969040510' for row in rows),
         'Exact recommended source/checksum rows')
    need(review['known_bug_review']['core_unresolved_bug_identified'] is False,
         'Unresolved core bug cannot be waived')
    return roots


def whole_gate(text, c):
    # Only NEW root annotations are qualified; inherited annotations keep their rules.
    native.whole_blocks(text, c['new_trusted_roots'])
    prior.whole_gate(text, dict(trusted_roots=c['new_trusted_roots'],
                               retained_EL_seal=c['retained_EL_seal']))
    other, _ = s.semantic(text)
    actual = {scope: checks for scope, checks, _, directive in other
              if directive == 'WHOLE_SCOPE' and prior.owned(scope, c['trusted_roots'])}
    need(actual == c['trusted_roots'], 'Exact594 whole roots/checksums, no extra descendants')


def approved(reader):
    base = reader.read(BASE / 'config.json', BASE_CONFIG, True)
    q = reader.read(BASE / 'qualification.json', BASE_QUAL, True)
    review = reader.read(REVIEW, REVIEW_SHA, True)
    new = review_gate(review, base, q)
    outputs = tail.checked_output_pins(q, BASE)
    el = reader.read(BASE / 'applied.el', outputs[str(BASE / 'applied.el')]).decode('ascii')
    native.whole_gate(el, base)
    need(s.semantic_seal(s.semantic(el)) ==
         s.semantic_seal(s.semantic((BASE / 'reloaded.el').read_text())), 'Qualified baseline reload EL')
    s.roots_gate(base['hierarchy_roots'])
    s.membership(base['input_ledger'], base['expected_selected'], 797)
    pins = s.merge(base['pins'], review['input_pins'], outputs, reader.pins, native.gui_pins(BASE))
    paths = (Path(__file__).resolve(), TCL, HERE / 'test_report_trusted_srt797.py',
             Path(prior.__file__).resolve(), Path(native.__file__).resolve(), Path(tail.__file__).resolve(),
             Path(review_tool.__file__).resolve(), HERE / 'test_review_srt_whole_trusted797.py',
             Path(s.__file__).resolve(), Path(s.inventory.__file__).resolve(),
             Path(s.tools.__file__).resolve(), Path(life.__file__).resolve(),
             s.TCL, s.EXPORT, s.ROOT_HELPER, HERE / 'report_scope_ancestors.py')
    pins = s.merge(pins, {str(p): life.digest(p) for p in paths})
    return base, q, new, el, pins


def scopes_tcl(roots):
    return 'set trusted_scopes {\n' + ''.join(' {' + r + '}\n' for r in sorted(roots)) + '}\n'


def prepare(out, unit):
    need(out.parent == s.OUT and not out.exists(), 'Fresh independent output')
    need(isinstance(unit, str) and s.re.fullmatch(r'ara-[a-zA-Z0-9-]+\.service', unit), 'Explicit owning service')
    reader = s.Reader()
    base, q, new, el, pins = approved(reader)
    reader.finish(pins)
    s.tools.revalidate(base['tool_identity'])
    out.mkdir()
    files = dict(**{'inputs.txt': '\n'.join(base['input_ledger']) + '\n',
                    'combined.el': el, 'root-selection.tcl': s.selection(base['hierarchy_roots']),
                    'trusted-scopes.tcl': scopes_tcl(new)})
    for name, text in files.items():
        with (out / name).open('x') as stream:
            stream.write(text)
        pins[str(out / name)] = life.digest(out / name)
    c = dict(schema=SCHEMA, population=797, output=str(out), pins=pins,
             trusted_roots=s.merge(base['trusted_roots'], new), new_trusted_roots=new,
             inherited_trusted_roots=base['trusted_roots'],
             retained_EL_seal=s.semantic_seal(prior.normalized(el, new)),
             baseline_EL_seal=s.semantic_seal(s.semantic(el)),
             input_ledger=base['input_ledger'], expected_selected=base['expected_selected'],
             hierarchy_roots=base['hierarchy_roots'], tool_identity=base['tool_identity'],
             baseline_qualification=BASE_QUAL, review_sha256=REVIEW_SHA,
             timeout_seconds=base['timeout_seconds'], owner_uid=os.getuid(), owning_service_unit=unit,
             expected_cgroup='/user.slice/user-%d.slice/user@%d.service/app.slice/%s' %
                             (os.getuid(), os.getuid(), unit),
             historical_PASS_only_no_new_RTL_signoff=True, unreachability_claim=False)
    life.save(out / 'config.json', c)
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'config.json'),
                          roots=594, GUI_new_excludes=17, EDA_launched=False)))


def check(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    need(c['schema'] == SCHEMA and c['output'] == str(out), 'Exact independent successor')
    life.check(c['pins'])
    reader = s.Reader()
    base, _, new, el, pins = approved(reader)
    need(all(c['pins'].get(p) == h for p, h in pins.items()), 'Every baseline/review/source/output obligation pinned')
    need(c['trusted_roots'] == s.merge(base['trusted_roots'], new) and len(c['trusted_roots']) == 594 and
         c['new_trusted_roots'] == new and c['inherited_trusted_roots'] == base['trusted_roots'], 'Exact577+17')
    for key in ('population', 'input_ledger', 'expected_selected', 'hierarchy_roots',
                'tool_identity', 'timeout_seconds'):
        need(c[key] == base[key], 'Original797 contract changed: ' + key)
    need(c['baseline_qualification'] == BASE_QUAL and c['review_sha256'] == REVIEW_SHA and
         c['historical_PASS_only_no_new_RTL_signoff'] is True and c['unreachability_claim'] is False,
         'Qualification and policy bindings')
    need(c['owner_uid'] == os.getuid() and type(c['owner_uid']) is int and
         s.re.fullmatch(r'ara-[a-zA-Z0-9-]+\.service', c['owning_service_unit']) and
         c['expected_cgroup'] == '/user.slice/user-%d.slice/user@%d.service/app.slice/%s' %
         (os.getuid(), os.getuid(), c['owning_service_unit']), 'Strict owning service')
    need((out / 'combined.el').read_text() == el and c['baseline_EL_seal'] == s.semantic_seal(s.semantic(el)) and
         c['retained_EL_seal'] == s.semantic_seal(prior.normalized(el, new)), 'Inherited fullEL/protected complement')
    need((out / 'inputs.txt').read_text().splitlines() == c['input_ledger'] and
         (out / 'root-selection.tcl').read_text() == s.selection(c['hierarchy_roots']) and
         (out / 'trusted-scopes.tcl').read_text() == scopes_tcl(new), 'Exact73 reporting scopes/GUI17only')
    reader.finish(c['pins'])
    s.tools.revalidate(c['tool_identity'])
    need(life.digest(out / 'config.json') == seal, 'Config changed during check')
    return c


def metric_rows(path):
    rows = csv.DictReader(io.StringIO(path.read_text()))
    return [tuple(row[k] for k in ('Name', 'Depth', *s.METRICS)) for row in rows]


def protected_gate(reports, baseline, new):
    s.summaries_gate(reports)
    for stage in ('raw', 'reset', 'final'):
        need(reports[stage] == baseline[stage], 'Same797 raw/reset/final metrics')
    for scope in reports['applied']:
        affected = prior.owned(scope, new) or any(r.startswith(scope + '.') for r in new)
        if not affected:
            need(reports['applied'][scope] == baseline['applied'][scope], 'Protected reporting scope changed: ' + scope)


def verify(out, seal):
    c = check(out, seal)
    qp = out / 'qualification.json'
    if qp.exists():
        q = json.loads(qp.read_bytes())
        need(q['status'] == 'TRUSTED_SRT797_594_NATIVE_VERIFIED' and q['config_seal'] == seal and
             q['trusted_roots'] == c['trusted_roots'], 'Existing qualification identity')
        life.check(q['output_pins'])
        return q
    terminal = json.loads((out / 'terminal.json').read_bytes())
    s.terminal_gate(terminal, c)
    need(terminal['config_seal'] == seal, 'Executed configuration seal')
    execution = json.loads((out / 'execution.json').read_bytes())
    need(execution['config_seal'] == seal and execution['cwd'] == str(out), 'Executed output/seal')
    baseline = life.read_bound(BASE / 'qualification.json', BASE_QUAL)
    reports = {}
    for stage in s.STAGES:
        ep = out / s.EL_FILES[stage]
        if stage in ('raw', 'reset', 'final'):
            need(ep.read_bytes() == b'', 'Native reset/global empty')
        else:
            whole_gate(ep.read_text(), c)
        reports[stage] = s.summary((out / ('modules_' + stage + '.csv')).read_bytes(), stage, c['hierarchy_roots'])
    protected_gate(reports, baseline['reports'], c['new_trusted_roots'])
    need(s.semantic_seal(s.semantic((out / 'applied.el').read_text())) ==
         s.semantic_seal(s.semantic((out / 'reloaded.el').read_text())), 'Complete native semantic reload')
    selected = (out / 'selected_tests.txt').read_text().splitlines()
    s.membership(c['input_ledger'], selected, 797)
    need(selected == c['expected_selected'], 'Exact797 unique ordered tests')
    s.raw_summary_gate((out / 'raw.csv').read_bytes(), c['hierarchy_roots'], reports['raw'])
    need(metric_rows(out / 'raw.csv') == metric_rows(BASE / 'raw.csv'), 'Complete original raw2989 unaffected')
    gui = (out / 'DVEfiles/dve_gui.log').read_text()
    for path in (out / 'launcher.log', *map(Path, native.gui_pins(out))):
        s.diagnostics(path.read_text())
    markers = (MARKER, 'COMPACT777_FIVE_PHASE_DONE', 'DVE_COVERAGE_EXPORT_DONE')
    need(all(gui.splitlines().count(m) == 1 for m in markers), 'Exactly one of each native/export DONE')
    need((out / 'cleanup-empty.el').read_bytes() == b'', 'Final cleanup empty')
    result = dict(status='TRUSTED_SRT797_594_NATIVE_VERIFIED', population=797, actual_selected_tests=797,
                  config_seal=seal, trusted_roots=c['trusted_roots'], new_trusted_roots=c['new_trusted_roots'],
                  baseline_qualification=BASE_QUAL, reports=reports, complete_raw_unchanged=True,
                  inherited_EL_outside_new17_preserved=True, markers={m: 1 for m in markers},
                  coverage_scope_changed_not_stimulus_gain=True, unreachability_claim=False,
                  historical_PASS_only_no_new_RTL_signoff=True)
    # Print BEFORE capturing stdout, so qualification never pins a pre-final prefix.
    print(json.dumps(dict(status=result['status'], metrics=reports['applied'][review_tool.SYSTEM])), flush=True)
    result['output_pins'] = s.merge({str(p): life.digest(p) for p in out.iterdir()
                                    if p.is_file() and p.name != 'qualification.json'}, native.gui_pins(out))
    life.check(result['output_pins'])
    life.save(qp, result)
    return result


def run(out, seal, reviewed):
    need(not (out / 'execution.json').exists(), 'One attempt; preserve failed evidence')
    ns = dict(s.run.__globals__, check=check, verify=verify, TCL=TCL)
    FunctionType(s.run.__code__, ns)(out, seal, reviewed)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=('prepare', 'check', 'verify', 'run-reviewed'))
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--seal')
    ap.add_argument('--service-unit')
    ap.add_argument('--parent-reviewed-seal')
    a = ap.parse_args()
    out = a.output.resolve()
    if a.mode == 'prepare':
        prepare(out, a.service_unit)
    elif a.mode == 'check':
        check(out, a.seal)
        print('TRUSTED_SRT797_594_CHECK_PASS_NO_EDA')
    elif a.mode == 'verify':
        verify(out, a.seal)
    else:
        run(out, a.seal, a.parent_reviewed_seal)
