#!/usr/bin/env python3
"""Freeze a held model observer/checker successor; syntax checks only, no link/run."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import shlex
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
MODELS = OUT/'stage5_models_prepare_20261110_04'
OVERLAY = OUT/'stage5_ggml_overlay_host_20261110_09'
PLATFORM = Path('/home/wangwy/llama/platforms/cva6-qemu')
OWN = ('prepare.py', 'check.py', 'observe.h', 'test_binding.py', 'README.md')
HASHES = dict(models='ae27251276ba052d232cf2bb3388f628069717fade303ec91e8bfa345ad662b2',
    model_pins='9cb49d8f979d9dc99dba3dc8e2707dfd1928b787f3f0c225337b0c7f9440ebfe',
    overlay='0a682a093837859d5cc43a2dd04e9859239827a839f4fedc4f9a76a838618f9c',
    overlay_pins='e1303ccc956a7ae3de2cd09f3a2915d3992c8207e0acb64db73ffc1fc449dc17',
    harness='84c985dd55828c32bf66a3f6e562826d778df7b4e1df90e57b4a7a5625d5d60f')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec); spec.loader.exec_module(obj); return obj


check = module('stage5_binding_check', HERE/'check.py')
require, sha, read = check.require, check.sha, check.read


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n')


def instrument(source):
    edits = [('#include <unistd.h>\n', '#include <unistd.h>\n#include "observe.h"\n'),
        ('        asm volatile("csrwi fcsr,8;',
         '        binding_snapshot(mode, step, "before");\n        asm volatile("csrwi fcsr,8;'),
        ('        need(rc == 0 && fc <= 31 && (fc & 8) && vc <= 7 && vs == 0, "decode_csr");',
         '        need(rc == 0 && fc <= 31 && (fc & 8) && vc <= 7 && vs == 0, "decode_csr");\n'
         '        binding_snapshot(mode, step, "after");'),
        ('        put(f, logits, count * sizeof(float));',
         '        put(f, logits, count * sizeof(float));\n        binding_logits(mode, step, logits, count);'),
        ('    std::setvbuf(stdout, nullptr, _IONBF, 0); std::setvbuf(stderr, nullptr, _IONBF, 0);',
         '    std::setvbuf(stdout, nullptr, _IONBF, 0); std::setvbuf(stderr, nullptr, _IONBF, 0);\n'
         '    std::printf("BIND_ID id=%s\\n", STAGE5_BINDING_ID);')]
    for before, after in edits:
        require(source.count(before) == 1, 'Sealed harness anchor drift')
        source = source.replace(before, after)
    return source


def prepare(out):
    require(out.parent == OUT and re.fullmatch('stage5_models_binding_prepare_[A-Za-z0-9_]+', out.name)
            and not out.exists(), 'Fresh independent binding prepare output required')
    for directory, receipt, pins in ((MODELS, 'models', 'model_pins'), (OVERLAY, 'overlay', 'overlay_pins')):
        require(sha(directory/'result.json') == HASHES[receipt] and
                sha(directory/'source-pins.json') == HASHES[pins], 'Sealed parent receipt/pins drift')
    oldpins = read(MODELS/'source-pins.json'); overlaypins = read(OVERLAY/'source-pins.json')
    basepath = ROOT/'verification/performance/chain_profile/q6_decode/build.py'
    require(sha(basepath) == oldpins[str(basepath)], 'Builder drift')
    base = module('stage5_binding_builder', basepath)
    out.mkdir(); b = base.Builder(out)
    try:
        inputs = out/'inputs'; inputs.mkdir()
        for n in OWN:
            b.pin(HERE/n); shutil.copyfile(HERE/n, inputs/n)
        b.pin(basepath)
        for directory in (MODELS, OVERLAY):
            b.pin(directory/'result.json'); b.pin(directory/'source-pins.json')
        def consume(path, pins, destination=None):
            require(str(path) in pins and sha(path) == pins[str(path)], 'Consumed frozen input drift: '+str(path))
            b.pin(path)
            if destination is not None: shutil.copyfile(path, destination)
        for name in ('input-manifest.json', 'model-inventory.json'):
            consume(MODELS/name, oldpins, inputs/name)
        manifest = read(inputs/'input-manifest.json'); inventory = read(inputs/'model-inventory.json')
        source = MODELS/'inputs/models/model_pair.cpp'
        require(sha(source) == HASHES['harness'], 'Wrong original harness')
        consume(source, oldpins, inputs/'models04-model_pair.cpp')
        (inputs/'model_pair.cpp').write_text(instrument(source.read_text()))
        for name in ('entry.h', 'platform.h'):
            consume(OVERLAY/'inputs/llama/ggml/src/ggml-cpu/arch/riscv'/name, overlaypins, inputs/name)
        raw = b.run('abi-archive', ['git', '-C', ROOT, 'show', manifest['ara_commit']+':config/akv_abi.json'])
        (inputs/'akv_abi.json').write_bytes(raw); abi = read(inputs/'akv_abi.json')
        cxx = PLATFORM/'tools/bin/riscv64-linux-g++'
        b.pin(cxx); b.pin(cxx.resolve())
        cc1 = Path(b.run('cc1plus-location', [cxx, '-print-prog-name=cc1plus']).decode().strip())
        b.pin(cc1); b.pin(cc1.resolve())
        flags = ['-std=c++17', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-O2',
                 '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
                 '-Wall', '-Wextra', '-Werror']
        sdk = MODELS/'inputs/sdk/software/akv'; llama = MODELS/'inputs/llama'
        includes = ['-I'+str(p) for p in (inputs, llama/'include', llama/'ggml/include', sdk/'include', sdk/'experimental')]
        cases = []
        for c in manifest['cases']:
            directory = inputs/c['id']; directory.mkdir()
            consume(MODELS/'inputs'/c['id']/'case_config.h', oldpins, directory/'case_config.h')
            consume(Path(c['token_file']), oldpins, directory/'tokens.json')
            meta = inventory[c['model']]
            spec = dict(c, abi=abi, layers=meta['layers'], vocabulary=meta['vocabulary'],
                        formats=sorted(k for k in meta['tensor_formats'] if k not in ('F32', 'F16', 'BF16')),
                        binding_id=None, execution_authorized=False)
            write(directory/'spec.json', spec)
            dep = out/(c['id']+'.d')
            args = [cxx, *flags, *includes, '-I'+str(directory), '-fsyntax-only', '-MD', '-MF', dep,
                    '-DSTAGE5_REVIEWED_RESIDENT_ENV="GGML_RISCV_AKV_RESIDENT"',
                    '-DSTAGE5_BINDING_ID="SYNTAX_ONLY_NOT_APPROVED"', inputs/'model_pair.cpp']
            b.run('syntax-'+c['id'], args)
            for p in shlex.split(dep.read_text().replace('\\\n', '').split(':', 1)[1]):
                if Path(p).resolve().is_relative_to(MODELS): consume(Path(p).resolve(), oldpins)
                b.pin(p)
            cases.append(dict(id=c['id'], spec=str(directory/'spec.json'), source=str(inputs/'model_pair.cpp'),
                              case_header=str(directory/'case_config.h'), output_elf=None))
        b.run('checker-host-tests', [sys.executable, '-B', '-m', 'unittest', 'test_binding', '-v'], cwd=inputs)
        binding = dict(schema='stage5-model-binding-held-v1', state='HELD', execution_authorized=False,
            model_inputs_changed=False, models04_receipt_sha256=HASHES['models'], overlay09_receipt_sha256=HASHES['overlay'],
            request_environment='GGML_RISCV_AKV_RESIDENT', requested_arms=[0, 1], same_on_library_and_elf=True,
            provider_authority_from_environment=False, common_environment=manifest['fixed_environment'],
            source_baseline='da56 + reviewed adapted06 + overlay09; never clean HEAD alone',
            sdk_reference=manifest['ara_commit'], sdk_library_reference='f50092f2d; QBS/AKV/apps-common trees identical',
            required_cmake=dict(GGML_RISCV_QBS='ON', GGML_RISCV_AKV='ON', GGML_RISCV_AKV_RESIDENT='ON',
                GGML_RISCV_AKV_QUANT_KV='ON', GGML_RISCV_AKV_QUANT_PREFILL='ON', GGML_RISCV_AKV_REGISTER_PV='ON',
                GGML_OPENMP='OFF', GGML_LTO='OFF', GGML_NATIVE='OFF', BUILD_SHARED_LIBS='OFF'),
            frontend_flags=flags, frontend_includes=includes, cases=cases,
            held_link_order=['frontend.o', 'accepted-provider.o', '-static', '-no-pie', '-Wl,--start-group',
                'libllama.a', 'libggml.a', 'libggml-cpu.a', 'libggml-base.a', '-Wl,--end-group',
                '-lm', '-pthread', '-ldl', '-latomic'],
            exact_bindings=dict(library_manifest=None, archive_hashes=None, provider_object=None,
                provider_contract=None, s3_receipt=None, qemu=None, kernel=None, bios=None,
                launcher=None, elf_pcs=None, trace_transport=None, parent_approval=None),
            resource_adjustment=dict(guest_memory='4G', host_memory_max='8G', cpu_quota='100%', guest_cpus=1,
                parallel_models=1, automatic_retries=0, reason='Reviewed host emulator overhead; no model/input change'),
            trace_requirement='Single causally ordered guest-serial/AKV-event transcript; transport must be independently proved.',
            remaining_proofs=['final ELF/library/provider/source identity', 'actual QBS instruction retirement',
                'PV_PREP actual execution', 'source/image/OS/RAM/ownership assurances', 'approved trace transport'],
            checker_scope='Full logits/CSR, control counters, QBS summaries, actual AKV event content; never release acceptance')
        write(out/'binding-held.json', binding)
        for p in inputs.rglob('*'):
            if p.is_file(): b.pin(p)
        b.pin(out/'binding-held.json')
        b.pin(out/'commands.json')
        for path, digest in b.pins.items(): require(sha(path) == digest, 'Binding source drift: '+path)
        write(out/'source-pins.json', b.pins)
        artifacts = {str(p): sha(p) for p in out.rglob('*') if p.is_file()}
        write(out/'result.json', dict(state='BINDING_SCAFFOLD_HELD', source_pins_sha256=sha(out/'source-pins.json'),
            files_pinned=len(b.pins), pins_match=True, artifacts=artifacts, syntax_cases=5,
            tests='checker-host-tests.log', inherited_full_model_inventory_rehashed=False,
            only_consumed_frozen_inputs_rechecked=True, provider_linked=False, model_executed=False,
            qemu_executed=False, library_built=False, execution_authorized=False))
        print('BINDING_SCAFFOLD_HELD '+str(out), flush=True)
    except Exception as exc:
        write(out/'result.json', dict(state='FAIL', error=str(exc), execution_authorized=False)); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    prepare(parser.parse_args().output.resolve())
