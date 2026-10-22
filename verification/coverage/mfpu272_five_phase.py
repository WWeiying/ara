"""Fresh local MFPU272 five-phase qualification. Prepare is not approval."""
import argparse
import csv
import json
import re
import subprocess
import tempfile
from pathlib import Path
from types import FunctionType

import mfpu272_indexed_binding as indexed
import check_generated_tcl

old = indexed.previous
life, require = old.life, old.require
HERE = Path(__file__).resolve().parent
TCL = HERE / 'mfpu272_five_phase.tcl'
BINDING = life.OUT / 'mfpu272-binding-offline-parent-review-20261007-01/native-binding.json'
BINDING_SHA = 'd9ff0be6713e0f85e3e27bf243ae1232ffc4859a26c32189cf7a4293653d9f48'
CLOSURE_SHA = '20b8c3e3af1da640088a6c7a09d9115e2942252233b1e638939bf9e734b95ae1'
INDEX_RECEIPT = life.OUT / 'mfpu272-indexed-all788-parent-review-20261007-01.json'
INDEX_SHA = '65302338ddd9d62e382bb5641f0deba63894febda7bea5900458b3f3e0be608c'
STAGES = ('before', 'applied', 'reset', 'reloaded', 'final')
ANNOTATION = 'Frozen post-reset source invariant; no X, pressure, or module waiver'


def origin():
    q = life.read_bound(BINDING, BINDING_SHA)
    closure = life.read_bound(BINDING.parent / 'closure.json', CLOSURE_SHA)
    require(closure['binding_sha256'] == BINDING_SHA and closure['original_directory_unchanged'] is True
            and closure['EDA_launched'] is False and closure['local_qualified'] is False,
            'Actual readonly closure required; not local qualification')
    require(q['status'] == 'MFPU272_COMPLETE_FRESH_BEFORE_OFFLINE_TYPED_BOUND_NOT_EXCLUSION_QUALIFICATION'
            and q['config_seal'] == old.SEAL and q['original_run'] == str(old.RUN)
            and q['targets'] == 272 and q['protected_child_scopes'] == 744
            and len(q['instances']) == 788 and q['local_qualified'] is False
            and q['terminal_evidence']['native_launch_returncode'] == 0
            and q['terminal_evidence']['wrapper_OS_exit_status'] == 1,
            'Exact completed binding/native0/original wrapper1 required')
    life.check(q['pins']); life.check(q['offline_adapter_pins']); life.check(closure['original_pins'])
    original = life.read_bound(old.RUN / 'config.json', old.SEAL)
    require(len(original['instances']) == 788, 'Complete compiled source inventory')
    require(closure['candidate_sha256'] == life.digest(q['proposed_EL']), 'Proposed EL pin differs')
    receipt = life.read_bound(INDEX_RECEIPT, INDEX_SHA)
    life.check(receipt['pins'])
    require(receipt['status'] == 'INDEXED_BINDING_ALL788_EXACT_EQUIVALENCE_PASS' and
            receipt['binding_seal'] == BINDING_SHA and receipt['closure_seal'] == CLOSURE_SHA
            and receipt['scopes'] == 788 and receipt['aliases'] == 1652,
            'Actual all788 indexed equivalence required')
    return q, original


def deps(q):
    files = [Path(__file__).resolve(), TCL, HERE / 'test_mfpu272_five_phase.py',
             Path(indexed.__file__), Path(old.__file__), Path(check_generated_tcl.__file__),
             HERE / 'mfpu_constants272_native_bind.tcl',
             HERE / 'cva6_fixed_fields_native768.tcl', HERE / 'apply_points740_v4.tcl']
    return life.merge_pins(life.merge_pins(q['pins'], q['offline_adapter_pins']),
        {**{str(p): life.digest(p) for p in files}, str(BINDING): BINDING_SHA,
         str(BINDING.parent / 'closure.json'): CLOSURE_SHA, str(INDEX_RECEIPT): INDEX_SHA})


