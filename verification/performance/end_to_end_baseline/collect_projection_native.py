#!/usr/bin/env python3
"""Re-audit actual SDK A/B runs and retain diagnostic, nonadditive counters."""
import argparse
import json
from pathlib import Path

from audit import digest, require, verify_pins
from check_projection_native import check, fields

PHASES = ('setup', 'activation', 'weight', 'compute', 'overlap', 'drain',
          'scheduler', 'commit', 'fault', 'terminal')
COUNTERS = ('busy_cycles', 'ar', 'r_beats', 'payload_bytes', 'weight_bytes',
            'activation_bytes', 'useful_pairs', 'pair_capacity', 'dot_active_cycles',
            'fp_uop_issue', 'accumulator_updates', 'weight_prefetch_wait_cycles',
            'probe_read_response_idle_cycles', 'probe_read_ar_ready_blocked_cycles',
            'probe_fp_input_blocked_cycles', 'probe_profile_result_blocked_cycles')


def activity(text, measured):
    rows = [fields(line, '[QBS_PERF]') for line in text.splitlines() if line.startswith('[QBS_PERF] ')]
    require(len(rows) == 24 and len(measured['parts']) == 6, 'Incomplete activity')
    result = []
    for index, part in enumerate(measured['parts']):
        commands = rows[index*4:index*4+4]
        for command in commands:
            require(all(k in command for k in COUNTERS), 'Missing diagnostic field')
            require(sum(command.get('phase_'+phase+'_cycles', -1000000) for phase in PHASES) ==
                    command['busy_cycles'], 'Phase accounting differs from busy')
            require(command['dot_active_cycles'] <= command['busy_cycles'], 'Invalid issue/busy domain')
        summed = {k:sum(c[k] for c in commands) for k in COUNTERS}
        require(summed['busy_cycles'] <= part['execution'], 'Busy longer than blocking SDK execution')
        result.append(dict(trial=part['trial'], part=part['part'], profile=part['profile'],
                           counters=summed, phases={k:sum(c['phase_'+k+'_cycles'] for c in commands) for k in PHASES}))
    return result


def paired(base, wide):
    require([r['wide'] for r in (base, wide)] == [0, 1], 'Pair direction')
    require(base['elf_sha256'] == wide['elf_sha256'] and base['build'] == wide['build'], 'Different workloads')
    a, b = base['measured'], wide['measured']
    require(a['useful_pairs'] == b['useful_pairs'] == 6291456 and a['qbs_commands'] == b['qbs_commands'] == 24,
            'Different amount of useful work')
    require(a['dot_issue_count'] == 2*b['dot_issue_count'], 'Wide issue effect absent')
    parts = []
    for part in range(3):
        aa = [row for row in a['parts'] if row['part'] == part]
        bb = [row for row in b['parts'] if row['part'] == part]
        require([row['trial'] for row in aa] == [row['trial'] for row in bb] == [0, 1], 'Trial pairing')
        require([(r['checksum'], r['fcsr'], r['vcsr']) for r in aa] ==
                [(r['checksum'], r['fcsr'], r['vcsr']) for r in bb], 'Numerical/CSR mismatch')
        x, y = sum(r['execution'] for r in aa), sum(r['execution'] for r in bb)
        require(x > 0 and y > 0, 'Empty timing interval')
        parts.append(dict(part=part, profile=aa[0]['profile'], baseline_execution=x,
                          candidate_execution=y, execution_ratio=x/y))
    for key in ('region_cycles', 'execution_cycles', 'preparation_cycles'):
        require(a[key] > 0 and b[key] > 0, 'Invalid timing denominator')
    return dict(parts=parts, region_ratio=a['region_cycles']/b['region_cycles'],
                execution_ratio=a['execution_cycles']/b['execution_cycles'],
                preparation_ratio=a['preparation_cycles']/b['preparation_cycles'])


def collect(run, expected_wide):
    # Importing these frozen helpers performs no simulation or compilation.
    from collect_matrix_soc import audit_build
    from run_output_native import s, accepted
    run = run.resolve(strict=True); result = json.loads((run/'result.json').read_text())
    require(result['state'] == 'PASS' and result['performance_measured'] and result['independent_protocol_checked'] and
            result['post_pins_match'] and result['wide'] == expected_wide, 'Unaccepted run')
    require(digest(run/'source-pins.json') == result['source_pins_sha256'], 'Pin-map drift')
    pins = json.loads((run/'source-pins.json').read_text()); checked = verify_pins(pins)
    build = Path(result['build']); receipt = json.loads((build/'build.json').read_text())
    require(pins.get(str(build/'build.json')) == digest(build/'build.json') and
            receipt['elf_sha256'] == result['elf_sha256'] and
            digest(receipt['elf']) == result['elf_sha256'], 'Program identity mismatch')
    status = json.loads((run/'status.json').read_text())
    simv = Path(status['simv']); soc = audit_build(simv.parent.parent)
    require(soc['wide'] == expected_wide and soc['image_pins'] == result['image_pins'] and
            s.hashes(s.image_files(simv)) == result['image_pins'], 'Actual image differs')
    golden = [(build/(name+'_expected.bin')).read_bytes() for name in ('attn_q', 'attn_k', 'attn_v')]
    for name in ('attn_q', 'attn_k', 'attn_v'):
        path = build/(name+'_expected.bin')
        require(pins.get(str(path)) == digest(path), 'Independent golden not pinned')
    work = run/'work'; text = (work/'run.vcs.log').read_text()
    measured = check(text, expected_wide, golden)
    require(measured == result['measured'], 'Raw replay differs from worker')
    accepted.protocol(work, result['elf_sha256'], result['image_pins'])
    counters = activity(text, measured)
    verify_pins(pins)
    return dict(wide=expected_wide, run=str(run), build=str(build), elf_sha256=result['elf_sha256'],
                measured=measured, activity=counters, checked_inputs=checked,
                result_sha256=digest(run/'result.json'), log_sha256=digest(work/'run.vcs.log'),
                protocol_sha256=digest(work/'uvm_result.json'), source_pins_sha256=result['source_pins_sha256'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--wide', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); out = args.output.absolute()
    require(out == out.resolve(), 'Nonaliased output required'); out.mkdir(parents=True, exist_ok=False)
    result = dict(state='CHECKING', model_performance_measured=False, area_measured=False)
    try:
        reports = [collect(args.base, 0), collect(args.wide, 1)]
        comparison = paired(*reports)
        result.update(state='REAL_QWEN3_SDK_RTL_PAIR_REAUDITED', reports=reports, comparison=comparison,
                      collector_sha256=digest(__file__), whole_model=False,
                      limitations=['Cropped output channels, full K and real first-layer prompt inputs',
                          'SDK preparation/execution included; full GGML dispatch and cold weight repack excluded',
                          'QBS phases partition busy; other wait counters overlap and must not be added',
                          'QBS reader traffic is not full SoC or physical DDR traffic',
                          'No synthesis, frequency, area or FPGA acceptance'])
    except BaseException as exc: result.update(state='FAIL', error=repr(exc)); raise
    finally: (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__': main()
