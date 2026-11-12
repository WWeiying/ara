#!/usr/bin/env python3
"""Reuse the accepted all-on build with only the optional QBINFO extension."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('/home/wangwy/openproject/ara_dsa')
SOURCE = ROOT / 'verification/performance/optimization_enablement/soc_build.py'


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('accepted_enablement_soc_build', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ('hardware/src/ara.sv', 'hardware/src/ara_dispatcher.sv', 'hardware/include/qbs_pkg.sv',
                 'config/llm.mk', 'config/qbs_abi.json', 'scripts/gen_qbs_abi.py',
                 'verification/performance/optimization_extension/build_soc.py'):
        module.OVERLAYS[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    revision = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    out = module.output(args.output)
    result = module.prepare(out, revision, True)
    command = module.service(out, result['review_sha256'])
    print(json.dumps(dict(prepared=result, command=command), indent=2), flush=True)
    subprocess.run(command, check=True)


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    main()
