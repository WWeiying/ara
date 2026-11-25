#!/usr/bin/env python3
"""Same strict DC activity gates, plus explicit RVV startup evidence and metadata."""
import argparse
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('frozen_short_dc', HERE / 'dc_power.py')
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)
original_inputs = dc.activity_inputs


def checked_inputs(run, role, kind):
    plan, binding, ddc, pins, roles = original_inputs(run, role, kind)
    dc.require(role == 'rvv', 'RVV-only startup successor')
    path = Path(plan['image']) / 'environment-validation.json'
    evidence = dc.read(path)
    dc.require(evidence['state'] == 'OPPOSITE_VRF_SEEDS_EXACT_REDUCTIONS_PASS' and
               evidence['seeds'] == [0, 1] and evidence['runtime_force'] is False and
               evidence['controls_initialized'] is False, 'Actual opposite-seed startup evidence required')
    pins[str(path)] = dc.sha(path)
    roles.update(initialization='Reset-only 512 VRF data words, opposite seeds match original RTL reductions; no control or runtime force',
                 startup_validation=dict(path=str(path), sha256=dc.sha(path)))
    return plan, binding, ddc, pins, roles


def main():
    p = argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--authorize-dc', action='store_true')
    a = p.parse_args()
    out = a.output.resolve()
    dc.require(Path(__file__).resolve() == out / 'inputs/gate_rvv_short_power_v1.py', 'Frozen metadata successor required')
    # Retain every original image, activity, conversion and DC gate; add startup proof.
    dc.activity_inputs = checked_inputs
    return dc.follow_activity(a)


if __name__ == '__main__':
    raise SystemExit(main())
