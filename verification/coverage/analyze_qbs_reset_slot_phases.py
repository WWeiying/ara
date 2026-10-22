"""Read existing qualified waves to select productive reset phases; no simulator."""
import argparse
import json
from pathlib import Path
from types import FunctionType
import audit_gap115_axi_v2 as reader
import run_qbs_affine_external_reset as run

life, require = run.life, run.require
REL = run.SCOPE[len('ara_tb.'):]
WIDTHS = {'clk': 1, 'rst_n': 1, REL + '.entry_valid_q': 16,
          **{REL + '.entry_state_q[%d]' % i: 3 for i in range(16)}}


def summarize(iterator):
    marker, declarations = next(iterator)
    require(marker == 'declarations', 'Missing declaration preamble')
    ids = {name: declarations['ara_tb.' + name]['code'] for name in WIDTHS}
    best = {str(stage): dict(active_slots=[], time=None) for stage in range(6)}
    resets, recovery = [], False
    for time, before, after in iterator:
        if before.get(ids['rst_n']) == '1' and after.get(ids['rst_n']) == '0':
            require(not resets, 'Unexpected repeated external reset')
            valid = before.get(ids[REL + '.entry_valid_q'], '')
            require(len(valid) == 16 and set(valid) <= set('01'), 'Unknown pre-reset valid bitmap')
            resets.append(dict(time=time, valid=valid, states=[
                before.get(ids[REL + '.entry_state_q[%d]' % i], 'x') for i in range(16)]))
        if resets and before.get(ids['rst_n']) == '0' and after.get(ids['rst_n']) == '1':
            recovery = True
        if not recovery or after.get(ids['rst_n']) != '1':
            continue
        if not (before.get(ids['clk']) == '0' and after.get(ids['clk']) == '1'):
            continue
        valid = before.get(ids[REL + '.entry_valid_q'], '')
        require(len(valid) == 16 and set(valid) <= set('01'), 'Unknown active valid bitmap')
        groups = {str(stage): [] for stage in range(6)}
        for slot in range(16):
            if valid[-1 - slot] == '0':
                continue
            bits = before.get(ids[REL + '.entry_state_q[%d]' % slot], '')
            require(len(bits) == 3 and set(bits) <= set('01') and int(bits, 2) < 6,
                    'Unknown active entry state')
            groups[str(int(bits, 2))].append(slot)
        for stage, slots in groups.items():
            if len(slots) > len(best[stage]['active_slots']):
                best[stage] = dict(active_slots=slots, time=time, valid=valid)
    require(recovery and len(resets) == 1, 'Incomplete reset/recovery observation')
    return dict(reset=resets[0], maximal_recovery_stage_groups=best,
                interpretation='Observed recovery opportunities only, not a new PASS or coverage increment.')


def collect(output):
    require(output.parent == life.OUT and not output.exists(), 'Fresh output only')
    roots = [life.OUT / name for name in (
        'qbs-affine-aux-qualified-746-agent-20261007-03',
        'qbs-affine-scale-qualified-agent-20261007-01',
        'qbs-affine-min-scale-qualified-agent-20261007-01')]
    pins, cases = {}, []
    for root in roots:
        qualification = root / 'qualification.json'
        qualified = json.loads(qualification.read_bytes())
        require(qualified['status'] == 'QBS_AFFINE_EXACT_RESET_REUSE_TWO_EPOCH_NATIVE_PASS_NOT_ADMITTED'
                and qualified['reset_stage_and_slot_reuse_wave_verified'], 'Unqualified input')
        wave = root / 'external-reset.vcd'
        require(life.digest(wave) == qualified['output_pins'][str(wave)], 'Waveform drift')
        local = FunctionType(reader.vcd.__code__, dict(reader.vcd.__globals__, ROOT='ara_tb', WIDTHS=WIDTHS))
        cases.append(dict(stage=qualified['stage'], wave=str(wave), **summarize(iter(local(wave)))))
        pins.update({str(p): life.digest(p) for p in (wave, qualification)})
    for path in (Path(__file__).resolve(), Path(reader.__file__).resolve(),
                 Path(run.__file__).resolve(), Path(__file__).with_name('test_analyze_qbs_reset_slot_phases.py')):
        pins[str(path)] = life.digest(path)
    life.check(pins)
    life.save(output, dict(status='QUALIFIED_WAVE_SLOT_PHASE_OPPORTUNITY_ANALYSIS_ONLY',
        cases=cases, pins=pins, simulation_started=False, coverage_admitted=False))
    for case in cases:
        print(case['stage'], {k: v['active_slots'] for k,v in case['maximal_recovery_stage_groups'].items()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    collect(parser.parse_args().output.resolve())
