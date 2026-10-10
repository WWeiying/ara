"""Read-only JSON-array successor; preserve the frozen proof and failed verifier."""
import argparse
import json
from pathlib import Path
import re

import prepare_qbs_payload_side1792_732 as frozen


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def compare(artifact, expected):
    # Tuples serialize as JSON arrays; boolean/integer and all values stay distinct.
    frozen.require(canonical(artifact) == canonical(expected), 'Current canonical JSON proof/plan differs')


def verify(path, seal):
    frozen.require(path.parent.parent == frozen.OUT and path.resolve() == path and not path.is_symlink(),
                   'Aliased/non-out proof path')
    frozen.require(re.fullmatch(r'[a-f0-9]{64}', seal or '') and frozen.digest(path) == seal,
                   'External proof seal differs')
    artifact = json.loads(path.read_bytes())
    compare(artifact, frozen.evidence())
    print('VERIFY_PASS_CANONICAL_JSON_NATIVE_HOLD_NOT_APPLIED')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal', required=True)
    args = parser.parse_args()
    verify(args.output.absolute()/'proof-native-plan.json', args.seal)
