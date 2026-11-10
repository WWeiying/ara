#!/usr/bin/env python3
"""Serialization-only successor; preserve the sealed runner and smoke bundle."""
import importlib.util
import json
from pathlib import Path
import signal
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('attention_v2_sealed_runner', HERE/'run.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
SUCCESSOR = ('run_v2.py', 'test_run_v2.py')
r.OWN = (*r.OWN, *SUCCESSOR)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        r.b.require(key not in result, 'Duplicate JSON key: '+key)
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('Non-finite JSON value: '+value)


def strict_json(text):
    value = json.loads(text, object_pairs_hook=unique_object,
                       parse_constant=reject_constant)
    json.dumps(value, allow_nan=False)  # Also reject exponent overflow to infinity.
    return value


def canonical(value):
    # Round-trip first: integer lane keys become strings, with collision checks.
    return strict_json(json.dumps(value, allow_nan=False))


def compare_evidence(report, evidence):
    normalized = canonical(evidence)
    for key, value in normalized.items():
        r.b.require(key in report and
            json.dumps(report[key], sort_keys=True, allow_nan=False) ==
            json.dumps(value, sort_keys=True, allow_nan=False),
            'Smoke acceptance replay mismatch: '+key)
    return normalized


def admitted_smoke(path, socdir):
    path = r.output_path(path)
    original = path/'inputs/run.py'
    r.b.require(r.b.sha(original) == r.b.sha(HERE/'run.py'),
                'Different sealed smoke reader')
    # Separate globals retain the original OWN inventory and __file__ identity.
    # Every image/source/artifact/recipe/owner/protocol check still runs unchanged.
    reader = r.load(original, 'attention_v2_immutable_smoke_reader')
    reader.b.read = lambda file: strict_json(Path(file).read_text())
    replay = reader.numerical_and_work

    def evidence_view(out, software):
        return compare_evidence(reader.b.read(out/'result.json'), replay(out, software))

    reader.numerical_and_work = evidence_view
    return reader.admitted_smoke(path, socdir)


r.admitted_smoke = admitted_smoke
sealed_service_command = r.service_command
sealed_run = r.run


def service_command(out, review):
    command = sealed_service_command(out, review)
    original = str(out/'inputs/run.py')
    r.b.require(command.count(original) == 1, 'Frozen worker recipe changed')
    command[command.index(original)] = str(out/'inputs/run_v2.py')
    return command


def run(out, review):
    r.b.require(Path(__file__).resolve() == Path(out)/'inputs/run_v2.py',
                'Execute frozen successor entrypoint')
    # The function's module is the actual frozen inputs/run.py, not a copied
    # function with a forged __file__. Its original identity check remains live.
    return sealed_run(out, review)


r.service_command = service_command
r.run = run


if __name__ == '__main__':
    def interrupted(sig, _frame):
        raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    raise SystemExit(r.main())
