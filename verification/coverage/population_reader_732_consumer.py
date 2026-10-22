"""Isolated formal732 population consumer, no EDA or native-policy approval.

Literal ledger keys are obligations, never silently normalized away. A bounded
explicit link catalog and the exact LLVM dot-dot spelling bind those keys to
canonical endpoint captures. Full source/native qualification remains mandatory
for a report; this population phase alone is NOT_REPORT_READY.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
from types import MappingProxyType

import population_reader_732 as root_api
from population_reader_epoch import PopulationReaderEpoch, require
import verification_epoch as core

LLVM = '/home/wangwy/openproject/ara/install/riscv-llvm'
LINKS = {
    LLVM + '/bin/clang': 'clang-22', LLVM + '/bin/ld.lld': 'lld',
    LLVM + '/bin/llvm-readelf': 'llvm-readobj',
    '/lib64': 'usr/lib64', '/lib64/libgcc_s.so.1': 'libgcc_s-11-20240719.so.1',
    '/usr/bin/python3': 'python3.9', '/usr/bin/cc': 'gcc',
}
DESIGN = str(root_api.ROOT / 'verification/out/repaired-aligned-build-20260930-01/sim/simv.vdb')


def path_binding(literal, links, dotdot_prefix=None):
    require(isinstance(literal, str) and os.path.isabs(literal), 'Absolute literal pin required')
    if literal != os.path.normpath(literal):
        prefixes = (dotdot_prefix,) if dotdot_prefix else (
            LLVM + '/bin/../riscv64-unknown-elf/include/',
            str(root_api.ROOT / 'apps/qbs_gap109_k2_sticky') + '/../common/',
            '/usr/lib/gcc/x86_64-redhat-linux/11/../../../../lib64/',
        )
        matches = [p for p in prefixes if literal.startswith(p)]
        require(len(matches) == 1, 'Unreviewed lexical path: ' + literal)
        prefix = matches[0]
        suffix = literal[len(prefix):]
        require(bool(suffix) and literal.count('/../') == prefix.count('/../') and
                suffix == os.path.normpath(suffix) and '/./' not in literal and
                not literal.endswith('/'), 'Unreviewed lexical suffix')
        if dotdot_prefix is None and prefix.endswith('/../common/'):
            require(suffix == 'qbs_abi.h', 'Unknown APP lexical source')
        if dotdot_prefix is None and prefix.startswith('/usr/lib/gcc/'):
            require(suffix in ('crt1.o', 'crti.o', 'crtn.o', 'libc.so'), 'Unknown GCC lexical input')
    prefix = Path('/')
    components = []
    for part in literal.split('/')[1:]:
        require(part not in ('', '.'), 'Invalid path component')
        if part == '..':
            before = prefix.lstat()
            require(stat.S_ISDIR(before.st_mode) and not prefix.is_symlink(),
                    'Dot-dot crosses nonordinary directory')
        prefix = prefix / part
        info = prefix.lstat()
        target = None
        if stat.S_ISLNK(info.st_mode):
            require(str(prefix) in links, 'Unreviewed symbolic-link component: ' + str(prefix))
            target = os.readlink(prefix)
            require(target == links[str(prefix)], 'Literal symbolic-link target changed')
        # Directory timestamps may change without changing path identity. They
        # are not content-cache authority; files retain full endpoint guards.
        components.append((str(prefix), info.st_dev, info.st_ino, info.st_mode, target))
    endpoint = Path(literal).resolve(strict=True)
    require(endpoint.is_file() and not endpoint.is_symlink(), 'Nonregular canonical endpoint')
    return str(endpoint), tuple(components)


class Context:
    """Real pin/JSON consumer context for one population-preflight phase."""

    def __init__(self, pins, json_paths, *, links=None, dotdot_prefix=None):
        self.pins = MappingProxyType(dict(pins))
        self.links = dict(LINKS if links is None else links)
        self.prefix = dotdot_prefix
        self.bindings, canonical = {}, {}
        for literal, expected in self.pins.items():
            core._sha(expected)
            binding = path_binding(literal, self.links, self.prefix)
            endpoint = binding[0]
            require(canonical.get(endpoint, expected) == expected, 'Conflicting endpoint SHA authorities')
            canonical[endpoint] = expected
            self.bindings[literal] = binding
        require(set(json_paths) <= set(self.pins), 'JSON path lacks literal pin')
        self.reader = PopulationReaderEpoch(canonical,
            json_paths=[self.bindings[name][0] for name in json_paths])
        self.visited = set()
        self.failed = False

    def _bind(self, path, expected=None):
        require(not self.failed, 'Literal context failed')
        literal = os.fspath(path)
        require(literal in self.pins and expected in (None, self.pins.get(literal)),
                'Unknown/conflicting literal pin')
        actual = path_binding(literal, self.links, self.prefix)
        require(actual == self.bindings[literal], 'Literal path identity changed')
        return literal, Path(actual[0])

    def digest(self, path):
        try:
            literal, endpoint = self._bind(path)
            result = self.reader.sha(endpoint)
            self._bind(path)
            self.visited.add(literal)
            return result
        except Exception:
            self.failed = True
            raise

    sha = digest

    def load_sealed(self, path, expected):
        try:
            literal, endpoint = self._bind(path, expected)
            result = self.reader.load_sealed(endpoint, expected)
            self._bind(path, expected)
            self.visited.add(literal)
            return result
        except Exception:
            self.failed = True
            raise

    def pin(self, destination, path, expected=None):
        try:
            literal, _ = self._bind(path, expected)
            require(destination.get(literal, self.pins[literal]) == self.pins[literal],
                    'Destination literal pin conflict')
            destination[literal] = self.digest(path)
            return Path(literal)
        except Exception:
            self.failed = True
            raise

    def finish(self):
        try:
            require(not self.failed and self.visited == set(self.pins), 'Unvisited literal pin obligations')
            for literal in self.pins:
                self._bind(literal)
            return self.reader.finish()
        except Exception:
            self.failed = True
            raise

    def namespace(self):
        return dict(sha=self.digest, pin=self.pin, load_sealed=self.load_sealed)


def verify_membership(bitmap, previous, input_sha, previous_input_sha, design=DESIGN):
    tests, older = bitmap['tests'], previous['tests']
    require(len(tests) == len(set(tests)) == 732 and len(older) == len(set(older)) == 731,
            'Exact unique732/731 membership required')
    require(tuple(tests[:731]) == tuple(older) and bitmap['design'] == previous['design'],
            'Exact predecessor prefix/design required')
    for names, expected in ((tests, input_sha), (older, previous_input_sha)):
        require(all(isinstance(name, str) and name == os.path.normpath(name) and
                    os.path.isabs(name) and not any(c in name for c in '\n\r\t') for name in names),
                'Unsafe/aliased textual member')
        data = ('\n'.join((design, *names)) + '\n').encode()
        require(hashlib.sha256(data).hexdigest() == expected, 'Exact ordered input-text SHA differs')


def consume():
    root = root_api.bind_root(root_api.ADMISSION, root_api.SEAL)
    # Preserve literal keys here; merge_pins deliberately refuses dot-dot paths.
    pins = dict(root.ledger)
    for name, expected in root.pins.items():
        require(pins.get(name, expected) == expected, 'Root/ledger authority conflict')
        pins[name] = expected
    baseline = Path(root.manifest['baseline'])
    selected_json = [str(root.admission / n) for n in
                     ('admission-manifest.json', 'combined-bits.json', 'status.json', 'evidence-pins.json')]
    selected_json += [str(baseline / n) for n in ('admission-manifest.json', 'combined-bits.json', 'status.json')]
    context = Context(pins, selected_json)
    current = context.load_sealed(root.admission / 'combined-bits.json', pins[str(root.admission / 'combined-bits.json')])
    old_manifest = context.load_sealed(baseline / 'admission-manifest.json', root.manifest['baseline_seal'])
    require(old_manifest['schema'] == 'PURE_WAR_HISTORICAL731_FULL_ARCHITECTURAL_ADMISSION_V1' and
            old_manifest['output'] == str(baseline) and
            all(old_manifest['output_pins'][str(baseline / name)] == pins[str(baseline / name)]
                for name in ('combined-bits.json', 'combined-inputs.txt', 'status.json')),
            'Predecessor bitmap authority differs')
    old_status = context.load_sealed(baseline / 'status.json', pins[str(baseline / 'status.json')])
    require(old_status['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and
            type(old_status['aggregate_passed']) is int and old_status['aggregate_passed'] == 731,
            'Exact PASS731 predecessor required')
    older = context.load_sealed(baseline / 'combined-bits.json', pins[str(baseline / 'combined-bits.json')])
    verify_membership(current, older, pins[str(root.admission / 'combined-inputs.txt')],
                      pins[str(baseline / 'combined-inputs.txt')])
    for name in pins:
        context.digest(name)
    stats = dict(context.finish())
    return dict(status='FORMAL732_POPULATION_CONSUMED_ALL_LITERAL_PINS_NOT_REPORT_READY',
        population=732, admission=str(root.admission), admission_seal=root.seal,
        literal_pins=len(pins), lexical_dotdot_pins=len(root.pending_literal_paths),
        canonical_endpoints=len(context.reader.pins), statistics=stats,
        membership_unique=True, exact731_prefix=True, all_literal_pins_rechecked=True,
        full_scalar_isa_verified=False, source_native_policy_qualification_complete=False,
        immutable_consumed_filesystem_proved=False, new_postrun_epoch_required=True,
        EDA_started=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('check-population',))
    parser.parse_args()
    print(json.dumps(consume(), sort_keys=True))


if __name__ == '__main__':
    main()
