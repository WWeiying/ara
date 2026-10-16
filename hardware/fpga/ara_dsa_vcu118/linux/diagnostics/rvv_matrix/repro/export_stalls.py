"""Export three-run stall evidence only after repeating its specific audit."""
import argparse
import json
from pathlib import Path
import shutil
from audit_slide import require
from audit_fp_move_stall import audit as audit_move
from audit_permute_stall import audit as audit_permute
from trace_masks import sha


def export(kind, trace_root, single_root, proof_dir, cross, out):
    require(kind in ('fp_move', 'permute'), 'Unsupported stall audit')
    original = proof_dir / 'original_report.json'
    traced = proof_dir / 'trace_report.json'
    single = proof_dir / 'single_report.json'
    sm = json.loads((single_root / 'manifest.json').read_text()); sc, = sm['cases']
    original_elf = single_root / sc['name'] / 'original_rebuilt.elf'
    if kind == 'fp_move':
        proof = audit_move(original, trace_root, traced, single_root, single, cross)
    else:
        proof = audit_permute(original, original_elf, trace_root, traced, single_root, single, cross)
    # Disassembly entries are tuples in memory and arrays in persisted JSON.
    require(json.loads(json.dumps(proof)) == json.loads((proof_dir / 'symptoms.json').read_text()),
            'Stored audit changed')
    require(proof['confirmed'] is True, 'No confirmed stall')
    out.mkdir(exist_ok=False)
    for file in ('original_report.json', 'trace_report.json', 'single_report.json', 'symptoms.json'):
        shutil.copy2(proof_dir / file, out / file)
    shutil.copy2(original_elf, out / 'original.elf')
    for role, root in (('trace', trace_root), ('single', single_root)):
        target = out / role; target.mkdir()
        m = json.loads((root / 'manifest.json').read_text()); c, = m['cases']
        shutil.copy2(root / 'manifest.json', target / 'manifest.json')
        shutil.copy2(root / 'overlay/opt/ara-tests' / c['name'], target / 'scenario.elf')
        for file in c['scenario_sources']:
            require(Path(file).name == file and file not in ('.', '..'), 'Unsafe source filename')
            shutil.copy2(root / c['name'] / file, target / file)
        disassembly = root / c['name'] / 'scenario.dis'
        if disassembly.exists():
            shutil.copy2(disassembly, target / 'scenario.dis')
    index = dict(kind=kind, original_name=sc['original_name'], single_name=sc['name'],
                 measured_trigger=proof['cases'][-1]['trigger'],
                 measured_vlen=1024, complete_historical_coverage=False,
                 original_uninstrumented_trigger_recorded=False, internal_rtl_root_cause_proven=False)
    (out / 'index.json').write_text(json.dumps(index, indent=2) + '\n')
    (out / 'README.txt').write_text(
        'Board-confirmed original/trace/single external stall\n\n'
        'single/ contains one selected target call plus its original setup, data and oracle.\n'
        'trace/ contains the instrumented full sequence. original.elf is byte-identical to the deployed original.\n'
        'Use VLEN1024 and the SEW/LMUL/VL/vstart/mask recorded in index.json and source.\n'
        'Do not omit register initialization, mask setup, CSR setup or the following vstart read.\n'
        'These are Linux userspace ELFs, not standalone bare-metal VCS executables.\n'
        'Port the target call AND setup into your existing RVV harness; retain the archived oracle.\n'
        'QEMU passing does not establish RTL behavior. Reproduce the stall in simulation before RTL edits.\n'
        'Capture a bounded waveform around issue/completion, queue handshakes, mask/operand consumption,\n'
        'and restart counters. Board PCs lack head-valid/internal queue state and do not prove root cause.\n'
        'The original uninstrumented exact trigger is unknown; trace and single triggers match.\n'
        'This is an incremental handoff, not completion of all historical failures.\n')
    hashes = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out / 'hashes.json').write_text(json.dumps(hashes, indent=2) + '\n')
    return index


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kind', choices=('fp_move', 'permute'), required=True)
    for key in ('trace-root', 'single-root', 'proof-dir', 'out'):
        p.add_argument('--' + key, type=Path, required=True)
    p.add_argument('--cross', required=True)
    a = p.parse_args()
    print(json.dumps(export(a.kind, a.trace_root, a.single_root, a.proof_dir, a.cross, a.out)))


if __name__ == '__main__':
    main()