def el_members(text, c):
    annotations = re.findall(r'^ANNOTATION:\s+"(.*)"\s*$', text, re.M)
    # Reuse the exact grammar accepted by the sealed native primitive.
    require(annotations and all(a == ANNOTATION for a in annotations), 'Missing/foreign annotation')
    wanted_headers = {(i['scope'], i['design_module_checksum'], i['toggle_checksum'])
                      for i in c['bound'] if i['signals']}
    headers = set(); checksum = None
    for line in map(str.strip, text.splitlines()):
        if line.startswith('CHECKSUM:'):
            match = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"', line)
            require(match is not None, 'Checksum grammar'); checksum = match.groups()
        if line.startswith('INSTANCE:'):
            require(checksum is not None, 'Missing checksum')
            headers.add((line.split(':', 1)[1].strip(), *checksum))
    require(headers == wanted_headers, 'Exact target scope/checksum headers required')
    expected = old.frozen.pack.native.primitive.bitset(dict(instances=c['bound']))
    actual = old.frozen.pack.native.parse_el(text, dict(instances=c['bound']))
    require(set(actual) == expected and len(actual) == 34816, 'Exact paired target EL required')
    return set(actual)


def check(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    life.check(c['pins']); old.frozen.tools.revalidate(c['identity'])
    require(c['schema'] == 'MFPU272_LOCAL_FIVE_PHASE_V1' and c['output'] == str(out)
            and c['timeout_seconds'] == 5400 and c['binding_sha'] == BINDING_SHA
            and c['closure_sha'] == CLOSURE_SHA and c['population_application'] is False,
            'Closed local qualification config')
    require(len(c['compiled']) == len(c['bound']) == 788 and
            sum(len(i['signals']) for i in c['bound']) == 272, 'Full scope/target contract')
    q = life.read_bound(BINDING, BINDING_SHA)
    original = life.read_bound(old.RUN / 'config.json', old.SEAL)
    for path, sha in deps(q).items():
        require(c['pins'].get(path) == sha, 'Required dependency missing/different: ' + path)
    require(c['bound'] == q['instances'] and c['compiled'] == original['instances'] and
            all(c[k] == original[k] for k in ('design', 'vdb', 'test', 'identity')),
            'Actual sealed source/native/sample binding')
    el_members((out / 'candidate.el').read_text(), c)
    return c


def prepare(out):
    require(out.parent == life.OUT and not out.exists(), 'Fresh prepare only')
    q, original = origin()
    c = dict(schema='MFPU272_LOCAL_FIVE_PHASE_V1', output=str(out), timeout_seconds=5400,
             binding_sha=BINDING_SHA, closure_sha=CLOSURE_SHA, population_application=False,
             compiled=original['instances'], bound=q['instances'], pins=deps(q),
             **{k: original[k] for k in ('design', 'vdb', 'test', 'identity')})
    candidate = Path(q['proposed_EL']).read_text()
    el_members(candidate, c)
    selection = ''.join('set mq_%s {%s}\n' % (k, c[k]) for k in ('design', 'vdb', 'test'))
    selection += 'set mq_instances [list ' + ' '.join(
        '[list {%s} [list %s]]' % (i['scope'], ' '.join('{%s}' % t['native_label'] for t in i['signals']))
        for i in c['bound']) + ']\n'
    life.check(c['pins']); out.mkdir()
    for name, text in [('selection.tcl', selection), ('native-bind.tcl', TCL.read_text()), ('candidate.el', candidate)]:
        old.frozen.pack.native.primitive.common.common.save(out / name, text)
        if name.endswith('.tcl'): check_generated_tcl.check(out / name)
        c['pins'][str(out / name)] = life.digest(out / name)
    host = host_hook(c, selection)
    life.save(out / 'host-evidence.json', host)
    c['pins'][str(out / 'host-evidence.json')] = life.digest(out / 'host-evidence.json')
    life.save(out / 'config.json', c)
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'config.json'),
                         targets=272, scopes=788, protected_children=744, EDA_launched=False)), flush=True)


def compare_stage(instance, reference, text, stage):
    value, _ = indexed.bind_with_aliases(instance, text)
    require(value['reference'] == reference['reference'] and value['signals'] == reference['signals']
            and value['array_bindings'] == reference['array_bindings'], 'Five-stage typed identity differs')
    target_labels = {s['native_label'] for s in reference['signals']}
    for label, row in value['native_rows'].items():
        before = reference['native_rows'][label]
        # Handles may change; all native identity/role and protected data must not.
        keys = set(row) - {'handle'}
        if stage in ('applied', 'reloaded') and label in target_labels:
            keys -= {'coverage', 'display'}
        require(all(row[k] == before[k] for k in keys), 'Protected/reset native row differs: ' + label)
    return value


