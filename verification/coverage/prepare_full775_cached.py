"""Offline private prepare optimization; original FULL775 check/run stays authoritative."""
import argparse
import hashlib
import json
from pathlib import Path
from types import FunctionType

import report_native_full775 as original

HERE = Path(__file__).resolve()
TEST = HERE.with_name('test_prepare_full775_cached.py')
FROZEN = {
    Path(original.__file__).resolve(): 'fe3f313310e269097d6a996b7d2a216c8b6f7e8d8a55fddf2c8916b1083afbdf',
    original.TCL.resolve(): 'bc7746666b8b6a9964d78c0d4ac7894e12f6ef0946a70cb2924d538a47052e10',
    Path(original.__file__).with_name('test_report_native_full775.py').resolve():
        'da1f1bf3ba0329495c63a5a4081d2cb2f0f83cccc840b839c0b7b85d33f7b554',
}


class ExactOwnersCache:
    def __init__(self, parser):
        self.parser = parser
        self.values = {}
        self.calls = 0
        self.hits = 0
        self.failures = 0

    def __call__(self, text):
        original.need(type(text) is str, 'Cache requires exact complete text')
        self.calls += 1
        if text in self.values:
            self.hits += 1
            return set(self.values[text])
        try:
            result = self.parser(text)
            original.need(type(result) is set and all(
                type(item) is tuple and len(item) == 2 and
                all(type(value) is str for value in item) for item in result),
                'Unexpected original owners parser return')
            saved = frozenset(result)
        except Exception:
            self.failures += 1
            raise
        self.values[text] = saved
        return set(saved)

    def evidence(self):
        return dict(calls=self.calls, hits=self.hits, successful_parses=len(self.values),
                    failures=self.failures, key='complete Python str equality, not hash-only',
                    entries=[dict(text_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),
                                  utf8_bytes=len(text.encode('utf-8')), owners=len(value))
                             for text, value in self.values.items()])


class PinnedSave:
    def __init__(self, backend, pins, output):
        self.backend, self.pins, self.output = backend, pins, output
        self.saved = False

    def __getattr__(self, name):
        return getattr(self.backend, name)

    def save(self, path, data):
        original.need(path == self.output / 'config.json' and not self.saved,
                      'Only first config save may add successor provenance')
        self.backend.check(self.pins)
        bound = dict(data, pins=original.prior.merge(data['pins'], self.pins))
        self.backend.save(path, bound)
        self.saved = True


def clone_prepare(cache, lifecycle):
    namespace = dict(original.prepare.__globals__)
    namespace.update(owners=cache, life=lifecycle)
    return FunctionType(original.prepare.__code__, namespace,
                        original.prepare.__name__, original.prepare.__defaults__)


def prepare(output):
    original.life.check({str(path): sha for path, sha in FROZEN.items()})
    helper_pins = {str(path): original.life.digest(path) for path in (HERE, TEST)}
    cache = ExactOwnersCache(original.owners)
    lifecycle = PinnedSave(original.life, helper_pins, output)
    clone_prepare(cache, lifecycle)(output)
    original.need(lifecycle.saved, 'Original prepare did not save config')
    seal = original.life.digest(output / 'config.json')
    # Deliberately uncached and unmodified authoritative final check.
    checked = original.check(output, seal)
    original.need(checked['successor_entry'] == str(Path(original.__file__).resolve()),
                  'Original run/verify entry must remain unchanged')
    pins = original.prior.merge(helper_pins, {str(path): sha for path, sha in FROZEN.items()},
                               {str(output / 'config.json'): seal})
    original.life.check(pins)
    receipt = dict(schema='FULL775_EXACT_TEXT_CACHED_PREPARE_V1',
                   status='ORIGINAL_FULL775_CHECK_PASS_NO_EDA', output=str(output),
                   config_seal=seal, original_entry=checked['successor_entry'],
                   original_final_check=True, EDA_launched=False,
                   cache=cache.evidence(), pins=pins)
    target = output / 'cached-prepare-receipt.json'
    original.need(not target.exists(), 'Fresh cache receipt only')
    original.life.save(target, receipt)
    print(json.dumps(dict(status=receipt['status'], output=str(output), config_seal=seal,
                          receipt_seal=original.life.digest(target), cache=receipt['cache'])), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    prepare(args.output.resolve())
