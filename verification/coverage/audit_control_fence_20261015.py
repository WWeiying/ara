#!/usr/bin/env python3
"""Replay pure FENCE/control oracles on existing current-image artifacts only.

No old frozen-image impersonation, runtime_proof wrapper, simulation, admission,
or modification of parent control scope results. Old pins bind ELF/oracle inputs
only; current parent evidence binds the actual logs, trace and VDB.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(ROOT / 'verification/tests'), str(ROOT / 'verification')]
import build_gap36_fence as builder
import fence_rvfi_audit as rvfi
import collect_fence_t_u_padding_post as padding
import gap37_csr_admission as gap37
import gap44_csr_oracle as gap44
import run_fence_checked_extension as fence

OUT = ROOT / 'verification/out'
REVIEW = OUT / 'full-regression-failure-review-20261015-01'
CACHE, PINS, STATS = {}, {}, {}
PROFILES = (616, 617, 618, 619, 620, 621, 622, 623, 624, 629, 638, 639, 641, 647, 648, 651, 727)
require = rvfi.require


def data(path, expected=None):
    path = Path(path).resolve(strict=True)
    if path not in CACHE:
        stat = path.stat()
        STATS[path] = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        CACHE[path] = path.read_bytes()
        PINS[str(path)] = hashlib.sha256(CACHE[path]).hexdigest()
    require(expected is None or PINS[str(path)] == expected, 'Input pin mismatch: ' + str(path))
    return CACHE[path]


def read(path, expected=None):
    return json.loads(data(path, expected))


def text(path, expected=None):
    return data(path, expected).decode('utf-8', errors='strict')


def xml(path, expected=None):
    blob = data(path, expected)
    return ET.fromstring(gzip.decompress(blob) if blob[:2] == b'\x1f\x8b' else blob)


def bound_current(index, run, parent):
    case = run / f'e{index:04d}'
    scope = read(parent / f'e{index:04d}.json')
    require(scope['status'] == 'PASS' and scope['index'] == index
            and scope['original_uvm_errors_retained'] is True, 'Parent scope proof absent')
    for path, digest in scope['pins'].items():
        data(path, digest)
    plan = read(case / 'plan.json')
    receipt = read(case / 'simulation-exit.json')
    require(receipt['executed'] is True and type(receipt['returncode']) is int
            and receipt['returncode'] == 0 and not receipt['timed_out'] and not receipt['cancelled'],
            'No successful actual simulator receipt')
    require(receipt['command'] == plan['command'] and receipt['cwd'] == plan['work'], 'Receipt command differs')
    data(case / 'input.elf', scope['elf_sha256'])
    require(plan['elf_sha256'] == scope['elf_sha256'], 'Current ELF identity differs')
    return case, scope, plan


def controller(case, scope, current):
    """Original six linebb anchors, mapped ONLY through the current design shape."""
    design = Path(current['design_vdb']) / 'snps/coverage/db'
    info_path = design / 'auxiliary/verilog.sourceinfo.xml'
    shape_path = design / 'shape/line.verilog.shape.xml'
    info = xml(info_path, current['design_files'][str(info_path)])
    shape = xml(shape_path, current['design_files'][str(shape_path)])
    manifest = read(Path(current['simv']).parent / 'vcs_source_manifest.json')
    sources = {r['path']: r['sha256'] for r in manifest['files']}
    source = text(fence.SOURCE, sources[str(fence.SOURCE)])
    ids = [n.get('id') for n in info.iter('fileinfo')
           if Path(n.get('name')).resolve() == fence.SOURCE.resolve()]
    require(len(ids) == 1, 'Current controller source ID ambiguous')
    metric_paths = [Path(p) for p in scope['vdb_files'] if Path(p).name == 'line.verilog.data.xml']
    require(len(metric_paths) == 1, 'Missing/ambiguous current line VDB')
    path = metric_paths[0]
    require(path.is_relative_to(case), 'Foreign current VDB')
    doc = xml(path, scope['vdb_files'][str(path)])
    instances = [n for n in doc.iter('instance_data') if n.get('name') == fence.INSTANCE]
    require(len(instances) == 1, 'Controller instance ambiguous')
    node = instances[0]
    bits, checksum = node.get('value'), node.get('chksum')
    require(bits and set(bits) <= {'0', '1'} and checksum, 'Unbound/nonbinary native bitmap')
    definitions = [n for n in shape.iter('linedef') if n.get('chksum') == checksum]
    require(len(definitions) == 1, 'Current line shape checksum ambiguous')
    row = dict(width=len(bits), checksum=checksum, bits=hex(int(bits, 2)))
    arms = fence.line_activity(definitions[0], row, ids[0], source)
    return dict(status='PASS', controller_arms=arms, current_line_bitmap=row,
                scope='Six original native controller linebb assignments hit on current compiled shape',
                old_baseline_reused=False, original_incremental_fsm_gain_reestablished=False,
                cyclequalified=False, continuous_counter_recurrence_verified=False)


def negative_checks(check, trace, metadata, blob, sites, successor=False):
    """Reject corrupted copies in memory; never write/repair/filter the real trace."""
    rows = trace.splitlines()
    names = rows[0].split(',')
    cols = {k: names.index(k) for k in names}
    capture_pc = int(sites[0]['resume_pc'], 16)
    position = next(i for i, line in enumerate(rows[1:], 1)
                    if int(line.split(',')[cols['pc']], 16) == capture_pc)
    tests = {}
    for label, field, value in (
        ('wrong_capture_store_data', 'mem_wdata', '0000000000000001'),
        ('wrong_resume_pc', 'pc', f'{capture_pc + 4:016x}'),
        ('duplicate_retirement_order', 'order', '0'),
    ):
        changed = rows.copy()
        cells = changed[position].split(',')
        cells[cols[field]] = value
        changed[position] = ','.join(cells)
        try:
            check('\n'.join(changed) + '\n')
        except ValueError as error:
            tests[label] = dict(rejected=True, reason=str(error))
        else:
            raise ValueError('Negative checker accepted: ' + label)
    if successor:
        changed = rows.copy()
        position = next(i for i, line in enumerate(rows[1:], 1) if line.split(',')[cols['trap']] == '1')
        cells = changed[position].split(',')
        cells[cols['trap']] = '0'
        changed[position] = ','.join(cells)
        try:
            check('\n'.join(changed) + '\n')
        except ValueError as error:
            tests['missing_precise_ecall'] = dict(rejected=True, reason=str(error))
        else:
            raise ValueError('Negative checker accepted missing ECALL')
    return tests


def audit_fence(index, run, parent, current):
    case, scope, plan = bound_current(index, run, parent)
    log, console = text(case / 'work/run.vcs.log'), text(case / 'console.log')
    trace, blob = text(case / 'work/commit_trace.csv'), data(case / 'input.elf')
    if index == 638:
        historical = read(OUT / 'gap37-control-current-20261004-01/plan.json')
        directory = OUT / 'gap36-fence-20261004-01'
        record_path, metadata_path = directory / 'precheck.json', directory / 'elf_metadata.json'
        record = read(record_path, historical['files'][str(record_path)])
        metadata = read(metadata_path, historical['files'][str(metadata_path)])[0]
        require(record['elf_sha256'] == scope['elf_sha256'], 'Original FENCE ELF differs')
        for helper in (Path(rvfi.__file__), Path(builder.__file__)):
            data(helper, historical['files'][str(helper)])
        static = builder.audit_elf(metadata, blob)
        require(static == record['elf_audit'], 'Static linked ELF proof differs')
        sites = static['sites']
        uart = [builder.validate_log(s) for s in (console, log)]
        check = lambda value: rvfi.audit(value, metadata, blob, sites)
        retirement = check(trace)
    else:
        data(Path(padding.__file__), '3cf24ee8d61e55178e2fa13d23d9048f078bab713cc89da620fee679bc8667e1')
        record = read(padding.PLAN, padding.PLAN_SHA)
        metadata_path = OUT / 'fence-t-u-padding-build-parent-727-20261006-01/elf_metadata.json'
        metadata = read(metadata_path, record['pins'][str(metadata_path)])[0]
        require(record['ELF_sha256'] == scope['elf_sha256'], 'Recovered 727 ELF differs')
        data(Path(padding.oracle.__file__), record['pins'][str(Path(padding.oracle.__file__))])
        sites = record['proof']['sites']
        # Only evaluate()/retirement_adapter(); never old collect()/execution_gate()
        # or a fabricated plan claiming that this is the old frozen simulator.
        check = lambda value: padding.evaluate(console, value, metadata, blob, sites)
        result = check(trace)
        other = padding.evaluate(log, trace, metadata, blob, sites)
        require(result == other, 'Console/VCS architectural oracle differs')
        uart, retirement = result['uart'], result['retirement']
    return dict(index=index, status='FOCUSED_ARCHITECTURAL_PASS_NOT_FULL_ORIGINAL_ADMISSION',
                exact_elf_sha256=scope['elf_sha256'], original_uvm_errors_retained=True,
                parent_control_scope=str(parent / f'e{index:04d}.json'),
                current_simulator=plan['command'][0], old_frozen_image_claimed=False,
                uart=uart, retirement=retirement,
                controller=controller(case, scope, current),
                negative_checks=negative_checks(check, trace, metadata, blob, sites, index == 727),
                unresolved_original_admission=['Incremental FSM/bitmap gain vs original baseline not re-established across changed images',
                    *(['Original relative727 protection/raw bitmap delta not re-established; no continuous native padding-counter trace'] if index == 727 else [])],
                security_proof=False, coverage_admitted=False)


def other_controls(run, parent):
    results = []
    for index in PROFILES:
        if index in (638, 727):
            continue
        case, scope, plan = bound_current(index, run, parent)
        command_source = Path(plan['command_source'])
        historical_root = command_source.parents[5]
        name = command_source.parents[3].name
        old = read(historical_root / 'outcomes' / (name + '.json'))
        gates = [p for p in old['files'] if Path(p).name.endswith('runtime_audit.json')]
        result = dict(index=index, original_runtime_reports=gates, parent_scope=str(parent / f'e{index:04d}.json'),
                      full_original_admission_replayed=False,
                      scope='Runtime gate inventory, not exhaustive historical static/Spike precheck replay')
        if index in (639, 641):
            checker = gap37.validate_runtime_log if index == 639 else lambda s: gap44.validate_log(s, spike=False)
            result.update(specialized_runtime_check=[checker(text(p)) for p in (case / 'console.log', case / 'work/run.vcs.log')],
                          status='ORIGINAL_EXTRA_UART_GATE_REPLAYED_PASS',
                          parent_omitted_extra='Unique complete gap37 UART contract' if index == 639 else 'Mandatory nonzero DUT HPM preservation guard/profile')
        else:
            require(not gates, 'Unexpected original extra runtime gate: ' + str(gates))
            result['status'] = 'NO_ADDITIONAL_RUNTIME_REPORT_FOUND_NOT_NEW_ADMISSION'
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=OUT / 'full-regression-20261015-01/extensions')
    parser.add_argument('--parent', type=Path, default=REVIEW / 'control-scope-final')
    parser.add_argument('--output', type=Path, default=REVIEW / 'fence')
    args = parser.parse_args()
    expected_outputs = {'summary.json', 'other-controls.json', 'e0638.json', 'e0727.json', 'input-pins.json', 'README.md'}
    require(not args.output.exists() or {p.name for p in args.output.iterdir()} == expected_outputs,
            'Output is not empty or owned by this audit')
    for module in (rvfi, builder, padding, padding.oracle, gap37, gap44, fence):
        data(Path(module.__file__))
    data(Path(__file__))
    current = read(args.run.parent / 'full-regression-core-20261015-01/plan.json')
    freeze = read(args.run.parent / 'freeze.json')
    require(current['image'] == freeze['image'], 'Current image binding differs')
    fences = []
    for index in (638, 727):
        try:
            fences.append(audit_fence(index, args.run, args.parent, current))
        except (OSError, ValueError, KeyError, TypeError) as error:
            fences.append(dict(index=index, status='FAIL_OR_MISSING_EVIDENCE', reason=str(error)))
    others = other_controls(args.run, args.parent)
    # Detect evidence changing during the audit without rehashing logs/images.
    # All bytes used by the pure oracles were hashed exactly once by data().
    for path, original in STATS.items():
        stat = path.stat()
        require(original == (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns),
                'Input changed during audit: ' + str(path))
    summary = dict(fences=fences, other_controls=others, tests_rerun=0,
                   parent_helper_modified=False, old_frozen_image_claimed=False,
                   counts=dict(Counter(r['status'] for r in fences)),
                   full_original_coverage_admissions=0,
                   scope='Supplemental architecture/original runtime gate audit; retains UVM errors; not full ISA/security/coverage admission')
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in [('summary', summary), ('other-controls', others),
                        *[(f'e{r["index"]:04d}', r) for r in fences], ('input-pins', PINS)]:
        (args.output / (name + '.json')).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    report = ['# FENCE Supplemental Audit', '',
              'Uses existing current-image traces, exact ELF and original pure checkers. No old-image impersonation.', '']
    for result in fences:
        report.append(f"- e{result['index']:04d}: {result['status']}")
        if 'retirement' in result:
            r = result['retirement']
            report.append(f"  Captures: {r['capture_stores_checked']}; rounds: {len(r['rounds'])}; exact PC+4 resume: {r['exact_pc4_resume']}.")
        if 'reason' in result:
            report.append('  ' + result['reason'])
    report += ['', 'e0639: original specialized UART gate replayed. e0641: original mandatory nonzero HPM guard replayed.',
               'Other 13: no additional historical runtime_audit report found; not a claim of exhaustive original admission.',
               'Unclosed: original incremental FSM/bitmap gain and relative727 protection delta on changed images.',
               'No continuous padding counter recurrence or exact-cycle proof. Six current controller linebb arms are checked separately.',
               'Original UVM diagnostics remain unchanged. Full original coverage admissions: 0.']
    (args.output / 'README.md').write_text('\n'.join(report) + '\n')
    print(json.dumps(dict(counts=summary['counts'], other_control_count=len(others), output=str(args.output))))
    return int(any(r['status'] == 'FAIL_OR_MISSING_EVIDENCE' for r in fences))


if __name__ == '__main__':
    raise SystemExit(main())