def terminal_gate(t, c, live):
    require(t['returncode'] == 0 and t['timeout'] is False and len(live) == 1
            and t['actual_dve'] == live and live[0]['exe'] == c['identity']['executable']
            and live[0]['cwd'] == c['output'], 'Actual native terminal0/identity required')


def flags_gate(rows, bound):
    expected = [dict(stage=stage, scope=i['scope'], label=s['native_label'],
                     excluded='1' if stage in ('applied', 'reloaded') else '0')
                for stage in STAGES for i in bound for s in i['signals']]
    require(rows == expected, 'Exact five-stage target excluded flags')


def host_hook(c, selection):
    """Source the actual entry/selection, with GUI-only stubs and real receipts."""
    with tempfile.TemporaryDirectory(prefix='mfpu272-host-') as temp:
        root = Path(temp)
        (root / 'selection.tcl').write_text(selection)
        (root / 'candidate.el').write_text(Path(c.get('output', '')) .joinpath('candidate.el').read_text()
            if (Path(c.get('output', '')) / 'candidate.el').exists() else Path(json.loads(BINDING.read_bytes())['proposed_EL']).read_text())
        # Tcl array keys are substituted only through variables below; literal
        # bracketed scopes must remain list-quoted when constructing the model.
        model = '\n'.join('set sim_key {%s}\nset sim_index($sim_key) %d' % (i['scope'], index)
                          for index, i in enumerate(c['bound']))
        script = '''
set mq_test_only 1
source {%s}
set env(DVE_COVERAGE_OUTPUT) {%s}
set sim_run {%s}
%s
set sim_active 0
set sim_selected {}
set sim_scope {}
proc gui_open_cov {args} {set ::sim_opened 1}
proc gui_covtable_show {args} {}
proc gui_covtable_setroot {args} {}
proc gui_list_expand {args} {}
proc gui_cov_show_value {args} {}
proc gui_process_events {args} {}
proc gui_covdetail_query {args} {return Toggle}
proc gui_list_action {args} {set ::sim_scope [lindex $args end]}
proc gui_list_get_property {args} {
    set c [lindex $args end]
    if {$c >= 4} {error end}
    return [lindex {Variable Type Coverage Display} $c]
}
proc gui_list_get {args} {
    if {[lsearch -exact $args -firstChild] >= 0} {return ara_tb}
    if {[lsearch -exact $args -path] >= 0} {return [lindex $args end]}
    error "Unmodeled get $args"
}
proc gui_list_get_selected {args} {return $::sim_selected}
proc gui_list_select {args} {
    if {[lsearch -exact $args -unselect] >= 0} {set ::sim_selected {}; return}
    set ::sim_selected [lindex $args end]
}
proc gui_exclusion {args} {
    if {[lsearch -exact $args -reset] >= 0} {set ::sim_active 0; return}
    if {[lsearch -exact $args -excluded] >= 0} {return $::sim_active}
}
proc gui_cov_excl_review {args} {return 1}
proc gui_exclusion_file {args} {
    set path [lindex [lindex $args end] 0]
    if {[lsearch -exact $args -load] >= 0} {set ::sim_active 1; return}
    if {$::sim_active} {
        file copy -force [file join $::env(DVE_COVERAGE_OUTPUT) candidate.el] $path
    } else {close [open $path w]}
}
proc qc_walk {item stream columns} {
    set index $::sim_index($::sim_scope)
    set f [open [file join $::sim_run native_before_${index}.tsv] r]
    set lines [split [string trimright [read $f] "\\n"] "\\n"];close $f
    set ::qc_seen {}
    foreach line [lrange $lines 1 end] {
        puts $stream $line
        lappend ::qc_seen [lindex [split $line "\\t"] 3]
    }
}
mq_session
if {![info exists sim_opened] || $sim_active != 0} {error "Session/final reset"}
puts HOST_EXACT_ENTRY_PASS
''' % (TCL, root, old.RUN, model)
        result = subprocess.run(['tclsh'], input=script, text=True, capture_output=True, timeout=120)
        require(result.returncode == 0 and result.stderr == '' and
                'HOST_EXACT_ENTRY_PASS' in result.stdout, 'Actual Tcl host hook failed: ' + result.stderr)
        require(all((root / ('native_%s_%d.tsv' % (s, i))).exists() for s in STAGES for i in range(788)),
                'Host entry omitted native inventory')
        with (root / 'flags.tsv').open() as stream:
            flags_gate(list(csv.DictReader(stream, delimiter='\t')), c['bound'])
        for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el'):
            require((root / name).read_bytes() == b'', 'Host reset failed')
        require(el_members((root / 'first.el').read_text(), c) ==
                el_members((root / 'second.el').read_text(), c), 'Host semantic reload failed')
        return dict(status='ACTUAL_GENERATED_TCL_FULL_ENTRY_STUB_PASS_NOT_NATIVE',
                    scopes=788, inventories=3940, target_flag_rows=1360,
                    stages=list(STAGES), EDA_launched=False)


