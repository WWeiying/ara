#!/usr/bin/env python3
"""Wide-window power successor; Q8 strict PASS admission is not Q4 deviation."""
import argparse
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('wide_frozen_dc', HERE / 'dc_power.py')
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)
original = dc.activity_inputs


def inputs(run, role, kind):
    if kind != 'q8':
        plan, binding, ddc, pins, roles = original(run, role, kind)
    else:
        root = run.parent.parent
        pins = dc.read(root / 'source-pins.json')
        dc.verify(pins)
        plan, binding = dc.read(run / 'plan.json'), dc.read(root / 'image-binding.json')
        gate = Path(plan['image'])
        gpins, images = dc.read(gate / 'source-pins.json'), dc.read(gate / 'image-pins.json')
        dc.verify(gpins)
        dc.verify(images)
        receipt = dc.read(gate / 'gate-receipt.json')
        dc.require(role == 'rvv' and plan['kind'] == 'q8' and receipt['memory']['bytes'] == 1048576 and
                   len(receipt['memory']['instances']) == 8, 'Actual Q8 RVV 1MiB image required')
        dc.require(binding['image_pins'] == images and binding['simv_sha256'] == images[str(gate / 'sim/simv')] and
                   binding['gate_source_pins_sha256'] == dc.sha(gate / 'source-pins.json') and
                   binding['gate_build_sha256'] == dc.sha(gate / 'build.json'), 'Q8 image binding drift')
        net, ddc = gate / 'source/ara_soc_dc.v', gate / 'inputs/ara_soc_dc.ddc'
        dc.require(dc.sha(net) == receipt['netlist_sha256'] and gpins[str(net)] == dc.sha(net) and
                   dc.sha(ddc) == receipt['ddc_sha256'], 'Mapped netlist/DDC correspondence failure')
        dc.require(dc.shared_libraries(dc.read(dc.DC / 'manifest.json'), receipt) == dc.read(dc.DC / 'manifest.json')['library_sha256'],
                   'Common pinned library set required')
        admission = dc.read(plan['rtl_admission'])
        dc.require(dc.sha(plan['rtl_admission']) == plan['rtl_admission_sha256'] and
                   admission['state'] == 'STRICT_RTL_PASS_REUSED_FOR_ACTIVITY', 'Q8 strict admission required')
        release = dc.read(admission['release'])
        dc.require(dc.sha(admission['release']) == admission['release_sha256'], 'Q8 release drift')
        dc.verify(release['evidence_pins'])
        result = dc.read(admission['original_result'])
        dc.require(dc.sha(admission['original_result']) == admission['original_result_sha256'] and
                   result['state'] == result['numeric']['state'] == 'PASS' and result['independent_protocol_checked'] is True,
                   'Do not convert an original Q8 failure to eligibility')
        benchmark = result['numeric']['benchmark']
        dc.require(all(benchmark[k] == v for k,v in dict(k='896', rows='256', inputs='1', outputs='256').items()), 'Q8 shape mismatch')
        dc.require(dc.sha(plan['elf']) == plan['elf_sha256'] == result['elf_sha256'] == admission['elf_sha256'], 'Exact Q8 ELF required')
        pins.update(gpins)
        pins.update(images)
        pins.update(release['evidence_pins'])
        for path in (net, ddc, root / 'image-binding.json', Path(plan['rtl_admission']), Path(admission['release'])):
            pins[str(path)] = dc.sha(path)
        roles = dict(rtl=dict(admission=plan['rtl_admission'], strict_original_state='PASS', independent_protocol_checked=True),
            ddc_sha256=dc.sha(ddc), gate_netlist_sha256=dc.sha(net), gate_simv_sha256=binding['simv_sha256'],
            elf_sha256=plan['elf_sha256'], memory_bytes=1048576, full_gate_smoke_verified=False,
            gate_protocol_proof_claimed=False, historical_baseline_identity='UNPROVEN')
    validation = Path(plan['image']) / 'environment-validation.json'
    evidence = dc.read(validation)
    dc.require(evidence['state'] == 'OPPOSITE_VRF_SEEDS_EXACT_REDUCTIONS_PASS' and evidence['seeds'] == [0, 1] and
               evidence['runtime_force'] is False and evidence['controls_initialized'] is False, 'Actual startup evidence required')
    dc.require(plan['last_cycle'] - plan['first_cycle'] >= 20000, 'Formal window must span >=20000 cycles')
    pins[str(validation)] = dc.sha(validation)
    roles.update(initialization='Reset-only 512 VRF data words; opposite seeds validated; no controls/runtime force',
                 phase_contract=plan['phase_contract'], paired_ratio_publishable=False)
    return plan, binding, ddc, pins, roles


def main():
    p = argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--authorize-dc', action='store_true')
    a = p.parse_args()
    dc.require(Path(__file__).resolve() == a.output.resolve() / 'inputs/gate_rvv_wide_power_v1.py', 'Frozen wide successor required')
    dc.activity_inputs = inputs
    return dc.follow_activity(a)


if __name__ == '__main__':
    raise SystemExit(main())
