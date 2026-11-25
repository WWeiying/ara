#!/usr/bin/env python3
"""Isolated read-DDC/SAIF power analysis; prepare/check are host-only.

prepare --conversion CONVERSION_RESULT_JSON --output NEW_DIR
--provisional-without-smoke permits only the scoped audited native EOF capture;
its output is explicitly provisional, without full smoke or compute-phase
representativeness acceptance. Missing annotation/link/library failures remain fatal.
Optional --smoke consumes gate_run.py's actual same-ELF GATE_SMOKE_PASS result. Without
it preparation is inspectable but ineligible for execution; reprepare fresh.
Proof roles are deliberately distinct: audited RTL release proves the exact
ELF's numerical/protocol behavior on the RTL image; the image binding connects
mapped gate netlist and DDC; smoke checks completion/numerics for the same ELF
and gate image; capture/conversion proves only a bounded representative window.
No gate protocol proof, per-capture full GLS mathematics PASS, or all-design
knownness is claimed or required. SAIF unknown record-time fraction is reported,
not required to be zero; root clock must be known and any measured critical
controls remain explicitly scoped. execute requires frozen worker + authorize.
This tool launches no synthesis, simulation, or conversion.

Optional --numerical-deviation-audit consumes a separate independent audit,
schema power-numerical-deviation-audit-v1, state
POWER_ELIGIBLE_WITH_NUMERICAL_DEVIATION, scope gate_smoke, purpose relative_power.
It references original_result, run_plan, image_binding, source_pins and auditor
as {path,sha256}, plus evidence_pins, elf_sha256, simv_sha256, target_path,
rationale, checks, task_scale {rtl,gate}, errors and limits. Checks must prove
task_complete, target_path_executed, no_exception, no_stall, guards_pass,
finite_outputs and numerical_only_failure. errors contains outputs, mismatches,
max_abs, max_rel, rms; limits contains max_abs,max_rel,rms. Scale dictionaries
must be identical positive integer dimensions. This is a power-only admission,
never a rewritten original PASS. RTL numerical deviations additionally need a
reviewed upstream RTL release adapter; sealed release checks are not bypassed.
"""
import argparse
import collections
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
DC = Path('/home/wangwy/dc_runs/ara_main_870cadb9_all_on_20261111_01/attempt_03')
DDC_REL = 'backend/syn/ara_soc/v1-dc/outputs/ara_soc_dc.ddc'
MANIFEST_SHA = '0a17d36c65573950c5e6dcd899cab65765e4183ef2b6443af9656426781e89d9'
STATUS_SHA = '06513a3edbbcdd4c4878c87097b8ac4f022207b36ca02732b27ac05d2821d7b2'
DDC_SHA = '06840a13976535c81500a86b663c8161d0dfb596b77dd15c4de73f50c967b5c7'
EOF_AUDITOR_SHA = '11bb1aba77e845d00c2630aa7afa971c98360d6ce965b343fc7f103e507c3531'
BASELINE_ADAPTER_SHA = 'e9d86b1bc5af7e935b9fd955521e45e79e4a37a141117d7f7a1715df62b7900b'
M1_LONG_AUDITOR_SHA = '70ca819c4b5dbe9c123d54b6590c20d0cc7f0d56b8532317ddf122b77b57ea77'
RVV_M1_PORT_AUDITOR_SHA = '4448cab3598fefb271b70cbe8b7ddbf3e7932e6a6f802629ec621146084063ea'
RVV_M1_PORT_V3_SHA = '36b85186a8e710d362c038b3ffa651738607e509c580ef7e67314f39655f6b5f'
TOOLROOT = Path('/home/wangwy/software/synopsys/install/syn/syn/T-2022.03-SP2')
DC_SHELL = TOOLROOT / 'bin/dc_shell'
DC_INIT_FILES = (TOOLROOT / 'admin/setup/.synopsys_dc.setup',
                 TOOLROOT / 'auxx/syn/.dc_common_procs.tcl', TOOLROOT / 'auxx/syn/.dc_procs.tcl')