def verify(out, seal):
    c = check(out, seal)
    require(not (out / 'error.txt').exists(), 'Recorded native failure is not qualification')
    execution = json.loads((out / 'execution.json').read_bytes())
    require(execution['config_seal'] == seal and execution['cwd'] == str(out) and
            execution['timeout_seconds'] == 5400 and execution['command'][-2:] ==
            ['-script', str(out / 'native-bind.tcl')], 'Exact execution/config/script identity')
    terminal_gate(json.loads((out / 'terminal.json').read_bytes()), c,
                  json.loads((out / 'live-identity.json').read_bytes()))
    gui = (out / 'DVEfiles/dve_gui.log').read_text() + (out / 'launcher.log').read_text()
    require(gui.splitlines().count('MFPU272_FIVE_PHASE_DONE') == 1 and not
            re.search(r'(?:MFPU272_FIVE_PHASE_FAILED|Error-|Fatal-|Warning-|\bError:)', gui), 'Full native completion required')
    for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el'):
        require((out / name).read_bytes() == b'', 'Global reset EL must be empty')
    first = el_members((out / 'first.el').read_text(), c)
    require(el_members((out / 'second.el').read_text(), c) == first, 'Semantic save/reload differs')
    for stage in STAGES:
        for index, (instance, bound) in enumerate(zip(c['compiled'], c['bound'])):
            compare_stage(instance, bound, (out / ('native_%s_%d.tsv' % (stage, index))).read_text(), stage)
    with (out / 'flags.tsv').open() as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        require(reader.fieldnames == ['stage', 'scope', 'label', 'excluded'], 'Flag schema')
        rows = list(reader)
    flags_gate(rows, c['bound'])
    files = [out / name for name in ('config.json', 'execution.json', 'terminal.json', 'live-identity.json',
        'launcher.log', 'DVEfiles/dve_gui.log', 'flags.tsv', 'first.el', 'second.el',
        'initial-empty.el', 'reset-empty.el', 'final-empty.el')]
    files += [out / ('native_%s_%d.tsv' % (s, i)) for s in STAGES for i in range(788)]
    pins = life.merge_pins(c['pins'], {str(p): life.digest(p) for p in files})
    life.check(pins)
    result = dict(status='MFPU272_EXACT_FIVE_PHASE_LOCAL_QUALIFIED_NOT_APPLIED',
        config_seal=seal, targets=272, directions=34816, protected_child_scopes=744,
        stages=list(STAGES), terminal_returncode=0, population_application=False, pins=pins,
        EL=str(out / 'first.el'), EL_semantic_roundtrip=True, initial_X_waiver=False)
    path = out / 'capture-result.json'
    if path.exists(): require(json.loads(path.read_bytes()) == result, 'Sealed result differs')
    else: life.save(path, result)
    return result


def run(out, seal, reviewed):
    # Same foreground wait, process identity, timeout and one-shot lifecycle.
    namespace = dict(vars(old.frozen), check=check, verify=verify)
    return FunctionType(old.frozen.run.__code__, namespace)(out, seal, reviewed)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'check', 'verify', 'run'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal'); p.add_argument('--parent-reviewed-seal')
    a = p.parse_args(); out = a.output.resolve()
    if a.mode == 'prepare': prepare(out)
    else:
        require(a.seal, 'Exact config seal required')
        if a.mode == 'run': run(out, a.seal, a.parent_reviewed_seal)
        else:
            result = check(out, a.seal) if a.mode == 'check' else verify(out, a.seal)
            print(json.dumps(dict(status=a.mode + '_PASS', targets=272, population_application=False)))
