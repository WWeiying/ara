"""Verify original, traced and single-trial zero-offset slidedown stalls."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from trace_masks import sha, TOOLS
from audit_slide import require

sys.path.insert(0, str(TOOLS))
from guest_watch import no_retirement

ORIGINAL = 'rvv_permute_restart_e16_m1_ops16'
TRIGGER = 'RVV_PERMUTE_BEGIN seed=0 op=16 scalar=0 vl=32 mask=0 vstart=16 cap=64'


def validate_stall(report, name, traced):
    result, = [r for r in report['results'] if r['name'] == name]
    require(result['status'] == 'stalled', 'No terminal stall evidence')
    diagnosis = report['progress_diagnosis']
    require(diagnosis['name'] == name and diagnosis['stalled'], 'Wrong stall attribution')
    samples = diagnosis['snapshots']
    require(no_retirement(samples), 'No live no-retirement evidence')
    require(samples[0]['live']['run_id'] == samples[1]['live']['run_id'], 'Snapshot run changed')
    if traced:
        require(result['output'].strip().splitlines()[-1] == TRIGGER, 'Wrong unreturned trigger')
    return samples


def inspect(report_path, binary, name, cross, traced, opcode='3c803c57'):
    raw = json.loads(report_path.read_text()); report = raw.get('report', raw)
    deployed, = [c for c in report['inputs']['cases'] if c['name'] == name]
    require(sha(binary) == deployed['sha256'], 'Deployed ELF identity differs')
    samples = validate_stall(report, name, traced)
    a, b = [s['core'] for s in samples]
    dis = subprocess.check_output([cross + 'objdump', '-d', str(binary)], text=True)
    instructions = {int(m[1], 16): (m[2], m[3].strip()) for m in
                    re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(.+)$', dis, re.M)}
    last, head = instructions.get(a['last_pc']), instructions.get(a['head_pc'])
    require(last is not None and last[0] == opcode, 'Different target opcode')
    require(head is not None and head[0] == '00802573', 'Different following vstart read')
    return dict(name=name, report_sha256=sha(report_path), elf_sha256=sha(binary),
                last_pc=hex(a['last_pc']), head_pc=hex(a['head_pc']),
                target_instruction=last, following_instruction=head,
                cycle_delta=b['cycles']-a['cycles'], retired=a['retired'],
                trigger=TRIGGER if traced else None)


def audit(original_report, original_elf, trace_root, trace_report, single_root, single_report, cross):
    rows = [inspect(original_report, original_elf, ORIGINAL, cross, False)]
    for root, report_path, name in (
        (trace_root, trace_report, 'rvv_trace_permute_restart_e16_m1_ops16'),
        (single_root, single_report, 'rvv_trace_permute_single_restart_e16_m1_ops16')):
        m = json.loads((root / 'manifest.json').read_text())
        require(m['original_report_sha256'] == sha(original_report), 'Original report lineage differs')
        case, = [c for c in m['cases'] if c['name'] == name]
        require(case['original_name'] == ORIGINAL and
                case['original_elf_sha256'] == sha(original_elf) ==
                sha(root / name / 'original_rebuilt.elf'), 'Original ELF lineage differs')
        for file, digest in case['scenario_sources'].items():
            require(sha(root / name / file) == digest, 'Scenario source changed')
        binary = root / 'overlay/opt/ara-tests' / name
        require(sha(binary) == case['sha256'], 'Candidate ELF changed')
        if root == single_root:
            require(m['trace_report_sha256'] == sha(trace_report), 'Measured trace changed')
            require(case['configurations'] == 1, 'Not a single original trial')
        rows.append(inspect(report_path, binary, name, cross, True))
    return dict(confirmed=True, cases=rows,
                scope='Same original opcode stall; traced and single runs retain the same measured trigger',
                original_uninstrumented_trigger_recorded=False,
                internal_rtl_root_cause_proven=False,
                caveat='PCs lack head-valid and internal queue state; they do not prove the blocked unit')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('original-report', 'original-elf', 'trace-root', 'trace-report',
                'single-root', 'single-report', 'out'):
        p.add_argument('--' + key, type=Path, required=True)
    p.add_argument('--cross', required=True)
    a = p.parse_args()
    result = audit(a.original_report, a.original_elf, a.trace_root, a.trace_report,
                   a.single_root, a.single_report, a.cross)
    a.out.mkdir(exist_ok=False)
    for role, path in (('original', a.original_report), ('trace', a.trace_report), ('single', a.single_report)):
        (a.out / (role + '_report.json')).write_bytes(path.read_bytes())
    (a.out / 'symptoms.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
