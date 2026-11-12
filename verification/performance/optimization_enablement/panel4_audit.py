#!/usr/bin/env python3
"""Read-only final identity/numerical/performance audit after the bounded VCS service."""
import argparse
import json
from pathlib import Path
import re
import shutil
import sys

from panel4_prepare import OUT, sha, save, require
from panel4_run import read, verify, image_inventory


def main():
    p = argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); run = a.run.resolve(strict=True); out = a.output.absolute()
    require(out == out.resolve() and out.parent == OUT and re.fullmatch(
        r'enablement_panel4_[A-Za-z0-9_-]+', out.name) and not out.exists(), 'Fresh PANEL4 audit output required')
    require(run.parent == OUT and (run/'result.json').is_file(), 'Terminal run required')
    terminal, plan = read(run/'result.json'), read(run/'plan.json')
    require(terminal['state'] == 'PANEL4_CURRENT_IMAGE_TWO_VERSION_PASS', 'Not a passing two-version run')
    pins = read(run/'source-pins.json')
    require(terminal['source_pins_sha256'] == sha(run/'source-pins.json'), 'Run closure receipt drift')
    verify(pins)
    require(image_inventory(Path(plan['simv'])) == plan['image_pins'], 'Current image membership drift')
    out.mkdir(); inputs = out/'inputs'; inputs.mkdir()
    for name in ('panel4_audit.py', 'panel4_prepare.py', 'panel4_run.py'):
        src = Path(__file__).resolve().parent/name; dst = inputs/name
        shutil.copyfile(src, dst); pins[str(src)] = sha(src); pins[str(dst)] = sha(dst)
    sys.path.insert(0, str(run/'inputs'))
    import panel4_check
    require(Path(panel4_check.__file__).resolve() == run/'inputs/panel4_check.py' and
        Path(panel4_check.old.__file__).resolve() == run/'inputs/run_qk_panel4_abba.py', 'Unfrozen evidence parser')
    rows = []
    for program in plan['programs']:
        work = run/program['name']; checked = read(work/'result.json')
        require(checked['state'] == 'PASS' and checked['post_pins_match'] and checked['post_image_match'], 'Incomplete case')
        verify(checked['io'])
        proof = read(work/'protocol.json')
        require(sha(work/'protocol.json') == checked['protocol_sha256'] and proof['status'] == 'PASS' and
            proof['issues'] == [] and proof['elf_sha256'] == program['elf_sha256'] and
            proof['simv_sha256'] == sha(plan['simv']) and
            proof['log_sha256'] == sha(work/'run.vcs.log') and
            proof['vector_trace_sha256'] == sha(work/'vector.csv') and
            all(proof['contract_counts'][k] == 0 for k in ('exceptions', 'protocol_errors', 'outstanding')), 'Protocol drift/failure')
        check = panel4_check.old.check_log if program['name'] == 'historical_explicit' else panel4_check.check_log
        numeric = check((work/'run.vcs.log').read_text())
        require(numeric == checked['numerical'] == read(work/'numerical.json'), 'Raw numerical recheck mismatch')
        rows.append(dict(name=program['name'], elf_sha256=program['elf_sha256'],
            cycle_reduction_percent=numeric['cycle_reduction_percent'],
            trial_cycles=[t['cycles'] for t in numeric['trials']], numerical=True, protocol=True))
        for name in ('result.json', 'protocol.json', 'numerical.json', 'run.vcs.log', 'vector.csv', 'commit.csv'):
            pins[str(work/name)] = sha(work/name)
    require(rows[0]['elf_sha256'] != rows[1]['elf_sha256'], 'Different SDK versions must stay distinct')
    positive = rows[1]['cycle_reduction_percent'] > 0
    for name in ('result.json', 'plan.json', 'source-pins.json', 'attempt.json'):
        pins[str(run/name)] = sha(run/name)
    verify(pins); save(out/'source-pins.json', pins)
    result = dict(state='PANEL4_DEFAULT_ENABLEMENT_AUDIT_PASS' if positive else 'PANEL4_CORRECT_BUT_NO_CURRENT_POSITIVE_GAIN',
        rows=rows, current_auto_positive=positive, minimum_five_percent_required=False,
        native_source_sha256=plan['current_native_source_sha256'], sdk_revision=plan['source_revision'],
        default_selection='unset auto F16 D128 GQA6 KV>=128 and all original PANEL4 capabilities',
        explicit0_and_invalid_env_disable=True, generic_unset_remains_off=True, badcap_fallback_checked=True,
        post_pins_match=True, source_pins_sha256=sha(out/'source-pins.json'),
        scope=plan['performance_scope'], arbitrary_length_or_rounding_benefit_claim=False,
        whole_model_claim=False, fpga_acceptance=False, old_reports_unchanged=True)
    save(out/'result.json', result)
    print(json.dumps(result, sort_keys=True))
    return int(not positive)


if __name__ == '__main__': raise SystemExit(main())
