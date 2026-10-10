"""Minimal scoped process-identity successor; no unrelated cwd visibility gate."""
import inspect
import os
import re
from pathlib import Path
from types import FunctionType

import run_lzc_seven_foreground_recovery as prior

frozen, require = prior.frozen, prior.require
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_run_lzc_seven_foreground_recovery_v2.py')
PRIOR_SHA = 'bca6c7399851857038c510a7c31c5bc07ee0bdfa049dc52494bb010025931808'

for _name, _value in vars(prior).items():
    if isinstance(_value, FunctionType) and _value.__module__ == prior.__name__:
        globals()[_name] = FunctionType(_value.__code__, globals(), _name,
                                       _value.__defaults__, _value.__closure__)
    elif not _name.startswith('__') and _name not in ('SCRIPT', 'TEST'):
        globals().setdefault(_name, _value)


def potential_target(argv, comm):
    names = {'dve', 'dve.exe', 'simv', 'xvfb-run', 'Xvfb'}
    scripts = {str(original.SCRIPT), str(prior.SCRIPT), str(SCRIPT), str(original.generic.TCL)}
    return (comm in names or any(Path(arg).name in names or arg in scripts for arg in argv)
            or '_background-worker' in argv
            or any(re.search(r'(?:^|[\s/])(?:dve(?:\.exe)?|simv|xvfb-run|Xvfb)(?:\s|$)', arg)
                   for arg in argv))


def inspect_candidate(entry):
    try:
        if entry.stat().st_uid != os.getuid() or int(entry.name) == os.getpid():
            return False
        raw = (entry / 'cmdline').read_bytes()
        argv = [v.decode('utf-8', errors='replace') for v in raw.split(b'\0') if v]
        comm = (entry / 'comm').read_text().strip()
    except FileNotFoundError:
        return False
    except PermissionError:
        require(False, 'HOLD: cannot classify possible process identity: ' + entry.name)
    # Exact observed user-service PAM identity, not a blanket PermissionError bypass.
    if argv == ['(sd-pam)'] and comm == '(sd-pam)':
        return False
    if not argv:
        try:
            status = (entry / 'status').read_text()
        except FileNotFoundError:
            return False
        except PermissionError:
            require(False, 'HOLD: empty command state unreadable: ' + entry.name)
        if re.search(r'^State:\s+Z(?:\s|$)', status, re.M):
            return False
        require(False, 'HOLD: empty command cannot disprove an EDA candidate: ' + entry.name)
    if not potential_target(argv, comm):
        return False
    try:
        cwd = (entry / 'cwd').resolve(strict=True)
    except FileNotFoundError:
        return False
    except PermissionError:
        require(False, 'HOLD: possible target EDA/worker cwd unreadable: ' + entry.name)
    output_arg = str(OUTPUT) in argv or ('--output=' + str(OUTPUT)) in argv
    recovery_arg = str(SIDECAR) in argv and any(arg in (str(prior.SCRIPT), str(SCRIPT)) for arg in argv)
    return cwd == OUTPUT or output_arg or recovery_arg


def scoped_candidates(proc=Path('/proc')):
    return [int(p.name) for p in proc.iterdir() if p.name.isdigit() and inspect_candidate(p)]


def fast_guard():
    launch, runtime = prior.fast_guard()
    require(not scoped_candidates(), 'Live target EDA/worker identity: no recovery')
    return launch, runtime


def scoped_dependencies():
    return (Path(prior.__file__).resolve(), prior.TEST, SCRIPT, TEST)


def adapt(function, old, new):
    require(frozen.sha(Path(prior.__file__).resolve()) == PRIOR_SHA, 'Frozen recovery source differs')
    source = inspect.getsource(function)
    require(source.count(old) == 1, 'Exact dependency adapter boundary differs')
    exec(compile(source.replace(old, new, 1), str(SCRIPT), 'exec'), globals())
    return globals()[function.__name__]


# Retain the same fresh fixed sidecar and exclusive receipt, original seals/records,
# foreground invoke_run and every pre-EDA gate. Only add actual successor dependencies.
prepare = adapt(prior.prepare, "OUTPUT / 'population-runner.log')",
                "OUTPUT / 'population-runner.log', *scoped_dependencies())")
reviewed = adapt(prior.reviewed, "OUTPUT / 'population-runner.log'):",
                 "OUTPUT / 'population-runner.log', *scoped_dependencies()):")


if __name__ == '__main__':
    main()
