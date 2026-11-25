#!/usr/bin/env python3
"""Q8 restart successor: recognize frozen one-shot v3 workers, share launch locks."""
import argparse
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
BASE = OUT / 'power_gls_20261117_q8_smoke_02/inputs/gate_run.py'
BASE_SHA = 'e05b5a5b23a5ca3ade67aebd10843029b5e1012745210fb1d87678ae43f37f5d'
spec = importlib.util.spec_from_file_location('sealed_q8_base', HERE / 'gate_run.py' if (HERE / 'program.elf').exists() else BASE)
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
b.require(b.sha(b.__file__) == BASE_SHA, 'Sealed runner identity drift')
V3 = '9bb3e37d9590261ab854cbdf934bbfec0c4bdb6ea56bc7e14ef43eb0bf3bd5ec'
old_reserved = b.reserved_slots
old_lock = b.slot_lock
SHARED = OUT / '.power-vcs-slots-20261117.lock'


def reserved_slots(rows, own_child=None):
    filtered = dict(rows)
    try:
        for pid, (ppid, argv) in rows.items():
            if 'execute' in argv and any(Path(a).name.startswith('precheck') and
                    Path(a).suffix == '.py' and Path(a).name not in
                    {*b.KNOWN_DISPATCHERS, 'precheck_power_v3.py'} for a in argv):
                return b.MAX_SLOTS
            workers = [Path(a) for a in argv if Path(a).name == 'precheck_power_v3.py']
            if not workers or 'execute' not in argv:
                continue
            b.require(len(workers) == 1 and argv.count('--output') == 1, 'Ambiguous v3 worker')
            worker = workers[0]
            output = Path(argv[argv.index('--output') + 1])
            b.require(output.parent == OUT and worker == output / 'inputs/precheck_power_v3.py', 'Unknown v3 output')
            pins = b.read(output / 'source-pins.json')
            for name, digest in dict(b.KNOWN_DISPATCHERS, precheck_power_v3_py=V3).items():
                name = 'precheck_power_v3.py' if name == 'precheck_power_v3_py' else name
                path = output / 'inputs' / name
                b.require(pins.get(str(path)) == digest == b.sha(path), 'v3 helper identity drift')
            plan_path = output / 'plan.json'
            b.require(pins.get(str(plan_path)) == b.sha(plan_path), 'v3 unpinned plan')
            plan = b.read(plan_path)
            b.require(len(plan['cases']) == 1 and plan['parallel'] == 1 and
                      plan['max_global_simv'] == 4 and plan['slot_lock'] == str(SHARED) and
                      b.read(output / 'attempt.json')['pid'] == pid, 'v3 dispatch contract drift')
            case = plan['cases'][0]
            children = [(child, args) for child, (parent, args) in rows.items()
                        if parent == pid and Path(args[0]).name == 'simv']
            b.require(len(children) <= 1, 'v3 multiple simulators')
            for child, args in children:
                b.require(args[0] == str(Path(plan['image']) / 'sim/simv') and
                          args.count('+PRELOAD=' + case['elf']) == 1 and
                          args.count('+TESTCASE=' + case['id']) == 1, 'v3 live image/ELF disagreement')
            # One-shot v3 has no subsequent dispatch. Waiting launches share SHARED;
            # keep live simv rows so the base counts each as an external simulator.
            del filtered[pid]
        return old_reserved(filtered, own_child)
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return b.MAX_SLOTS


@contextmanager
def slot_lock():
    with old_lock():
        with SHARED.open('a') as stream:
            b.fcntl.flock(stream, b.fcntl.LOCK_EX)
            try:
                yield
            finally:
                b.fcntl.flock(stream, b.fcntl.LOCK_UN)


b.reserved_slots = reserved_slots
b.slot_lock = slot_lock


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('action', choices=('prepare-q8', 'bind-image', 'check', 'execute'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--plan-sha256')
    parser.add_argument('--binding-sha256')
    parser.add_argument('--authorize-run', action='store_true')
    args = parser.parse_args()
    out = b.scoped_output(args.output)
    if args.action == 'execute':
        return b.execute(out, args.plan_sha256, args.binding_sha256, args.authorize_run)
    b.require(not args.authorize_run, 'Authorization only for execute')
    if args.action == 'prepare-q8':
        config = argparse.Namespace(output=out, image=b.GATE, release=b.GATE / 'initial-release.json',
            release_sha256=b.INITIAL_SHA, case=b.Q8, mode='capture', first_cycle=19638,
            last_cycle=23190, max_cycles=25000, wall_seconds=7200, slot_seconds=7200,
            max_vcd_bytes=4*1024**3)
        b.prepare(config)
        pins = b.read(out / 'source-pins.json')
        for name in ('gate_native_v2.py', 'test_gate_native_v2.py'):
            source, dest = HERE / name, out / 'inputs' / name
            b.shutil.copyfile(source, dest)
            pins[str(source)] = b.sha(source)
            pins[str(dest)] = b.sha(dest)
        b.save(out / 'source-pins.json', pins)
    elif args.action == 'bind-image':
        b.bind_image(out)
        ready = b.read(out / 'ready-command.json')
        ready['service'] = [str(out / 'inputs/gate_native_v2.py') if a == str(out / 'inputs/gate_run.py') else a
                            for a in ready['service']]
        ready['shell'] = b.shlex.join(ready['service'])
        b.save(out / 'ready-command.json', ready)
    else:
        b.check_binding(out, args.plan_sha256, args.binding_sha256)
    print(json.dumps(dict(action=args.action, output=str(out), state='HOST_READY_NOT_LAUNCHED')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
