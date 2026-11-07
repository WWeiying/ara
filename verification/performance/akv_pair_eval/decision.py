#!/usr/bin/env python3
"""Recheck sealed receipts and distinguish functional PASS from promotion evidence."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location('pair_decision_owner', Path(__file__).with_name('run.py'))
owner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(owner)


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def effect(cycles):
    require(isinstance(cycles, list) and len(cycles) == 4 and
            all(type(x) is int and x > 0 for x in cycles), 'Four real full-call cycles required')
    generic, paired = (cycles[0]+cycles[3])/2, (cycles[1]+cycles[2])/2
    gain = generic-paired
    spread = max(abs(cycles[0]-cycles[3]), abs(cycles[1]-cycles[2]))
    return dict(cycles=cycles, generic_mean=generic, paired_mean=paired,
                speedup=generic/paired, cycle_reduction=1-paired/generic,
                largest_within_arm_spread=spread,
                improvement_exceeds_arm_spread=gain > spread,
                all_paired_samples_faster=max(cycles[1:3]) < min(cycles[0], cycles[3]))


def checked_receipt(directory, kind):
    directory = Path(directory).resolve(strict=True)
    result = json.loads((directory/'result.json').read_text())
    require(result['state'] == 'PASS' and result['kind'] == kind and
            result['post_pins_match'] is True and result['independent_protocol_checked'] is True and
            result['hardware_changed'] is False and result['whole_model'] is False,
            'No current independently checked functional PASS: '+kind)
    require(result['performance_measured'] is (kind != 'boundary'), 'Scope mismatch')
    pinfile = directory/'source-pins.json'
    require(sha(pinfile) == result['source_pins_sha256'], 'Pin inventory changed')
    pins = json.loads(pinfile.read_text())
    require(pins and result['artifacts'], 'Empty pin/artifact inventory')
    for inventory in (pins, result['artifacts']):
        for path, digest in inventory.items():
            require(sha(path) == digest, 'Sealed input/artifact changed: '+path)
    measured = result['measured']
    require(measured['state'] == 'PASS' and result['vector_command_work'], 'Missing work validation')
    soc, _ = owner.checked_soc(Path(result['soc_build']))
    software, _ = owner.checked_software(Path(result['build']))
    require(result['configuration'] == soc['configuration'] and
            result['image_sha256'] == sha(soc['simv']) and
            result['software_sha256'] == software['elf_sha256'], 'Image/software identity mismatch')
    _, checker = owner.load_checker(kind)
    work = directory/'work'
    # Recompute from raw records: the terminal report cannot authenticate itself.
    fresh = checker.check_run(work/'run.vcs.log', Path(result['build']))
    vector = checker.check_vector_workcounts(work/'vector_trace.csv', Path(result['build']))
    require(fresh == measured and vector == result['vector_command_work'],
            'Summary differs from independently recomputed numerical/cycle/work evidence')
    proof = json.loads((work/'uvm_result.json').read_text())
    require(proof['status'] == 'PASS' and proof['issues'] == [] and
            proof['elf_sha256'] == software['elf_sha256'] and
            proof['log_sha256'] == sha(work/'run.vcs.log') and
            proof['vector_trace_sha256'] == sha(work/'vector_trace.csv'),
            'Independent protocol proof identity mismatch')
    if kind != 'boundary':
        require(measured['order'] == [0, 1, 1, 0], 'Not the same-ELF ABBA order')
        counts = [1046, 237, 237, 1046] if kind == 'qwen3_abba' else [209, 92, 92, 209]
        require(measured['work']['per_call_commands'] == counts and
                result['vector_command_work']['per_call_commands'] == counts,
                'Actual command work does not match the evaluated path')
    return result


def decide(qwen3, smol, boundary):
    receipts = [checked_receipt(path, kind) for path, kind in
                ((qwen3, 'qwen3_abba'), (smol, 'regression'), (boundary, 'boundary'))]
    first = receipts[0]
    require(all(r['configuration'] == first['configuration'] and
                r['image_sha256'] == first['image_sha256'] for r in receipts), 'Different RTL images')
    primary, secondary = [effect(r['measured']['measured_total_cycles']) for r in receipts[:2]]
    eligible = (primary['cycle_reduction'] >= 0.05 and secondary['cycle_reduction'] > 0 and
                all(r['improvement_exceeds_arm_spread'] and r['all_paired_samples_faster']
                    for r in (primary, secondary)))
    return dict(state='EVIDENCE_RECHECKED', primary=primary, secondary=secondary,
                candidate_eligible_for_call_local_integration=eligible,
                production_default_changed=False, model_speedup_measured=False,
                evidence={str(Path(p).resolve()/'result.json'): sha(Path(p)/'result.json')
                          for p in (qwen3, smol, boundary)},
                next_step='Validate call-local SDK/GGML selection and fallback' if eligible else
                          'Keep current default; investigate the measured crossover without changing RTL')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('qwen3', 'smol', 'boundary'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(decide(args.qwen3, args.smol, args.boundary), indent=2))
