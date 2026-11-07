#!/usr/bin/env python3
"""Cross-compile committed GGML/SDK archives, never the unrelated working-tree deltas."""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
LLAMA = Path('/home/wangwy/llama/llama.cpp')
SDK = 'b7c9e6c3c1f8c5e469c130f46ec5bbfaf37a55d1'
LLAMA_COMMIT = '03959acc0f649f9071668d5b72888284e4676d2b'
HELPER = ROOT/'verification/akv/paired_heads/build_live_ggml_runtime.py'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def extract(repo, commit, paths, target):
    raw = subprocess.check_output(['git', '-C', str(repo), 'archive', commit, *paths])
    target.mkdir()
    (target/'source.tar').write_bytes(raw)
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        members = tar.getmembers()
        require(all((m.isfile() or m.isdir()) and not Path(m.name).is_absolute() and
                    '..' not in Path(m.name).parts for m in members), 'Unexpected archive member')
        tar.extractall(target, filter='data')
    return {str(p): sha(p) for p in target.rglob('*') if p.is_file()}


def build(args):
    out = args.output.resolve()
    require(out.parent == OUT.resolve() and not out.exists(), 'Fresh verification output required')
    require(1 <= args.jobs <= 32, 'Build jobs must be 1..32')
    out.mkdir()
    inputs = out/'inputs'
    inputs.mkdir()
    pins = {str(p): sha(p) for p in (Path(__file__), HELPER,
        HELPER.with_name('build_ggml_candidate.py'), HELPER.with_name('test_live_ggml_policy.py'))}
    result = dict(state='FAIL', target_executed=False, rtl_executed=False, model_executed=False,
                  performance_measured=False, private_runtime_overlay=False, dirty_sources_excluded=True)
    try:
        pins.update(extract(ROOT, SDK, ['software/akv', 'software/qbs'], inputs/'ara'))
        pins.update(extract(LLAMA, LLAMA_COMMIT, ['ggml'], inputs/'llama'))
        save(out/'source-pins.json', pins)
        sys.path.insert(0, str(HELPER.parent))
        spec = importlib.util.spec_from_file_location('frozen_ggml_compiler', HELPER)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        helper.ROOT, helper.LLAMA = inputs/'ara', inputs/'llama'
        # Do not let an archive's CMake metadata discover the outer verification Git repo.
        os.environ['GIT_CEILING_DIRECTORIES'] = str(inputs)
        sys.argv = [str(HELPER), '--output', str(out/'compile'), '--jobs', str(args.jobs)]
        helper.main()
        evidence = json.loads((out/'compile/result.json').read_text())
        require(evidence['state'] == 'LIVE_QBS_AKV_GGML_COMPILED_NOT_EXECUTED' and
                evidence['verified_native_fp_source_properties'] is True, 'Actual compile/FP gate failed')
        inherited = json.loads((out/'compile/source-pins.json').read_text())
        for p, digest in inherited.items():
            require(p not in pins or pins[p] == digest, 'Compiler input drift')
            pins[p] = digest
        archive = [Path(p) for p in evidence['artifacts'] if p.endswith('libggml-cpu.a')]
        require(len(archive) == 1, 'Missing/ambiguous CPU archive')
        nm = helper.TOOLS/'riscv64-linux-nm'
        symbols = subprocess.check_output([str(nm), str(archive[0])], text=True)
        (out/'native-symbols.log').write_text(symbols)
        for name in ('akv_attention_execute_v2_native_auto',
                     'akv_attention_execute_v2_with_features_native_auto'):
            require(any(line.strip() == 'U '+name for line in symbols.splitlines()) and
                    any(line.endswith(' T '+name) for line in symbols.splitlines()),
                    'Adapter must reference the new API and canonical SDK must define it: '+name)
        pins[str(nm.resolve())] = sha(nm.resolve())
        for p, digest in pins.items():
            require(sha(p) == digest, 'Sealed compilation input changed: '+p)
        save(out/'source-pins.json', pins)
        result.update(state='GGML_AUTO_PAIR_COMPILED_NOT_EXECUTED', sdk_commit=SDK,
                      llama_commit=LLAMA_COMMIT, adapter_references_canonical_auto_api=True,
                      source_pins_sha256=sha(out/'source-pins.json'), compile_receipt=evidence,
                      artifacts={**evidence['artifacts'], str(out/'native-symbols.log'): sha(out/'native-symbols.log')})
    except BaseException as exc:
        result.update(error=repr(exc))
        raise
    finally:
        save(out/'result.json', result)
    print(json.dumps(dict(state=result['state'], output=str(out))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=8)
    build(parser.parse_args())
