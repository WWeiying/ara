#!/usr/bin/env python3
"""One discriminating first-X capture, not a power measurement or repaired run."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('frozen_native_activity', HERE / 'gate_activity_v3.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
b = g.b


def diagnostic_check(out, plan, binding, run):
    result = g.final_check(out, plan, binding, run)
    result.update(state='DIAGNOSTIC_CAPTURE_COMPLETE_NOT_POWER',
        representative_power_window=False, power_acceptance=False,
        scope='First VRF X write through CPU/cache/control and gated-clock corruption; not a repaired image')
    return result


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('action', choices=('prepare', 'bind-image', 'execute'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--plan-sha256')
    parser.add_argument('--binding-sha256')
    parser.add_argument('--authorize-run', action='store_true')
    args = parser.parse_args()
    out = b.scoped_output(args.output)
    if args.action == 'execute':
        b.require(Path(__file__).resolve() == out / 'inputs/gate_activity_diag_v4.py', 'Frozen diagnostic worker required')
        plan = b.read(out / 'plan.json')
        b.require((plan['first_cycle'], plan['last_cycle'], plan['max_cycles']) ==
                  (12980, 13430, 13500), 'Exact diagnostic scope required')
        b.final_check = diagnostic_check
        return b.execute(out, args.plan_sha256, args.binding_sha256, args.authorize_run)
    b.require(not args.authorize_run, 'Authorization only for execute')
    if args.action == 'prepare':
        g.CASES['m1'] = (g.CASES['m1'][0], 12980, 13430, 13500,
            'DIAGNOSTIC ONLY: first VRF data X at 13027.5 ns, cache control X at 13417.5 ns, clock X at 13422.5 ns')
        args.case = 'm1'
        args.release = b.OUT / 'power_native_release_20261117_activity_03/m1-release.json'
        args.release_sha256 = b.sha(args.release)
        g.prepare(args, out)
        pins = b.read(out / 'source-pins.json')
        source, dest = Path(__file__).resolve(), out / 'inputs/gate_activity_diag_v4.py'
        b.shutil.copyfile(source, dest)
        pins[str(source)] = b.sha(source)
        pins[str(dest)] = b.sha(dest)
        prior = b.OUT / 'power_gls_20261117_native_m1_activity_01/result.json'
        pins[str(prior)] = b.sha(prior)
        b.save(out / 'source-pins.json', pins)
    else:
        b.bind_image(out)
        ready = b.read(out / 'ready-command.json')
        for key in ('worker', 'service'):
            ready[key] = [str(out / 'inputs/gate_activity_diag_v4.py')
                if v == str(out / 'inputs/gate_run.py') else v for v in ready[key]]
        ready['shell'] = b.shlex.join(ready['service'])
        b.save(out / 'ready-command.json', ready)
    print(json.dumps(dict(action=args.action, output=str(out), measurement=False, launched=False)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
