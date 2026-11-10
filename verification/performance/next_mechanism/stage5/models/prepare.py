#!/usr/bin/env python3
"""Prepare pinned model inputs only. No library build, QEMU, inference or launcher."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
LLAMA = Path('/home/wangwy/llama/llama.cpp')
MODELS = Path('/home/wangwy/llama/models')
PLATFORM = Path('/home/wangwy/llama/platforms/cva6-qemu')
TOKENIZER = LLAMA / 'build-prof/bin/llama-tokenize'
OLD_QEMU = OUT / 'qemu-context-20261023-01/qemu-10.2.0-build/qemu-system-riscv64'
BASE = ROOT / 'verification/performance/chain_profile/q6_decode/build.py'
OLD_HARNESS = ROOT / 'verification/akv/quantized_kv/prefill/sums_model_test.cpp'
OWN = ('prepare.py', 'plan.json', 'model_pair.cpp', 'test_prepare.py', 'README.md')
PENDING = ('accepted_resident_qemu_and_instruction_check', 'reviewed_baseline_reconciliation_and_selector_overlay',
           'explicit_platform_eligibility_contract', 'resident_only_environment_switch',
           'route_counter_checker_and_expected_counts', 'guest_payload_and_elf_binding',
           'parent_execution_authorization')


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def constant(value):
        raise ValueError('Nonfinite JSON: ' + value)
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


def validate(plan):
    require(plan['schema'] == 'stage5-model-plan-v1' and plan['execution_authorized'] is False, 'Not a held plan')
    require(plan['llama_commit'] == 'da56aa750559c180d631b466de983ff2bb5d54d9' and
            plan['llama_native_auto_reference'] == '03959acc0f649f9071668d5b72888284e4676d2b' and
            plan['llama_common_ancestor'] == '8ed9403e37f1ceb43c6279cdefef01354eac6fd3', 'Wrong baseline ancestry')
    require(plan['worker'] == dict(guest_memory='4G', guest_cpus=1, memory_max='4G', cpu_quota='100%', parallel_models=1,
                                 timeout_seconds=5400, automatic_retries=0), 'Worker bounds changed')
    expected = [('smol_f16', 63, 128, 'f16', 'f16', True),
                ('qwen3_f16', 136, 256, 'f16', 'f16', True),
                ('qwen25_q8kv', 40, 128, 'q8_0', 'q8_0', False),
                ('qwen25_q4kv', 40, 128, 'q4_0', 'q8_0', False),
                ('gemma_d256', 4, 128, 'f16', 'f16', False)]
    actual = [tuple(c[k] for k in ('id', 'prompt_tokens', 'context_capacity', 'cache_k', 'cache_v', 'resident_decode'))
              for c in plan['cases']]
    require(actual == expected, 'Not the reviewed five-pair matrix')
    env = plan['common_environment']
    require(env['GGML_RISCV_QBS'] == '1' and env['GGML_RISCV_QBS_EMULATE'] == '0' and
            env['GGML_RISCV_QBS_M4_PARALLEL_SUMS'] == '1' and env['AKV_PAIR_HEADS'] == '1' and
            env['GGML_RISCV_AKV_PORTABLE'] == '0', 'Baseline optimization/fallback switches changed')
    require(all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()), 'Environment types')


def token_prefix(tokens, count, vocab):
    require(isinstance(tokens, list) and len(tokens) >= count + 2, 'Insufficient tokenizer output')
    require(all(type(t) is int and 0 <= t < vocab for t in tokens), 'Token outside vocabulary')
    return tokens[:count + 2]


def tokenize(b, label, model, prompt):
    argv = list(map(str, [TOKENIZER, '-m', model, '-f', prompt, '--ids', '--no-escape', '--no-parse-special',
                         '--offline', '-t', '1']))
    environment = dict(PATH='/usr/bin:/bin', LC_ALL='C', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    command = dict(label=label, argv=argv, environment=environment, timeout_seconds=120, inference=False)
    b.commands.append(command); write(b.output/'commands.json', b.commands)
    process = subprocess.run(argv, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False)
    (b.output/(label+'.stdout')).write_bytes(process.stdout)
    (b.output/(label+'.stderr')).write_bytes(process.stderr)
    command['returncode'] = process.returncode; write(b.output/'commands.json', b.commands)
    require(process.returncode == 0, 'Tokenizer failed, rc='+str(process.returncode)+': '+label)
    return strict_json(process.stdout.decode())


def pin_dependencies(b, executable):
    b.pin(executable); b.pin(Path(executable).resolve())
    raw = b.run('ldd-' + Path(executable).name, ['ldd', executable]).decode()
    require('not found' not in raw, 'Missing tokenizer/tool dependency')
    for line in raw.splitlines():
        for word in line.split():
            if word.startswith('/') and Path(word).is_file():
                b.pin(word); b.pin(Path(word).resolve())


def disk_model_hash(b, disk, name):
    # Read-only ext4 extraction; do not mount, mutate or duplicate model disks.
    argv = [shutil.which('timeout'), '240', shutil.which('debugfs'), '-R', 'cat /models/' + name, str(disk)]
    b.commands.append(dict(label='disk-model-' + name, argv=argv, read_only=True))
    write(b.output / 'commands.json', b.commands)
    with (b.output / ('disk-' + name + '.stderr')).open('wb') as err:
        p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=err)
        h = hashlib.sha256(); size = 0
        for chunk in iter(lambda: p.stdout.read(1024 * 1024), b''):
            h.update(chunk); size += len(chunk)
        p.stdout.close()
        require(p.wait(timeout=30) == 0, 'Cannot read guest model')
    return dict(sha256=h.hexdigest(), bytes=size)


def metadata(path, case):
    from gguf import GGUFReader
    reader = GGUFReader(str(path))
    def value(key, default=None):
        field = reader.get_field(key)
        return field.contents() if field else default
    arch = value('general.architecture')
    require(isinstance(arch, str), 'Architecture missing')
    heads = value(arch + '.attention.head_count')
    kv_heads = value(arch + '.attention.head_count_kv', heads)
    dim = value(arch + '.attention.key_length', value(arch + '.embedding_length') // heads)
    require((dim, heads, kv_heads) == (case['head_dim'], case['q_heads'], case['kv_heads']), 'Unexpected real model geometry')
    fields = {}
    for key, field in reader.fields.items():
        if key.startswith('tokenizer.'):
            h = hashlib.sha256()
            for part in field.parts:
                h.update(part.tobytes())
            fields[key] = h.hexdigest()
    require('tokenizer.ggml.tokens' in fields, 'Missing embedded vocabulary')
    tokhash = hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return dict(architecture=arch, head_dim=dim, q_heads=heads, kv_heads=kv_heads,
                layers=value(arch + '.block_count'), vocabulary=len(reader.get_field('tokenizer.ggml.tokens').data),
                metadata_context_length_not_tested=value(arch + '.context_length'),
                tensor_formats=dict(sorted(Counter(t.tensor_type.name for t in reader.tensors).items())),
                tokenizer_fields_sha256=fields, tokenizer_metadata_sha256=tokhash,
                external_tokenizer_assets_used=False)


def header(case, model, tokens, source, environment):
    quote = lambda text: json.dumps(text, ensure_ascii=True)
    types = dict(f16='GGML_TYPE_F16', q8_0='GGML_TYPE_Q8_0', q4_0='GGML_TYPE_Q4_0')
    lines = ['// Generated pinned input. No selector definition or capability advertising.',
             'static const char *case_id = ' + quote(case['id']) + ';',
             'static const char *model_path = ' + quote('/model/models/' + Path(case['model']).name) + ';',
             'static const char source_text[] = ' + quote(source) + ';',
             'static const llama_token source_tokens[] = {' + ','.join(map(str, tokens)) + '};',
             'static const llama_token frozen_tokens[] = {' + ','.join(map(str, token_prefix(tokens, case['prompt_tokens'], model['vocabulary']))) + '};',
             'static const uint32_t expected_vocab = ' + str(model['vocabulary']) + ';',
             'static const int expected_layers = ' + str(model['layers']) + ';',
             'static const unsigned prompt_tokens = ' + str(case['prompt_tokens']) + ';',
             'static const unsigned context_capacity = ' + str(case['context_capacity']) + ';',
             'static const unsigned effective_context_capacity = 256;',
             'static const ggml_type cache_k = ' + types[case['cache_k']] + ';',
             'static const ggml_type cache_v = ' + types[case['cache_v']] + ';',
             'static const struct { const char *key; const char *value; } common_environment[] = {']
    lines += ['    {' + quote(k) + ',' + quote(v) + '},' for k, v in sorted(environment.items())]
    return '\n'.join(lines + ['};', ''])


def syntax_checks(b, inputs, cases):
    cxx = PLATFORM/'tools/bin/riscv64-linux-g++'
    pin_dependencies(b, cxx)
    cc1 = Path(b.run('locate-cc1plus', [cxx, '-print-prog-name=cc1plus']).decode().strip())
    pin_dependencies(b, cc1)
    base = [str(cxx), '-std=c++17', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d',
            '-fno-fast-math', '-ffp-contract=off', '-Wall', '-Wextra', '-Werror', '-fsyntax-only',
            '-I'+str(inputs/'llama/include'), '-I'+str(inputs/'llama/ggml/include')]
    for case in cases:
        dep = b.output/(case['id']+'.d')
        args = [*base, '-DSTAGE5_REVIEWED_RESIDENT_ENV="STAGE5_SYNTAX_ONLY_NOT_A_SELECTOR"',
                '-I'+str(inputs/case['id']), '-MD', '-MF', str(dep), str(inputs/'models/model_pair.cpp')]
        b.run('syntax-'+case['id'], args)
        for path in shlex.split(dep.read_text().replace('\\\n', '').split(':', 1)[1]): b.pin(path)
    args = [*base, '-I'+str(inputs/cases[0]['id']), str(inputs/'models/model_pair.cpp')]
    process = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120, check=False)
    (b.output/'missing-selector.log').write_bytes(process.stdout)
    b.commands.append(dict(label='missing-selector-must-reject', argv=args, returncode=process.returncode))
    write(b.output/'commands.json', b.commands)
    require(process.returncode != 0 and b'Bind the independently reviewed resident-only selector' in process.stdout,
            'Unbound selector was not rejected by the compiler')


def held_commands(output, plan):
    inputs = output / 'inputs'
    cc = PLATFORM / 'tools/bin/riscv64-linux-gcc'
    cxx = cc.with_name('riscv64-linux-g++')
    flags = '-march=rv64gcv_zfh_zvfh -mabi=lp64d -fno-fast-math -ffp-contract=off'
    opts = dict(CMAKE_SYSTEM_NAME='Linux', CMAKE_SYSTEM_PROCESSOR='riscv64', CMAKE_C_COMPILER=str(cc),
                CMAKE_CXX_COMPILER=str(cxx), CMAKE_C_FLAGS=flags, CMAKE_CXX_FLAGS=flags,
                CMAKE_EXE_LINKER_FLAGS='-static', CMAKE_BUILD_TYPE='Release', BUILD_SHARED_LIBS='OFF',
                GGML_NATIVE='OFF', GGML_CCACHE='OFF', GGML_LTO='OFF', GGML_OPENMP='OFF', GGML_BACKEND_DL='OFF',
                GGML_CPU='ON', GGML_CPU_REPACK='ON', GGML_RVV='ON', GGML_RV_ZFH='ON', GGML_RV_ZVFH='ON',
                GGML_RV_ZICBOP='OFF', GGML_RV_ZIHINTPAUSE='OFF', GGML_RV_ZVFBFWMA='OFF', GGML_RISCV_QBS='ON',
                GGML_RISCV_AKV='ON', GGML_RISCV_AKV_QUANT_KV='ON', GGML_RISCV_AKV_QUANT_PREFILL='ON',
                GGML_RISCV_AKV_REGISTER_PV='ON', GGML_RISCV_QBS_RUNTIME_DIR=str(inputs/'sdk/software/qbs'),
                GGML_RISCV_AKV_RUNTIME_DIR=str(inputs/'sdk/software/akv'), LLAMA_BUILD_COMMON='OFF',
                LLAMA_BUILD_TESTS='OFF', LLAMA_BUILD_EXAMPLES='OFF', LLAMA_BUILD_TOOLS='OFF',
                LLAMA_BUILD_SERVER='OFF', LLAMA_BUILD_APP='OFF', LLAMA_BUILD_MTMD='OFF',
                LLAMA_CURL='OFF', LLAMA_OPENSSL='OFF', LLAMA_HTTPLIB='OFF')
    configure = ['cmake', '-S', str(inputs/'llama'), '-B', str(output/'baseline-build')]
    configure += ['-D'+k+'='+v for k, v in sorted(opts.items())]
    cases = []
    for c in plan['cases']:
        qemu = ['@ACCEPTED_RESIDENT_QEMU@', '-M', 'virt', '-cpu', '@REVIEWED_CPU_EXTENSION_STRING@',
                '-smp', '1', '-m', '4G', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
                '-bios', str(PLATFORM/'images/fw_dynamic.bin'), '-kernel', str(PLATFORM/'images/Image'),
                '-initrd', '@PINNED_'+c['id']+'_INITRAMFS@', '-drive',
                'file='+str(PLATFORM/'images'/c['disk'])+',if=virtio,format=raw,readonly=on',
                '-append', 'console=ttyS0 rdinit=/init']
        cases.append(dict(case=c['id'], argv_template=qemu, timeout_seconds=5400,
                          owner='future direct systemd worker; no detached launcher',
                          systemd_properties={'MemoryMax': '4G', 'CPUQuota': '100%', 'RuntimeMaxSec': 5400},
                          requested=[0, 1], environment=plan['common_environment']))
    return dict(state='HELD_NOT_EXECUTABLE', unresolved=list(PENDING),
                baseline_configure_argv=configure,
                baseline_build_argv=['cmake', '--build', str(output/'baseline-build'), '--target', 'llama', '-j4'],
                candidate_build='Successor recipe must bind reviewed overlays and ELF symbols; baseline recipe is not resident-enabled.',
                cases=cases, automatic_retries=0, performance_measured=False)


def prepare(output):
    require(output.parent == OUT and re.fullmatch(r'stage5_models_prepare_[A-Za-z0-9_]+', output.name)
            and not output.exists(), 'Fresh direct OUT/stage5_models_prepare_* directory required')
    plan = strict_json((HERE/'plan.json').read_text()); validate(plan)
    output.mkdir()
    spec = importlib.util.spec_from_file_location('stage5_model_builder', BASE)
    base = importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
    b = base.Builder(output)
    try:
        inputs = output/'inputs'; own = inputs/'models'; own.mkdir(parents=True)
        for name in OWN:
            b.pin(HERE/name); shutil.copyfile(HERE/name, own/name)
        b.pin(BASE); shutil.copyfile(BASE, own/'q6_build.py')
        b.pin(OLD_HARNESS); shutil.copyfile(OLD_HARNESS, own/'historical_sums_model_test.cpp')
        b.archive(ROOT, plan['ara_commit'], ['software/akv', 'software/qbs', 'apps/common'], inputs/'sdk')
        b.archive(LLAMA, plan['llama_commit'], ['CMakeLists.txt', 'cmake', 'ggml', 'include', 'src',
                   'common', 'vendor', 'LICENSE', 'gguf-py', 'tools/tokenize'], inputs/'llama')
        auto_paths = ['ggml/src/ggml-cpu/CMakeLists.txt', 'ggml/src/ggml-cpu/arch/riscv/akv.cpp']
        b.archive(LLAMA, plan['llama_native_auto_reference'], auto_paths, inputs/'llama-native-auto-reference')
        delta = b.run('registered-native-auto-diff', ['git', '-C', LLAMA, 'diff',
                    plan['llama_common_ancestor'], plan['llama_native_auto_reference'], '--', *auto_paths])
        (inputs/'native-auto-reference.patch').write_bytes(delta)
        # These files must be present: merely setting their environment switches is insufficient.
        for name in ('q8_K-m4-packed.h', 'q8_K-prepared-reuse.h', 'quant-kv.cpp'):
            require((inputs/'llama/ggml/src/ggml-cpu/arch/riscv'/name).is_file(), 'Missing accepted baseline feature: '+name)
        for p in inputs.rglob('*'):
            if p.is_file(): b.pin(p)
        sys.path.insert(0, str(inputs/'llama/gguf-py'))
        for tool in (TOKENIZER, OLD_QEMU, PLATFORM/'images/Image', PLATFORM/'images/fw_dynamic.bin',
                     PLATFORM/'tools/bin/riscv64-linux-gcc', PLATFORM/'tools/bin/riscv64-linux-g++',
                     PLATFORM/'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio',
                     Path(shutil.which('debugfs')), Path(shutil.which('timeout')), Path(sys.executable)):
            b.pin(tool); b.pin(tool.resolve())
        pin_dependencies(b, TOKENIZER)
        producer_version = b.run('tokenizer-version', [TOKENIZER, '--version']).decode().strip()
        # Preserve the concrete old-tool ABI mismatch without repairing that installation.
        for stem, binary in (('old', LLAMA/'build/bin/llama-tokenize'), ('selected', TOKENIZER)):
            library = binary.parent/'libllama.so.0.1.0'
            b.pin(binary); b.pin(library)
            b.run(stem+'-tokenizer-disassembly', ['objdump', '-d', '-C', binary])
            b.run(stem+'-context-abi-disassembly', ['objdump', '-d', '--disassemble=llama_context_default_params', library])
        source = plan['prompt_unit'] * plan['prompt_repetitions']
        prompt = inputs/'prompt.txt'; prompt.write_text(source); b.pin(prompt)
        inventory = {}; tokenizations = {}; cases = []
        for case in plan['cases']:
            name = case['model']; model = MODELS/name; disk = PLATFORM/'images'/case['disk']
            if name not in inventory:
                b.pin(model); b.pin(disk)
                info = metadata(model, case)
                info.update(path=str(model), sha256=base.digest(model), bytes=model.stat().st_size,
                            guest_path='/model/models/'+model.name, disk=str(disk), disk_sha256=base.digest(disk))
                contained = disk_model_hash(b, disk, model.name)
                require(contained == dict(sha256=info['sha256'], bytes=info['bytes']), 'Guest model differs from inventoried GGUF')
                info['guest_model_matches_host'] = True
                tokens = tokenize(b, 'tokenize-'+case['id'], model, prompt)
                token_prefix(tokens, case['prompt_tokens'], info['vocabulary'])
                inventory[name] = info; tokenizations[name] = tokens
            info, tokens = inventory[name], tokenizations[name]
            prefix = token_prefix(tokens, case['prompt_tokens'], info['vocabulary'])
            directory = inputs/case['id']; directory.mkdir()
            record = dict(case=case['id'], model_sha256=info['sha256'], tokenizer_metadata_sha256=info['tokenizer_metadata_sha256'],
                          source_text_sha256=base.digest(prompt), add_special=True, parse_special=False,
                          full_source_token_ids=tokens, prompt_ids=prefix[:-2], continuation_ids=prefix[-2:],
                          policy='fixed teacher forcing; not generated text or a captured model trajectory')
            write(directory/'tokens.json', record)
            (directory/'case_config.h').write_text(header(case, info, tokens, source, plan['common_environment']))
            cases.append(dict(**case, logical_contexts=[case['prompt_tokens']+i for i in range(3)],
                              context_capacity_is_requested=True, expected_effective_context_capacity=256,
                              token_file=str(directory/'tokens.json'), token_file_sha256=base.digest(directory/'tokens.json'),
                              logits_compared=3*info['vocabulary'], outputs='all vocabulary logits at three API calls',
                              prefill_resident_commands=0, decode_resident_expectation='positive' if case['resident_decode'] else 'zero'))
        write(output/'model-inventory.json', inventory)
        write(output/'held-commands.json', held_commands(output, plan))
        write(output/'input-manifest.json', dict(schema='stage5-model-inputs-v1', state='PREPARED_HELD',
              ara_commit=plan['ara_commit'], llama_commit=plan['llama_commit'], cases=cases,
              llama_native_auto_reference=plan['llama_native_auto_reference'],
              llama_common_ancestor=plan['llama_common_ancestor'],
              native_auto_reference_patch_applied=False, runtime_baseline_reconciliation_review_required=True,
              fixed_environment=plan['common_environment'], worker=plan['worker'], unresolved=list(PENDING),
              tokenizer_producer=dict(path=str(TOKENIZER), sha256=base.digest(TOKENIZER),
                  reported_version=producer_version,
                  provenance='Existing binary plus resolved library hashes; source-build identity not inferred.',
                  future_guest_retokenization_required=True),
              equality=['full_logits_bitwise', 'greedy_token', 'FCSR', 'VCSR', 'vstart', 'logical_work'],
              counters_required=['native_QBS_per_format_gemv_gemm', 'legacy_AKV_and_quant_KV_routes',
                  'resident_QK_PV_PV_PREP_per_phase', 'groups_tiles_heads_querybase', 'fallback_reason',
                  'context_fill_release_and_whole_command_completion'],
              primitive_counts_equal_across_routes=False, counter_checker_bound=False,
              production_capability_changed=False, model_regression_executed=False, performance_measured=False))
        b.run('host-contract-tests', [sys.executable, '-B', '-m', 'unittest', 'test_prepare', '-v'], cwd=own)
        syntax_checks(b, inputs, plan['cases'])
        for name, module in list(sys.modules.items()):
            if name.startswith(('numpy', 'gguf')) and getattr(module, '__file__', None): b.pin(module.__file__)
        for p in inputs.rglob('*'):
            if p.is_file(): b.pin(p)
        for name in ('model-inventory.json', 'input-manifest.json', 'held-commands.json'):
            b.pin(output/name)
        # Rehash assets as well as source files: prep success must not hide concurrent drift.
        for path, sha in b.pins.items():
            require(base.digest(path) == sha, 'Input drift: '+path)
        write(output/'source-pins.json', b.pins)
        artifacts = {str(p): base.digest(p) for p in output.iterdir() if p.is_file()}
        write(output/'result.json', dict(state='PREPARED_HELD', pins_match=True, files_pinned=len(b.pins),
              source_pins_sha256=base.digest(output/'source-pins.json'), artifacts=artifacts,
              models=len(inventory), pairs=len(cases), inference_executed=False, qemu_executed=False,
              builds_executed=False, syntax_only_cases=5, missing_selector_compile_rejected=True,
              host_checks=11, tokenizer_only_executed=True, execution_authorized=False))
        print('PREPARED_HELD '+str(output), flush=True)
    except Exception as exc:
        write(output/'result.json', dict(state='PREPARATION_FAILED', error=str(exc), execution_authorized=False))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.output.resolve())
