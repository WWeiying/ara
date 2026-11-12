#!/usr/bin/env python3
"""Derive a new all-on SoC worker, preserving the sealed predecessor verbatim."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import types

from resident_capability_validator import CAP_FILES, DISCOVERY, DISCOVERY_REVIEW, WORD

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
BASE = ROOT/'verification/performance/optimization_enablement/soc_build.py'
BASE_SHA = 'f5f8c6380a7a5c9e5f7c55e5a525e1eae956ae9be230a55404d0488880885610'
TEST = BASE.with_name('soc_build_test.py')
TEST_SHA = 'd4faba63fa4e781411d0bafcf841f372156fdce05aa454492964879c2e466696'
EXTENSION = ROOT/'verification/performance/optimization_extension/build_soc.py'
EXTENSION_SHA = 'ada2fe8d4177e67bf136718693fdf87acf5ce03eb594e8c0adb3ebc54683ebfe'
EXTENSION_FILES = ('hardware/src/ara.sv', 'hardware/src/ara_dispatcher.sv',
                   'hardware/include/qbs_pkg.sv', 'config/llm.mk',
                   'config/qbs_abi.json', 'scripts/gen_qbs_abi.py')
OWN = ('build_image.py', 'resident_capability_validator.py', 'resident_soc_test.py')
OLD_CAP_BLOCK = '''    pkg = (source/'hardware/include/akv_pkg.sv').read_text()
    for name in ('Pv', 'Qk'):
        require("localparam bit AkvResident" + name + "Supported = 1'b0;" in pkg,
                'Resident production capability changed')
        body = re.search(r'function automatic logic \\[63:0\\] akv_resident_' + name.lower() +
                         r'_capability_word\\(.*?endfunction', pkg, re.S)
        require(body is not None and "return '0;" in body[0], 'Resident capability function changed')
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Derivation preimage mismatch: '+old[:100])
    return text.replace(old, new)


def derive(text):
    text = replace_once(text, 'resident_capability=0, ideal_dispatcher=0)',
                        'resident_capability='+str(WORD)+', ideal_dispatcher=0)')
    text = replace_once(text, OLD_CAP_BLOCK,
                        '    from resident_capability_validator import validate\n    validate(source, b)\n')
    text = replace_once(text, "r'enablement_soc_[A-Za-z0-9_-]+'",
                        "r'enablement_soc_resident_deployment_[A-Za-z0-9_-]+'")
    text = replace_once(text, "schema='enablement-soc-build-v1'",
                        "schema='enablement-resident-deployment-soc-build-v1'")
    text = text.replace('ENABLEMENT_SOC_BUILT_NOT_EXECUTED', 'RESIDENT_DEPLOYMENT_SOC_BUILT_NOT_EXECUTED')
    text = replace_once(text, "    for name in OWN:\n        shutil.copyfile(HERE/name, inputs/name)\n",
        "    for name, content in DERIVED_FILES.items():\n        (inputs/name).write_text(content)\n"
        "    for name in SUCCESSORS:\n        shutil.copyfile(HERE/name, inputs/name)\n")
    text = replace_once(text, "    live = {str(ROOT/p): h for p, h in OVERLAYS.items()}\n",
                        "    live = {str(ROOT/p): h for p, h in OVERLAYS.items()}\n"
                        "    live.update(DERIVATION_PINS)\n")
    # Frozen execute/preflight must retain exactly the same explicit overlay list.
    text = replace_once(text, "    configuration(source, text, command, b, closure, shared)\n",
                        "    from resident_capability_validator import WORD\n"
                        "    b.require(config['resident_capability'] == WORD, 'New index4 contract required')\n"
                        "    configuration(source, text, command, b, closure, shared)\n")
    compile(text, 'resident_successor_soc_build.py', 'exec')
    return text


def worker():
    for path, expected in ((BASE, BASE_SHA), (TEST, TEST_SHA), (EXTENSION, EXTENSION_SHA)):
        if sha(path) != expected:
            raise ValueError('Sealed predecessor changed: '+str(path))
    code = derive(BASE.read_text())
    tests = replace_once(TEST.read_text(), "s.CONFIG['resident_capability'], 0)",
                         "s.CONFIG['resident_capability'], "+str(WORD)+")")
    tests = tests.replace('enablement_soc_build_test', 'enablement_soc_resident_deployment_build_test')
    module = types.ModuleType('resident_successor_soc_build')
    module.__file__ = str(HERE/'soc_build.py')
    exec(compile(code, module.__file__, 'exec'), module.__dict__)
    original = dict(module.OVERLAYS)
    pins = json.loads((DISCOVERY/'source-pins.json').read_text())
    if sha(DISCOVERY/'source-pins.json') != DISCOVERY_REVIEW:
        raise ValueError('Discovery review drift')
    for name in CAP_FILES:
        module.OVERLAYS[name] = pins[str(ROOT/name)]
    for name in EXTENSION_FILES:
        module.OVERLAYS[name] = sha(ROOT/name)
    module.require(set(module.OVERLAYS) == set(original) | set(CAP_FILES) | set(EXTENSION_FILES),
                   'Non-whitelisted source overlay')
    # Serialise the dynamic whitelist so the frozen worker cannot fall back to v1.
    suffix = '\nOVERLAYS = '+repr(module.OVERLAYS)+'\n'
    module.DERIVED_FILES = {'soc_build.py': code.replace("if __name__ == '__main__':", suffix+"\nif __name__ == '__main__':"),
                            'soc_build_test.py': tests}
    module.SUCCESSORS = OWN
    module.DERIVATION_PINS = {str(p): sha(p) for p in (BASE, TEST, EXTENSION, *(HERE/n for n in OWN))}
    return module


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--launch', action='store_true')
    args = parser.parse_args()
    module = worker()
    out = module.output(args.output)
    revision = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    result = module.prepare(out, revision, True)
    # Freeze provenance beside the worker; do not edit the inherited plan/pins.
    command = module.service(out, result['review_sha256'])
    print(json.dumps(dict(output=str(out), prepared=result, service=command), indent=2), flush=True)
    if args.launch:
        subprocess.run(command, check=True)


if __name__ == '__main__':
    main()
