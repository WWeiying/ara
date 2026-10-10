"""Two exact passive scopes, five code metrics; prepare is not EDA approval."""
import argparse
import csv
import io
import json
from pathlib import Path
import re
import subprocess
import sys
from types import FunctionType, SimpleNamespace
import cva6_fixed_fields_native768 as local

life, require = local.life, local.require
HERE = Path(__file__).resolve().parent
REVIEW = life.OUT / 'cvxif-passive-bind-testbench-scope-source-review770-agent-20261007-01.json'
REVIEW_SHA = 'a274a9ae809ab2bcc8823cf45e1b3a259ef263ed7a9cb0a903d021796cfa5b08'
SAMPLE = life.OUT / 'vlsu-address-padding51-native770-agent-20261007-02/config.json'
SAMPLE_SHA = 'bb0fad46532f16abe55da63f4522bbeb92f6d83dda5e6e0767a01ee89b7509c7'
QUAL = life.OUT / 'vlsu-padding51-native770-offline-qualified-parent-20261007-01/qualification.json'
QUAL_SHA = 'f46d8d1d5405f72673bb11f70b226122e57a2e892fd0e6d9fe49d85386d4500d'
METRICS = ('Line', 'Condition', 'Branch', 'FSM', 'Toggle')
PROTECTED = ('Assert', 'Group')
STAGES = ('before', 'selected', 'reset', 'reloaded', 'final')
ROOT = 'ara_tb.dut.i_ara_soc.i_system'
SCOPES = (ROOT + '.i_ara_cvxif_dut_bind', ROOT + '.i_ara_cvxif_dut_bind.cvxif')
ANNOTATION = 'Passive verification scopes only; five code metrics; assertions and functional coverage retained'
HELP = life.OUT / 'fsm741-native-token-probe-20261007-01/DVEfiles/dve_gui.log'
MENU = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/gui/dve/auxx/gui/dve/metricExclude.tcl')


def contract(c):
    require(c['scopes'] == list(SCOPES) and c['metrics'] == list(METRICS), 'Exact scopes/metrics')
    require(c['protected_metrics'] == list(PROTECTED) and c['root'] == ROOT, 'Protected contract')
    require(c['recursive'] is False and c['timeout_seconds'] == 900, 'No recursive/budget drift')
    require(c['native_qualified'] is False and c['population_application'] is False, 'No premature qualification')


def rows(text):
    r = csv.DictReader(io.StringIO(text), delimiter='\t')
    require(r.fieldnames == ['path', 'meta', 'name', 'excluded', 'cells'], 'Snapshot schema')
    result = {}
    for row in r:
        require(None not in row and all(v is not None for v in row.values()), 'Truncated snapshot')
        key = (row['path'], row['meta'], row['name'])
        require(all(key) and key not in result and row['excluded'] in ('0', '1'), 'Native identity/flag')
        result[key] = (row['excluded'], row['cells'])
    return result


def parse_el(text, c):
    """Do not accept scope-only directives: they cannot prove the metric boundary."""
    found, scope, checksum = [], None, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('//'):
            continue
        if line.startswith('ANNOTATION:'):
            require(line == 'ANNOTATION: ' + json.dumps(ANNOTATION), 'Foreign annotation')
            continue
        m = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"', line)
        if m:
            checksum = m.groups(); scope = None
            continue
        if line.startswith('INSTANCE:'):
            scope = line.split(':', 1)[1].strip()
            require(scope in SCOPES and checksum is not None, 'Scope-only/global/non-code EL rejected')
            expected = next(i for i in c['compiled_scopes'] if i['scope'] == scope)
            require(checksum[0] == str(expected['design_module_checksum']), 'Module checksum')
            require(checksum[1] in c['metric_checksums'][scope], 'Metric variant checksum')
            continue
        require(scope is not None and re.match(r'^(Block|Line|Condition|Branch|Fsm|FSM|Toggle)(?:\s|$)', line),
                'Unknown or protected metric directive; format needs review')
        require(not any(x in line for x in ('*', '\x00')), 'Wildcard/NUL')
        found.append((scope, checksum, line))
    require(found and len(found) == len(set(found)), 'Empty/duplicate native EL')
    return sorted(found)


