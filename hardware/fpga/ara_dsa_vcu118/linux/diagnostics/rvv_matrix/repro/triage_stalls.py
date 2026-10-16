"""Classify historical stalls without equating a candidate with proven causality."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def classify(name, instructions, output):
    text = ' '.join(i['asm'] for i in instructions)
    if 'vslide' in text or 'vfslide' in text:
        return 'slide_mask_stream', 'rtl_mechanism_confirmed_case_link_candidate'
    if 'vzext.' in text or 'vsext.' in text:
        return 'extension_overlap_dependency', 'static_candidate'
    if any(i['pc'] >= 0xffffffff80000000 for i in instructions):
        return 'kernel_vector_state_wait', 'boundary_only'
    if 'vmand.' in text or 'vmor.' in text or 'vmxor.' in text:
        return 'mask_logic_source_stream', 'static_candidate'
    if 'vlseg' in text or 'vlsseg' in text:
        return 'segment_request_completion', 'boundary_only'
    boundary = bool(re.search(r'vl=512\b[^\n]*vstart=256\b', output))
    if boundary and any(op in text for op in (
            'vsmul.', 'vmacc.', 'vfmerge.', 'vmerge.', 'vmfeq.', 'vmseq.',
            'vrgather.', 'vadd.', 'vxor.')):
        return 'packed_mask_restart_boundary', 'static_candidate'
    if 'vmerge.' in text or 'vfmerge.' in text:
        return 'packed_mask_restart_boundary', 'opcode_family_candidate_no_trial'
    if 'vrgather' in text:
        return 'gather_operand_stream', 'opcode_family_candidate_no_trial'
    if 'zero_stride' in name:
        return 'kernel_vector_state_wait', 'family_only'
    if 'extension_' in name:
        return 'extension_overlap_dependency', 'family_only'
    if 'segment_alignment_' in name:
        return 'segment_request_completion', 'family_only'
    return 'unresolved', 'insufficient_evidence'


def inspect(case, objdump):
    paths = list(reversed([a['report'] for a in case.get('retest_attempts', [])
                           if a.get('status') == 'stalled']))
    paths += case['evidence'].get('stalled', [])
    row = dict(name=case['name'], elf_sha256=case['sha256'],
               retest_status=case['retest_status'], report=None, instructions=[],
               elf_verified=False, snapshot_verified=False, last_trial=None)
    for filename in dict.fromkeys(paths):
        p = Path(filename)
        if not p.exists():
            continue
        report = json.loads(p.read_text())
        report = report.get('report', report)
        diagnosis = report.get('progress_diagnosis') or {}
        samples = diagnosis.get('snapshots', [])
        # Early observers omit diagnosis.name; accept only the unique terminal
        # stalled record, never an earlier accumulated result in that report.
        results_all = report.get('results', [])
        attributed = diagnosis.get('name')
        if attributed is None and results_all and results_all[-1].get('status') == 'stalled':
            attributed = results_all[-1]['name']
        if attributed != case['name'] or len(samples) < 2:
            continue
        results = [r for r in report.get('results', []) if r['name'] == case['name']]
        if len(results) != 1 or results[0]['status'] != 'stalled':
            continue
        a, b = samples[-2:]
        ac, bc = a['core'], b['core']
        row.update(report=filename, report_sha256=digest(p),
                   last_pc=bc['last_pc'], head_pc=bc['head_pc'],
                   cycle_delta=bc['cycles'] - ac['cycles'],
                   snapshot_verified=(bc['cycles'] > ac['cycles'] and
                       bc['retired'] == ac['retired'] and
                       a['live']['run_id'] == b['live']['run_id'] and
                       not a.get('watchdog_snapshot') and not b.get('watchdog_snapshot') and
                       a['live']['flags'] == b['live']['flags'] == 0),
                   ddr={k: {f: b[k][f] for f in
                       ('read_outstanding', 'write_outstanding', 'error_count')}
                        for k in ('ddr1', 'ddr2')})
        output = results[0].get('output', '')
        trials = [line for line in output.splitlines() if 'TRIAL ' in line or '_BEGIN ' in line]
        row['last_trial'] = trials[-1] if trials else None
        deployed = [c for c in report.get('inputs', {}).get('cases', [])
                    if c['name'] == case['name']]
        for release in case['releases']:
            root = Path(release).parent
            for binary in (root / 'binaries' / case['name'],
                           root / 'overlay/opt/ara-tests' / case['name']):
                if not binary.exists() or digest(binary) != case['sha256']:
                    continue
                row['elf_verified'] = len(deployed) == 1 and deployed[0]['sha256'] == case['sha256']
                row['binary'] = str(binary)
                # Kernel PCs cannot be decoded using the userspace test ELF.
                for pc in dict.fromkeys((bc['last_pc'], bc['head_pc'])):
                    if pc >= 0xffffffff80000000:
                        row['instructions'].append(dict(pc=pc, asm='kernel PC; see accepted Image annotation'))
                        continue
                    dis = subprocess.check_output([objdump, '-d', f'--start-address={pc}',
                                                   f'--stop-address={pc+4}', str(binary)], text=True)
                    match = re.search(r'^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(.+)$', dis, re.M)
                    if match and int(match[1], 16) == pc:
                        row['instructions'].append(dict(pc=pc, opcode=match[2], asm=match[3].strip()))
                break
            if row.get('binary'):
                break
        row['group'], row['confidence'] = classify(case['name'], row['instructions'], output)
        return row
    row['group'], row['confidence'] = 'unresolved', 'insufficient_evidence'
    return row


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ledger', type=Path, required=True)
    p.add_argument('--objdump', required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    ledger = json.loads(a.ledger.read_text())
    cases = [c for c in ledger['cases'] if 'stalled' in c['evidence'] or
             c['retest_status'] == 'no_retirement_stall_observed']
    rows = [inspect(c, a.objdump) for c in cases]
    result = dict(scope='All historical stalled original/partition records in supplied ledger',
                  ledger_sha256=digest(a.ledger), total=len(rows),
                  groups=dict(Counter(r['group'] for r in rows)),
                  confidence=dict(Counter(r['confidence'] for r in rows)),
                  all_internal_causes_proven=False, rtl_modified=False, cases=rows)
    a.out.mkdir(exist_ok=False)
    (a.out / 'triage.json').write_text(json.dumps(result, indent=2) + '\n')
    (a.out / 'ledger.json').write_bytes(a.ledger.read_bytes())
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}, indent=2))


if __name__ == '__main__':
    main()
