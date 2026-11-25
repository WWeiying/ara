#!/usr/bin/env python3
"""Add outer parent-runner pins without mutating any existing build evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def release(directory):
    directory = Path(directory).resolve()
    expected = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
    if directory.parent != expected or not directory.name.startswith('operator_qbs_prepare_20261115_'):
        raise ValueError('Not an owned preparation output')
    manifest_path, pins_path = directory / 'runner-manifest.json', directory / 'runner-source-pins.json'
    if manifest_path.exists() or pins_path.exists():
        raise ValueError('Refusing to overwrite runner evidence')
    build_path = directory / 'build.json'
    build = json.loads(build_path.read_text())
    original_pins = Path(build['source_pins'])
    if build['state'] != 'BUILT_NOT_EXECUTED' or digest(original_pins) != build['source_pins_sha256']:
        raise ValueError('Build/inventory identity mismatch')
    pins = json.loads(original_pins.read_text())
    for path,sha in pins.items():
        if digest(path) != sha:
            raise ValueError('Source drift: '+path)
    for p in (build_path, original_pins, Path(__file__).resolve()):
        pins[str(p)] = digest(p)
    manifest = json.loads((directory / 'manifest.json').read_text())
    pins[str(directory / 'manifest.json')] = digest(directory / 'manifest.json')
    pins_path.write_text(json.dumps(pins, indent=2, sort_keys=True)+'\n')
    for c in manifest['cases']:
        c['source_pins'] = str(pins_path)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n')
    print(str(manifest_path))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', required=True, type=Path)
    release(p.parse_args().build)