def check(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    contract(c); life.check(c['pins']); local.tools.revalidate(c['identity'])
    return c


def prepare(out):
    require(out.parent == life.OUT and not out.exists(), 'Fresh independent output')
    review = life.read_bound(REVIEW, REVIEW_SHA); life.check(review['pins'])
    require(len(review['exact_exclusion_scopes']) == 2 and set(review['exact_exclusion_scopes']) == set(SCOPES), 'Source review scopes')
    q = life.read_bound(QUAL, QUAL_SHA); life.check(q['pins'])
    sample = life.read_bound(SAMPLE, SAMPLE_SHA); life.check(sample['pins'])
    local.tools.revalidate(sample['identity'])
    require('-metric' in HELP.read_text() and 'Line, Toggle, Condition, FSM, Branch, Assert' in HELP.read_text(), 'Actual command help')
    menu = MENU.read_text()
    require('-selected -metric $metric' in menu and re.search(r'if\s+\{\$recursive\s*==\s*0\s*\}',menu), 'Metric-specific nonrecursive API')
    # Bind each metric variant to the same frozen design, not arbitrary native IDs.
    checksums = {s: set() for s in SCOPES}
    shape_dir = Path(sample['design']) / 'snps/coverage/db/shape'
    shape_pins = {}
    for p in sorted(shape_dir.glob('*.verilog.shape.xml')):
        shape_pins[str(p)] = life.digest(p)
        tree = local.primitive.toggle.xml(p)
        for i in review['compiled_scopes']:
            for node in tree.iter():
                if node.get('name') == i['module'] and node.get('chksum'):
                    checksums[i['scope']].add(node.get('chksum'))
    require(all(checksums.values()), 'Compiled variants absent')
    files = [Path(__file__), HERE / 'capture_cvxif_passive_two_scope770.tcl',
             HERE / 'test_capture_cvxif_passive_two_scope770.py', Path(local.__file__),
             HERE / 'apply_points740_v4.tcl', Path(local.primitive.toggle.__file__), HELP, MENU, REVIEW, SAMPLE, QUAL]
    pins = dict(review['pins'])
    for entries in (sample['pins'], q['pins'], shape_pins, {str(p):life.digest(p) for p in files}):
        pins = life.merge_pins(pins, entries)
    c = dict(schema='PASSIVE_TWO_SCOPE_CODE_ONLY_NATIVE_CAPTURE_V1', scopes=list(SCOPES),
             root=ROOT, metrics=list(METRICS), protected_metrics=list(PROTECTED), recursive=False,
             compiled_scopes=review['compiled_scopes'], metric_checksums={s:sorted(v) for s,v in checksums.items()},
             timeout_seconds=900, launch_authorized=False, native_qualified=False, population_application=False,
             format_gate='Unknown/native whole-instance syntax HOLD; never infer Assert/Group preservation',
             **{k:sample[k] for k in ('identity','design','vdb','test')})
    contract(c)
    # Python's JSON encoding is not a Tcl text writer.
    def quote(s):
        require(not any(x in str(s) for x in ('{','}','\\','\n','\x00')), 'Unsafe Tcl literal')
        return '{' + str(s) + '}'
    selection = ''.join('set ::cv_' + k + ' ' + quote(c[k]) + '\n' for k in ('design','vdb','test','root'))
    selection += 'set ::cv_scopes [list ' + ' '.join(map(quote,SCOPES)) + ']\n'
    selection += 'set ::cv_library ' + quote(HERE / 'apply_points740_v4.tcl') + '\n'
    selection += 'set ::cv_annotation ' + quote(ANNOTATION) + '\n'
    tcl = (HERE / 'capture_cvxif_passive_two_scope770.tcl').read_text()
    require('{*}' not in tcl and 'rename gui_' not in tcl, 'Embedded Tcl compatibility')
    # Source/eval generated text with definitions only, no GUI calls.
    script = 'set ::cv_test_only 1\n' + selection + '\n' + tcl + '\nputs HOST_SOURCE_OK\n'
    r = subprocess.run(['tclsh'], input=script, text=True, capture_output=True, timeout=10)
    require(r.returncode == 0 and not r.stderr and 'HOST_SOURCE_OK' in r.stdout, 'Generated source/eval')
    out.mkdir()
    for name,text in [('selection.tcl',selection), ('queue_constant_native.tcl',tcl)]:
        with (out/name).open('x') as f: f.write(text)
        pins[str(out/name)] = life.digest(out/name)
    c['pins'] = pins
    life.save(out/'config.json', c)
    print(json.dumps(dict(output=str(out), seal=life.digest(out/'config.json'), pins=len(pins),
                          generated_source_eval='PASS', EDA_launched=False, parent_review_required=True)))


def verify(out, seal):
    c = check(out,seal)
    terminal = json.loads((out/'terminal.json').read_text())
    require(terminal['returncode'] == 0 and not terminal['timeout'] and len(terminal['actual_dve']) == 1, 'Actual terminal/identity')
    log = (out/'DVEfiles/dve_gui.log').read_text()
    require(log.splitlines().count('CVXIF_TWO_SCOPE_DONE') == 1 and not (out/'error.txt').exists(), 'Capture completion')
    require(not re.search(r'(?:Error-|Fatal-|\bError:|CVXIF_TWO_SCOPE_FAILED)',log), 'GUI error')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el'):
        require((out/name).read_bytes() == b'', 'Global reset not empty')
    require(parse_el((out/'first.el').read_text(),c) == parse_el((out/'second.el').read_text(),c), 'Semantic reload')
    availability = [json.loads((out/(s+'_availability.json')).read_text()) for s in STAGES]
    require(all(a == availability[0] for a in availability), 'Metric availability changed')
    require(set(availability[0]) == set(METRICS+PROTECTED) and all(type(v) is bool for v in availability[0].values()), 'Actual availability')
    require(all(availability[0][m] for m in METRICS), 'Five metrics not loaded')
    counts = {}
    for metric in METRICS+PROTECTED:
        if not availability[0][metric]: continue
        scopes = SCOPES if metric in METRICS else (ROOT,)
        for n,scope in enumerate(scopes):
            snapshots = {s:rows((out/(s+'_'+metric+'_'+str(n)+'.tsv')).read_text()) for s in STAGES}
            before = snapshots['before']
            columns = [(out/(s+'_'+metric+'_'+str(n)+'.columns')).read_text() for s in STAGES]
            require(all(v == columns[0] for v in columns) and columns[0].strip(), 'Native column identities changed')
            if metric in PROTECTED:
                require(before, 'Loaded protected metric snapshot empty; cannot establish preservation')
            if metric == 'Toggle':
                instance = next(i for i in c['compiled_scopes'] if i['scope'] == scope)
                labels = set()
                for kind,name,line,typecode,port,left,right in instance['typed_inventory']:
                    require(kind in ('node','vectornode'), 'Unbound typed array')
                    labels.add(local.normalized_label(name if kind=='node' else name+'['+left+':'+right+']'))
                actual = [local.normalized_label(k[2]) for k in before]
                require(len(actual) == len(set(actual)) and labels <= set(actual), 'Compiled 86-object inventory missing/ambiguous')
            for s,actual in snapshots.items():
                require(set(actual) == set(before), 'Full native identities changed')
                if metric in PROTECTED or s in ('before','reset','final'):
                    require(actual == before, 'Protected coverage/flags or reset changed')
                else:
                    require(all(v[0]=='1' for v in actual.values()), 'Code scope not fully excluded')
            require(snapshots['selected'] == snapshots['reloaded'], 'Native reload changed')
            counts[scope+'|'+metric] = len(before)
    result = dict(status='EXACT_TWO_PASSIVE_SCOPES_FIVE_CODE_METRICS_NATIVE_QUALIFIED_NOT_APPLIED',
                  code_metrics=list(METRICS), scopes=list(SCOPES), protected_metric_availability=availability[0],
                  native_counts=counts, semantic_reload=True, final_reset=True, population_application=False,
                  official_percentage=None, pins={**c['pins'], **{str(p):life.digest(p) for p in out.rglob('*')
                      if p.is_file() and p.name not in ('capture-result.json','service.log')}})
    life.save(out/'capture-result.json',result)


def run(out,seal,approved):
    require(approved, 'Explicit parent review required')
    c = check(out,seal)
    def bound(path,s):
        require(Path(path)==out/'config.json' and s==seal, 'Lifecycle config identity')
        return {**c, 'launch_authorized':True}
    namespace = dict(local.run.__globals__)
    namespace.update(life=SimpleNamespace(read_bound=bound,check=life.check,save=life.save), verify=verify)
    FunctionType(local.run.__code__,namespace)(out,seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','check','run','verify'))
    p.add_argument('--output',type=Path,required=True); p.add_argument('--seal')
    p.add_argument('--parent-reviewed',action='store_true')
    a=p.parse_args(); out=a.output.resolve()
    if a.mode=='prepare': prepare(out)
    elif a.mode=='run': run(out,a.seal,a.parent_reviewed)
    elif a.mode=='verify': verify(out,a.seal)
    else: check(out,a.seal); print('SEALED_CHECK_PASS_NO_EDA')
