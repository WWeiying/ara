#!/usr/bin/env python3
"""Separate, source-bound audit of an unchanged failed quantized model pair."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve()
CHECKER = HERE.with_name('quant_check.py')
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
FAILURE = "ValueError('QBS native-entry hits differ from complete command summaries')"
PASS = 'SCOPED_QUANT_COMMAND_AUDIT_PASS'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Nonfinite JSON: ' + value)
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=invalid)


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def merge(pins, extra):
    require(isinstance(extra, dict) and bool(extra), 'Empty/invalid pin inventory')
    for path, digest in extra.items():
        require(isinstance(path, str) and Path(path).is_absolute() and
                isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest),
                'Invalid pin: ' + str(path))
        require(path not in pins or pins[path] == digest, 'Conflicting pin: ' + path)
        pins[path] = digest


def verify(pins):
    require(bool(pins), 'Empty verification inventory')
    for path, digest in pins.items():
        require(sha(path) == digest, 'Pin drift: ' + path)


def bound_checker(out, assets, digest):
    source = CHECKER.read_bytes()
    require(hashlib.sha256(source).hexdigest() == digest, 'Unreviewed quant checker')
    spec = importlib.util.spec_from_file_location('scoped_quant_command_checker', CHECKER)
    checker = importlib.util.module_from_spec(spec)
    # Execute the exact reviewed bytes, never a cached bytecode file.
    exec(compile(source, str(CHECKER), 'exec'), checker.__dict__)
    require(checker.Path is Path and callable(checker.check), 'Checker Path/check interface drift')
    mapped = {out/name: assets/name for name in ('pcs.json', 'symbols.json')}

    class InputView:
        def __truediv__(self, name):
            return mapped.get(out/name, out/name)

    checker.Path = lambda value: InputView() if Path(value) == out else Path(value)
    return checker


def audit(execution, output, checker_sha256):
    out, dest = Path(execution).resolve(), Path(output).resolve()
    require(dest.parent == OUT and not dest.exists(), 'Fresh direct audit output required')
    dest.mkdir()
    report = dict(state='FAIL', execution=str(out), original_worker_state='FAIL',
                  original_failure_preserved=False, model_reexecuted=False,
                  performance_measured=False, performance_claim=False,
                  original_worker_pass_claim=False)
    try:
        require(out.parent == OUT and out.name.startswith('stage5_models_execution_final_'),
                'Owned final model execution required')
        require(isinstance(checker_sha256, str) and
                re.fullmatch('[0-9a-f]{64}', checker_sha256), 'Invalid checker SHA256')
        evidence = {str(path): sha(path) for path in
                    (out/'guest.log', out/'result.json', out/'source-pins.json',
                     out/'prepare.json', out/'launch-assets-binding.json', HERE, CHECKER)}
        require(evidence[str(CHECKER)] == checker_sha256, 'Unreviewed quant checker')
        original = read(out/'result.json')
        require(original['state'] == 'FAIL' and original['model_executed'] is True and
                original['error'] == FAILURE, 'Original failure is outside this audit scope')
        report['original_failure_preserved'] = True
        binding = read(out/'launch-assets-binding.json')
        assets = Path(binding['assets'])
        require(assets == assets.resolve() and assets.parent == OUT and
                assets.name.startswith('stage5_models_launch_assets_') and
                binding['original_preparation_unchanged'] is True, 'Invalid asset binding')
        pins = {}
        merge(pins, read(out/'source-pins.json'))
        merge(pins, binding['pins'])
        manifest_path = assets/'manifest.json'
        require(str(manifest_path) in binding['pins'] and
                sha(manifest_path) == binding['pins'][str(manifest_path)], 'Unbound asset manifest')
        manifest = read(manifest_path)
        prepared = read(out/'prepare.json')
        require(manifest['prepared'] == str(out) and
                manifest['original_pins_sha256'] == evidence[str(out/'source-pins.json')] ==
                prepared['source_pins_sha256'] and
                manifest['original_prepare_sha256'] == evidence[str(out/'prepare.json')] and
                manifest['model_inputs_changed'] is False and manifest['libraries_rebuilt'] is False,
                'Original preparation/asset ancestry drift')
        for path, digest in manifest['artifacts'].items():
            require(binding['pins'].get(path) == digest, 'Asset absent from binding pins: ' + path)
        for path in (assets/'pcs.json', assets/'symbols.json', assets/'test', out/'test',
                     out/'inputs/binding_check.py'):
            require(str(path) in pins, 'Required input outside pinned closure: ' + str(path))
        require(pins[str(assets/'test')] == manifest['executed_elf_sha256'] and
                pins[str(out/'test')] == manifest['original_elf_sha256'] == prepared['elf_sha256'],
                'ELF identity differs from manifest')
        merge(evidence, {str(manifest_path): binding['pins'][str(manifest_path)]})
        merge(pins, evidence)
        verify(pins)
        report.update(pre_pins_match=True, pins=len(pins), assets=str(assets),
                      checker_sha256=checker_sha256, evidence=evidence)
        save(dest/'source-pins.json', pins)
        try:
            proof = bound_checker(out, assets, checker_sha256).check(out)
            dependencies = {}
            merge(dependencies, proof['source_dependencies'])
            for path, digest in dependencies.items():
                require(pins.get(path) == digest,
                        'Checker dependency outside preverified pins or conflicting: ' + path)
            report['source_dependencies_checked'] = len(dependencies)
        finally:
            # Also detect drift when the checker itself raises an exception.
            verify(pins)
            report['post_pins_match'] = True
        save(dest/'checked.json', proof)
        report.update(state=PASS, all_original_pins_match=True, all_binding_pins_match=True,
                      checked_sha256=sha(dest/'checked.json'),
                      audit_pins_sha256=sha(dest/'source-pins.json'),
                      original_source_pins_sha256=evidence[str(out/'source-pins.json')],
                      input_mapping={'pcs.json': str(assets/'pcs.json'),
                                     'symbols.json': str(assets/'symbols.json')},
                      model_inputs_changed=False, numerical_expectation_changed=False,
                      command_accounting_corrected=True)
    except BaseException as exc:
        report['state'] = 'FAIL'
        report['error'] = repr(exc)
    save(dest/'result.json', report)
    print(json.dumps(report, sort_keys=True, allow_nan=False), flush=True)
    return 0 if report['state'] == PASS else 1


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--execution', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--checker-sha256', required=True)
    args = parser.parse_args()
    return audit(args.execution, args.output, args.checker_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