DC_FLAGS = ('-64bit', '-no_home_init', '-no_local_init')
VCD2SAIF = TOOLROOT / 'bin/vcd2saif'
VCS = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/vcs')
NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
SCALE = {'W': 1, 'mW': 1e-3, 'uW': 1e-6, 'nW': 1e-9, 'pW': 1e-12}
_SHA_CACHE = {}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    path = Path(path)
    stat = path.stat()
    identity = (str(path), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    if identity in _SHA_CACHE:
        return _SHA_CACHE[identity]
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    after = path.stat()
    require((stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns) ==
            (after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'Input changed while hashing: ' + str(path))
    _SHA_CACHE[identity] = h.hexdigest()
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, obj):
    with Path(path).open('x') as stream:
        json.dump(obj, stream, indent=2, sort_keys=True)
        stream.write('\n')


def verify(pins):
    for path, expected in pins.items():
        require(sha(path) == expected, 'Identity drift: ' + str(path))


def watts(value, unit):
    require(unit in SCALE, 'Unknown power unit: ' + unit)
    result = float(value) * SCALE[unit]
    require(math.isfinite(result) and result >= 0, 'Invalid power quantity')
    return result


def parse_power(text):
    """Use explicit units on the summary/Total line, never library-header units."""
    total_re = (r'^Total\s+' + r'\s+'.join([f'({NUMBER})\s+(\w+)'] * 4) + r'\s*$')
    totals = re.findall(total_re, text, re.M)
    require(len(totals) == 1, 'Missing/ambiguous unit-bearing Total row')
    fields = totals[0]
    values = [watts(fields[i], fields[i+1]) for i in range(0, 8, 2)]
    result = dict(zip(('internal_w', 'switching_w', 'leakage_w', 'total_w'), values))
    dynamic = re.findall(r'^Total Dynamic Power\s*=\s*(' + NUMBER + r')\s+(\w+)', text, re.M)
    require(len(dynamic) == 1, 'Missing/ambiguous dynamic summary')
    result['dynamic_w'] = watts(*dynamic[0])
    require(result['total_w'] > 0 and result['dynamic_w'] > 0, 'Empty power estimate')
    # DC's rounded group totals can differ slightly from its summary calculation.
    for actual, expected in ((result['total_w'], sum(values[:3])),
                             (result['dynamic_w'], sum(values[:2]))):
        require(abs(actual-expected) <= max(1e-6, actual*0.001), 'Inconsistent power totals/units')
    black = re.findall(r'^black_box\s+(' + NUMBER + r')\s+(' + NUMBER + r')\s+('
                       + NUMBER + r')\s+(' + NUMBER + r')\s+', text, re.M)
    require(len(black) == 1 and all(float(v) == 0 for v in black[0]), 'Missing/nonzero black-box group')
    return result


def parse_annotation(text, gate_level=True):
    """Strict direct-annotation policy; zero-object categories are permitted."""
    require('Report : saif' in text and '-missing' in text, 'Missing annotation report')
    if gate_level:
        require('-rtl_saif' not in text, 'RTL-only annotation report cannot accept gate power')
    pattern = (r'^\s*(Nets|Ports|Pins|Seq Cells|Tri Cells)\s+'
               r'(\d+)\(([\d.]+)%\)\s+(\d+)\(([\d.]+)%\)\s+'
               r'(\d+)\(([\d.]+)%\)\s+(\d+)\s*$')
    matches = re.findall(pattern, text, re.M)
    counts = {}
    required = {'Nets', 'Ports', 'Pins'} if gate_level else {'Ports', 'Seq Cells', 'Tri Cells'}
    for name, user, percent, default, _, propagated, _, total in matches:
        require(name not in counts, 'Duplicate annotation category')
        user, default, propagated, total = map(int, (user, default, propagated, total))
        require(user+default+propagated == total and user == total and default == propagated == 0,
                'Missing/default/propagated annotation: ' + name)
        require(float(percent) == (100 if total else 0), 'Inconsistent annotation percentage')
        counts[name] = dict(user=user, total=total, default=default, propagated=propagated)
    require(set(counts) == required and counts['Ports']['total'] > 0, 'Incomplete/empty annotation table')
    require(sum(c['total'] for c in counts.values()) > counts['Ports']['total'], 'Empty internal annotation')
    labels = ('ports', 'nets', 'pins') if gate_level else ('ports', 'sequential cells', 'three-state cells')
    for label in labels:
        pattern = r'List of Non-annotated ' + re.escape(label) + r'\s*:\s*0\s+' + re.escape(label)
        require(len(re.findall(pattern, text, re.I)) == 1, 'Missing/nonzero unannotated list: ' + label)
    require(not re.search(r'(?i)conflict|\(PWR-19\)', text), 'Conflicting SAIF annotation')
    return counts


def check_log(text):
    require(not re.search(r'(?m)^\s*POWER_DC_FATAL:', text), 'Tcl power failure')
    require(not re.search(r'(?mi)^\s*(?:Error:|Fatal:)|\(PWR-19\)|'
                          r'Unable to resolve reference|Cannot find.*library|no switching activity', text),
            'DC error, unresolved reference, activity conflict or missing activity')
    for marker in ('POWER_LINK_PASS', 'POWER_READ_SAIF_PASS', 'POWER_DC_COMPLETE'):
        require(len(re.findall(r'^' + marker + r'$', text, re.M)) == 1, 'Missing/duplicate DC marker: ' + marker)


def collect_power_reports(run):
    """Retain measured values even when the separate strict annotation gate fails."""
    check_log((run / 'console.log').read_text(errors='replace'))
    for name in ('power_groups.rpt', 'power_hierarchy.rpt', 'power_modulegroups.rpt', 'saif_rtl_missing.rpt'):
        require((run / 'reports' / name).stat().st_size > 0, 'Missing report: ' + name)
    result = dict(dc_execution_completed=True,
                  power_watts=parse_power((run / 'reports/power_total.rpt').read_text()),
                  power_acceptance=False)
    text = (run / 'reports/saif_gate_missing.rpt').read_text()
    rows = re.findall(r'^\s*(Nets|Ports|Pins)\s+(\d+)\([\d.]+%\)\s+'
                      r'(\d+)\([\d.]+%\)\s+(\d+)\([\d.]+%\)\s+(\d+)\s*$', text, re.M)
    result['annotation_counts'] = {name: dict(user=int(user), default=int(default),
        propagated=int(propagated), total=int(total)) for name,user,default,propagated,total in rows}
    try:
        result['annotation'] = parse_annotation(text)
        result['annotation_gate'] = 'PASS'
    except ValueError as error:
        result.update(annotation_gate='FAIL', error=str(error))
    return result


def audit_reports(args):
    """Postprocess the completed false-positive run without rerunning DC."""
    previous, out = args.previous_run.resolve(), args.output.resolve()
    require(out.parent == OUT and out.name.startswith('power_dc_20261117_') and not out.exists(),
            'Fresh owned audit output required')
    original = read(previous / 'result.json')
    require(original['state'] == 'FAIL' and original['error'] == "ValueError('Tcl power failure')",
            'Report reuse is scoped to the known echoed-fatal false positive')
    require(original['provisional'] is True, 'Only provisional report recovery is in scope')
    pins = read(previous / 'source-pins.json')
    verify(pins)
    reports = collect_power_reports(previous)
    result = dict(original)
    result.pop('error', None)
    result.update(reports)
    result.update(state='FAIL' if reports['annotation_gate'] == 'FAIL' else 'PROVISIONAL_POWER_REPORT_NOT_ACCEPTED',
                  original_result=dict(path=str(previous / 'result.json'), sha256=sha(previous / 'result.json'), state='FAIL'),
                  original_worker_reclassified=False, dc_reexecuted=False,
                  recovery_scope='Echoed Tcl source was not a runtime fatal; annotation policy unchanged')
    for p in (previous / 'result.json', previous / 'console.log', previous / 'source-pins.json',
              *(previous / 'reports').iterdir()):
        if p.is_file():
            pins[str(p)] = sha(p)
    out.mkdir()
    (out / 'inputs').mkdir()
    for name in ('dc_power.py', 'test_dc_power.py'):
        source = Path(__file__).with_name(name)
        shutil.copyfile(source, out / 'inputs' / name)
        pins[str(out / 'inputs' / name)] = sha(source)
    save(out / 'source-pins.json', pins)
    save(out / 'result.json', result)
    save(out / 'status.json', dict(state=result['state'], dc_reexecuted=False, completed=True))
    print(json.dumps(dict(output=str(out), state=result['state'], annotation_gate=result['annotation_gate'],
                          power_watts=result['power_watts'], dc_reexecuted=False)))


def inspect_saif(path, instance):
    require(re.fullmatch(r'[A-Za-z_][\w$]*(?:/[A-Za-z_][\w$]*)*', instance), 'Unsafe instance')
    require(0 < path.stat().st_size <= 2 * 1024**3, 'SAIF size outside preparation budget')
    # Bounded header inspection only. DC and the independent capture gate must
    # validate full content; finding an INSTANCE substring elsewhere is unsafe.
    with path.open(errors='strict') as stream:
        prefix = stream.read(1024**2)
    duration = re.findall(r'\(DURATION\s+(\d+)\s*\)', prefix)
    timescale = re.findall(r'\(TIMESCALE\s+(' + NUMBER + r')\s+(fs|ps|ns|us|ms|s)\s*\)', prefix)
    require(prefix.lstrip().startswith('(SAIFILE') and len(duration) == len(timescale) == 1,
            'Invalid SAIF header')
    require(int(duration[0]) > 0 and float(timescale[0][0]) > 0, 'Empty SAIF duration')
    chain = r'\s*'.join(r'\(INSTANCE\s+' + re.escape(n) + r'\b' for n in instance.split('/'))
    root = re.search(r'\(INSTANCE\s+', prefix)
    require(root and re.match(chain, prefix[root.start():]), 'Instance path not in bounded SAIF root chain')
    return dict(instance=instance, duration_ticks=int(duration[0]), timescale=list(timescale[0]),
                validation='bounded root/header check only; full capture gate and DC parse required')


def check_conversion_activity(conversion, capture):
    require(conversion['state'] == 'SAIF_CONVERSION_PASS_NOT_POWER', 'Conversion has not passed')
    require(capture['state'] == 'CAPTURE_COMPLETE_NOT_TASK_PASS', 'Not a bounded completed capture')
    require(conversion['instance'] == 'ara_tb/dut/i_ara_soc', 'Wrong converted instance')
    require(capture['clock_period_ns'] == 1, 'Only the documented 1ns power assumption is supported')
    cycles = capture['last_cycle'] - capture['first_cycle']
    require(capture['first_cycle'] > 0 and cycles >= 1024, 'Insufficient bounded capture')
    window, summary = conversion['window'], conversion['saif_summary']
    require(window['tick_fs'] > 0 and window['last_tick'] > window['first_tick'] > 0 and
            window['duration_ticks'] == window['last_tick'] - window['first_tick'] and
            window['duration_fs'] == window['duration_ticks'] * window['tick_fs'] and
            window['initial_snapshot_values'] > 0, 'Invalid initial snapshot/window')
    require(abs(window['duration_fs'] - cycles * 1000000) <= window['tick_fs'], 'Conversion cycle/time mismatch')
    require(summary['duration_ticks'] > 0 and summary['tick_fs'] > 0 and
            summary['duration_ticks'] * summary['tick_fs'] == window['duration_fs'], 'Converted SAIF duration mismatch')
    clock = summary['clock_activity']
    require(summary['clock'] == 'clk_i' and clock['TX'] == clock.get('TZ', 0) == 0 and
            clock['T0'] + clock['T1'] == summary['duration_ticks'] and
            abs(clock['TC'] - 2 * cycles) <= 2, 'Unknown/inconsistent captured clock')
    for name in ('elf_sha256', 'simv_sha256'):
        require(conversion[name] == capture[name], 'Conversion/capture identity mismatch: ' + name)


def validate_conversion(path):
    conversion = read(path)
    require(conversion['state'] == 'SAIF_CONVERSION_PASS_NOT_POWER', 'Conversion has not passed')
    inventory = Path(conversion['source_pins'])
    pins = read(inventory)
    verify(pins)
    capture_path, saif = Path(conversion['capture']), Path(conversion['saif'])
    require(capture_path.is_absolute() and saif.is_absolute(), 'Absolute conversion paths required')
    require(pins.get(str(capture_path)) == conversion['capture_sha256'] == sha(capture_path) and
            pins.get(str(saif)) == conversion['saif_sha256'] == sha(saif), 'Conversion input/output drift')
    capture = read(capture_path)
    check_conversion_activity(conversion, capture)
    header = inspect_saif(saif, conversion['instance'])
    tick_units = dict(s=10**15, ms=10**12, us=10**9, ns=10**6, ps=1000, fs=1)
    require(header['duration_ticks'] == conversion['saif_summary']['duration_ticks'] and
            float(header['timescale'][0]) * tick_units[header['timescale'][1]] ==
            conversion['saif_summary']['tick_fs'], 'SAIF header differs from conversion summary')
    expected_command = [str(VCD2SAIF), '-input', capture['vcd'], '-output', str(saif),
                        '-instance', 'ara_tb.dut.i_ara_soc', '-time',
                        str(conversion['window']['first_tick']), str(conversion['window']['last_tick'])]
    require(conversion['command'] == expected_command, 'Conversion did not use exact raw-VCD-tick window')
    for key in ('vcd', 'log'):
        p = Path(capture[key])
        require(p.is_absolute() and pins.get(str(p)) == sha(p), 'Capture evidence not pinned: ' + key)
    require(pins.get(str(VCD2SAIF)) == sha(VCD2SAIF), 'Conversion tool identity missing')
    # The verified converter owns full VCD/snapshot scanning and raw-tick -time
    # interpretation. Recheck its pinned receipt and arithmetic, never reconvert.
    pins.update({str(path): sha(path), str(inventory): sha(inventory)})
    return conversion, capture, pins


def bound_run(root):
    """Revalidate immutable plan/image/release, separately from result acceptance."""
    inventory = root / 'source-pins.json'
    pins = read(inventory)
    verify(pins)
    worker = root / 'inputs/gate_run.py'
    require(pins.get(str(worker)) == sha(worker), 'Unpinned gate-run validator')
    spec = importlib.util.spec_from_file_location('power_frozen_gate_run', worker)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plan, binding = module.check_binding(root, sha(root / 'plan.json'), sha(root / 'image-binding.json'))
    pins.update(binding['image_pins'])
    for p in (inventory, root / 'plan.json', root / 'image-binding.json', root / 'image-pins.json'):
        pins[str(p)] = sha(p)
    return plan, binding, module, pins


def checked_run(receipt_path):
    """Normal checked PASS/capture path, unchanged by deviation admission."""
    receipt = read(receipt_path)
    if receipt.get('schema') == 'independent-native-eof-capture-audit-v1':
        return checked_eof_audit(receipt_path, receipt)
    root = Path(receipt_path).parent
    require(receipt['source_pins'] == str(root / 'source-pins.json') and
            receipt['image_pins'] == str(root / 'image-pins.json') and
            receipt['image_binding'] == str(root / 'image-binding.json'), 'Unexpected gate-run evidence layout')
    plan, binding, module, pins = bound_run(root)
    verify(receipt['checked_artifacts'])
    require(receipt['schema'] == 'power-gls-result-v1' and receipt['mode'] == plan['mode'] and
            receipt['case_id'] == plan['case_id'] and receipt['returncode'] == 0 and
            receipt['elf_sha256'] == plan['elf_map']['sha256'] and
            receipt['simv_sha256'] == binding['simv_sha256'] and
            receipt['release'] == plan['release'] and receipt['release_sha256'] == plan['release_sha256'],
            'Gate run/result binding mismatch')
    pins.update(receipt['checked_artifacts'])
    pins[str(receipt_path)] = sha(receipt_path)
    return receipt, plan, binding, module, pins


def check_eof_audit_data(receipt, original, plan, binding):
    require(receipt['schema'] == 'independent-native-eof-capture-audit-v1' and
            receipt['state'] == 'CAPTURE_COMPLETE_NOT_TASK_PASS' and receipt['independent_audit'] is True,
            'Not the scoped native EOF audit')
    require(original['state'] == receipt['original_result']['state'] == 'FAIL' and
            original['error'] == "ValueError('Truncated/nonrepresentative gate window')" and
            receipt['original_worker_reclassified'] is False, 'Original EOF-check FAIL must remain unchanged')
    require(all(receipt[k] is False for k in ('task_pass', 'capture_is_task_pass', 'full_gate_task_pass',
                'gate_numeric_checked', 'gate_protocol_checked', 'timing_acceptance', 'power_acceptance')) and
            receipt['rtl_admission_preserved'] is True, 'Audit scope was widened')
    require(plan['mode'] == original['mode'] == 'capture' and
            original['case_id'] == plan['case_id'] == 'legacy_q8_qbs_sdk_v2_successor' and
            receipt['elf_sha256'] == plan['elf_map']['sha256'] and
            receipt['simv_sha256'] == binding['simv_sha256'] and
            (receipt['first_cycle'], receipt['last_cycle']) == (plan['first_cycle'], plan['last_cycle']),
            'Audit/run/image/window mismatch')
    evidence = receipt['vcd_evidence']
    require(evidence['complete_initial_state'] is True and evidence['eof_at_selected_end'] is True and
            evidence['textual_dumpoff_present'] is False and
            evidence['declared_identifiers'] == evidence['initial_identifiers'] > 0 and
            evidence['clock_path'] == 'ara_tb.dut.i_ara_soc.clk_i' and
            (evidence['first_tick'], evidence['last_tick']) == (receipt['first_tick'], receipt['last_tick']) and
            evidence['duration_fs'] == (plan['last_cycle']-plan['first_cycle']) * 1000000 and
            abs(evidence['clock_edges'] - 2*(plan['last_cycle']-plan['first_cycle'])) <= 1,
            'Incomplete native EOF/snapshot/clock evidence')


def checked_eof_audit(receipt_path, receipt):
    original_ref = receipt['original_result']
    original_path = Path(original_ref['path'])
    root = original_path.parent
    require(receipt['source_pins'] == str(root / 'source-pins.json') and
            receipt['image_pins'] == str(root / 'image-pins.json') and
            receipt['vcd'] == str(root / 'run/window.vcd') and receipt['log'] == str(root / 'run/run.vcs.log'),
            'Audited capture layout mismatch')
    verify(receipt['checked_artifacts'])
    require(receipt['checked_artifacts'].get(str(original_path)) == original_ref['sha256'] == sha(original_path),
            'Original failed receipt identity drift')
    auditor = ROOT / 'verification/performance/power_eval_20261117/audit_gate_capture_eof.py'
    require(receipt['checked_artifacts'].get(str(auditor)) == EOF_AUDITOR_SHA == sha(auditor),
            'Unknown native EOF auditor implementation')
    plan, binding, module, pins = bound_run(root)
    check_eof_audit_data(receipt, read(original_path), plan, binding)
    for key in ('vcd', 'log'):
        require(receipt['checked_artifacts'].get(receipt[key]) == receipt[key+'_sha256'],
                'Audit artifact identity mismatch: ' + key)
    module.clean_log(Path(receipt['log']).read_text())
    module.clean_log((root / 'run/console.log').read_text())
    pins.update(receipt['checked_artifacts'])
    pins[str(receipt_path)] = sha(receipt_path)
    return receipt, plan, binding, module, pins


def validate_capture_image(conversion, capture):
    receipt, plan, binding, module, pins = checked_run(Path(conversion['capture']))
    require(receipt == capture and plan['mode'] == 'capture' and capture['full_gate_task_pass'] is False and
            capture['gate_numeric_checked'] is False and capture['task_pass'] is False and
            binding['simv_sha256'] == conversion['simv_sha256'] and
            plan['elf_map']['sha256'] == conversion['elf_sha256'], 'Capture role/identity mismatch')
    module.capture_markers(Path(capture['log']).read_text(), plan['first_cycle'], plan['last_cycle'])
    gate_root = Path(plan['image'])
    source_inventory = gate_root / 'source-pins.json'
    source_pins = read(source_inventory)
    verify(source_pins)
    receipt_path = gate_root / 'gate-receipt.json'
    require(source_pins.get(str(receipt_path)) == sha(receipt_path), 'Unpinned gate static receipt')
    receipt = read(receipt_path)
    status = read(DC / 'status.json')
    netlist = DC / 'backend/syn/ara_soc/v1-dc/outputs/ara_soc_dc.v'
    require(sha(DC / 'status.json') == STATUS_SHA, 'DC status identity drift')
    check_dc_correspondence(receipt, status, sha(netlist))
    build_path, release_path = gate_root / 'build.json', gate_root / 'initial-release.json'
    build, release = read(build_path), read(release_path)
    require(build['state'] == 'DC_MATCHED_GATE_BUILT_NOT_SIMULATED' and build['image_pins'] == binding['image_pins'] and
            build['release_sha256'] == sha(release_path), 'Wrong gate build/release identity')
    # bound_run has already called the frozen release validator through
    # check_binding. Consume its pinned admission instead of rehashing the
    # entire model/RTL dependency tree two additional times.
    admission_path = Path(capture['source_pins']).parent / 'admission.json'
    require(pins.get(str(admission_path)) == sha(admission_path), 'Unpinned capture admission')
    capture_admission = read(admission_path)
    selected = rtl_role(capture_admission, conversion['elf_sha256'])
    pins.update(source_pins)
    for p in (source_inventory, receipt_path, build_path, release_path, admission_path, Path(plan['release'])):
        pins[str(p)] = sha(p)
    roles = dict(rtl=selected, gate_netlist_sha256=receipt['netlist_sha256'], ddc_sha256=DDC_SHA,
                 initial_release_sha256=sha(release_path),
                 initial_admitted_cases=[c['id'] for c in release['cases']],
                 capture_release_sha256=plan['release_sha256'], gate_simv_sha256=conversion['simv_sha256'],
                 capture_full_program_gls_math_pass=False,
                 critical_control_activity=capture.get('critical_control_activity',
                                                      dict(state='NOT_MEASURED', acceptance_claim=False)))
    if capture.get('independent_audit'):
        roles['independent_capture_audit'] = dict(path=conversion['capture'], sha256=conversion['capture_sha256'],
            original_result=capture['original_result'], original_worker_reclassified=False,
            limitation=capture['limitation'])
    return pins, roles


def check_dc_correspondence(receipt, status, observed_netlist_sha):
    netlist = str(DC / 'backend/syn/ara_soc/v1-dc/outputs/ara_soc_dc.v')
    require(status['state'] == 'SYNTHESIS_COMPLETE' and
            status['output_sha256'][str(DC / DDC_REL)] == DDC_SHA and
            receipt['dc_attempt'] == str(DC) and
            receipt['netlist_sha256'] == observed_netlist_sha == status['output_sha256'][netlist],
            'Captured netlist does not correspond to the exact DDC attempt')


def rtl_role(admission, elf_sha):
    require(admission['state'] == 'COMPOSITE_RTL_EVIDENCE_ADMITTED_NOT_COMPILE_AUTHORIZATION',
            'Audited RTL release admission required')
    selected = [c for c in admission['cases'] if c['elf_sha256'] == elf_sha]
    require(len(selected) == 1, 'Capture ELF lacks audited RTL admission')
    entry = selected[0]
    # No invented elf_sha256 field in numerical.json. The frozen release
    # validator binds it through original work/plan/protocol/image identities.
    for name in ('numerical', 'protocol'):
        reference = entry[name]
        require(sha(reference['path']) == reference['sha256'], 'RTL evidence identity drift: ' + name)
    require(read(entry['numerical']['path'])['state'] == 'PASS', 'RTL numerical evidence failed')
    protocol = read(entry['protocol']['path'])
    require(protocol['status'] == 'PASS' and protocol['issues'] == [] and
            protocol['elf_sha256'] == elf_sha, 'RTL protocol/ELF evidence failed')
    return dict(case_id=entry['id'], elf_sha256=elf_sha, numerical=entry['numerical'],
                protocol=entry['protocol'], rtl_simv_sha256=protocol['simv_sha256'],
                role='RTL numerical/protocol only, not gate protocol',
                original_worker_reclassified=entry['original_worker_reclassified'])


def check_smoke_roles(smoke, conversion, numeric):
    require(smoke['state'] == 'GATE_SMOKE_PASS' and smoke['mode'] == 'smoke' and
            smoke['full_gate_task_pass'] is True and smoke['simv_sha256'] == conversion['simv_sha256'] and
            smoke['elf_sha256'] == conversion['elf_sha256'],
            'Independent smoke for the same ELF and exact gate image required')
    require(numeric['state'] == 'PASS' and numeric['log_sha256'] == sha(smoke['log']) and
            smoke['numerical'] == numeric, 'Gate smoke numerical/log mismatch')


def check_deviation_policy(audit, conversion):
    require(audit['schema'] == 'power-numerical-deviation-audit-v1' and
            audit['state'] == 'POWER_ELIGIBLE_WITH_NUMERICAL_DEVIATION' and
            audit['scope'] == 'gate_smoke' and audit['purpose'] == 'relative_power', 'Wrong power-only deviation audit')
    require(all(audit[k] == conversion[k] for k in ('elf_sha256', 'simv_sha256')), 'Deviation ELF/image mismatch')
    required = {'task_complete', 'target_path_executed', 'no_exception', 'no_stall',
                'guards_pass', 'finite_outputs', 'numerical_only_failure'}
    require(set(audit['checks']) == required and all(v is True for v in audit['checks'].values()),
            'Incomplete/failed independent deviation checks')
    rtl, gate = audit['task_scale']['rtl'], audit['task_scale']['gate']
    require(rtl == gate and {'m', 'n', 'k'} <= set(rtl) and
            all(type(v) is int and v > 0 for v in rtl.values()), 'Task scale mismatch')
    require(audit['target_path'].strip() and audit['rationale'].strip(), 'Missing audit path/rationale')
    errors, limits = audit['errors'], audit['limits']
    require(type(errors['outputs']) is int and type(errors['mismatches']) is int and
            0 < errors['mismatches'] <= errors['outputs'] == gate['m'] * gate['n'], 'Missing exhaustive error counts')
    for name in ('max_abs', 'max_rel', 'rms'):
        value, limit = errors[name], limits[name]
        require(type(value) in (int, float) and type(limit) in (int, float) and
                math.isfinite(value) and math.isfinite(limit) and 0 <= value <= limit,
                'Unbounded/nonfinite or excessive error: ' + name)
    require(errors['rms'] <= errors['max_abs'], 'Inconsistent RMS/max error')


def validate_deviation_audit(path, original_path, conversion):
    audit, original = read(path), read(original_path)
    check_deviation_policy(audit, conversion)
    require(original['state'] == 'FAIL', 'Deviation audit must preserve the original FAIL')
    require(not re.search(r'(?i)timeout|watchdog|interrupted|signal', original.get('error', '')),
            'Timeout/interruption is not a numerical deviation')
    root = Path(original_path).parent
    plan, binding, module, pins = bound_run(root)
    require(plan['mode'] == 'smoke' and plan['elf_map']['sha256'] == conversion['elf_sha256'] and
            binding['simv_sha256'] == conversion['simv_sha256'], 'Deviation run/ELF/image mismatch')
    for name, expected in (('original_result', Path(original_path)), ('run_plan', root / 'plan.json'),
                           ('image_binding', root / 'image-binding.json'), ('source_pins', root / 'source-pins.json')):
        ref = audit[name]
        require(Path(ref['path']) == expected and ref['sha256'] == sha(expected), 'Deviation reference mismatch: ' + name)
        pins[str(expected)] = ref['sha256']
    auditor = audit['auditor']
    require(Path(auditor['path']).name not in ('dc_power.py', 'gate_run.py', 'original_checker.py') and
            auditor['sha256'] == sha(auditor['path']), 'Independent auditor source required')
    evidence = audit['evidence_pins']
    verify(evidence)
    log = root / 'run/run.vcs.log'
    checker_log = root / 'run/checker.log'
    for p in (log, checker_log, Path(plan['elf_map']['gls']), Path(auditor['path'])):
        require(evidence.get(str(p)) == sha(p), 'Missing deviation evidence identity: ' + str(p))
    text = log.read_text()
    # A numerical FAIL/tohost failure may be present; hardware exceptions,
    # assertions and watchdog failures cannot be admitted by this policy.
    require(not re.search(r'(?mi)^\s*(?:Error[-:]|Fatal:)|Assertion failed|\$fatal|'
                          r'Q8_TRAP|Gate watchdog|Gate exit before ROI|Unhandled trap|illegal instruction', text),
            'Non-numerical failure cannot be power-admitted')
    require('GATE_ROI_BEGIN' not in text and 'GATE_CAPTURE_WINDOW_COMPLETE' not in text,
            'Window-only capture is not a completed smoke task')
    require(text.count('Core Test *** SUCCESS ***') + text.count('Core Test *** FAILED ***') == 1,
            'Exactly one full-task completion is required even with numerical deviation')
    pins.update(evidence)
    pins[str(path)] = sha(path)
    return pins


def validate_smoke(path, conversion, deviation_audit=None):
    if read(path)['state'] != 'GATE_SMOKE_PASS':
        require(deviation_audit is not None, 'Failed numerical smoke needs an independent power deviation audit')
        return validate_deviation_audit(deviation_audit, path, conversion)
    require(deviation_audit is None, 'Normal PASS needs no deviation override')
    smoke, plan, binding, module, pins = checked_run(path)
    proof = smoke['numericproof']
    require(smoke['checked_artifacts'].get(proof['path']) == proof['sha256'] == sha(proof['path']),
            'Unpinned smoke numerical proof')
    numeric = read(proof['path'])
    check_smoke_roles(smoke, conversion, numeric)
    log = Path(smoke['log']).read_text()
    module.clean_log(log)
    require(log.count('Core Test *** SUCCESS ***') == 1 and 'GATE_ROI_BEGIN' not in log and
            'GATE_CAPTURE_WINDOW_COMPLETE' not in log, 'Invalid smoke completion scope')
    return pins


def saif_unknown_fraction(path):
    totals = {k: 0 for k in (b'T0', b'T1', b'TX', b'TZ')}
    records, tail = 0, b''
    pattern = re.compile(rb'\((T0|T1|TX|TZ)\s+(\d+)\)')
    with Path(path).open('rb') as stream:
        while True:
            block = stream.read(4 * 1024**2)
            if block:
                data = tail + block
                end = data.rfind(b'\n') + 1
                data, tail = data[:end], data[end:]
            else:
                data, tail = tail, b''
            for key, value in pattern.findall(data):
                totals[key] += int(value)
                records += int(key == b'T0')
            if not block:
                break
    totals = {k.decode(): v for k,v in totals.items()}
    observed = sum(totals.values())
    require(records > 0 and observed > 0, 'No SAIF observation statistics')
    return dict(activity_records=records, record_time_ticks=totals,
                unknown_record_time_fraction=(totals['TX'] + totals['TZ']) / observed,
                metric='SAIF activity-record time weighted, not bit-weighted full-design coverage',
                zero_unknown_required=False, whole_design_knownness_claim=False)


def tcl_word(value):
    require(not any(c in str(value) for c in '{}\n\r\\'), 'Unsafe Tcl literal')
    return '{' + str(value) + '}'


def make_tcl(out, libraries, instance):
    targets = [p for p in libraries if Path(p).name.startswith('tcbn')]
    require(len(targets) >= 4, 'Incomplete standard-cell library set')
    wordlist = lambda paths: '[list ' + ' '.join(tcl_word(p) for p in paths) + ']'
    preamble = (f'set_app_var target_library {wordlist(targets)}\n'
                f'set_app_var link_library [concat [list *] {wordlist(libraries)}]\n'
                f'set ddc {tcl_word(out / "inputs/design.ddc")}\n'
                f'set saif {tcl_word(out / "inputs/activity.saif")}\n'
                f'set instance {tcl_word(instance)}\n')
    body = r'''
proc power_main {} {
  global ddc saif instance
  set_app_var sh_continue_on_error false
  read_ddc $ddc
  if {[sizeof_collection [get_designs -quiet ara_soc]] != 1} {error "read_ddc did not load ara_soc"}
  current_design ara_soc
  if {![link]} {error "link failed"}
  set black [get_cells -hierarchical -filter "is_black_box == true"]
  set unmapped [get_cells -hierarchical -filter "is_unmapped == true"]
  set unresolved 0
  set virtual_constants 0
  set library_backed 0
  set flagged_references [dict create]
  redirect -file reports/mapping_flags.rpt {
    foreach_in_collection cell $black {
      set ref [get_attribute $cell ref_name]
      dict incr flagged_references $ref
      # DC flags virtual constants and mapped sequential library cells as black
      # boxes too. Only an actual bound library object establishes resolution.
      if {$ref eq "**logic_0**" || $ref eq "**logic_1**"} {
        incr virtual_constants
      } elseif {[sizeof_collection [get_lib_cells -quiet -of_objects $cell]] == 1} {
        incr library_backed
      } else {
        incr unresolved
        puts "UNRESOLVED [get_object_name $cell] ref=$ref"
      }
    }
    dict for {ref count} $flagged_references {puts "REFERENCE $ref count=$count"}
  }
  puts "POWER_MAPPING_COUNTS flagged_black=[sizeof_collection $black] library_backed=$library_backed virtual_constants=$virtual_constants unresolved=$unresolved unmapped=[sizeof_collection $unmapped]"
  if {$unresolved || [sizeof_collection $unmapped]} {
    error "Unresolved black-box or unmapped cells remain"
  }
  if {[get_attribute [current_design] is_unmapped]} {error "Design not fully mapped"}
  puts "POWER_LINK_PASS"
  report_reference -hierarchy > reports/references.rpt
  check_design > reports/check_design.rpt
  # Frequency normalization only, NOT a timing-closure claim. No optimization.
  remove_clock [all_clocks]
  create_clock -name power_clk -period 1.0 [get_ports clk_i]
  update_timing
  report_clock > reports/clocks.rpt
  report_timing -max_paths 10 > reports/timing_context.rpt
  saif_map -start
  if {![read_saif -input $saif -instance_name $instance -auto_map_names -verbose]} {
    error "read_saif annotated no objects"
  }
  puts "POWER_READ_SAIF_PASS"
  report_saif -hierarchy -missing > reports/saif_gate_missing.rpt
  report_saif -hierarchy -rtl_saif -missing > reports/saif_rtl_missing.rpt
  report_power -analysis_effort high > reports/power_total.rpt
  report_power -groups {io_pad memory black_box clock_network register sequential combinational} > reports/power_groups.rpt
  report_power -hierarchy -verbose > reports/power_hierarchy.rpt
  report_power -hierarchy -levels 3 > reports/power_modulegroups.rpt
  puts "POWER_DC_COMPLETE"
}
if {[catch {power_main} reason]} {
  puts stderr "POWER_DC_FATAL: $reason"
  exit 1
}
exit 0
'''
    return preamble + body


def make_real_load_tcl(out, libraries, configuration):
    """DC-only successor: disable the documented approximation, not pin loads."""
    clocks = ['clk_i', 'i_system/i_ara/i_vlsu/clk_i']
    clocks += [f'i_system/i_ara/gen_lanes_{i}__i_lane/clk_i' for i in range(4)]
    if configuration == 'qbs':
        clocks += ['i_system/i_ara/i_vlsu/' + name for name in ('qbs_clk', 'akv_clk', 'shared_read_clk')]
    require(configuration in ('qbs', 'rvv'), 'Unknown paired configuration')
    tcl = make_tcl(out, libraries, 'ara_tb/dut/i_ara_soc')
    before = '  update_timing\n'
    require(tcl.count(before) == 1, 'Timing insertion point changed')
    tcl = tcl.replace(before, '''  set_app_var high_fanout_net_threshold 0
  if {[get_app_var high_fanout_net_threshold] != 0} {error "High-fanout approximation still enabled"}
  puts "POWER_REAL_LOAD_PASS threshold=[get_app_var high_fanout_net_threshold] pin_capacitance=[get_app_var high_fanout_net_pin_capacitance]"
  redirect -file reports/load_model.rpt {
    puts "high_fanout_net_threshold=[get_app_var high_fanout_net_threshold]"
    puts "high_fanout_net_pin_capacitance=[get_app_var high_fanout_net_pin_capacitance]"
    puts "Library pin loads retained; no set_load override, synthesis or CTS"
  }
  update_timing
''')
    reports = '  set selected_clocks [list ' + ' '.join(tcl_word(n) for n in clocks) + ']\n'
    reports += '''  redirect -file reports/clock_nets.rpt {
    foreach name $selected_clocks {
      set net [get_nets -quiet $name]
      if {[sizeof_collection $net] != 1} {error "Missing/ambiguous clock net $name"}
      puts "CLOCK_NET_BEGIN $name"
      report_net -nosplit -significant_digits 9 -transition_times $net
      puts "CLOCK_NET_END $name"
    }
  }
  redirect -file reports/clock_power_calculation.rpt {
    foreach name $selected_clocks {
      puts "CLOCK_NET_BEGIN $name"
      report_power_calculation [get_nets $name] -nosplit
      puts "CLOCK_NET_END $name"
    }
  }
'''
    if configuration == 'qbs':
        reports += '''  report_net -connections -verbose -nosplit -significant_digits 9 [get_nets i_system/i_ara/i_vlsu/qbs_clk] > reports/qbs_clock_connections.rpt
'''
    require(tcl.count('  puts "POWER_DC_COMPLETE"') == 1, 'Completion insertion point changed')
    return tcl.replace('  puts "POWER_DC_COMPLETE"', reports + '  puts "POWER_DC_COMPLETE"')


def parse_clock_calculations(text):
    blocks = re.findall(r'^CLOCK_NET_BEGIN (\S+)\n(.*?)^CLOCK_NET_END \1\s*$', text, re.M | re.S)
    require(blocks, 'No per-clock switching calculation reports')
    clocks = {}
    for name, block in blocks:
        require(name not in clocks, 'Duplicate clock calculation')
        require(re.search(r'Capacitance Units\s*=\s*1(?:\.0+)?\s*pf', block, re.I) and
                re.search(r'Time Units\s*=\s*1(?:\.0+)?\s*ns', block), 'Unexpected clock report units')
        def one(pattern):
            matches = re.findall(pattern, block, re.I | re.M)
            require(len(matches) == 1, 'Missing/duplicate clock calculation quantity: ' + name)
            value = float(matches[0])
            require(math.isfinite(value) and value >= 0, 'Invalid clock calculation quantity')
            return value
        capacitance = one(r'total net capacitance\s*=\s*(' + NUMBER + r')\s*$')
        rate = one(r'^\s*Net Toggle Rate\s*=\s*(' + NUMBER + r')\b')
        power = one(r'^\s*Switching power\s*=\s*(' + NUMBER + r')\s*$')
        unit = re.findall(r'Dynamic Power Units\s*=\s*1(?:\.0+)?\s*(mW|uW|nW|pW|W)\b', block)
        require(len(unit) == 1, 'Missing clock power unit')
        voltage = one(r'^\s*voltage\s*=\s*(' + NUMBER + r')\s*$')
        power_w = watts(power, unit[0])
        expected = .5 * capacitance * 1e-12 * voltage**2 * rate * 1e9
        require(abs(power_w - expected) <= max(1e-12, expected * .002), 'Clock C/V/toggle/power disagreement')
        clocks[name] = dict(capacitance_pf=capacitance, toggle_per_ns=rate, voltage_v=voltage,
                            switching_w=power_w, scope='Library pin + existing wire-load model; not post-route')
    return clocks


def atomic_save(path, data):
    temporary = path.with_name(path.name + '.tmp')
    save(temporary, data)
    os.link(temporary, path)
    temporary.unlink()


def prepare_real_load_pair(args):
    pair = args.output.resolve()
    require(not args.authorize_dc and pair.parent == OUT and pair.name.startswith('power_dc_20261117_') and
            not pair.exists(), 'Fresh owned host-only pair preparation required')
    require(1 <= args.execute_seconds <= 3600, 'DC execution budget must be 1..3600 seconds')
    previous = dict(qbs=OUT / 'power_dc_20261117_q8_native_provisional_05',
                    rvv=OUT / 'power_dc_20261117_q8_baseline_follow_01_dc')
    qplan, bplan = read(previous['qbs'] / 'plan.json'), read(previous['rvv'] / 'execution-plan.json')
    libraries = qplan['library_sha256']
    require(libraries == bplan['library_sha256'] and qplan['period_ns'] == bplan['period_ns'] == 1,
            'Original pair library/frequency mismatch')
    verify(libraries)
    original_plan = dict(qbs=qplan, rvv=bplan)
    conversions = dict(qbs=Path(qplan['conversion_result']), rvv=Path(bplan['conversion']))
    dependencies, captures = {}, {}
    for role, run in previous.items():
        pins = read(run / 'source-pins.json')
        if role == 'rvv':
            pins.update(read(run / 'execution-pins.json'))
        verify(pins)
        collect_power_reports(run)
        conversion, capture, conversion_pins = validate_conversion(conversions[role])
        pins.update(conversion_pins)
        expected_ddc = original_plan[role]['proof_roles']['ddc_sha256']
        require(sha(run / 'inputs/design.ddc') == expected_ddc and
                sha(run / 'inputs/activity.saif') == conversion['saif_sha256'], 'Original DDC/SAIF snapshot mismatch')
        for p in (run / 'result.json', run / 'console.log', run / 'source-pins.json', conversions[role],
                  run / ('plan.json' if role == 'qbs' else 'execution-plan.json')):
            pins[str(p)] = sha(p)
        dependencies[role], captures[role] = pins, capture
    same_q8_task(read(qplan['proof_roles']['rtl']['numerical']['path']),
                 read(bplan['proof_roles']['same_elf_gate_smoke']['numerical']['path']))
    pair.mkdir()
    paired = dict(schema='power-real-pin-load-pair-v1', period_ns=1, library_sha256=libraries,
        runs={k: str(pair / k) for k in previous}, original_runs={k: str(v) for k,v in previous.items()},
        original_ratio_reliable=False, automatic_retry=False,
        limitations=['Reconstructed baseline: historical byte identity UNPROVEN',
            'QBS lacks matching full-program gate smoke; RTL proof is not GLS proof',
            'QBS window includes command setup/load/wait/compute/drain; RVV gate PC phase not independently verified',
            'Known X/Z fractions and pre-window QBS SRAM unknown-write warnings retained',
            'Strict propagated/missing annotation failures remain failures',
            'Library pin-load/ZeroWireload estimate, not CTS/post-route/timing closure or whole-task energy'])
    save(pair / 'pair-plan.json', paired)
    for role, previous_run in previous.items():
        out = pair / role
        out.mkdir()
        inputs = out / 'inputs'
        inputs.mkdir()
        (out / 'reports').mkdir()
        for source, name in ((previous_run / 'inputs/design.ddc', 'design.ddc'),
                (previous_run / 'inputs/activity.saif', 'activity.saif'),
                (Path(__file__), 'dc_power.py'), (Path(__file__).with_name('test_dc_power.py'), 'test_dc_power.py')):
            shutil.copyfile(source, inputs / name)
        (inputs / 'power.tcl').write_text(make_real_load_tcl(out, sorted(libraries), role))
        tool_pins = {str(p): sha(p) for p in (DC_SHELL, *DC_INIT_FILES)}
        cpins = dict(libraries)
        cpins.update(tool_pins)
        cpins.update({str(inputs / name): sha(inputs / name) for name in ('design.ddc', 'activity.saif', 'power.tcl')})
        (inputs / 'container-pins.sha256').write_text(''.join(h+'  '+p+'\n' for p,h in sorted(cpins.items())))
        docker = Path(shutil.which('docker') or '/usr/bin/docker')
        command = [str(docker), 'exec', '-u', f'{os.getuid()}:{os.getgid()}', '-e', 'HOME=/home/wangwy',
            '-e', 'SNPSLMD_LICENSE_FILE=27000@t7920', '-w', str(out), 'synopsys_workspace',
            '/usr/bin/timeout', '--signal=TERM', '--kill-after=20', str(args.execute_seconds),
            '/bin/bash', '-c', 'sha256sum -c "$1" || exit 1; exec "$2" '+ ' '.join(DC_FLAGS)+' -f "$3"',
            'power-dc', str(inputs / 'container-pins.sha256'), str(DC_SHELL), str(inputs / 'power.tcl')]
        old_result = read(previous_run / 'result.json')
        plan = dict(schema='power-real-pin-load-run-v1', role=role, pair=str(pair), command=command,
            period_ns=1, high_fanout_net_threshold=0, library_sha256=libraries,
            execute_seconds=args.execute_seconds, service_unit=f'power-dc-20261117-q8-real-load-{role}-01.service',
            original_result=dict(path=str(previous_run / 'result.json'), sha256=sha(previous_run / 'result.json')),
            proof_roles=original_plan[role]['proof_roles'], saif_unknowns=old_result['saif_unknowns'],
            capture= str(conversions[role]), original_capture_state=captures[role]['state'],
            limitations=paired['limitations'], ddc_sha256=sha(inputs / 'design.ddc'), saif_sha256=sha(inputs / 'activity.saif'))
        save(out / 'plan.json', plan)
        tests = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(inputs),
            '-p', 'test_dc_power.py', '-q'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
        (inputs / 'host-tests.log').write_text(tests.stdout)
        require(tests.returncode == 0, 'Frozen paired worker tests failed')
        pins = dependencies[role]
        pins.update(cpins)
        pins.update({str(p): sha(p) for p in inputs.iterdir() if p.is_file()})
        pins.update({str(p): sha(p) for p in (out / 'plan.json', pair / 'pair-plan.json', docker)})
        save(out / 'source-pins.json', pins)
        save(out / 'status.json', dict(state='PREPARED_NOT_EXECUTED'))
    print(json.dumps(dict(output=str(pair), state='PAIR_PREPARED_NOT_EXECUTED', no_eda_launched=True)))


def complete_real_load_pair(pair):
    paired = read(pair / 'pair-plan.json')
    paths = {k: Path(v) / 'result.json' for k,v in paired['runs'].items()}
    if not all(p.exists() for p in paths.values()):
        return
    try:
        claim = os.open(pair / 'comparison.claim', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    os.close(claim)
    results = {k: read(p) for k,p in paths.items()}
    comparison = dict(state='FAIL', power_acceptance=False, original_results_unchanged=True,
        results=results, limitations=paired['limitations'], period_ns=1,
        result_refs={k: dict(path=str(p), sha256=sha(p)) for k,p in paths.items()})
    if all(r.get('dc_execution_completed') and r.get('real_load_model_verified') for r in results.values()):
        native = 'native' if 'native' in results else 'qbs'
        comparison.update(state='PAIRED_REAL_PIN_LOAD_POWER_DATA_NOT_SIGNOFF',
            library_sha256=paired['library_sha256'], phase_comparability_verified=False,
            annotation_gates={k:r['annotation_gate'] for k,r in results.items()})
        comparison[native+'_over_rvv'] = {k: results[native]['power_watts'][k]/v for k,v in results['rvv']['power_watts'].items() if v>0}
        comparison['rvv_over_'+native] = {k: results['rvv']['power_watts'][k]/v for k,v in results[native]['power_watts'].items() if v>0}
        if 'semantic_contract' in paired:
            comparison.update(state='CROSS_PHASE_DIAGNOSTIC_POWER_ONLY_NOT_SIGNOFF',
                semantic_contract=paired['semantic_contract'], paired_ratio_publishable=False,
                same_stage_average_power_ratio=None, whole_task_energy_ratio=None)
            for key in (native+'_over_rvv','rvv_over_'+native):
                comparison['cross_phase_diagnostic_'+key] = comparison.pop(key)
            if not all(r.get('period_ns')==1 and r.get('library_sha256')==paired['library_sha256'] for r in results.values()):
                comparison['state']='FAIL'
                comparison['error']='External/native result library or frequency mismatch'
                for key in list(comparison):
                    if key.startswith('cross_phase_diagnostic_'):
                        del comparison[key]
    elif 'semantic_contract' in paired:
        comparison.update(semantic_contract=paired['semantic_contract'],paired_ratio_publishable=False,
                          same_stage_average_power_ratio=None,whole_task_energy_ratio=None)
    atomic_save(pair / 'comparison.json', comparison)


def validate_real_load_plan(plan):
    require(plan['schema']=='power-real-pin-load-run-v1' and plan['high_fanout_net_threshold']==0,
            'Wrong paired load-model plan')
    require('library_sha256' in plan and bool(plan['library_sha256']), 'DC plan missing library_sha256')
    require(plan['period_ns']==1 and plan['library_sha256']==read(Path(plan['pair'])/'pair-plan.json')['library_sha256'],
            'DC plan differs from paired library/frequency contract')


def execute_real_load(args):
    out = args.output.resolve()
    require(args.authorize_dc and Path(__file__).resolve() == out / 'inputs/dc_power.py', 'Explicit frozen worker required')
    require(not (out / 'attempt.json').exists(), 'No retry/overwrite')
    plan, pins = read(out / 'plan.json'), read(out / 'source-pins.json')
    validate_real_load_plan(plan)
    unit = plan['service_unit']
    owner = subprocess.check_output(['systemctl', '--user', 'show', unit, '-p', 'MainPID', '--value'], text=True).strip()
    require('/'+unit in Path('/proc/self/cgroup').read_text() and owner == str(os.getpid()),
            'Service must directly own frozen DC worker')
    verify(pins)
    save(out / 'attempt.json', dict(pid=os.getpid(), started=time.time()))
    (out / 'status.json').write_text(json.dumps(dict(state='DC_RUNNING', pid=os.getpid()))+'\n')
    result = dict(state='FAIL', role=plan['role'], provisional=True, power_acceptance=False,
        original_result=plan['original_result'], proof_roles=plan['proof_roles'], saif_unknowns=plan['saif_unknowns'],
        limitations=plan['limitations'], period_ns=1, high_fanout_net_threshold=0,
        ddc_sha256=plan['ddc_sha256'], saif_sha256=plan['saif_sha256'], library_sha256=plan['library_sha256'])
    try:
        with (out / 'console.log').open('x') as stream:
            subprocess.run(plan['command'], cwd=out, stdout=stream, stderr=subprocess.STDOUT,
                           timeout=plan['execute_seconds']+60, check=True)
        result.update(collect_power_reports(out))
        text = (out / 'console.log').read_text()
        require(len(re.findall(r'^POWER_REAL_LOAD_PASS threshold=0 pin_capacitance=', text, re.M)) == 1 and
                'high_fanout_net_threshold=0' in (out / 'reports/load_model.rpt').read_text(),
                'Real-load configuration not confirmed by DC')
        result['clock_nets'] = parse_clock_calculations((out / 'reports/clock_power_calculation.rpt').read_text())
        expected = 9 if plan['role'] in ('qbs', 'native') else 6
        require(len(result['clock_nets']) == expected and (out / 'reports/clock_nets.rpt').stat().st_size > 0,
                'Incomplete clock diagnostics')
        verify(pins)
        result.update(real_load_model_verified=True,
            state='PROVISIONAL_POWER_REPORT_NOT_ACCEPTED' if result['annotation_gate']=='PASS' else 'FAIL')
    except Exception as error:
        result['error'] = repr(error)
    result['report_pins'] = {str(p):sha(p) for p in (out / 'reports').iterdir() if p.is_file()}
    atomic_save(out / 'result.json', result)
    (out / 'status.json').write_text(json.dumps(dict(state=result['state'], completed=True))+'\n')
    complete_real_load_pair(Path(plan['pair']))
    print(json.dumps(dict(state=result['state'], output=str(out), error=result.get('error'))), flush=True)
    return int(not result.get('real_load_model_verified', False))


ACTIVITY_ROOT = 'ara_tb/dut/i_ara_soc/'


def activity_label(path):
    base = ACTIVITY_ROOT
    fixed = {base+'clk_i': 'clock', base+'rst_ni': 'reset',
        base+'i_system/i_ariane/commit_stage_i/pc_o': 'pc',
        base+'i_system/i_ariane/commit_stage_i/commit_ack_o': 'ack',
        base+'i_system/i_ara/i_dispatcher/state_q': 'dispatcher',
        base+'i_system/i_ara/i_sequencer/state_q': 'sequencer',
        base+'i_system/i_ara/i_sequencer/ara_req_valid_i': 'vector_valid',
        base+'i_system/i_ara/i_vlsu/i_qbs_engine/state_q': 'qbs_state',
        base+'i_system/i_ara/i_vlsu/i_qbs_engine/i_compute_engine/state_q': 'compute_state',
        base+'i_system/i_ara/i_vlsu/i_qbs_engine/i_compute_engine/loan_valid_o': 'loan_valid',
        base+'i_system/i_ara/i_vlsu/i_qbs_engine/i_compute_engine/loan_activation_o': 'activation',
        base+'i_system/i_ara/i_vlsu/gen_resident_pv_i_control/state_q': 'pv_state',
        base+'i_system/i_ara/i_vlsu/gen_resident_pv_i_control/qk_q': 'qk_mode'}
    if path in fixed:
        return fixed[path]
    for lane in range(4):
        prefix = base+f'i_system/i_ara/gen_lanes_{lane}__i_lane/gen_resident_pv_i_resident_pv/'
        for name in ('fpu_valid_o', 'fpu_operands_o', 'fpu_mask_o'):
            if path == prefix+name:
                return f'pv{lane}_{name}'
    return None


def activity_policy(report, role, kind, anchor=None):
    """Critical controls/active payloads, never an all-design zero-X rule."""
    reasons = []
    required = ['clock', 'reset', 'ack', 'pc', 'dispatcher', 'sequencer', 'vector_valid']
    if role == 'native':
        required += ['pv_state', 'qk_mode'] if kind == 'akv' else ['qbs_state', 'compute_state']
    missing = [n for n in required if n not in report['signals']]
    if missing:
        reasons.append('Missing measured controls: '+','.join(missing))
    for name in required:
        if name != 'pc' and report['signals'].get(name, {}).get('unknown_ticks', 0):
            reasons.append('Critical control X/Z time: '+name)
    if report.get('pc_unknown_when_committing', 0):
        reasons.append('Unknown PC at an acknowledged retirement')
    if report['signals'].get('reset', {}).get('values', {}).get('1', 0) != report['duration_ticks']:
        reasons.append('Reset not continuously deasserted')
    if not report.get('retire_samples'):
        reasons.append('No known acknowledged retirements')
    if abs(report.get('clock_edges', 0)-2*report['cycles']) > 1:
        reasons.append('Root clock edge/cycle mismatch')
    if report.get('active_payload_unknown_samples', 0):
        reasons.append('Unknown measured payload while its operation is active')
    if role == 'rvv':
        if not anchor or report.get('anchor_retire_samples', 0) == 0:
            reasons.append('RTL loop anchor not observed retiring in mapped gate window')
        if not report['signals'].get('vector_valid', {}).get('values', {}).get('1', 0):
            reasons.append('No measured Ara request activity')
    elif kind != 'akv':
        states = report['signals'].get('compute_state', {}).get('values', {})
        if not any(int(v,2)==3 and ticks for v,ticks in states.items() if set(v)<=set('01')):
            reasons.append('No mapped QBS COMPUTE_TILE state')
        fault = report['signals'].get('qbs_state', {}).get('values', {})
        if any(int(v,2) in (6,9) and ticks for v,ticks in fault.items() if set(v)<=set('01')):
            reasons.append('Mapped QBS fault/drain state observed')
    else:
        if not report.get('pv_fpu_samples', 0):
            reasons.append('No mapped resident PV FPU activity')
        if not report['signals'].get('qk_mode', {}).get('values', {}).get('0', 0):
            reasons.append('PV mode not observed')
    return dict(state='ACTIVITY_WINDOW_ELIGIBLE_NOT_GLS_PASS' if not reasons else 'ACTIVITY_WINDOW_REJECTED',
        reasons=reasons, power_acceptance=False, full_gate_numeric_pass=False,
        exact_phase_equivalence_claimed=False,
        limitation='Selected control/active-payload and phase evidence only; unused SRAM/idle X is not forbidden')


def check_m1_long_audit(audit, original, plan, binding):
    require(audit['state']=='INDEPENDENT_LONG_CAPTURE_ELIGIBLE_NOT_TASK_PASS', 'Independent long-M1 audit did not pass')
    require(original['state']=='FAIL' and original.get('error')=="FileNotFoundError(2, 'No such file or directory')" and
            audit['original_state']=='FAIL' and audit['original_worker_reclassified'] is False and
            audit['original_result_unchanged'] is True, 'Original missing-ROI FAIL must remain unchanged')
    require(all(audit[k] is False for k in ('task_pass','gate_numeric_checked','gate_protocol_checked',
                'power_acceptance','SAIF_or_DC_launched','new_GLS_launched')), 'Independent audit scope widened')
    require(plan['case_id']=='qwen3_real_decode_attn_q_m1_n64_native' and plan['mode']=='capture' and
            plan['init_seed']==0 and not plan['environment_diagnostic'], 'Not the scoped M1 capture/environment')
    cycles=plan['last_cycle']-plan['first_cycle']
    require(cycles>=20000 and audit['cycles']==cycles and audit['clock_period_ns']==1 and
            (audit['first_cycle'],audit['last_cycle'])==(plan['first_cycle'],plan['last_cycle']) and
            audit['elf_sha256']==plan['elf_map']['sha256'] and audit['simv_sha256']==binding['simv_sha256'],
            'Independent audit duration/ELF/image mismatch')
    ev=audit['vcd_evidence']
    require(ev['complete_initial_state'] is True and ev['eof_at_selected_end'] is True and
            ev['declared_identifiers']==ev['initial_identifiers']>0 and ev['timescale_fs']==100 and
            ev['duration_fs']==(ev['last_tick']-ev['first_tick'])*ev['timescale_fs']==cycles*1000000 and
            ev['clock_path']=='ara_tb.dut.i_ara_soc.clk_i' and abs(ev['clock_edges']-2*cycles)<=1,
            'Incomplete audited M1 snapshot/EOF/clock evidence')


def accepted_m1_long_audit(path, run, original, plan, binding):
    path=Path(path)
    audit=read(path)
    check_m1_long_audit(audit,original,plan,binding)
    require(not (run/'roi-selection.json').exists(), 'Original missing ROI failure disposition changed')
    require(audit['original_result']['path']==str(run/'result.json') and
            audit['original_result']['sha256']==sha(run/'result.json') and
            audit['vcd']==str(run/'run/window.vcd') and audit['log']==str(run/'run/run.vcs.log'),
            'Independent audit original-result/artifact layout mismatch')
    directory=path.parent
    auditor=directory/'inputs/m1_long_eof_audit_v1.py'
    inventory=directory/'source-pins.json'
    checked=directory/'checked-artifacts.json'
    require(sha(auditor)==M1_LONG_AUDITOR_SHA and read(inventory).get(str(auditor))==M1_LONG_AUDITOR_SHA and
            audit['source_pins']==str(checked), 'Unreviewed M1 long auditor or checked inventory')
    verify(read(inventory))
    pins=read(checked)
    verify(pins)
    for key in ('parent_independent_audit','activity_audit','vcd','log'):
        p=Path(audit[key])
        require(pins.get(str(p))==sha(p), 'Missing audited M1 artifact identity: '+key)
    require(audit['vcd_sha256']==sha(audit['vcd']) and audit['log_sha256']==sha(audit['log']),
            'Audited M1 waveform/log drift')
    parent=read(audit['parent_independent_audit'])
    require(parent['state']=='INDEPENDENT_EOF_CAPTURE_AUDIT_PASS_NOT_TASK_PASS' and
            parent['original_result']==audit['original_result'] and parent['vcd_sha256']==audit['vcd_sha256'] and
            'absent roi-selection.json' in parent['bookkeeping_failure'], 'Missing independent bookkeeping failure proof')
    activity=read(audit['activity_audit'])
    policy=activity_policy(activity,'native','m1')
    require(activity['state']==policy['state']=='ACTIVITY_WINDOW_ELIGIBLE_NOT_GLS_PASS' and
            activity['reasons']==policy['reasons']==[] and activity['cycles']==audit['cycles'] and
            (activity['first_tick'],activity['last_tick'])==(audit['vcd_evidence']['first_tick'],audit['vcd_evidence']['last_tick']),
            'Independent M1 critical-control/activity audit rejected or wrong window')
    for p in (path,inventory,checked,auditor):
        pins[str(p)]=sha(p)
    recovery=dict(path=str(path),sha256=sha(path),original_result=audit['original_result'],
                  original_worker_reclassified=False,scope='Independent missing-ROI recovery; original FAIL preserved')
    return dict(audit,state='CAPTURE_COMPLETE_NOT_TASK_PASS',independent_audit=recovery),activity,pins,recovery


def scan_activity_vcd(path, cycles, first, last, anchor=None, budget=2400):
    """One streaming pass; sample settled VCD time steps, not delta intermediates."""
    codes, scopes, widths, states = {}, [], {}, {}
    dwell = collections.defaultdict(collections.Counter)
    edges = collections.Counter()
    current = None
    definitions = snapshot = False
    initial_count = initial_unknown = 0
    retire = pc_unknown = anchor_hits = payload_unknown = pv_samples = 0
    pcs = collections.Counter()
    deadline = time.monotonic()+budget
    def known(value):
        return bool(value) and set(value) <= set(b'01')
    def value(name):
        return states.get(name)
    def flush(tick):
        nonlocal retire, pc_unknown, anchor_hits, payload_unknown, pv_samples
        if current is None or tick == current:
            return
        dt = tick-current
        for name, val in states.items():
            dwell[name][val.decode()] += dt
        if known(value('ack')) and int(value('ack'),2)&1:
            if known(value('pc')):
                retire += 1
                pc = int(value('pc'),2)
                pcs[hex(pc)] += 1
                anchor_hits += int(anchor is not None and pc == int(anchor,16))
            else:
                pc_unknown += 1
        if value('loan_valid') == b'1' and 'activation' in widths and not known(value('activation')):
            payload_unknown += 1
        for lane in range(4):
            prefix = f'pv{lane}_'
            if value(prefix+'fpu_valid_o') != b'1':
                continue
            pv_samples += 1
            mask, operands = value(prefix+'fpu_mask_o'), value(prefix+'fpu_operands_o')
            if not known(mask) or operands is None:
                payload_unknown += 1
            else:
                mask = int(mask,2)
                for operand in range(3):
                    for half in range(4):
                        low = operand*64+half*16
                        if mask & (1<<half) and not known(operands[len(operands)-low-16:len(operands)-low]):
                            payload_unknown += 1
    with Path(path).open('rb') as stream:
        for index, raw in enumerate(stream):
            if index % 1000000 == 0:
                require(time.monotonic()<deadline, 'Finite VCD activity audit budget expired')
            if not definitions:
                f = raw.split()
                if not f:
                    continue
                if f[0] == b'$scope':
                    scopes.append(f[2])
                elif f[0] == b'$upscope':
                    scopes.pop()
                elif f[0] == b'$var':
                    name = f[4]
                    if name in (b'clk_i',b'rst_ni',b'pc_o',b'commit_ack_o',b'state_q',b'ara_req_valid_i',
                                b'loan_valid_o',b'loan_activation_o',b'qk_q',b'fpu_valid_o',b'fpu_operands_o',b'fpu_mask_o'):
                        label = activity_label(b'/'.join(scopes+[name]).decode())
                        if label:
                            codes.setdefault(f[3], []).append(label)
                            widths[label] = int(f[2])
                elif f[0] == b'$enddefinitions':
                    definitions = True
                continue
            if raw.startswith(b'#'):
                tick = int(raw[1:])
                require(first<=tick<=last and (current is None or tick>=current), 'VCD time bounds/order')
                flush(tick)
                current = tick
                continue
            if raw.startswith(b'$dumpvars'):
                snapshot = True
                continue
            if raw.startswith(b'$end'):
                snapshot = False
                continue
            if raw[:1] in (b'b',b'B',b'r',b'R'):
                parts = raw.split()
                val, code = parts[0][1:].lower(), parts[-1]
            elif raw[:1] in (b'0',b'1',b'x',b'X',b'z',b'Z'):
                val, code = raw[:1].lower(), raw[1:].rstrip()
            else:
                continue
            if snapshot:
                initial_count += 1
                initial_unknown += int(not known(val))
            for label in codes.get(code, ()):
                fill = val[:1] if val[:1] in (b'x',b'z') else b'0'
                normalized = val.rjust(widths[label], fill)
                if label in states and states[label] != normalized:
                    edges[label] += 1
                states[label] = normalized
    require(current==last and definitions and not snapshot, 'VCD audit incomplete')
    signals = {name: dict(width=widths[name], values=dict(counts),
        unknown_ticks=sum(t for v,t in counts.items() if set(v)-set('01')), transitions=edges[name])
        for name,counts in dwell.items()}
    return dict(signals=signals, cycles=cycles, first_tick=first, last_tick=last, duration_ticks=last-first,
        initial_value_records=initial_count, initial_unknown_value_records=initial_unknown,
        clock_edges=edges['clock'], retire_samples=retire, pc_unknown_when_committing=pc_unknown,
        anchor_retire_samples=anchor_hits, top_committing_pcs=pcs.most_common(24),
        active_payload_unknown_samples=payload_unknown, pv_fpu_samples=pv_samples,
        sample_semantics='Settled positive-duration VCD intervals; PC samples require slot0 commit ack, not instruction counts',
        whole_design_knownness_claim=False)


def activity_inputs(run, role, kind):
    """Bind actual producer layouts without requiring invented gate protocol fields."""
    root = run if role == 'native' else run.parent.parent
    pins = read(root / 'source-pins.json')
    verify(pins)
    plan, binding = read(run / 'plan.json'), read(root / 'image-binding.json')
    gate = Path(plan['image'])
    gpins = read(gate / 'source-pins.json')
    verify(gpins)
    image = read(gate / 'image-pins.json')
    verify(image)
    require(binding['simv_sha256'] == image[str(gate / 'sim/simv')], 'Activity gate image mismatch')
    if role == 'native':
        require(binding['plan_sha256']==sha(run/'plan.json') and
                binding['source_pins_sha256']==sha(root/'source-pins.json'), 'Native capture binding drift')
        for key in ('gate_build','gate_image_inventory'):
            verify({binding[key]['path']:binding[key]['sha256']})
        require(read(binding['gate_image_inventory']['path'])==image, 'Native image inventory mismatch')
    else:
        require(binding['image_pins']==image and binding['gate_source_pins_sha256']==sha(gate/'source-pins.json') and
                binding['gate_build_sha256']==sha(gate/'build.json'), 'RVV capture binding drift')
    receipt = read(gate / 'gate-receipt.json')
    require(receipt['memory']['bytes']==1048576 and len(receipt['memory']['instances'])==8,
            'Activity capture must use actual 1MiB memory')
    net = gate / 'source/ara_soc_dc.v'
    require(gpins.get(str(net)) == receipt['netlist_sha256'] == sha(net), 'Captured mapped netlist drift')
    ddc = DC / DDC_REL if role=='native' else gate / 'inputs/ara_soc_dc.ddc'
    require(sha(ddc) == receipt['ddc_sha256'], 'Activity DDC correspondence failed')
    if role == 'native':
        parent = Path(read(gate / 'plan.json')['parent'])
        require(sha(parent / 'source/ara_soc_dc.v') == sha(net) and receipt['ddc_sha256']==DDC_SHA,
                'VRF environment changed mapped netlist/DDC')
        env = gate / 'environment-validation.json'
        require(read(env)['state']=='RESET_ONLY_VRF_INIT_DIAGNOSTICS_PASS_NOT_TASK_PASS', 'Unvalidated VRF environment')
        admission_path = run/'admission.json'
        require(pins.get(str(admission_path))==sha(admission_path), 'Capture-specific RTL admission missing/drifted')
        admission = read(admission_path)
        elfsha = plan['elf_map']['sha256']
        proof = rtl_role(admission, elfsha)
        for p in (env, admission_path, Path(plan['release'])):
            pins[str(p)] = sha(p)
        require(sha(plan['release'])==plan['release_sha256'], 'Native selected release drift')
    else:
        require(shared_libraries(read(DC/'manifest.json'),receipt)==read(DC/'manifest.json')['library_sha256'],
                'RVV library set is not the shared pinned superset')
        require(plan['kind']==('attention' if kind=='akv' else kind), 'Wrong RVV task')
        admission = read(plan['rtl_admission'])
        require(sha(plan['rtl_admission'])==plan['rtl_admission_sha256'] and
                admission['state']=='POWER_ELIGIBLE' and admission['original_worker_reclassified'] is False and
                admission['elf_sha256']==plan['elf_sha256'], 'Missing actual RVV power-deviation admission')
        verify(read(Path(plan['rtl_admission']).parent / 'source-pins.json'))
        verify(admission['artifacts'])
        elfsha = plan['elf_sha256']
        proof = dict(admission=plan['rtl_admission'], strict_original_state='FAIL', full_protocol_pass=False)
        pins.update(admission['artifacts'])
    elf = Path(plan['elf_map']['gls'] if role=='native' else plan['elf'])
    require(sha(elf)==elfsha, 'Capture ELF changed')
    pins.update(gpins)
    pins.update(image)
    for p in (root / 'source-pins.json', root / 'image-binding.json', run / 'plan.json',
              gate / 'source-pins.json', gate / 'image-pins.json', gate / 'gate-receipt.json', ddc, elf):
        pins[str(p)] = sha(p)
    return plan, binding, ddc, pins, dict(rtl=proof, ddc_sha256=sha(ddc), gate_netlist_sha256=sha(net),
        gate_simv_sha256=binding['simv_sha256'], elf_sha256=elfsha, memory_bytes=1048576,
        full_gate_smoke_verified=False, gate_protocol_proof_claimed=False, historical_baseline_identity='UNPROVEN',
        initialization='reset-only native VRF payload seed; baseline has no matching initialization' if role=='native' else 'original reconstructed baseline environment')


def queue_activity(args):
    campaign = args.output.resolve()
    require(not args.authorize_dc and campaign.parent==OUT and campaign.name.startswith('power_dc_20261117_')
            and not campaign.exists(), 'Fresh owned host-only activity campaign required')
    libraries = read(DC / 'manifest.json')['library_sha256']
    verify(libraries)
    campaign.mkdir()
    limitations = ['Relative bounded-window average power only; not full-program GLS mathematics/protocol/timing signoff',
        'RVV original numerical/protocol FAIL retained with separate reviewed power-only admission',
        'Native reset-only VRF seed environment differs from original RVV environment',
        'Only selected critical controls/active payloads measured; idle/unused SRAM X not forbidden',
        'Phase observations are not whole-task energy or proof of identical instruction/operation mixes',
        'Reconstructed baseline historical byte identity UNPROVEN; strict annotation failures retained']
    for kind in ('m1','m4','akv'):
        pair = campaign / kind
        pair.mkdir()
        runs = dict(native=OUT/f'power_gls_20261117_vrfinit_{kind}_activity_01',
                    rvv=OUT/'power_gls_20261117_baseline_rvv_activity_02/cases'/('attention' if kind=='akv' else kind))
        release = read(OUT/f'power_native_release_20261117_activity_03/{kind}-release.json')['cases'][0]
        audit = read(OUT/f'power_rvv_activity_audit_20261117_{"attention" if kind=="akv" else kind}_01/result.json')
        nb, rb = Path(release['elf']['path']).parent/'build.json', Path(audit['elf']).parent/'build.json'
        native, rvv = read(nb), read(rb)
        if kind=='akv':
            # Fixture order encodes implementation-specific arithmetic order,
            # not input identity; do not require those mode flags to match.
            fixture = {k:native['fixture'][k] for k in ('case','data_hash','data_bytes')}
            require(native['paired_source_data']==rvv['paired_source_data'] and
                    fixture=={k:rvv['fixture'][k] for k in fixture},
                    'Attention paired input identity/shape mismatch')
            task = dict(fixture=fixture, paired_source_data=native['paired_source_data'],
                        arithmetic_order=dict(native=native['fixture']['order'],rvv=rvv['fixture']['order']))
        else:
            task = {k:native['case'][k] for k in ('m','n','k','source','operator')}
            require(task=={k:rvv['case'][k] for k in task}, 'Q4 paired task scale/source mismatch')
        pairplan = dict(runs={role:str(pair/role) for role in runs}, library_sha256=libraries,
            limitations=limitations, task_identity=task, period_ns=1, phase_gate_required=True)
        save(pair/'pair-plan.json', pairplan)
        for role, run in runs.items():
            out = pair/role
            (out/'inputs').mkdir(parents=True)
            (out/'reports').mkdir()
            root = run if role=='native' else run.parent.parent
            cpins = read(root/'source-pins.json')
            require(not any(p in cpins for p in (str(Path(__file__)),str(Path(__file__).with_name('test_dc_power.py')))),
                    'Current helper is a sealed producer input')
            pins = {str(p):sha(p) for p in (root/'source-pins.json',root/'image-binding.json',run/'plan.json',
                pair/'pair-plan.json',nb,rb,DC/'manifest.json')}
            for name in ('dc_power.py','test_dc_power.py','convert.py'):
                dest = out/'inputs'/name
                shutil.copyfile(Path(__file__).with_name(name),dest)
                pins[str(dest)] = sha(dest)
            pins.update(libraries)
            pins.update({str(p):sha(p) for p in (DC_SHELL,VCD2SAIF,*DC_INIT_FILES)})
            job = dict(role=role,kind=kind,capture_run=str(run),pair=str(pair),wait_seconds=28800,
                execute_seconds=3600,poll_seconds=300,task_identity=task,library_sha256=libraries,
                service_unit=f'power-dc-20261117-activity-{kind}-{role}-01.service',
                conversion_output=str(OUT/f'power_saif_20261117_activity_chain_{kind}_{role}_01'),
                limitations=limitations, automatic_retry=False)
            save(out/'chain-plan.json',job)
            pins[str(out/'chain-plan.json')]=sha(out/'chain-plan.json')
            save(out/'chain-pins.json',pins)
            save(out/'status.json',dict(state='PREPARED_ACTIVITY_FOLLOWUP_NOT_EXECUTED'))
    print(json.dumps(dict(output=str(campaign),workers=6,no_eda_launched=True)))


@contextmanager
def activity_dc_slot(deadline):
    streams = [(OUT/f'.power-dc-real-load-slot-{i}.lock').open('a') for i in range(2)]
    acquired = None
    try:
        while acquired is None:
            for stream in streams:
                try:
                    fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    acquired = stream
                    break
                except BlockingIOError:
                    pass
            if acquired is None:
                require(time.monotonic()<deadline, 'Finite two-worker DC slot wait exhausted')
                time.sleep(300)
        yield
    finally:
        if acquired is not None:
            fcntl.flock(acquired,fcntl.LOCK_UN)
        for stream in streams:
            stream.close()


def follow_activity(args):
    out = args.output.resolve()
    require(args.authorize_dc and Path(__file__).resolve()==out/'inputs/dc_power.py', 'Authorized frozen activity worker required')
    require(not (out/'chain-attempt.json').exists(), 'No activity retry')
    job = read(out/'chain-plan.json')
    unit = job['service_unit']
    owner = subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','--value'],text=True).strip()
    require('/'+unit in Path('/proc/self/cgroup').read_text() and owner==str(os.getpid()), 'Direct systemd owner required')
    verify(read(out/'chain-pins.json'))
    save(out/'chain-attempt.json',dict(pid=os.getpid(),started=time.time()))
    def status(state):
        (out/'status.json').write_text(json.dumps(dict(state=state,pid=os.getpid()))+'\n')
        print(state,flush=True)
    run = Path(job['capture_run'])
    try:
        audit_path=Path(job['independent_capture_audit']) if job.get('independent_capture_audit') else None
        status('WAITING_INDEPENDENT_M1_LONG_AUDIT' if audit_path else 'WAITING_COMPLETED_ACTIVITY_CAPTURE')
        deadline = time.monotonic()+job['wait_seconds']
        while not (audit_path if audit_path else run/'result.json').exists():
            if not audit_path:
                root = run if job['role']=='native' else run.parent.parent
                require(not (root/'result.json').exists(), 'Collector ended without this case capture')
            require(time.monotonic()<deadline, 'Finite capture wait exhausted')
            time.sleep(300)
        original = read(run/'result.json')
        if audit_path:
            require(read(audit_path)['state']=='INDEPENDENT_LONG_CAPTURE_ELIGIBLE_NOT_TASK_PASS',
                    'Independent M1 audit failed; preserve original FAIL and do not convert')
        else:
            require(original['state']=='CAPTURE_COMPLETE_NOT_TASK_PASS', 'Upstream capture failed; no retry')
        status('CHECKING_CAPTURE_LINEAGE_AND_ACTIVITY')
        plan,binding,ddc,pins,roles = activity_inputs(run,job['role'],job['kind'])
        audited_activity=None
        if audit_path:
            require(job['role']=='native' and job['kind']=='m1', 'Missing-ROI adapter is M1-specific')
            original,audited_activity,audit_pins,recovery=accepted_m1_long_audit(audit_path,run,original,plan,binding)
            pins.update(audit_pins)
            roles['independent_capture_audit']=recovery
        if job.get('minimum_cycles'):
            require(not plan.get('environment_diagnostic') and
                    plan['last_cycle']-plan['first_cycle']>=job['minimum_cycles'],
                    'Diagnostic/short capture cannot satisfy formal duration policy')
            roles['window_semantics']=job['window_semantics']
        require(original['elf_sha256']==roles['elf_sha256'] and original['simv_sha256']==binding['simv_sha256'],
                'Completed capture ELF/image mismatch')
        vcd, log = run/'run/window.vcd',run/'run/run.vcs.log'
        require(sha(vcd)==original['vcd_sha256'] and sha(log)==original['log_sha256'], 'Capture file drift')
        evidence = original['vcd_evidence']
        require(evidence['complete_initial_state'] and evidence['eof_at_selected_end'] and evidence['timescale_fs']==100,
                'Missing actual snapshot/EOF/timescale proof')
        anchor = plan.get('window_basis',{}).get('anchor_pc') if job['role']=='rvv' else None
        report = dict(audited_activity) if audited_activity is not None else scan_activity_vcd(
            vcd,plan['last_cycle']-plan['first_cycle'],evidence['first_tick'],evidence['last_tick'],
            anchor,budget=job.get('audit_seconds',2400))
        report.update(activity_policy(report,job['role'],job['kind'],anchor))
        report['original_capture']=dict(path=str(run/'result.json'),sha256=sha(run/'result.json'))
        report['vcd_sha256']=sha(vcd)
        save(out/'activity-audit.json',report)
        require(report['state']=='ACTIVITY_WINDOW_ELIGIBLE_NOT_GLS_PASS', 'Activity rejected: '+'; '.join(report['reasons']))
        for p in (run/'result.json',vcd,log,out/'activity-audit.json'):
            pins[str(p)]=sha(p)
        save(out/'inputs/capture-pins.json',pins)
        accepted = dict(original, original_capture=report['original_capture'], log=str(log),
            first_cycle=plan['first_cycle'],last_cycle=plan['last_cycle'],clock_period_ns=1,
            source_pins=str(out/'inputs/capture-pins.json'),image_pins=str(Path(plan['image'])/'image-pins.json'),
            adapter_scope='Field-layout adapter only; original capture state unchanged; independent activity audit required')
        save(out/'inputs/accepted-capture.json',accepted)
        status('CONVERTING_ACCEPTED_ACTIVITY_VCD')
        conversion_root = Path(job['conversion_output'])
        require(not conversion_root.exists(), 'Conversion output already exists; do not overwrite/retry')
        with (out/'conversion-worker.log').open('x') as stream:
            subprocess.run([sys.executable,'-B',str(out/'inputs/convert.py'),'--capture',str(out/'inputs/accepted-capture.json'),
                '--output',str(conversion_root)],stdout=stream,stderr=subprocess.STDOUT,check=True,
                timeout=job.get('conversion_seconds',2400))
        conversion_path = conversion_root/'result.json'
        conversion,_,conversion_pins = validate_conversion(conversion_path)
        pins.update(conversion_pins)
        unknowns = saif_unknown_fraction(Path(conversion['saif']))
        roles['activity_audit']=dict(path=str(out/'activity-audit.json'),sha256=sha(out/'activity-audit.json'))
        inputs = out/'inputs'
        shutil.copyfile(ddc,inputs/'design.ddc')
        shutil.copyfile(conversion['saif'],inputs/'activity.saif')
        (inputs/'power.tcl').write_text(make_real_load_tcl(out,sorted(job['library_sha256']),'qbs' if job['role']=='native' else 'rvv'))
        cpins = dict(job['library_sha256'])
        cpins.update({str(p):sha(p) for p in (DC_SHELL,*DC_INIT_FILES,inputs/'design.ddc',inputs/'activity.saif',inputs/'power.tcl')})
        (inputs/'container-pins.sha256').write_text(''.join(h+'  '+p+'\n' for p,h in sorted(cpins.items())))
        docker = Path(shutil.which('docker') or '/usr/bin/docker')
        command = [str(docker),'exec','-u',f'{os.getuid()}:{os.getgid()}','-e','HOME=/home/wangwy',
            '-e','SNPSLMD_LICENSE_FILE=27000@t7920','-w',str(out),'synopsys_workspace',
            '/usr/bin/timeout','--signal=TERM','--kill-after=20',str(job['execute_seconds']),'/bin/bash','-c',
            'sha256sum -c "$1" || exit 1; exec "$2" '+' '.join(DC_FLAGS)+' -f "$3"',
            'power-dc',str(inputs/'container-pins.sha256'),str(DC_SHELL),str(inputs/'power.tcl')]
        dcplan = dict(schema='power-real-pin-load-run-v1',role=job['role'],pair=job['pair'],command=command,
            high_fanout_net_threshold=0,execute_seconds=job['execute_seconds'],service_unit=unit,
            original_result=report['original_capture'],proof_roles=roles,saif_unknowns=unknowns,period_ns=1,
            library_sha256=job['library_sha256'],
            limitations=job['limitations'],ddc_sha256=sha(inputs/'design.ddc'),saif_sha256=sha(inputs/'activity.saif'))
        validate_real_load_plan(dcplan)
        save(out/'plan.json',dcplan)
        pins.update(cpins)
        pins.update(read(out/'chain-pins.json'))
        pins.update({str(p):sha(p) for p in inputs.iterdir() if p.is_file()})
        pins.update({str(out/'plan.json'):sha(out/'plan.json'),str(docker):sha(docker)})
        save(out/'source-pins.json',pins)
        status('WAITING_BOUNDED_DC_SLOT')
        with activity_dc_slot(time.monotonic()+14400):
            return execute_real_load(argparse.Namespace(output=out,authorize_dc=True))
    except Exception as error:
        if not (out/'result.json').exists():
            atomic_save(out/'result.json',dict(state='FAIL',error=repr(error),dc_execution_completed=False,
                power_acceptance=False,automatic_retry=False,limitations=job['limitations'],capture_run=str(run)))
        status('FAILED_OR_REJECTED_NO_RETRY')
        complete_real_load_pair(Path(job['pair']))
        return 1


def prepare_activity_successor(args):
    campaign, previous = args.output.resolve(), args.previous_run.resolve()
    require(not args.authorize_dc and campaign.parent==OUT and campaign.name.startswith('power_dc_20261117_') and
            not campaign.exists(), 'Fresh host-only successor campaign required')
    campaign.mkdir()
    for kind in ('m1','m4','akv'):
        pair = campaign/kind
        pair.mkdir()
        paired = read(previous/kind/'pair-plan.json')
        paired.update(runs={r:str(pair/r) for r in ('native','rvv')},
            predecessor=str(previous/kind), recovery_scope='Known missing library field only; no rejected activity override')
        save(pair/'pair-plan.json',paired)
        for role in ('native','rvv'):
            old, out = previous/kind/role, pair/role
            (out/'inputs').mkdir(parents=True)
            (out/'reports').mkdir()
            job = read(old/'chain-plan.json')
            require(job['library_sha256']==paired['library_sha256'], 'Predecessor library contract mismatch')
            unit = f'power-dc-20261117-activity-{kind}-{role}-successor-01.service'
            save(out/'successor-plan.json',dict(previous=str(old),pair=str(pair),service_unit=unit,
                wait_seconds=43200,poll_seconds=300,automatic_retry=False,library_sha256=job['library_sha256']))
            pins = {str(p):sha(p) for p in (old/'chain-plan.json',old/'chain-pins.json',pair/'pair-plan.json',out/'successor-plan.json')}
            for name in ('dc_power.py','test_dc_power.py'):
                dest = out/'inputs'/name
                shutil.copyfile(Path(__file__).with_name(name),dest)
                pins[str(dest)] = sha(dest)
            save(out/'successor-pins.json',pins)
            save(out/'status.json',dict(state='PREPARED_POSTPROCESS_SUCCESSOR_NOT_EXECUTED'))
    print(json.dumps(dict(output=str(campaign),workers=6,no_eda_launched=True)))


def formal_semantics(native, rvv):
    native_cycles=native['last_cycle']-native['first_cycle']
    rvv_cycles=rvv['last_cycle']-rvv['first_cycle']
    require(native_cycles>=20000 and rvv_cycles>=20000 and not native.get('environment_diagnostic'),
            'Only admitted >=20000-cycle non-diagnostic captures can enter formal postprocessing')
    return dict(native=dict(cycles=native_cycles,scope=native['window_selection']['stages'],
                            metric='first_complete_firmware_timed_call'),
        rvv=dict(cycles=rvv_cycles,scope=rvv['phase_contract']['phase']+' including actual waits',
                 metric='contiguous_matmul_subwindow_not_complete_timed_call'),
        same_stage=False, same_stage_average_power_ratio=None,
        reason='Native includes quantization/preparation plus matmul; RVV window contains matmul only',
        ratio_policy='Cross-phase diagnostic raw average powers only; not same-phase power or whole-task energy',
        automatic_window_trimming=False, automatic_window_merging=False)


def prepare_formal_follow(args):
    campaign=args.output.resolve()
    require(not args.authorize_dc and campaign.parent==OUT and campaign.name.startswith('power_dc_20261117_') and
            not campaign.exists(), 'Fresh owned host-only formal follow-up required')
    baseline=OUT/'power_gls_20261117_baseline_rvv_wide_02'
    libraries=read(DC/'manifest.json')['library_sha256']
    verify(libraries)
    campaign.mkdir()
    limitations=['>=20000 cycles does not imply identical semantic phase or whole-task work',
        'Native includes quantization/preparation/matmul; RVV wide windows cover matmul and waits only',
        'No same-stage average-power or whole-task energy ratio will be published',
        'Existing RVV wide collector owns conversion/DC; consume its results without duplicate EDA',
        'Preserve critical-X, selected-active-payload, annotation and reconstructed baseline limitations',
        'Reset-only VRF initialization is not full-program GLS numerical/protocol acceptance']
    for kind, native_name in dict(q8='power_gls_20261117_long_q8_02',
            m1='power_gls_20261117_long_m1_01',m4='power_gls_20261117_long_m4_01').items():
        pair=campaign/kind
        (pair/'native/inputs').mkdir(parents=True)
        (pair/'native/reports').mkdir()
        (pair/'reporter/inputs').mkdir(parents=True)
        run=OUT/native_name
        nplan=read(run/'plan.json')
        rplan=read(baseline/'cases'/kind/'plan.json')
        semantic=formal_semantics(nplan,rplan)
        paired_files=rplan['phase_contract']['paired_capture_inputs']
        for ref in paired_files.values():
            verify({ref['native']:ref['sha256'],ref['rvv']:ref['sha256']})
        paired=dict(runs=dict(native=str(pair/'native'),rvv=str(OUT/'power_dc_20261117_baseline_rvv_wide_02'/kind/'rvv')),
            capture_runs=dict(native=str(run),rvv=str(baseline/'cases'/kind)),library_sha256=libraries,
            limitations=limitations,semantic_contract=semantic,paired_inputs=paired_files,period_ns=1)
        save(pair/'pair-plan.json',paired)
        out=pair/'native'
        job=dict(role='native',kind=kind,capture_run=str(run),pair=str(pair),wait_seconds=86400,
            execute_seconds=3600,poll_seconds=300,minimum_cycles=20000,audit_seconds=7200,
            conversion_seconds=14400,window_semantics=semantic['native'],library_sha256=libraries,
            service_unit=f'power-dc-20261117-formal-{kind}-native-01.service',
            conversion_output=str(OUT/f'power_saif_20261117_formal_{kind}_native_01'),
            limitations=limitations,automatic_retry=False)
        save(out/'chain-plan.json',job)
        inventory=read(run/'source-pins.json')
        require(not any(p in inventory for p in (str(Path(__file__)),str(Path(__file__).with_name('test_dc_power.py')))),
                'Current helper is a sealed capture input')
        pins={str(p):sha(p) for p in (run/'source-pins.json',run/'image-binding.json',run/'plan.json',
            run/'admission.json',pair/'pair-plan.json',out/'chain-plan.json',baseline/'source-pins.json',
            baseline/'cases'/kind/'plan.json',DC/'manifest.json')}
        for ref in paired_files.values():
            pins.update({ref['native']:ref['sha256'],ref['rvv']:ref['sha256']})
        for name in ('dc_power.py','test_dc_power.py','convert.py'):
            dest=out/'inputs'/name
            shutil.copyfile(Path(__file__).with_name(name),dest)
            pins[str(dest)]=sha(dest)
        pins.update(libraries)
        pins.update({str(p):sha(p) for p in (DC_SHELL,VCD2SAIF,*DC_INIT_FILES)})
        save(out/'chain-pins.json',pins)
        save(out/'status.json',dict(state='PREPARED_FORMAL_NATIVE_FOLLOWUP'))
        report=pair/'reporter'
        shutil.copyfile(Path(__file__),report/'inputs/dc_power.py')
        save(report/'report-plan.json',dict(pair=str(pair),wait_seconds=172800,poll_seconds=300,
            upstream_collector=str(baseline),service_unit=f'power-dc-20261117-formal-{kind}-report-01.service'))
        save(report/'report-pins.json',{str(p):sha(p) for p in (report/'inputs/dc_power.py',report/'report-plan.json',pair/'pair-plan.json')})
        save(report/'status.json',dict(state='PREPARED_CROSS_PHASE_REPORT_WAITER'))
    assessment=OUT/'power_formal_windows_20261117_01/assessment.json'
    save(campaign/'akv-formal-blocked.json',dict(state='NO_FORMAL_AKV_WINDOW_ADMITTED',
        evidence=dict(path=str(assessment),sha256=sha(assessment)),
        reason='Current AKV 7500-cycle job is an X diagnostic, not a >=20000-cycle power capture',
        diagnostic_not_converted=True,no_new_simulation_launched=True,power_acceptance=False))
    print(json.dumps(dict(output=str(campaign),native_workers=3,report_waiters=3,
                          rvv_pipeline_reused=True,AKV_formal_blocked=True,no_eda_launched=True)))


def prepare_audited_m1(args):
    pair=args.output.resolve()
    audit=args.capture_audit.resolve()
    previous=args.previous_run.resolve()
    require(not args.authorize_dc and pair.parent==OUT and pair.name.startswith('power_dc_20261117_') and
            not pair.exists(), 'Fresh host-only audited-M1 successor required')
    require(sha(audit.parent/'inputs/m1_long_eof_audit_v1.py')==M1_LONG_AUDITOR_SHA, 'Reviewed independent auditor required')
    paired=read(previous/'pair-plan.json')
    job=read(previous/'native/chain-plan.json')
    require(job['kind']=='m1' and job['role']=='native' and job['minimum_cycles']>=20000,
            'Formal M1 predecessor contract required')
    (pair/'native/inputs').mkdir(parents=True)
    (pair/'native/reports').mkdir()
    (pair/'reporter/inputs').mkdir(parents=True)
    paired['runs']['native']=str(pair/'native')
    paired['capture_audits']=dict(native=str(audit))
    paired['limitations'] += ['Original long_m1 capture remains FAIL; independent missing-ROI EOF/activity audit gates this successor']
    save(pair/'pair-plan.json',paired)
    out=pair/'native'
    job.update(pair=str(pair),independent_capture_audit=str(audit),wait_seconds=28800,
        service_unit='power-dc-20261117-m1-long-eof-native-01.service',limitations=paired['limitations'],
        conversion_output=str(OUT/'power_saif_20261117_m1_long_eof_01'))
    save(out/'chain-plan.json',job)
    parent=Path(job['capture_run'])
    pins={str(p):sha(p) for p in (previous/'pair-plan.json',previous/'native/chain-plan.json',
        parent/'result.json',parent/'plan.json',parent/'source-pins.json',parent/'image-binding.json',
        audit.parent/'plan.json',audit.parent/'source-pins.json',audit.parent/'inputs/m1_long_eof_audit_v1.py',
        pair/'pair-plan.json',out/'chain-plan.json')}
    for name in ('dc_power.py','test_dc_power.py','convert.py'):
        dest=out/'inputs'/name
        shutil.copyfile(Path(__file__).with_name(name),dest)
        pins[str(dest)]=sha(dest)
    pins.update(job['library_sha256'])
    save(out/'chain-pins.json',pins)
    save(out/'status.json',dict(state='PREPARED_WAITING_INDEPENDENT_M1_LONG_AUDIT'))
    reporter=pair/'reporter'
    shutil.copyfile(Path(__file__),reporter/'inputs/dc_power.py')
    config=read(previous/'reporter/report-plan.json')
    config.update(pair=str(pair),service_unit='power-dc-20261117-m1-long-eof-report-01.service')
    save(reporter/'report-plan.json',config)
    save(reporter/'report-pins.json',{str(p):sha(p) for p in
        (reporter/'inputs/dc_power.py',reporter/'report-plan.json',pair/'pair-plan.json')})
    save(reporter/'status.json',dict(state='PREPARED_AUDITED_M1_PAIR_WAITER'))
    print(json.dumps(dict(output=str(pair),waiting_for=str(audit),minimum_cycles=20000,no_eda_launched=True)))


def check_rvv_m1_port_contract(final, capture, plan, alignment):
    require(final['state']=='OFFLINE_ACTIVITY_ELIGIBLE_PORT0_COMPANION_NOT_GLS_PASS' and
            final['original_FAIL_unchanged'] is True and final['simulations_launched']==0 and
            final['power_acceptance'] is False and final['alignment']==alignment, 'RVV port audit did not pass in scope')
    require(capture['state']=='CAPTURE_COMPLETE_NOT_TASK_PASS' and capture['kind']=='m1' and
            capture['offline_scoped_successor'] is True and capture['original_FAIL_unchanged'] is True and
            capture['simulations_launched']==0 and capture['strict_original_state']=='FAIL' and
            all(capture[k] is False for k in ('full_gate_task_pass','gate_numeric_checked','paired_ratio_publishable','power_acceptance')),
            'RVV audit capture scope widened')
    require(plan['last_cycle']-plan['first_cycle']>=20000 and
            (capture['first_cycle'],capture['last_cycle'])==(plan['first_cycle'],plan['last_cycle']) and
            capture['elf_sha256']==plan['elf_sha256'] and capture['clock_period_ns']==1,
            'RVV port audit duration/ELF mismatch')
    require(alignment['original_missing_anchor_port']==1 and alignment['measured_companion_port']==0 and
            alignment['companion_pc']=='0x800022f4' and alignment['missing_branch_pc']=='0x800022f8' and
            alignment['exact_instruction_equivalence_claimed'] is False, 'Wrong measured retirement-port proof')
    expected,observed,offsets=(alignment[k] for k in
        ('expected_rtl_cycles','observed_gate_cycles','gate_minus_rtl_cycles'))
    require(len(expected)==len(observed)==len(offsets)>=4 and all(
        math.isfinite(float(d)) and abs(d)<=2 and abs((g-r)-d)<1e-6 for r,g,d in zip(expected,observed,offsets)),
        'RVV companion episode count/alignment bound failed')


def check_rvv_m1_port_v3(final, capture, plan, alignment, timebase, representation):
    require(final['original_FAILs_unchanged'] is True and capture['original_FAILs_unchanged'] is True and
            final['power_uses_original_full_VCD'] is True and capture['projection_used_for_power'] is False and
            final['exact_ordered_PC_counts_equal'] is True and final['control_statistics_unchanged'] is True,
            'V3 audit widened scope or used projected waveform for power')
    # V3 uses the plural flag because both earlier audit FAILs are retained.
    check_rvv_m1_port_contract(dict(final,original_FAIL_unchanged=final['original_FAILs_unchanged']),
        dict(capture,original_FAIL_unchanged=capture['original_FAILs_unchanged']),plan,alignment)
    cycles=plan['last_cycle']-plan['first_cycle']
    ev=capture['vcd_evidence']
    require(final['timebase']==timebase and timebase['timestamp_multiplier']==1 and
            timebase['no_waveform_rewrite'] is True and timebase['timescale_fs']==100 and
            timebase['cycle_period_fs']==1000000 and timebase['cycles']==cycles and
            timebase['duration_fs']==cycles*1000000 and
            (timebase['marker_first_raw_tick'],timebase['marker_last_raw_tick'])==(ev['first_tick'],ev['last_tick']) and
            (ev['last_tick']-ev['first_tick'])*100==timebase['duration_fs'], 'V3 raw timebase/physical duration mismatch')
    require(representation['exact_ordered_PC_and_counts_equal'] is True and
            representation['port1_samples_added'] is False and representation['ordering_or_counts_relaxed'] is False and
            representation['actual_rows']==representation['original_rows'], 'V3 PC/count representation mismatch')


def rvv_m1_port_auditor(directory):
    v3=directory/'inputs/audit_m1_port_v3.py'
    path,digest,version=(v3,RVV_M1_PORT_V3_SHA,3) if v3.exists() else (
        directory/'inputs/audit_m1_port_v1.py',RVV_M1_PORT_AUDITOR_SHA,1)
    require(sha(path)==digest and read(directory/'audit-source-pins.json').get(str(path))==digest,
            'Unreviewed RVV M1 port auditor implementation')
    return path,version


def accepted_rvv_m1_port_audit(directory):
    directory=Path(directory)
    final=read(directory/'result.json')
    capture=read(directory/'cases/m1/result.json')
    plan=read(directory/'cases/m1/plan.json')
    alignment=read(directory/'alignment-proof.json')
    auditor,version=rvv_m1_port_auditor(directory)
    if version==3:
        check_rvv_m1_port_v3(final,capture,plan,alignment,read(directory/'timebase-proof.json'),
                             read(directory/'representation-proof.json'))
    else:
        check_rvv_m1_port_contract(final,capture,plan,alignment)
    source=read(directory/'audit-source-pins.json')
    verify(source)
    pins=read(directory/'source-pins.json')
    verify(pins)
    parent=OUT/'power_gls_20261117_baseline_rvv_wide_02'
    original_audit=parent/'cases/m1/activity-audit.json'
    require(capture['original_failure']==str(parent/'result.json') and
            read(original_audit)['reasons']==['RTL loop anchor not observed retiring in mapped gate window'],
            'Original RVV failure is not the scoped port-only mismatch')
    if version==3:
        previous=[OUT/f'power_gls_20261117_rvv_m1_port_audit_0{i}/result.json' for i in (1,2)]
        require(capture['previous_audit_failures']==list(map(str,previous)), 'V3 predecessor disposition mismatch')
        for p in previous:
            require(read(p)['state']=='FAIL' and pins.get(str(p))==sha(p), 'Earlier port audit FAIL changed')
        for p in (directory/'timebase-proof.json',directory/'representation-proof.json'):
            require(pins.get(str(p))==sha(p), 'V3 timebase/representation proof not pinned')
    else:
        require(capture['original_audit']==str(original_audit), 'V1 original audit reference changed')
    require(Path(capture['vcd']).resolve()==(parent/'cases/m1/run/window.vcd').resolve() and
            sha(capture['vcd'])==capture['vcd_sha256'] and sha(capture['log'])==capture['log_sha256'],
            'Audited RVV VCD/log identity changed')
    binding=read(directory/'image-binding.json')
    require(capture['simv_sha256']==binding['simv_sha256'], 'Audited RVV image drift')
    report=read(directory/'cases/m1/activity-audit.json')
    policy=activity_policy(report,'rvv','m1','0x800022f4')
    require(report['state']==policy['state']=='ACTIVITY_WINDOW_ELIGIBLE_NOT_GLS_PASS' and report['reasons']==[] and
            report['cycles']==plan['last_cycle']-plan['first_cycle'] and
            report['vcd_sha256']==capture['vcd_sha256'], 'RVV companion audit control/window rejection')
    for p in (original_audit,parent/'result.json',directory/'alignment-proof.json',
              directory/'cases/m1/activity-audit.json',Path(capture['vcd']),Path(capture['log'])):
        digest=pins.get(str(p))
        if digest is None and p.is_symlink():
            digest=pins.get(str(p.resolve()))
        require(digest==sha(p), 'Missing RVV audit evidence pin: '+str(p))
    return dict(result=dict(path=str(directory/'result.json'),sha256=sha(directory/'result.json')),
        capture=dict(path=str(directory/'cases/m1/result.json'),sha256=sha(directory/'cases/m1/result.json')),
        alignment=alignment,auditor_version=version,original_results_reclassified=False,
        scope='Measured port0 companion and MAC-body PCs; port1 branch PC not directly measured; no GLS numeric PASS')


def prepare_rvv_m1_port_pair(args):
    pair=args.output.resolve()
    audit=args.capture_audit.resolve().parent
    previous=args.previous_run.resolve()
    require(not args.authorize_dc and pair.parent==OUT and pair.name.startswith('power_dc_20261117_') and
            not pair.exists(), 'Fresh host-only RVV port-audit paired-report successor required')
    auditor,version=rvv_m1_port_auditor(audit)
    paired=read(previous/'pair-plan.json')
    native_result=Path(paired['runs']['native'])/'result.json'
    native=read(native_result)
    require(native['dc_execution_completed'] is True and native['real_load_model_verified'] is True and
            native['proof_roles']['window_semantics']['cycles']==27241, 'Matching completed native M1 power result required')
    paired['runs']['rvv']=str(OUT/audit.name.replace('power_gls_','power_dc_',1)/'m1/rvv')
    paired['capture_runs']['rvv']=str(audit/'cases/m1')
    paired.setdefault('capture_audits',{})['rvv']=str(audit/'result.json')
    paired['capture_audit_states']=dict(rvv='OFFLINE_ACTIVITY_ELIGIBLE_PORT0_COMPANION_NOT_GLS_PASS')
    paired['required_rvv_port_audit']=str(audit)
    paired['limitations'] += ['RVV M1 original port1 anchor is not directly measured; independently aligned port0 companion proves loop phase within two cycles',
        'Reuse auditor-owned automatic SAIF/DC chain; do not duplicate waveform conversion or EDA']
    (pair/'reporter/inputs').mkdir(parents=True)
    save(pair/'pair-plan.json',paired)
    out=pair/'reporter'
    shutil.copyfile(Path(__file__),out/'inputs/dc_power.py')
    config=read(previous/'reporter/report-plan.json')
    config.update(pair=str(pair),upstream_collector=str(audit),
        service_unit=pair.name.replace('_','-')+'.service')
    save(out/'report-plan.json',config)
    save(out/'report-pins.json',{str(p):sha(p) for p in (out/'inputs/dc_power.py',out/'report-plan.json',
        pair/'pair-plan.json',audit/'audit-source-pins.json',auditor,previous/'pair-plan.json',native_result)})
    save(out/'status.json',dict(state='PREPARED_WAITING_ACTUAL_RVV_PORT_AUDIT',no_eda_launched=True))
    print(json.dumps(dict(output=str(pair),waiting_for=str(audit/'result.json'),reuse_auditor_owned_power_chain=True,no_eda_launched=True)))


def watch_formal_pair(args):
    out=args.output.resolve()
    require(Path(__file__).resolve()==out/'inputs/dc_power.py' and args.authorize_dc,
            'Explicit frozen report waiter required; never launches EDA')
    require(not (out/'attempt.json').exists(), 'No report waiter retry')
    config=read(out/'report-plan.json')
    unit=config['service_unit']
    owner=subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','--value'],text=True).strip()
    require('/'+unit in Path('/proc/self/cgroup').read_text() and owner==str(os.getpid()), 'Direct report waiter owner required')
    verify(read(out/'report-pins.json'))
    save(out/'attempt.json',dict(pid=os.getpid(),started=time.time()))
    pair=Path(config['pair'])
    paired=read(pair/'pair-plan.json')
    deadline=time.monotonic()+config['wait_seconds']
    (out/'status.json').write_text(json.dumps(dict(state='WAITING_NATIVE_AND_EXISTING_RVV_POSTPROCESS',pid=os.getpid()))+'\n')
    port_checked=False
    while True:
        if paired.get('required_rvv_port_audit') and not port_checked:
            audited=Path(paired['required_rvv_port_audit'])
            if not (audited/'result.json').exists() and time.monotonic()<deadline:
                (out/'status.json').write_text(json.dumps(dict(state='WAITING_ACTUAL_RVV_M1_PORT_AUDIT',pid=os.getpid()))+'\n')
                time.sleep(config['poll_seconds'])
                continue
            try:
                acceptance=accepted_rvv_m1_port_audit(audited)
                save(out/'port-audit-acceptance.json',acceptance)
                port_checked=True
                (out/'status.json').write_text(json.dumps(dict(state='AUDIT_ACCEPTED_WAITING_AUDITOR_OWNED_SAIF_DC',pid=os.getpid()))+'\n')
            except Exception as error:
                atomic_save(pair/'comparison.json',dict(state='RVV_PORT_AUDIT_REJECTED_NO_POWER_PAIR',error=repr(error),
                    power_acceptance=False,paired_ratio_publishable=False,same_stage_average_power_ratio=None,
                    semantic_contract=paired['semantic_contract'],limitations=paired['limitations']))
                break
        if all((Path(p)/'result.json').exists() for p in paired['runs'].values()):
            complete_real_load_pair(pair)
            break
        failures=[]
        for role,path in paired['capture_runs'].items():
            result=Path(path)/'result.json'
            if role in paired.get('capture_audits',{}):
                reviewed=Path(paired['capture_audits'][role])
                expected=paired.get('capture_audit_states',{}).get(role,'INDEPENDENT_LONG_CAPTURE_ELIGIBLE_NOT_TASK_PASS')
                if reviewed.exists() and read(reviewed)['state']!=expected:
                    failures.append(dict(role=role,result=str(reviewed),sha256=sha(reviewed),state='INDEPENDENT_AUDIT_FAILED'))
                post=Path(paired['runs'][role])/'result.json'
                if post.exists() and not read(post).get('real_load_model_verified',False):
                    failures.append(dict(role=role,result=str(post),sha256=sha(post),state='AUDITED_POSTPROCESS_FAILED'))
                continue
            if result.exists() and read(result)['state']!='CAPTURE_COMPLETE_NOT_TASK_PASS':
                failures.append(dict(role=role,result=str(result),sha256=sha(result),state=read(result)['state']))
        collector=Path(config['upstream_collector'])/'result.json'
        rvv_capture=Path(paired['capture_runs']['rvv'])/'result.json'
        if collector.exists() and read(collector)['state']=='FAIL' and not rvv_capture.exists():
            failures.append(dict(role='rvv',result=str(collector),sha256=sha(collector),state='UPSTREAM_COLLECTOR_FAILED'))
        if failures or time.monotonic()>=deadline:
            if not (pair/'comparison.json').exists():
                atomic_save(pair/'comparison.json',dict(state='FORMAL_PAIR_BLOCKED',failures=failures,
                    semantic_contract=paired['semantic_contract'],paired_ratio_publishable=False,
                    same_stage_average_power_ratio=None,whole_task_energy_ratio=None,power_acceptance=False,
                    limitations=paired['limitations'],reason='Capture rejected or finite report wait expired'))
            break
        time.sleep(config['poll_seconds'])
    state=read(pair/'comparison.json')['state']
    (out/'status.json').write_text(json.dumps(dict(state=state,completed=True))+'\n')
    print(json.dumps(dict(pair=str(pair),state=state)),flush=True)
    return 0


def follow_activity_successor(args):
    out = args.output.resolve()
    require(args.authorize_dc and Path(__file__).resolve()==out/'inputs/dc_power.py', 'Authorized frozen successor required')
    require(not (out/'successor-attempt.json').exists(), 'No successor retry')
    follow, frozen = read(out/'successor-plan.json'),read(out/'successor-pins.json')
    unit = follow['service_unit']
    owner = subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','--value'],text=True).strip()
    require('/'+unit in Path('/proc/self/cgroup').read_text() and owner==str(os.getpid()), 'Direct successor service owner required')
    verify(frozen)
    save(out/'successor-attempt.json',dict(pid=os.getpid(),started=time.time()))
    old = Path(follow['previous'])
    def status(state):
        (out/'status.json').write_text(json.dumps(dict(state=state,pid=os.getpid()))+'\n')
        print(state,flush=True)
    try:
        status('WAITING_PREDECESSOR_POSTPROCESS_RESULT')
        deadline = time.monotonic()+follow['wait_seconds']
        while not (old/'result.json').exists():
            require(time.monotonic()<deadline, 'Predecessor wait budget expired')
            time.sleep(300)
        original = read(old/'result.json')
        original_ref = dict(path=str(old/'result.json'),sha256=sha(old/'result.json'),state=original['state'])
        if original.get('error') != "KeyError('library_sha256')":
            atomic_save(out/'result.json',dict(state='PREDECESSOR_RESULT_RETAINED_NO_EDA_RETRY',
                original_result=original_ref, predecessor=original, dc_execution_completed=False,
                power_acceptance=False, reason='Not the scoped missing-library failure; no activity rejection override'))
            status('PREDECESSOR_RESULT_RETAINED_NO_EDA_RETRY')
            complete_real_load_pair(Path(follow['pair']))
            return 0
        status('VALIDATING_REUSABLE_ACCEPTED_SAIF_AND_DDC')
        require(not (old/'console.log').exists(), 'Predecessor may have launched DC; do not automatically rerun')
        pins = read(old/'source-pins.json')
        verify(pins)
        job, prior = read(old/'chain-plan.json'),read(old/'plan.json')
        audit = read(old/'activity-audit.json')
        require(audit['state']=='ACTIVITY_WINDOW_ELIGIBLE_NOT_GLS_PASS' and audit['reasons']==[],
                'No successor for rejected activity')
        require('library_sha256' not in prior and job['library_sha256']==follow['library_sha256'],
                'Not the reviewed missing-field defect')
        conversion_path = Path(job['conversion_output'])/'result.json'
        conversion,_,conversion_pins = validate_conversion(conversion_path)
        require(conversion['saif_sha256']==prior['saif_sha256']==sha(old/'inputs/activity.saif') and
                prior['ddc_sha256']==sha(old/'inputs/design.ddc'), 'Reusable SAIF/DDC identity drift')
        pins.update(conversion_pins)
        recovery = dict(original_worker_result=original_ref,original_worker_reclassified=False,
            conversion_reused=dict(path=str(conversion_path),sha256=sha(conversion_path)),
            activity_audit=dict(path=str(old/'activity-audit.json'),sha256=sha(old/'activity-audit.json')),
            capture_reexecuted=False,conversion_reexecuted=False,
            scope='Add missing library_sha256 from pinned chain plan; no admission policy changes')
        save(out/'inputs/recovery-receipt.json',recovery)
        for name in ('design.ddc','activity.saif'):
            shutil.copyfile(old/'inputs'/name,out/'inputs'/name)
        (out/'inputs/power.tcl').write_text(make_real_load_tcl(out,sorted(follow['library_sha256']),
            'qbs' if prior['role']=='native' else 'rvv'))
        cpins = dict(follow['library_sha256'])
        cpins.update({str(p):sha(p) for p in (DC_SHELL,*DC_INIT_FILES,out/'inputs/design.ddc',
                                            out/'inputs/activity.saif',out/'inputs/power.tcl')})
        (out/'inputs/container-pins.sha256').write_text(''.join(h+'  '+p+'\n' for p,h in sorted(cpins.items())))
        command_map = {str(old):str(out),str(old/'inputs/container-pins.sha256'):str(out/'inputs/container-pins.sha256'),
                       str(old/'inputs/power.tcl'):str(out/'inputs/power.tcl')}
        plan = dict(prior,library_sha256=follow['library_sha256'],pair=follow['pair'],service_unit=unit,
                    command=[command_map.get(s,s) for s in prior['command']])
        plan['proof_roles'] = dict(plan['proof_roles'],postprocess_recovery=recovery)
        validate_real_load_plan(plan)
        save(out/'plan.json',plan)
        pins.update(cpins)
        pins.update(frozen)
        pins.update({str(p):sha(p) for p in (old/'result.json',old/'plan.json',old/'source-pins.json',old/'activity-audit.json')})
        pins.update({str(p):sha(p) for p in (out/'inputs').iterdir() if p.is_file()})
        pins[str(out/'plan.json')] = sha(out/'plan.json')
        save(out/'source-pins.json',pins)
        status('WAITING_BOUNDED_DC_SLOT_REUSING_EXISTING_SAIF')
        with activity_dc_slot(time.monotonic()+14400):
            return execute_real_load(argparse.Namespace(output=out,authorize_dc=True))
    except Exception as error:
        if not (out/'result.json').exists():
            atomic_save(out/'result.json',dict(state='FAIL',error=repr(error),dc_execution_completed=False,power_acceptance=False))
        status('SUCCESSOR_FAILED_NO_RETRY')
        complete_real_load_pair(Path(follow['pair']))
        return 1


def shared_libraries(all_on, baseline):
    libraries = dict(all_on['library_sha256'])
    other = baseline.get('library_database_hashes', baseline.get('library_sha256', {}))
    require(other, 'Missing baseline library evidence')
    for path, digest in other.items():
        require(path not in libraries or libraries[path] == digest, 'Baseline library identity conflict')
        libraries[path] = digest
    return libraries


def baseline_plan(args):
    """Minimal host-only DDC/library/Tcl adapter; not an execution admission."""
    out, gate = args.output.resolve(), args.baseline_gate.resolve()
    require(out.parent == OUT and out.name.startswith('power_dc_20261117_') and not out.exists(),
            'Fresh owned output required')
    reference = gate / 'gate-receipt.json'
    receipt = read(reference)
    require(receipt['schema'] == 'power-baseline-gate-static-v2', 'Expected actual baseline v2 receipt')
    pins = read(gate / 'source-pins.json')
    require(pins.get(str(reference)) == sha(reference), 'Baseline receipt drift')
    ddc, netlist = gate / 'inputs/ara_soc_dc.ddc', gate / 'source/ara_soc_dc.v'
    require(pins.get(str(ddc)) == receipt['ddc_sha256'] == sha(ddc) and
            pins.get(str(netlist)) == receipt['netlist_sha256'] == sha(netlist), 'Baseline DDC/netlist drift')
    require(sha(DC / 'manifest.json') == MANIFEST_SHA, 'All-on library manifest drift')
    libraries = shared_libraries(read(DC / 'manifest.json'), receipt)
    verify(libraries)
    conversion = None
    conversion_pins = {}
    if args.conversion:
        conversion, capture, conversion_pins = validate_conversion(args.conversion.resolve())
        binding = read(capture['image_binding'])
        require(Path(binding['gate_build']['path']).parent == gate and
                binding['simv_sha256'] == conversion['simv_sha256'], 'Not this baseline capture/image')
        verify({binding['gate_build']['path']: binding['gate_build']['sha256']})
        conversion_pins[capture['image_binding']] = sha(capture['image_binding'])
    out.mkdir()
    (out / 'inputs').mkdir()
    (out / 'reports').mkdir()
    shutil.copyfile(ddc, out / 'inputs/design.ddc')
    if conversion:
        shutil.copyfile(conversion['saif'], out / 'inputs/activity.saif')
        save(out / 'inputs/conversion-result.json', conversion)
    (out / 'inputs/power.tcl').write_text(make_tcl(out, sorted(libraries), 'ara_tb/dut/i_ara_soc'))
    save(out / 'library-manifest.json', dict(library_sha256=libraries))
    save(out / 'plan.json', dict(state='BASELINE_INPUTS_ONLY_NOT_EXECUTION_AUTHORIZED',
        ddc_sha256=receipt['ddc_sha256'], netlist_sha256=receipt['netlist_sha256'],
        baseline_receipt=str(reference), library_sha256=libraries,
        common_tcl=str(out / 'inputs/power.tcl'), saif_snapshotted=bool(conversion),
        historical_byte_identity=receipt['historical_byte_identity'], period_ns=1,
        next_step='Same-ELF baseline smoke/capture acceptance, then explicit frozen DC worker release',
        all_on_use_same_library_manifest=str(out / 'library-manifest.json'), no_eda_launched=True))
    frozen = {str(p): sha(p) for p in out.rglob('*') if p.is_file()}
    frozen.update(libraries)
    frozen.update(conversion_pins)
    for p in (reference, gate / 'source-pins.json', ddc, netlist, DC / 'manifest.json'):
        frozen[str(p)] = sha(p)
    save(out / 'source-pins.json', frozen)
    print(json.dumps(dict(output=str(out), state='BASELINE_INPUTS_ONLY_NOT_EXECUTION_AUTHORIZED',
                          shared_libraries=len(libraries), no_eda_launched=True)))


def load_frozen(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def baseline_chain_inputs(run, qbs):
    """Use the real frozen baseline adapter, not the all-on release contract."""
    worker = run / 'inputs/gate_run_baseline_serial.py'
    require(sha(worker) == BASELINE_ADAPTER_SHA, 'Unreviewed baseline adapter')
    adapter = load_frozen(worker, 'power_baseline_adapter')
    plan, binding = adapter.check_binding(run, sha(run / 'plan.json'), sha(run / 'image-binding.json'))
    require(plan['mode'] == 'capture' and plan['case_id'] == 'legacy_q8_rvv' and
            plan['clock_period_ns'] == 1 and '+GATE_STOP_AFTER_CAPTURE' in plan['command'],
            'Expected bounded baseline Q8 capture at 1ns')
    smoke = adapter.smoke_pass(plan, binding)
    gate = Path(plan['image'])
    receipt = read(gate / 'gate-receipt.json')
    require(receipt['memory']['bytes'] == 1048576 and len(receipt['memory']['instances']) == 8 and
            not receipt['unresolved_mapped_cell_types'], 'Baseline memory/mapping mismatch')
    require(receipt['ddc_sha256'] == binding['baseline_context']['ddc_sha256'] == sha(gate / 'inputs/ara_soc_dc.ddc')
            and receipt['netlist_sha256'] == binding['baseline_context']['netlist_sha256'] == sha(gate / 'source/ara_soc_dc.v'),
            'Baseline capture netlist/DDC correspondence failed')
    qplan = read(qbs / 'plan.json')
    require(qplan['ddc_sha256'] == DDC_SHA and qplan['period_ns'] == 1,
            'Wrong QBS reference DDC/frequency')
    verify(read(qbs / 'source-pins.json'))
    require(shared_libraries(read(DC / 'manifest.json'), receipt) == qplan['library_sha256'],
            'Baseline and QBS must use identical library bytes')
    require(qplan['library_sha256'] == read(DC / 'manifest.json')['library_sha256'], 'QBS library set drift')
    # The numerical receipts bind both implementations to the same actual task
    # and embedded golden data, without pretending their ELFs are identical.
    qnumeric_ref = qplan['proof_roles']['rtl']['numerical']
    verify({qnumeric_ref['path']: qnumeric_ref['sha256']})
    qnumeric = read(qnumeric_ref['path'])
    numeric = read(smoke['numerical']['path'])
    scale = same_q8_task(qnumeric, numeric)
    pins = {str(p): sha(p) for p in (run / 'plan.json', run / 'source-pins.json', run / 'image-binding.json',
        run / 'image-pins.json', run / 'admission.json', worker, gate / 'gate-receipt.json',
        gate / 'inputs/ara_soc_dc.ddc', gate / 'source/ara_soc_dc.v', qbs / 'plan.json',
        qbs / 'source-pins.json', qbs / 'result.json', qbs / 'console.log', DC / 'manifest.json',
        Path(qnumeric_ref['path']), Path(smoke['result']['path']), Path(smoke['numerical']['path']))}
    pins.update(read(run / 'source-pins.json'))
    pins.update(read(gate / 'source-pins.json'))
    pins.update(binding['image_pins'])
    pins.update(qplan['library_sha256'])
    pins.update(qplan['tool_pins'])
    roles = dict(baseline_context=binding['baseline_context'], historical_byte_identity='UNPROVEN',
        gate_simv_sha256=binding['simv_sha256'], elf_sha256=plan['elf_map']['sha256'],
        ddc_sha256=receipt['ddc_sha256'], gate_netlist_sha256=receipt['netlist_sha256'],
        rtl_admission=str(run / 'admission.json'), same_elf_gate_smoke=smoke, task_scale=scale,
        memory_bytes=1048576, gate_protocol_proof_claimed=False,
        compute_phase_representativeness_verified=False, capture_full_program_gls_math_pass=False,
        window_basis=plan['window_basis'])
    collect_power_reports(qbs)
    return adapter, plan, binding, pins, roles


def same_q8_task(qbs, rvv):
    require(qbs['state'] == rvv['state'] == 'PASS', 'Reference numerical receipts not passing')
    require(qbs['scalar_model_reference_sha256'] == rvv['scalar_model_reference_sha256'],
            'Different embedded golden model data')
    scale = {k: int(qbs['benchmark'][k]) for k in ('rows', 'k', 'inputs', 'outputs')}
    require(scale == {k: int(rvv['benchmark'][k]) for k in scale} and
            all(v > 0 for v in scale.values()), 'Different Q8 task scale')
    return scale


def baseline_capture_receipt(run, out, adapter, plan, binding):
    original = read(run / 'result.json')
    if original['state'] == 'CAPTURE_COMPLETE_NOT_TASK_PASS':
        verify(original['checked_artifacts'])
        require(original['elf_sha256'] == plan['elf_map']['sha256'] and
                original['simv_sha256'] == binding['simv_sha256'], 'Capture result/image mismatch')
        return run / 'result.json'
    require(original['state'] == 'FAIL' and original.get('error') ==
            "ValueError('Truncated/nonrepresentative gate window')", 'Not the known EOF checker defect')
    log, vcd = run / 'run/run.vcs.log', run / 'run/window.vcd'
    text = log.read_text()
    first, last = adapter.g.capture_markers(text, plan['first_cycle'], plan['last_cycle'])
    adapter.g.clean_log((run / 'run/console.log').read_text())
    require(re.search(r'\$finish at simulation time\s+' + str(last) + r'\s*$', text, re.M) and
            'V C S   S i m u l a t i o n   R e p o r t' in text and
            'Core Test *** SUCCESS ***' not in text, 'Missing clean bounded simulator finish')
    attempt = read(run / 'attempt.json')
    progress = [json.loads(line) for line in (run / 'progress.jsonl').read_text().splitlines()]
    require(progress and all(p['owner_pid'] == attempt['pid'] and p['child_pid'] == progress[0]['child_pid']
            for p in progress), 'Capture PID provenance disagreement')
    stat = vcd.stat()
    require(0 < stat.st_size <= plan['max_vcd_bytes'] and
            attempt['started_ns'] <= stat.st_mtime_ns <= log.stat().st_mtime_ns + 2*10**9 and
            attempt['started_ns'] <= stat.st_ctime_ns <= log.stat().st_mtime_ns + 2*10**9,
            'Capture timestamp/size provenance')
    inspector = load_frozen(Path(__file__).with_name('audit_gate_capture_eof.py'), 'power_eof_inspector')
    require(sha(inspector.__file__) == EOF_AUDITOR_SHA, 'EOF inspector drift')
    evidence = inspector.inspect_vcd(vcd, first, last, plan['last_cycle']-plan['first_cycle'])
    paths = [run / name for name in ('result.json', 'attempt.json', 'progress.jsonl', 'plan.json',
        'source-pins.json', 'image-pins.json', 'image-binding.json', 'run/run.vcs.log',
        'run/window.vcd', 'run/console.log')]
    paths.extend((Path(__file__), Path(inspector.__file__)))
    pins = {str(p): sha(p) for p in paths}
    out.mkdir()
    receipt = dict(schema='independent-baseline-eof-capture-audit-v1', state='CAPTURE_COMPLETE_NOT_TASK_PASS',
        original_result=dict(path=str(run / 'result.json'), sha256=sha(run / 'result.json'), state='FAIL'),
        original_worker_reclassified=False, independent_audit=True, checked_artifacts=pins,
        vcd=str(vcd), log=str(log), vcd_sha256=sha(vcd), log_sha256=sha(log),
        source_pins=str(run / 'source-pins.json'), image_pins=str(run / 'image-pins.json'),
        image_binding=str(run / 'image-binding.json'), first_cycle=plan['first_cycle'], last_cycle=plan['last_cycle'],
        first_tick=first, last_tick=last, clock_period_ns=1, simv_sha256=binding['simv_sha256'],
        elf_sha256=plan['elf_map']['sha256'], vcd_evidence=evidence, full_gate_task_pass=False,
        task_pass=False, gate_numeric_checked=False, gate_protocol_checked=False, power_acceptance=False,
        limitation='Exact closed EOF/snapshot/clock only; gate compute phase not independently measured')
    save(out / 'source-pins.json', pins)
    save(out / 'result.json', receipt)
    return out / 'result.json'


def queue_baseline(args):
    out, run, qbs = args.output.resolve(), args.capture_run.resolve(), args.qbs_run.resolve()
    require(args.authorize_dc and out.parent == OUT and out.name.startswith('power_dc_20261117_') and
            not out.exists(), 'Explicit authorization and fresh owned follow-up output required')
    require(300 <= args.wait_seconds <= 28800, 'Wait budget must be 300..28800 seconds')
    _, plan, _, pins, roles = baseline_chain_inputs(run, qbs)
    out.mkdir()
    (out / 'inputs').mkdir()
    for name in ('dc_power.py', 'test_dc_power.py', 'convert.py', 'audit_gate_capture_eof.py'):
        source = Path(__file__).with_name(name)
        if name == 'audit_gate_capture_eof.py':
            require(sha(source) == EOF_AUDITOR_SHA, 'Reviewed EOF inspector required')
        dest = out / 'inputs' / name
        shutil.copyfile(source, dest)
        pins[str(dest)] = sha(dest)
    follow = dict(capture_run=str(run), qbs_run=str(qbs), baseline_gate=plan['image'],
        wait_seconds=args.wait_seconds, poll_seconds=300, execute_seconds=1800,
        saif_output=str(OUT / out.name.replace('power_dc_', 'power_saif_', 1)),
        dc_output=str(OUT / (out.name + '_dc')), proof_roles=roles,
        authorize_dc=True, automatic_retry=False, period_ns=1,
        library_sha256=read(qbs / 'plan.json')['library_sha256'])
    for path in (follow['saif_output'], follow['dc_output']):
        require(not Path(path).exists(), 'Follow-up output already exists')
    save(out / 'follow-plan.json', follow)
    pins[str(out / 'follow-plan.json')] = sha(out / 'follow-plan.json')
    save(out / 'source-pins.json', pins)
    save(out / 'status.json', dict(state='QUEUED_NOT_STARTED', no_eda_launched=True))
    print(json.dumps(dict(output=str(out), frozen_worker=str(out / 'inputs/dc_power.py'),
                          state='QUEUED_NOT_STARTED', proof_roles=roles)))


def follow_baseline(args):
    out = args.output.resolve()
    require(args.authorize_dc and Path(__file__).resolve() == out / 'inputs/dc_power.py',
            'Authorized frozen follow-up worker required')
    require(not (out / 'attempt.json').exists(), 'No follow-up retry')
    unit = out.name.replace('_', '-') + '.service'
    owner = subprocess.check_output(['systemctl', '--user', 'show', unit, '-p', 'MainPID', '--value'], text=True).strip()
    require('/' + unit in Path('/proc/self/cgroup').read_text() and owner == str(os.getpid()),
            'Service must directly own the frozen follow-up worker')
    verify(read(out / 'source-pins.json'))
    follow = read(out / 'follow-plan.json')
    require(follow['authorize_dc'] is True and follow['poll_seconds'] == 300 and
            300 <= follow['wait_seconds'] <= 28800, 'Invalid finite follow-up budget')
    save(out / 'attempt.json', dict(pid=os.getpid(), started=time.time()))
    run, qbs = Path(follow['capture_run']), Path(follow['qbs_run'])
    def status(state):
        (out / 'status.json').write_text(json.dumps(dict(state=state, pid=os.getpid(), updated=time.time()))+'\n')
        print(state, flush=True)
    result = dict(state='FAIL', power_acceptance=False, automatic_retry=False)
    try:
        status('WAITING_FOR_BASELINE_CAPTURE')
        deadline = time.monotonic() + follow['wait_seconds']
        unit = run.name.replace('_', '-') + '.service'
        while True:
            active = subprocess.check_output(['systemctl', '--user', 'show', unit, '-p', 'ActiveState', '--value'], text=True).strip()
            if (run / 'result.json').exists() and active not in ('active', 'activating', 'deactivating'):
                break
            require(time.monotonic() < deadline, 'Capture wait budget exhausted; no EDA started')
            require(active in ('active', 'activating', 'deactivating'), 'Capture service ended without result')
            time.sleep(min(300, max(0, deadline-time.monotonic())))
        status('VALIDATING_COMPLETED_CAPTURE')
        verify(read(out / 'source-pins.json'))
        adapter, plan, binding, _, roles = baseline_chain_inputs(run, qbs)
        capture = baseline_capture_receipt(run, out / 'capture-audit', adapter, plan, binding)
        status('CONVERTING_VCD_TO_SAIF')
        with (out / 'conversion-worker.log').open('x') as log:
            subprocess.run([sys.executable, '-B', str(out / 'inputs/convert.py'), '--capture', str(capture),
                            '--output', follow['saif_output']], stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=2100)
        conversion_path = Path(follow['saif_output']) / 'result.json'
        conversion, captured, _ = validate_conversion(conversion_path)
        require(conversion['elf_sha256'] == plan['elf_map']['sha256'] and
                conversion['simv_sha256'] == binding['simv_sha256'] and
                (captured['first_cycle'], captured['last_cycle']) == (plan['first_cycle'], plan['last_cycle']),
                'Converted capture identity/window mismatch')
        status('PREPARING_BASELINE_DDC_POWER')
        dc = Path(follow['dc_output'])
        baseline_plan(argparse.Namespace(output=dc, baseline_gate=Path(follow['baseline_gate']), conversion=conversion_path))
        require(read(dc / 'library-manifest.json')['library_sha256'] == follow['library_sha256'], 'Library set changed')
        unknowns = saif_unknown_fraction(Path(conversion['saif']))
        docker = Path(shutil.which('docker') or '/usr/bin/docker')
        inputs = dc / 'inputs'
        for name in ('dc_power.py', 'test_dc_power.py'):
            shutil.copyfile(out / 'inputs' / name, inputs / name)
        cpins = dict(follow['library_sha256'])
        cpins.update({str(p): sha(p) for p in (*DC_INIT_FILES, DC_SHELL, inputs / 'design.ddc',
                                             inputs / 'activity.saif', inputs / 'power.tcl')})
        (inputs / 'container-pins.sha256').write_text(''.join(h+'  '+p+'\n' for p,h in sorted(cpins.items())))
        command = [str(docker), 'exec', '-u', f'{os.getuid()}:{os.getgid()}', '-e', 'HOME=/home/wangwy',
            '-e', 'SNPSLMD_LICENSE_FILE=27000@t7920', '-w', str(dc), 'synopsys_workspace',
            '/usr/bin/timeout', '--signal=TERM', '--kill-after=20', str(follow['execute_seconds']),
            '/bin/bash', '-c', 'sha256sum -c "$1" || exit 1; exec "$2" '+ ' '.join(DC_FLAGS)+' -f "$3"',
            'power-dc', str(inputs / 'container-pins.sha256'), str(DC_SHELL), str(inputs / 'power.tcl')]
        save(dc / 'execution-plan.json', dict(command=command, proof_roles=roles, period_ns=1,
            library_sha256=follow['library_sha256'], runner=str(Path(__file__)),
            conversion=str(conversion_path), annotation_policy='Strict direct annotation; retain provisional values on failure'))
        epins = {str(p): sha(p) for p in inputs.iterdir() if p.is_file()}
        epins.update(cpins)
        epins.update({str(p): sha(p) for p in (docker, dc / 'execution-plan.json', capture, conversion_path)})
        save(dc / 'execution-pins.json', epins)
        verify(epins)
        save(dc / 'attempt.json', dict(pid=os.getpid(), started=time.time(), frozen_worker=str(Path(__file__))))
        status('DC_POWER_RUNNING')
        with (dc / 'console.log').open('x') as log:
            subprocess.run(command, cwd=dc, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=follow['execute_seconds']+60)
        measured = collect_power_reports(dc)
        verify(epins)
        verify(read(out / 'source-pins.json'))
        measured.update(state='PASS' if measured['annotation_gate'] == 'PASS' else 'FAIL',
            provisional=True, power_acceptance=False, proof_roles=roles, saif_unknowns=unknowns,
            period_ns=1, full_gate_smoke_verified=True, architectural_gls_signoff=False,
            report_pins={str(p): sha(p) for p in (dc / 'reports').iterdir() if p.is_file()})
        save(dc / 'result.json', measured)
        reference = collect_power_reports(qbs)
        reference['saif_unknowns'] = read(qbs / 'result.json')['saif_unknowns']
        result.update(state='RELATIVE_POWER_DATA_READY_NOT_SIGNOFF', baseline=measured, qbs=reference,
            baseline_result=str(dc / 'result.json'), qbs_original_result=str(qbs / 'result.json'),
            qbs_over_baseline={k: reference['power_watts'][k]/v for k,v in measured['power_watts'].items() if v > 0},
            identical_library_sha256=follow['library_sha256'], period_ns=1,
            limitations=['Baseline source is reconstructed; historical byte identity UNPROVEN',
                'QBS capture lacks matching full gate smoke; its original FAIL remains unchanged',
                'Strict annotation failures remain failures; values are provisional relative data only',
                'Windows differ in length and gate compute phase is not independently verified',
                'Average window power, not whole-task energy, timing closure, SDF or architectural GLS signoff',
                'Unknown SRAM/idle activity is reported, not assumed zero'])
    except Exception as error:
        result['error'] = repr(error)
    save(out / 'result.json', result)
    status(result['state'])
    return int(result['state'] == 'FAIL')


def prepare(args):
    started = time.monotonic()
    out = args.output.resolve()
    require(out.parent == OUT and out.name.startswith('power_dc_20261117_') and not out.exists(), 'Fresh owned output required')
    require(1 <= args.execute_seconds <= 3600, 'Execution budget must be 1..3600 seconds')
    require(sha(DC / 'manifest.json') == MANIFEST_SHA and sha(DC / 'status.json') == STATUS_SHA, 'DC evidence drift')
    manifest, status = read(DC / 'manifest.json'), read(DC / 'status.json')
    require(status['state'] == 'SYNTHESIS_COMPLETE' and status['output_sha256'][str(DC / DDC_REL)] == DDC_SHA,
            'Wrong mapped DDC evidence')
    libraries = dict(manifest['library_sha256'])
    evidence = {str(DC / 'manifest.json'): MANIFEST_SHA, str(DC / 'status.json'): STATUS_SHA}
    if args.baseline_manifest:
        baseline = args.baseline_manifest.resolve()
        libraries = shared_libraries(manifest, read(baseline))
        evidence[str(baseline)] = sha(baseline)
    verify(libraries)
    require(sha(DC / DDC_REL) == DDC_SHA, 'DDC drift')
    conversion_path = args.conversion.resolve()
    conversion, capture, conversion_pins = validate_conversion(conversion_path)
    chain_pins, roles = validate_capture_image(conversion, capture)
    conversion_pins.update(chain_pins)
    saif = Path(conversion['saif'])
    instance = conversion['instance']
    header = inspect_saif(saif, instance)
    activity_sha = conversion['saif_sha256']
    smoke_path = args.smoke.resolve() if args.smoke else None
    audit_path = args.numerical_deviation_audit.resolve() if args.numerical_deviation_audit else None
    require(not audit_path or smoke_path, 'Deviation audit requires its original smoke result')
    smoke_pins = validate_smoke(smoke_path, conversion, audit_path) if smoke_path else {}
    provisional = args.provisional_without_smoke
    require(not provisional or (not smoke_path and not audit_path and capture.get('schema') ==
            'independent-native-eof-capture-audit-v1'), 'Provisional mode is scoped to the audited EOF capture without smoke')
    unknowns = saif_unknown_fraction(saif)
    docker = Path(shutil.which('docker') or '/usr/bin/docker')
    tool_pins = {str(p): sha(p) for p in (docker, DC_SHELL, VCD2SAIF, VCS, *DC_INIT_FILES)}
    require(time.monotonic()-started < 120, 'Preparation identity phase exceeded 120-second budget')
    out.mkdir()
    inputs = out / 'inputs'
    inputs.mkdir()
    (out / 'reports').mkdir()
    for src, name in ((DC / DDC_REL, 'design.ddc'), (saif, 'activity.saif'),
                      (DC / 'manifest.json', 'dc-manifest.json'), (DC / 'status.json', 'dc-status.json'),
                      (Path(__file__), 'dc_power.py'), (Path(__file__).with_name('test_dc_power.py'), 'test_dc_power.py')):
        shutil.copyfile(src, inputs / name)
    require(sha(inputs / 'activity.saif') == activity_sha and sha(inputs / 'design.ddc') == DDC_SHA, 'Snapshot drift')
    (inputs / 'power.tcl').write_text(make_tcl(out, sorted(libraries), instance))
    save(inputs / 'conversion-result.json', conversion)
    save(inputs / 'capture-result.json', capture)
    if smoke_path:
        save(inputs / 'smoke-result.json', read(smoke_path))
    if audit_path:
        save(inputs / 'numerical-deviation-audit.json', read(audit_path))
    container_pins = dict(libraries)
    container_pins.update({str(p): sha(p) for p in DC_INIT_FILES})
    container_pins.update({str(p): sha(p) for p in (inputs / 'design.ddc', inputs / 'activity.saif',
                                                  inputs / 'power.tcl', DC_SHELL)})
    (inputs / 'container-pins.sha256').write_text(''.join(h + '  ' + p + '\n' for p, h in sorted(container_pins.items())))
    command = [str(docker), 'exec', '-u', f'{os.getuid()}:{os.getgid()}',
               '-e', 'HOME=/home/wangwy', '-e', 'SNPSLMD_LICENSE_FILE=27000@t7920',
               '-w', str(out), 'synopsys_workspace',
               '/usr/bin/timeout', '--signal=TERM', '--kill-after=20', str(args.execute_seconds),
               '/bin/bash', '-c',
               'sha256sum -c "$1" || exit 1; exec "$2" ' + ' '.join(DC_FLAGS) + ' -f "$3"',
               'power-dc', str(inputs / 'container-pins.sha256'), str(DC_SHELL), str(inputs / 'power.tcl')]
    tests = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(inputs),
                            '-p', 'test_dc_power.py', '-v'], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=30, text=True)
    (inputs / 'host-tests.log').write_text(tests.stdout)
    require(tests.returncode == 0, 'Frozen host tests failed; see inputs/host-tests.log')
    plan = dict(schema='power-dc-plan-v5', command=command, cwd=str(out),
                execute_seconds=args.execute_seconds, preparation_seconds=time.monotonic()-started,
                ddc_sha256=DDC_SHA, saif_sha256=activity_sha, saif_header=header,
                library_sha256=libraries, evidence_refs=evidence, tool_pins=tool_pins,
                smoke_frozen=bool(smoke_path), smoke_result=str(smoke_path) if smoke_path else None,
                numerical_deviation_audit=str(audit_path) if audit_path else None,
                provisional_without_smoke=provisional,
                power_eligibility=('PROVISIONAL_AUDITED_CAPTURE_WITHOUT_FULL_SMOKE' if provisional else
                                   'POWER_ELIGIBLE_WITH_NUMERICAL_DEVIATION' if audit_path else
                                   'NORMAL_CHECKED_PASS' if smoke_path else 'AWAITING_GATE_SMOKE'),
                proof_roles=roles, saif_unknowns=unknowns, saif_instance=instance, period_ns=1,
                conversion_result=str(conversion_path), conversion_sha256=sha(conversion_path),
                scope='Representative bounded-window average power at assumed 1ns; not architectural GLS or timing signoff',
                limitations=['RTL numeric/protocol applies to the admitted RTL ELF/image, not to gate internal traces',
                             'Gate smoke applies only to its matching ELF and gate image; no cross-ELF substitution',
                             'Capture completeness is not full-program GLS numerical acceptance',
                             'Unused SRAM/idle paths may be unknown; report the measured SAIF fraction',
                             'Only root clock knownness is mandatory; other critical controls may be unmeasured',
                             'No synthesis, SDF/timing closure, post-route or whole-program power claim'],
                annotation_policy='100% direct gate Nets/Ports/Pins; zero missing/default/propagated/conflicts',
                library_policy='Exact own DC manifest set; optional explicitly pinned baseline superset',
                vcd2saif_host_recipe=[str(VCD2SAIF), '-input', '/absolute/accepted-window.vcd',
                                      '-output', '/absolute/accepted-window.saif'],
                capture_gate_contract=__doc__, no_eda_launched=True)
    save(out / 'plan.json', plan)
    pins = {str(p): sha(p) for p in inputs.iterdir() if p.is_file()}
    pins.update(libraries)
    pins.update(evidence)
    pins.update(tool_pins)
    pins.update(smoke_pins)
    pins.update(conversion_pins)
    pins[str(out / 'plan.json')] = sha(out / 'plan.json')
    save(out / 'source-pins.json', pins)
    verify(pins)
    require(time.monotonic()-started < 180, 'Preparation exceeded 180-second budget; do not execute')
    state = 'PREPARED_PROVISIONAL_NOT_EXECUTED' if provisional else ('PREPARED_NOT_EXECUTED' if smoke_path else 'PREPARED_AWAITING_GATE_SMOKE')
    save(out / 'status.json', dict(state=state))
    print(json.dumps(dict(output=str(out), smoke_frozen=bool(smoke_path), no_eda_launched=True)))


def execute(out, authorized):
    require(authorized, '--authorize-dc is required')
    require(Path(__file__).resolve() == out / 'inputs/dc_power.py', 'Execute frozen worker only')
    require(not (out / 'attempt.json').exists(), 'No automatic retry')
    pins, plan = read(out / 'source-pins.json'), read(out / 'plan.json')
    verify(pins)
    require(plan['schema'] == 'power-dc-plan-v5' and
            (plan['smoke_frozen'] or plan['provisional_without_smoke']), 'No smoke/provisional authorization; reprepare fresh')
    conversion, capture, _ = validate_conversion(Path(plan['conversion_result']))
    validate_capture_image(conversion, capture)
    audit_path = Path(plan['numerical_deviation_audit']) if plan['numerical_deviation_audit'] else None
    if plan['provisional_without_smoke']:
        require(not plan['smoke_frozen'] and capture.get('schema') == 'independent-native-eof-capture-audit-v1',
                'Wrong provisional capture scope')
    else:
        validate_smoke(Path(plan['smoke_result']), conversion, audit_path)
    save(out / 'attempt.json', dict(pid=os.getpid(), started=time.time()))
    result = dict(state='FAIL', scope=plan['scope'], proof_roles=plan['proof_roles'],
                  power_eligibility=plan['power_eligibility'], numerical_deviation_audit=plan['numerical_deviation_audit'],
                  saif_unknowns=plan['saif_unknowns'], limitations=plan['limitations'],
                  architectural_gls_signoff=False, capture_full_program_gls_math_pass=False)
    result.update(provisional=plan['provisional_without_smoke'], full_gate_smoke_verified=plan['smoke_frozen'],
                  compute_phase_representativeness_verified=False, original_capture_fail_reclassified=False,
                  power_acceptance=False)
    try:
        # The planned container timeout owns dc_shell after exec; killing only
        # the docker client would not reliably terminate the container process.
        command = plan['command']
        with (out / 'console.log').open('x') as stream:
            subprocess.run(command, cwd=out, stdout=stream, stderr=subprocess.STDOUT,
                           timeout=plan['execute_seconds']+60, check=True)
        result.update(collect_power_reports(out))
        verify(pins)
        if result['annotation_gate'] == 'PASS':
            result['state'] = 'PROVISIONAL_POWER_REPORT_NOT_ACCEPTED' if plan['provisional_without_smoke'] else 'PASS'
        result['report_pins'] = {str(p): sha(p) for p in (out / 'reports').iterdir() if p.is_file()}
    except Exception as exc:
        result['error'] = repr(exc)
    save(out / 'result.json', result)
    (out / 'status.json').write_text(json.dumps(dict(state=result['state'])) + '\n')
    print(json.dumps(result))
    return int(result['state'] == 'FAIL')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'prepare-rvv-m1-port-pair', 'prepare-audited-m1', 'prepare-formal-follow', 'watch-formal-pair', 'prepare-activity-successor', 'follow-activity-successor', 'queue-activity', 'follow-activity', 'prepare-real-load-pair', 'execute-real-load', 'baseline-plan', 'queue-baseline', 'follow-baseline', 'audit-reports', 'check', 'execute'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--conversion', type=Path)
    parser.add_argument('--smoke', type=Path)
    parser.add_argument('--numerical-deviation-audit', type=Path)
    parser.add_argument('--provisional-without-smoke', action='store_true')
    parser.add_argument('--previous-run', type=Path)
    parser.add_argument('--baseline-manifest', type=Path)
    parser.add_argument('--baseline-gate', type=Path, default=OUT / 'power_gate_build_20261117_baseline_02')
    parser.add_argument('--capture-run', type=Path)
    parser.add_argument('--capture-audit', type=Path)
    parser.add_argument('--qbs-run', type=Path, default=OUT / 'power_dc_20261117_q8_native_provisional_05')
    parser.add_argument('--wait-seconds', type=int, default=21600)
    parser.add_argument('--execute-seconds', type=int, default=1800)
    parser.add_argument('--authorize-dc', action='store_true')
    args = parser.parse_args()
    if args.action == 'prepare-rvv-m1-port-pair':
        require(args.capture_audit is not None and args.previous_run is not None, '--capture-audit and --previous-run required')
        prepare_rvv_m1_port_pair(args)
    elif args.action == 'prepare-audited-m1':
        require(args.capture_audit is not None and args.previous_run is not None, '--capture-audit and --previous-run required')
        prepare_audited_m1(args)
    elif args.action == 'prepare-formal-follow':
        prepare_formal_follow(args)
    elif args.action == 'watch-formal-pair':
        return watch_formal_pair(args)
    elif args.action == 'prepare-activity-successor':
        require(args.previous_run is not None, '--previous-run required')
        prepare_activity_successor(args)
    elif args.action == 'follow-activity-successor':
        return follow_activity_successor(args)
    elif args.action == 'queue-activity':
        queue_activity(args)
    elif args.action == 'follow-activity':
        return follow_activity(args)
    elif args.action == 'prepare-real-load-pair':
        prepare_real_load_pair(args)
    elif args.action == 'execute-real-load':
        return execute_real_load(args)
    elif args.action == 'queue-baseline':
        require(args.capture_run is not None, '--capture-run required')
        queue_baseline(args)
    elif args.action == 'follow-baseline':
        return follow_baseline(args)
    elif args.action == 'audit-reports':
        require(args.previous_run is not None and not args.authorize_dc, 'Report audit is host-only and requires --previous-run')
        audit_reports(args)
    elif args.action == 'baseline-plan':
        require(not args.authorize_dc, 'baseline-plan is host-only')
        baseline_plan(args)
    elif args.action == 'prepare':
        require(args.conversion is not None and not args.authorize_dc, 'Preparation requires conversion receipt, not launch authorization')
        prepare(args)
    elif args.action == 'check':
        verify(read(args.output.resolve() / 'source-pins.json'))
        print('HOST_PIN_CHECK_PASS')
    else:
        return execute(args.output.resolve(), args.authorize_dc)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
