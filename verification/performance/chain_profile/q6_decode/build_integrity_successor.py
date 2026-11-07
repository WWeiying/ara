#!/usr/bin/env python3
"""Build-only payload-integrity successor; no simulator or production edits.

Install the subclass in the CSR builder's private base module, not in the CSR
module itself: its build() would otherwise replace this subclass. Inherit the
exact main-source routing and restore the sealed CSR metadata after base build.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PARENT_SHA256 = 'd1998794b583b18e75bb49f52585ab442b9c704a737548c6b61278b33a9536d1'
CHECKER_SHA256 = '51bde4493ea93501e9b42ec822332bf3eb5eae9ce95b58c22f8db231f30822b5'
FROZEN_BUILD_SHA256 = '177bbc08302d84e9e46eed7fb3df9532abe77d08a2ddc88a98c9fdeafbf1b729'
FROZEN_RESULT_SHA256 = '60aeea43752a8296bd023c0b44154728f8d0b15c865afcc4036d142cddd72e0f'
RENAME_MAIN = '-Dmain=q6_profile_body'
METHOD = 'fnv1a64-after-both-timed-calls-v1'
PAYLOADS = {'activation': ('input_f32.bin', 8192, 'profile_input'),
            'weight': ('weights_r4.bin', 107520, 'profile_weights')}


def load_pinned(path, sha, name):
    if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
        raise ValueError('Pinned module identity mismatch: ' + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_parent(path=HERE / 'build_csr_successor.py'):
    return load_pinned(path, PARENT_SHA256, 'q6_integrity_private_csr_build')


parent = load_parent()
base = parent.parent
checker = load_pinned(HERE / 'check_successor.py', CHECKER_SHA256,
                      'q6_integrity_private_csr_check')
FROZEN = base.OUT / 'chain_q6_build_20261107_csr01'
FROZEN_RESULT = base.OUT / 'chain_q6_csr_vcs_20261107_01/result.json'
OUTPUT = base.OUT / 'chain_q6_build_20261107_integrity02'


def fnv1a64(data):
    value = 14695981039346656037
    for byte in data:
        value = ((value ^ byte) * 1099511628211) & ((1 << 64) - 1)
    return f'{value:016x}'


def frozen_build():
    base.require(base.digest(FROZEN / 'build.json') == FROZEN_BUILD_SHA256,
                 'Frozen CSR build identity mismatch')
    base.require(base.digest(FROZEN_RESULT) == FROZEN_RESULT_SHA256,
                 'Frozen CSR result identity mismatch')
    result = json.loads(FROZEN_RESULT.read_text())
    base.require(result['state'] == 'PASS' and result['post_pins_match'] is True and
                 result['independent_protocol_checked'] is True and
                 result['measured']['build_sha256'] == FROZEN_BUILD_SHA256,
                 'Frozen CSR execution was not accepted')
    return checker.check_build(FROZEN / 'build.json')


def payload_records(output, frozen):
    records = {}
    for tag, (filename, size, symbol) in PAYLOADS.items():
        reference = FROZEN / 'data' / filename
        data = reference.read_bytes()
        base.require(len(data) == size and
                     hashlib.sha256(data).hexdigest() == frozen['artifacts'][str(reference)],
                     'Frozen payload identity mismatch: ' + tag)
        path = output / 'data' / filename
        base.require(path.read_bytes() == data, 'Fresh payload differs from frozen: ' + tag)
        records[tag] = dict(path=str(path), bytes=size, expected_hash=fnv1a64(data), symbol=symbol)
    return records


def config_text(payloads):
    return ('/* Host constants from SHA-verified frozen payloads, never target-derived. */\n'
            '#define Q6_INPUT_EXPECTED_HASH UINT64_C(0x' +
            payloads['activation']['expected_hash'] + ')\n'
            '#define Q6_WEIGHT_EXPECTED_HASH UINT64_C(0x' +
            payloads['weight']['expected_hash'] + ')\n')


class Builder(parent.Builder):
    def __init__(self, output):
        super().__init__(output)
        self.frozen = frozen_build()
        self.frozen_pins = json.loads(Path(self.frozen['source_pins']).read_text())
        self.main_compile = None
        for path in (FROZEN / 'build.json', Path(self.frozen['source_pins']), FROZEN_RESULT,
                     FROZEN / 'sdk.tar', FROZEN / 'llama.tar',
                     *(FROZEN / 'data' / name for name, _, _ in PAYLOADS.values())):
            self.pin(path)

    def compile(self, cc, flags, source, obj):
        if Path(source) == base.HERE / 'main.c':
            base.require(self.main_compile is None and RENAME_MAIN not in flags,
                         'Duplicate/renamed profile main')
            self.main_compile = (cc, list(flags), Path(obj))
            flags = [*flags, RENAME_MAIN]
        return super().compile(cc, flags, source, obj)

    def run(self, label, argv, cwd=None):
        if label in ('sdk-head', 'llama-head'):
            # The workspace may have newer profiling-only commits. Resolve the
            # frozen commit with a real recorded command before git archive.
            prefix = label.split('-')[0]
            argv = [str(v) for v in argv]
            base.require(argv[-2:] == ['rev-parse', 'HEAD'], 'Unexpected source revision query')
            argv[-1] = self.frozen[prefix + '_commit']
        if label == 'link':
            base.require(self.main_compile is not None, 'Missing profile compile flags')
            cc, flags, main_obj = self.main_compile
            argv = [str(v) for v in argv]
            base.require(argv.count(str(main_obj)) == 1 and argv[0] == str(cc),
                         'Unexpected profile link')
            payloads = payload_records(self.output, self.frozen)
            config = self.output / 'integrity_config.h'
            base.require(not config.exists(), 'Refusing to reuse integrity header/object')
            config.write_text(config_text(payloads))
            self.pin(config)
            obj = self.output / 'wrapper.o'
            base.require(not obj.exists(), 'Refusing to reuse wrapper object')
            self.compile(cc, flags, HERE / 'input_integrity.c', obj)
            argv.insert(argv.index(str(main_obj)) + 1, str(obj))
        result = super().run(label, argv, cwd)
        for prefix in ('sdk', 'llama'):
            if label == prefix + '-head':
                base.require(result.decode().strip() == self.frozen[prefix + '_commit'],
                             'Resolved revision differs from frozen: ' + prefix)
            if label == prefix + '-archive':
                base.require(base.digest(self.output / (prefix + '.tar')) ==
                             self.frozen_pins[str(FROZEN / (prefix + '.tar'))],
                             'Archived sources differ from frozen: ' + prefix)
        return result


def integrity_manifest(output, frozen):
    source, obj, config = HERE / 'input_integrity.c', output / 'wrapper.o', output / 'integrity_config.h'
    return dict(method=METHOD, payloads=payload_records(output, frozen),
                wrapper=dict(source=str(source), source_sha256=base.digest(source),
                             object=str(obj), object_sha256=base.digest(obj),
                             config=str(config), config_sha256=base.digest(config)),
                entrypoint='main -> q6_profile_body', memory_checked_after_both_calls=True)


def check_integrity_build(path):
    """Build evidence only; the owner independently gates the new runtime lines."""
    receipt = checker.check_build(path)
    output = path.parent
    frozen = frozen_build()
    manifest = integrity_manifest(output, frozen)
    base.require(receipt['input_integrity'] == manifest, 'Input integrity manifest mismatch')
    pins = json.loads(Path(receipt['source_pins']).read_text())
    wrapper = manifest['wrapper']
    for key in ('source', 'object', 'config'):
        name, sha = wrapper[key], wrapper[key + '_sha256']
        base.require(pins.get(name) == sha and receipt['artifacts'].get(name) == sha,
                     'Missing integrity pin/artifact: ' + key)
    for record in manifest['payloads'].values():
        name = record['path']
        base.require(pins.get(name) == receipt['artifacts'].get(name) == base.digest(name),
                     'Missing payload pin/artifact')
    base.require(Path(wrapper['config']).read_text() == config_text(manifest['payloads']),
                 'Integrity header constants mismatch')
    commands = json.loads((output / 'commands.json').read_text())
    main = [c['argv'] for c in commands if c['label'] == 'compile-main']
    wrap = [c['argv'] for c in commands if c['label'] == 'compile-wrapper']
    links = [c['argv'] for c in commands if c['label'] == 'link']
    base.require(len(main) == len(wrap) == len(links) == 1 and
                 main[0].count(RENAME_MAIN) == 1 and
                 sum(c['argv'].count(RENAME_MAIN) for c in commands) == 1,
                 'Profile main rename routing mismatch')
    expected = [v for v in main[0] if v != RENAME_MAIN]
    for old, new in ((str(HERE / 'main_csr_successor.c'), wrapper['source']),
                     (str(output / 'main.d'), str(output / 'wrapper.d')),
                     (str(output / 'main.o'), wrapper['object'])):
        expected = [new if v == old else v for v in expected]
    base.require(wrap[0] == expected and links[0].count(wrapper['object']) == 1 and
                 links[0].count(str(output / 'main.o')) == 1 and
                 receipt['rebuilt_objects'].count(wrapper['object']) == 1 and
                 receipt['rebuilt_runtime_objects'] == len(receipt['rebuilt_objects']),
                 'Wrapper compile/link/object inventory mismatch')
    for prefix in ('sdk', 'llama'):
        base.require(receipt[prefix + '_commit'] == frozen[prefix + '_commit'] and
                     base.digest(output / (prefix + '.tar')) ==
                     base.digest(FROZEN / (prefix + '.tar')), 'Frozen source mismatch')
    for ref in (FROZEN / 'data').iterdir():
        base.require(base.digest(output / 'data' / ref.name) == base.digest(ref),
                     'Frozen data mismatch: ' + ref.name)
    return receipt


def build(args):
    output = args.output.resolve()
    base.require(output == OUTPUT.resolve() and not output.exists(),
                 'Output must be the new chain_q6_build_20261107_integrity02 directory')
    base.require(base.digest(HERE / 'build_csr_successor.py') == PARENT_SHA256,
                 'CSR builder changed before build')
    original = base.Builder
    try:
        base.Builder = Builder
        base.build(args)
    finally:
        base.Builder = original
    path = output / 'build.json'
    receipt = json.loads(path.read_text())
    frozen = frozen_build()
    # Keep the original checker's full metadata/entrypoint contract unchanged.
    for key in ('csr_contract', 'successor_reason', 'parent_builder', 'measurement_source'):
        receipt[key] = frozen[key]
    receipt['checker_entry'] = [sys.executable, '-B', str(HERE / 'check_successor.py'),
                                '--build', str(path), '--log', '<run.vcs.log>',
                                '--output', '<new authorized output.json>']
    receipt['input_integrity'] = integrity_manifest(output, frozen)
    receipt['input_integrity_parent_builder'] = dict(
        path=str(HERE / 'build_csr_successor.py'), sha256=PARENT_SHA256)
    receipt['sdk_ref'] = 'Pinned CSR parent commit (git archive, not current HEAD)'
    receipt['rebuilt_objects'].append(str(output / 'wrapper.o'))
    receipt['rebuilt_runtime_objects'] = len(receipt['rebuilt_objects'])
    wrapper = receipt['input_integrity']['wrapper']
    for key in ('source', 'object', 'config'):
        receipt['artifacts'][wrapper[key]] = wrapper[key + '_sha256']
    base.write_json(path, receipt)
    check_integrity_build(path)
    print(json.dumps(dict(build=str(path), state=receipt['state'],
                          input_integrity=receipt['input_integrity']), indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--llama', type=Path, default=base.LLAMA)
    parser.add_argument('--toolchain', type=Path, default=base.TOOLCHAIN)
    parser.add_argument('--host-cc', default='/usr/bin/gcc')
    try:
        build(parser.parse_args())
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error


if __name__ == '__main__':
    main()
