"""Host-only successor audit. No EDA entry point; never writes frozen packets."""
import ast
from collections import Counter
import csv
import hashlib
import io
import itertools
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest
from types import SimpleNamespace

import run_scoreboard_cause60_native796 as launcher
import targeted_toggle_evidence_v2 as raw

core = launcher.core
need, digest = core.need, core.u.digest
HERE, ROOT = core.HERE, core.u.ROOT
OUT = core.u.OUT / 'cause60-readonly797-audit-agent-20261008-04'
ADMISSION = core.u.OUT / 'vsmul-saturation-offline-admitted797-parent-20261008-01'
QUALIFIED = core.u.OUT / 'current-population797-inherited796-agent-20261008-01'
OLD_REPORT = core.u.OUT / 'current-population796-alua137-ptw156-agent-20261008-01'
CONFIG_SHA = '0dfac59d46bc38c97662796e5624d361eb899c7808b8c96119cadffc3adb6b29'
LAUNCH_SHA = '0391b3c0cebae789508d1b263ca9864d99ded49510268677c607ffaa750a2774'
ADMISSION_SHA = '775485fa0a5cfbb8bb1715374e60d3228d341522b2df3c666754407b30ef55f4'
EL_SHA = '2704de24f115e289d8c1e60c3847dc39d7f7d13e955eb284ddc66f6fd42596c9'


def semantic_parser(pins):
    # Load only established pure parsers, not the report runner's import graph.
    namespace = dict(Counter=Counter, re=re, require=need, need=need,
                     itertools=itertools, hashlib=hashlib, json=json)
    for filename, names in (('branch720_next_report_contract.py', ('native_inventory',)),
                            ('report_global777_compact.py', ('semantic', 'semantic_seal'))):
        path = HERE / filename
        pins[str(path)] = digest(path)
        tree = ast.parse(path.read_text())
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        need(len(nodes) == len(names), 'Exact existing pure parser functions')
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
        if 'native_inventory' in names:
            namespace['inventory'] = SimpleNamespace(native_inventory=namespace['native_inventory'])
    return lambda blob: namespace['semantic_seal'](namespace['semantic'](blob.decode('ascii')))


def frozen_bundle(path):
    pins = {}
    for line in path.read_text().splitlines():
        sha, filename = line.split('  ', 1)
        p = Path(filename)
        if not p.is_absolute():
            p = ROOT / p
        need(str(p) not in pins and digest(p) == sha, 'Frozen bundle drift: ' + str(p))
        pins[str(p)] = sha
    pins[str(path)] = digest(path)
    return pins


def zero_gate(copies, before, suffix, after):
    need(raw.union(before, suffix) == after, 'Full published797 OR mismatch')
    coords = set()
    for t in copies:
        a = t['compiled_attributes']
        need(t['selected_physical_bits'] == list(range(6, 63)) and
             a['left'] == '63' and a['right'] == '0', 'Only exact cause62:6')
        expected = [a['serialized_offset'] + 2*b + pair for b in range(6, 63) for pair in (0, 1)]
        need(expected == t['selected_residual_slots'], 'Source serialized pair coordinates')
        for coordinate in expected:
            key = t['scope'], coordinate
            need(key not in coords, 'Duplicate coordinate')
            coords.add(key)
            for population in (before, suffix, after):
                row = population[t['scope']]
                need(row['checksum'] == t['checksum'] and 0 <= coordinate < row['width'],
                     'Compiled raw identity')
                need(not (int(row['bits'], 16) >> (row['width']-1-coordinate)) & 1,
                     'Candidate raw counterexample')
    need(len(copies) == 60 and len(coords) == 6840, 'Exact60 paired positions')
    return dict(copies=60, physical_bits_per_copy=57, physical_bits=3420,
                unnamed_serialized_pairslots_checked_each_population=6840,
                raw796_zero=True, suffix797_zero=True, raw797_zero=True,
                all_scope_OR_verified=len(after), native_direction_IDs_inferred=False,
                observation_is_not_constant_proof=True, protected_bits=[0,1,2,3,4,5,63])


def ownership_gate(text, copies):
    scope, directives = None, []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if line.startswith('INSTANCE:'):
            scope = line.split(':', 1)[1].strip()
        elif scope and (line.startswith('Toggle ') or line == 'WHOLE_SCOPE'):
            directives.append(dict(scope=scope, line=number, directive=line))
    for t in copies:
        need(not any(core.source.prior.ownership_conflict(t['scope'], t['name'], d)
                     for d in directives), 'Existing EL owns candidate field/parent/scope')
    return dict(candidate_EL_overlaps=0, no_whole_field_or_parent_waiver=True,
                candidate60_not_applied=True, protected_low6_bit63_and_all_other_fields=True)


