"""Independent offline source-closure replay; never changes an admission or simulates."""
import argparse
import sys
from pathlib import Path
from types import FunctionType, SimpleNamespace

import qualify_qbs_affine_external_reset as q


def source_pins():
    pins = {}
    root = q.life.ROOT / 'verification'
    for module in tuple(sys.modules.values()):
        file = getattr(module, '__file__', None)
        if not file:
            continue
        path = Path(file).resolve()
        if path.suffix == '.py' and root in path.parents:
            pins[str(path)] = q.life.digest(path)
    for name in ('qualify_gap105_native.py', 'qualify_gap105_native_v5.py', 'rv64_compressed_memory.py'):
        q.require(str(Path(__file__).with_name(name)) in pins, 'Missing actual native/RVC source dependency')
    q.require(str(Path(__file__).resolve()) in pins, 'Source closure lost this checker')
    return pins


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    dependencies = source_pins()
    old = q.life

    def check(pins):
        return old.check(old.merge_pins(pins, dependencies))

    def save(path, value):
        if path.name == 'evidence-pins.json':
            value = old.merge_pins(value, dependencies)
        old.save(path, value)

    life = SimpleNamespace(**dict(vars(old), check=check, save=save))
    namespace = dict(q.collect.__globals__, life=life)
    source = old.OUT / 'qbs-affine-aux-external-reset-old-image-745-agent-20261007-01'
    FunctionType(q.collect.__code__, namespace)('aux', source,
        '5171d639d29aab47f33b3aa2b823e62b4098315ccea668a8206f21e03b1fc4ad', out)
    check(dependencies)
    result = old.read_bound(out/'qualification.json', old.digest(out/'qualification.json'))
    admitted = old.OUT / 'qbs-affine-aux-offline-admitted-747-agent-20261007-01/admission-manifest.json'
    original = old.OUT / 'qbs-affine-aux-qualified-746-agent-20261007-03/qualification.json'
    first = old.read_bound(original, '22f3b7f7f359c3955f536fdd119d160c12338deab88b3fe51296f92d6989277d')
    for key in ('status', 'raw_delta', 'targets', 'recovery_full_vrf_bytes', 'CSR_values', 'native_active_bytes'):
        q.require(result[key] == first[key], 'Independent source-complete native replay differs')
    old.save(out/'source-closure-review.json', dict(status='QBS_AUX_NATIVE_SOURCE_CLOSED_REPLAY_PASS_NOT_NEW_ADMISSION',
        admission_manifest=str(admitted), admission_sha256=old.digest(admitted),
        original_qualification_sha256=old.digest(original), independent_qualification_sha256=old.digest(out/'qualification.json'),
        dependency_pins=dependencies, exact_native_result_equal=True, simulations_started=False,
        original_admission_preserved=True, no_retroactive_capture_identity_claim=True))
    print('SOURCE_CLOSED_REPLAY_PASS ' + old.digest(out/'source-closure-review.json'), flush=True)


if __name__ == '__main__': main()
