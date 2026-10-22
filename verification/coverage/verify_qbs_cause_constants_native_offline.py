"""Read-only replay of completed QBS native capture; percent syntax adapter only."""
import argparse
import csv
import json
from pathlib import Path
import re
from types import FunctionType

import qbs_cause_constants_native as original

OUT = original.life.OUT / 'qbs-cause9-constant13-native-agent-20261007-01'
SEAL = 'e7de3cba0d0c0612f9dcb9704c94b38b1aefe7350bd941e02e4f5cf5394d3632'
DEST = original.life.OUT / 'qbs-cause9-constant13-native-offline-qualified-agent-20261007-01'
HERE = Path(__file__).resolve().parent


def metrics(out, c, stage):
    with (out / ('rooted_' + stage + '.csv')).open(newline='') as stream:
        reader = csv.DictReader(stream)
        original.require(reader.fieldnames == ['Stage', 'Scope', 'Token', 'Handle', 'GUIPath', 'Name',
            'Score', 'Line', 'Toggle', 'FSM', 'Condition', 'Branch'], 'Exact rooted metric schema')
        rows = list(reader)
    original.require(len(rows) == 3, 'Exactly three actual rooted rows')
    found = {}
    for row in rows:
        scope = row['Scope']
        original.require(scope in {i['scope'] for i in c['instances']} and scope not in found
            and row['Stage'] == stage and row['Token'] == scope and row['Handle'].isdigit()
            and row['GUIPath'] == row['Name'] == scope.split('.')[-1], 'Rooted identity differs')
        found[scope] = {m: row[m] for m in ('Score', 'Line', 'Toggle', 'FSM', 'Condition', 'Branch')}
        for metric, value in found[scope].items():
            if value == 'NA':
                original.require(metric == 'FSM', 'Unexpected unavailable metric'); continue
            # Actual native rooted ratio presentation; no arbitrary suffix stripping.
            original.require(re.fullmatch(r'(?:0|[1-9]\d{0,2})\.\d{2}%', value) is not None
                             and 0 <= float(value[:-1]) <= 100, 'Strict native percent encoding/range')
    return found


def collect():
    original.require(not (OUT / 'capture-result.json').exists(), 'Original HOLD must remain unchanged')
    hold = json.loads((OUT / 'qualification-reject.json').read_bytes())
    original.require(hold == dict(status='REJECTED_NOT_QUALIFIED',
        reason="could not convert string to float: '17.94%'", config_seal=SEAL,
        captures_preserved=True, automatic_retry=False), 'Not the exact percent-only HOLD')
    result = {}

    class ResultSink:
        def __getattr__(self, name): return getattr(original.life, name)

        def save(self, path, value):
            original.require(path == OUT / 'capture-result.json' and not result, 'Only independent result sink')
            result.update(value)

        def digest(self, path):
            if path == OUT / 'capture-result.json': return 'INDEPENDENT_OFFLINE_RESULT_NOT_WRITTEN_TO_ORIGINAL'
            return original.life.digest(path)

    # Retain every original source/compiled/pin, actual-binding, five-stage inventory,
    # terminal, global EL, retained-bit, reset/reload and non-Toggle metric check.
    FunctionType(original.verify.__code__, dict(vars(original), metrics=metrics, life=ResultSink()))(OUT, SEAL)
    result.update(status='QBS_CAUSE9_CONSTANT13_PARTIAL743_NATIVE_OFFLINE_QUALIFIED_NOT_POPULATION_APPLIED',
        original_hold_preserved=str(OUT / 'qualification-reject.json'),
        original_native_output=str(OUT), original_harness_qualification_failed=True,
        adapter='Only accepts actual DVE fixed-two-decimal percent format; original comparisons preserve exact strings.',
        verifier_entry=str(Path(__file__).resolve()), no_simulation_or_EDA_repeat=True,
        no_measured_percent_gain_claim=True)
    for path in (Path(__file__).resolve(), HERE / 'test_verify_qbs_cause_constants_native_offline.py'):
        result['pins'][str(path)] = original.life.digest(path)
    return result


def verify(destination):
    original.require(destination.parent == original.life.OUT, 'Workspace independent output only')
    result = collect(); path = destination / 'capture-result.json'
    original.life.check(result['pins'])
    if path.exists():
        original.require(json.loads(path.read_bytes()) == result, 'Offline seal replay differs')
    else:
        original.require(not destination.exists(), 'Fresh independent qualification output required')
        destination.mkdir(); original.life.save(path, result)
    print(json.dumps(dict(status=result['status'], result=str(path), sha256=original.life.digest(path),
        actual_objects=622, actual_EL_members=1486, protected_bits=216)), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEST)
    args = parser.parse_args(); verify(args.output.absolute())