def command_receipt(command, cwd):
    env = dict(os.environ, PYTHONPATH=str(HERE), PYTHONDONTWRITEBYTECODE='1')
    p = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=180)
    return dict(command=command, cwd=str(cwd), PYTHONPATH=env['PYTHONPATH'],
                returncode=p.returncode, stdout=p.stdout, stderr=p.stderr, EDA_started=False)


def collect():
    pins = frozen_bundle(launcher.LAUNCH / 'bundle.sha256')
    need(len(pins) == 17, '16 frozen bundle members plus manifest')
    c = launcher.load_launch(core.OUT, CONFIG_SHA, launcher.LAUNCH / 'launch-manifest.json', LAUNCH_SHA)
    pins.update(c['pins'])
    report, bindings, source_pins = core.source_packet()
    pins.update(source_pins)
    need(len(bindings) == 450, 'All original source bindings')
    receipt = json.loads((launcher.LAUNCH / 'offline-tests.json').read_text())
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(n) for n in
        ('test_scoreboard_cause60_native796', 'test_run_scoreboard_cause60_native796'))
    def ids(s):
        return [i for t in s for i in (ids(t) if isinstance(t, unittest.TestSuite) else [t.id()])]
    need(receipt['status'] == 'PASS_HOST_ONLY_NO_EDA' and receipt['tests_run'] == 16 and
         receipt['failures'] == receipt['errors'] == 0 and sorted(ids(suite)) == sorted(receipt['test_ids']),
         'Actual sealed16 receipt must match discovered tests')
    rerun = command_receipt([c['python'], '-B', '-m', 'unittest', '-v',
        'test_scoreboard_cause60_native796', 'test_run_scoreboard_cause60_native796'], core.OUT)
    need(rerun['returncode'] == 0 and 'Ran 16 tests' in rerun['stderr'] and
         rerun['stderr'].rstrip().endswith('OK'), 'Independent real16 host rerun')
    checks = []
    for python in ('/usr/bin/python3', '/usr/bin/python3.9'):
        check = command_receipt([python, '-B', str(launcher.SCRIPT), 'check', '--seal', LAUNCH_SHA], core.OUT)
        need(check['returncode'] == 0 and json.loads(check['stdout'])['status'] == 'CHECK_PASS_NO_EDA',
             'Actual minimal-PYTHONPATH alias check')
        check.update(resolved_interpreter=str(Path(python).resolve()), interpreter_sha256=digest(Path(python)))
        checks.append(check)

    def bind(path, expected=None):
        path = Path(path)
        sha = digest(path)
        need(expected is None or sha == expected, 'Evidence drift: ' + str(path))
        pins[str(path)] = sha
        return path.read_bytes()

    admission = json.loads(bind(ADMISSION / 'admission-manifest.json', ADMISSION_SHA))
    need(admission['coverage_admitted'] is True, 'Admitted797')
    baseline = Path(admission['baseline'])
    baseline_manifest = json.loads(bind(baseline / 'admission-manifest.json', admission['baseline_seal']))
    def output(directory, manifest, name):
        path = directory / name
        return bind(path, manifest['output_pins'][str(path)])
    old_ledger = output(baseline, baseline_manifest, 'combined-inputs.txt').decode().splitlines()
    ledger = output(ADMISSION, admission, 'combined-inputs.txt').decode().splitlines()
    need(len(ledger) == len(set(ledger)) == 798 and ledger[:-1] == old_ledger, 'Exact796 prefix plus unique797 suffix')
    before = json.loads(output(baseline, baseline_manifest, 'combined-toggle-bits.json'))
    after = json.loads(output(ADMISSION, admission, 'combined-toggle-bits.json'))
    files = list((Path(ledger[-1]) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    need(len(files) == 1, 'One actual suffix')
    bind(files[0], admission['input_pins'][str(files[0])])
    suffix, sha = raw.rows(files[0], set(before))
    need(sha == pins[str(files[0])], 'Raw suffix immutable')
    copies = report['previously_independent14'] + report['newly_closed46']
    zeros = zero_gate(copies, before, suffix, after)
    qualified = json.loads(bind(QUALIFIED / 'qualification.json'))
    cfg = json.loads(bind(QUALIFIED / 'config.json', qualified['config_seal']))
    need(qualified['status'] == 'CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED' and
         qualified['population'] == qualified['actual_selected_tests'] == 797 and
         qualified['admission_seal'] == ADMISSION_SHA and cfg['input_ledger'] == ledger and
         cfg['new_exclusions_added'] is False, 'Stable797 qualification authority')
    for path, sha in qualified['output_pins'].items():
        bind(path, sha)
    old_qual = json.loads(bind(OLD_REPORT / 'qualification.json',
        'f439bae9092c0a787ee8fb8177ee33277e6ec25f61ef0c198f5a8dce50807270'))
    inherited = bind(QUALIFIED / 'combined.el', EL_SHA)
    need(bind(OLD_REPORT / 'combined.el', EL_SHA) == inherited, 'Exact796->797 EL bytes')
    semantic = semantic_parser(pins)
    semantic_seal = semantic(inherited)
    need(semantic_seal == cfg['expected_EL_semantic_sha256'], 'Qualified exact semantic EL seal')
    for directory, qualification in ((OLD_REPORT, old_qual), (QUALIFIED, qualified)):
        for name in ('applied.el', 'reloaded.el'):
            blob = bind(directory / name, qualification['output_pins'][str(directory / name)])
            need(semantic(blob) == semantic_seal, 'Exact full EL membership')
            need(blob == (OLD_REPORT / name).read_bytes(), 'Byte-exact same-stage796->797 inheritance')
    ownership = ownership_gate(inherited.decode(), copies)
    modules = list(csv.DictReader(io.StringIO((QUALIFIED / 'modules_applied.csv').read_text())))
    root = 'ara_tb.dut.i_ara_soc.i_system'
    row = [r for r in modules if r['Scope'] == root]
    need(len(row) == 1 and row[0]['Toggle'] == qualified['module_reports']['applied'][root]['Toggle'] == '73.14%',
         'Actual qualified system-root toggle')

    api = core.history(c['groups'])
    installation = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/gui/dve/auxx/gui')
    installed_help = bind(installation / 'dialogs/helpstrings.tcl').decode()
    bind(installation / 'dve/cliCommandWrappers.tcl')
    installed_menu = bind(installation / 'dve/preferencesCovMainMenu.tcl').decode()
    need('gui_eval_and_log_cmd gui_cov_tgl_compress -id $window -opt $opt' in installed_menu and
         'gui_cov_tgl_expand "uncompress"' in installed_menu and
         'gui_cov_tgl_can_compress -id $window -opt $opt' in installed_menu,
         'Installed native menu command chain')
    need('Compress selected vector bits.' in installed_help and 'Uncompress selected vector bits.' in installed_help,
         'Installed vector controls help')
    fresh = core.u.OUT / 'c910-lane23-padding1424-launcher-v2-prepared796-agent-20261008-03'
    bitfiles = sorted(fresh.glob('bits_before_*.tsv'))
    need(len(bitfiles) == 8, 'Actual fresh03 file universe')
    empty = []
    for path in bitfiles:
        rows = list(csv.DictReader(io.StringIO(bind(path).decode()), delimiter='\t'))
        empty.append(dict(path=str(path), data_rows=len(rows), sha256=pins[str(path)]))
    error = bind(fresh / 'error.txt').decode()
    terminal = json.loads(bind(fresh / 'terminal.json'))
    need('Full117 bit complement' in error and all(r['data_rows'] == 0 for r in empty), 'Observed failed full complement')
    historical = []
    for p in sorted({r['evidence'] for r in api['compressed_cause_paths']}):
        rows = list(csv.DictReader(io.StringIO(bind(p).decode()), delimiter='\t'))
        historical.append(dict(path=p, data_rows=len(rows),
            single_cause_bit_labels=[r['name'] for r in rows if core.re.fullmatch(r'.*\.cause\[\d+\]', r['name'])]))
    need(not any(r['single_cause_bit_labels'] for r in historical), 'Historical path evidence is compressed only')
    need(not list(core.OUT.glob('bits_*.tsv')) and not (core.OUT / 'launch-once.json').exists(), 'Cause60 never started')
    core.source.check_pins(pins)
    return dict(status='READONLY_AUDIT_PASS_NATIVE_HOLD_WAIT_HARVEY', EDA_started=False,
        frozen03_unchanged=True, all450_original_source_bindings_verified=True,
        original_source_bindings=bindings, source_launcher_frozen_hashes=frozen_bundle(launcher.LAUNCH / 'bundle.sha256'),
        sealed16_actual_receipt=receipt, independent16_rerun=rerun, actual_alias_checks=checks,
        launcher_reliability=dict(minimal_PYTHONPATH_actual_checks_pass=True,
            verification_plic_soc_extra_paths_currently_required=False,
            frozen_python=c['python'], current_service_python_from_sys_executable=True,
            future_alias_or_environment_changes_require_actual_recheck=True,
            precheck_failure_can_lack_terminal=True,
            minimal_successor_plan=['Pin worker and Tcl helper interpreter explicitly.',
                'Wrap approval/precheck/owning/native/inspect under one terminal try/finally.',
                'Track phase and EDA_started; mark started only after actual process creation.',
                'Persist terminal for precheck rejection; fail closed on capture/identity errors.',
                'No API changes until Harvey cause and verified bit expansion evidence.'],
            lifecycle_patch_prepared_only_not_implemented=True),
        suffix797=dict(raw=zeros, suffix_file=str(files[0]), ownership=ownership,
            approved_EL_sha256=EL_SHA, exact_same_stage796_to797_bytes=True,
            exact_combined_applied_reloaded_semantics=True, semantic_sha256=semantic_seal,
            qualified_root=root, qualified_Toggle='73.14%',
            MaskU_running_report_not_read_or_incorporated=True,
            future_MaskU_qualification_requires_new_EL_ownership_and_baseline_check=True),
        partial_API=dict(status='HOLD_NO_VALIDATED_CAUSE_BIT_EXPANSION', installed_help_controls_verified=True,
            installed_menu_command='gui_cov_tgl_compress -id CURRENT_VIEW -opt uncompress',
            installed_menu_enable_gate='gui_cov_tgl_can_compress -id CURRENT_VIEW -opt uncompress',
            installed_menu_not_executed=True, alternative_API_not_qualified=True,
            historical_API=api, historical_inventories=historical,
            C910_before_files=empty, C910_terminal=terminal, C910_has_eight_files_not_nine=True,
            C910_failure_reason_not_inferred=True, wait_for_Harvey=True,
            guessed_bit_labels=False, completeness_relaxed=False,
            full64_each_copy_and_entire_scope_complement_still_required=True),
        compile_boundary='Original compiled XLEN64/RVH0/CvxifEn0/ACC enabled only; RVH1 or source/config/cause contract changes invalidate eligibility.',
        startup_X_waived=False, CSR_mcause_scause_waived=False, native_qualified=False, pins=pins)


if __name__ == '__main__':
    need(not OUT.exists(), 'Fresh independent audit output only')
    result = collect()
    OUT.mkdir()
    core.source.write_json(OUT / 'audit.json', result)
    handoff = ('READONLY_AUDIT_PASS_NATIVE_HOLD_WAIT_HARVEY\n'
        'Frozen03 bundle and all450 original source bindings verified; real16 host tests rerun PASS.\n'
        'Both python aliases real check PASS with PYTHONPATH=HERE only. Precheck terminal gap remains.\n'
        '797 exact6840 unnamed pairslots raw-zero in796/suffix797/OR797; full2989-scope OR checked.\n'
        '796->797 same-stage EL bytes unchanged; combined/applied/reloaded full semantics match. Cause60 not applied.\n'
        'Qualified i_system Toggle73.14%; pending MaskU not consumed.\n'
        'Installed help plus60 compressed paths are NOT proof of per-bit expansion.\n'
        'Installed menu uses gui_cov_tgl_compress -opt uncompress, can_compress enable gate; not executed/qualified.\n'
        'C910 fresh03 all8 bits_before files have0 rows; no ninth file. Wait Harvey, no native launch.\n'
        'Preserve low6,bit63,all CSR bits and full scope complement; no X->0 or assertknown claim.\n'
        'Lifecycle successor requirements recorded only, no executable launcher patch prepared.\n')
    with (OUT / 'HANDOFF.txt').open('x') as f:
        f.write(handoff)
    test_receipt = command_receipt([result['launcher_reliability']['frozen_python'], '-B', '-m',
        'unittest', '-v', 'test_review_cause60_readonly797_04'], core.OUT)
    need(test_receipt['returncode'] == 0 and 'Ran 7 tests' in test_receipt['stderr'], 'Audit7 actual tests')
    core.source.write_json(OUT / 'audit-tests.json', test_receipt)
    paths = [Path(__file__).resolve(), Path(__file__).with_name('test_review_cause60_readonly797_04.py'),
             OUT / 'audit.json', OUT / 'HANDOFF.txt', OUT / 'audit-tests.json']
    with (OUT / 'bundle.sha256').open('x') as f:
        f.write(''.join(digest(p) + '  ' + str(p) + '\n' for p in paths))
    print(json.dumps(dict(status=result['status'], output=str(OUT), EDA_started=False), indent=2))
