#!/usr/bin/env python3
"""Host/GNU gates plus one bounded Spike entry-rejection test; no attention execution."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
BASE = 'd3d92ad72a3cabb91e8c333186160ae422f0866b'
SDK_BASE = 'ca772ef9096899be4749335581eb45077d5377e8'
BASE_CORE_SHA = '78872026dd5377469a0c991564456b8550763ba170999302b5c7b774d35294ee'
SDK = Path('software/akv')
CORE = SDK/'src/akv_v2_native_riscv.c'
FEATURES = SDK/'experimental/resident_attention/features_v2'
GNU = '/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-'
SPIKE = '/home/wangwy/software/toolchains/spike/bin/spike'
ARCH = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d']
OLD_FLAG = 'AKV_EXPERIMENTAL_RESIDENT_ATTENTION'
FLAG = 'AKV_EXPERIMENTAL_RESIDENT_FEATURES_V2'
ENTRY = 'akv_experimental_attention_execute_features_v2_native'
OWN = (CORE, FEATURES/'admission.h', FEATURES/'executor.h',
       HERE.relative_to(ROOT)/'test_features.c', HERE.relative_to(ROOT)/'test_features.py')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def function(source, name):
    start = source.index(name+'(')
    brace = source.index('{', start)
    depth = 1
    end = brace+1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[brace:end]


def run(output):
    output = output.absolute()
    require(output.parent == OUT and not output.is_symlink() and
            re.fullmatch(r'stage4_resident_features_host_[A-Za-z0-9_-]+', output.name) and
            not output.exists(), 'Use a fresh direct stage4_resident_features_host_ output')
    output.mkdir()
    commands, checks, pins = [], [], {}
    report = dict(state='FAIL', native_execution=False, simulator_launched=False,
                  native_attention_executed=False, target_guard_executed=False, eda_launched=False,
                  target_libm_checked=False, performance_measured=False, baseline_revision=BASE,
                  predecessor_sdk_revision=SDK_BASE, predecessor_core_sha256=BASE_CORE_SHA)

    def command(label, argv, success=True, timeout=120):
        argv = list(map(str, argv))
        record = dict(label=label, argv=argv, cwd=str(output), timeout_seconds=timeout)
        commands.append(record)
        log = output/(label+'.log')
        with log.open('x') as stream:
            proc = subprocess.run(argv, cwd=output, stdin=subprocess.DEVNULL,
                                  stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
        record['returncode'] = proc.returncode
        require((proc.returncode == 0) == success, 'Unexpected command status: '+label)
        return log.read_text()

    try:
        delta = subprocess.check_output(['git', 'diff', '--name-only', SDK_BASE, BASE, '--', str(SDK)],
                                        cwd=ROOT, text=True, timeout=60).splitlines()
        require(delta == ['software/akv/experimental/resident_attention/README.md'],
                'Unreviewed SDK source delta between Stage3 and Stage4 baseline')
        archive = subprocess.check_output(['git', 'archive', SDK_BASE, str(SDK)], cwd=ROOT, timeout=60)
        (output/'baseline.tar').write_bytes(archive)
        baseline, candidate = output/'baseline', output/'candidate'
        baseline.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
            for member in tree:
                path = Path(member.name)
                require(not path.is_absolute() and '..' not in path.parts and
                        (member.isfile() or member.isdir()), 'Unsafe archive member')
                tree.extract(member, baseline)
        require(sha(baseline/CORE) == BASE_CORE_SHA, 'Wrong predecessor core')
        shutil.copytree(baseline, candidate)
        for relative in OWN:
            source, dest = ROOT/relative, candidate/relative
            require(source.is_file() and not source.is_symlink(), 'Missing/linked owned source')
            pins[str(source)] = sha(source)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
        for source in (baseline/SDK/'experimental/resident_attention').glob('*'):
            if source.is_file() and source.suffix in ('.h', '.c', '.S', '.py'):
                live = ROOT/source.relative_to(baseline)
                require(sha(source) == sha(live), 'Stage3 helper changed: '+str(live))
                pins[str(live)] = sha(live)
        for root in (baseline, candidate):
            pins.update({str(p): sha(p) for p in root.rglob('*') if p.is_file()})
        pins[str(output/'baseline.tar')] = sha(output/'baseline.tar')
        for tool in ('/usr/bin/cc', '/usr/bin/clang', '/usr/bin/c++', GNU+'gcc', GNU+'nm', GNU+'objdump', SPIKE):
            path = Path(tool).resolve(strict=True)
            pins[str(path)] = sha(path)
        for name in ('cc1', 'as', 'ld', 'libm.a', 'libc.a', 'libgcc.a', 'libnosys.a'):
            option = '-print-file-name=' if name.endswith('.a') else '-print-prog-name='
            path = Path(command('locate-'+name, [GNU+'gcc', *ARCH, option+name]).strip()).resolve(strict=True)
            pins[str(path)] = sha(path)
        save(output/'source-pins.json', pins)

        src = candidate/SDK/'src'
        include = candidate/SDK/'include'
        common = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-unknown-pragmas',
                  '-fno-fast-math', '-ffp-contract=off', '-I'+str(include), '-iquote', src]
        other = [src/name for name in ('akv_runtime.c', 'akv_native_riscv.c', 'akv_v2_reference.c',
                  'akv_prefill_reference.c', 'akv_features.c', 'akv_decode.c')]
        test = candidate/HERE.relative_to(ROOT)/'test_features.c'
        enabled = ['-D'+OLD_FLAG+'=1', '-D'+FLAG+'=1']
        for mode, compiler, extra in (('optimized', '/usr/bin/cc', []),
                ('ubsan', '/usr/bin/clang', ['-fsanitize=undefined', '-fno-sanitize-recover=all'])):
            binary = output/('features-'+mode)
            command(mode+'-compile', [compiler, *common, *enabled, *extra, test, *other, '-lm', '-o', binary])
            text = command(mode+'-run', [binary])
            require('FEATURES_V2_HOST_PASS maps=15360 leaf_stubs=76800 feature_combinations=32 native_execution=0'
                    in text, 'Incomplete feature admission/dispatch exercise')
            checks.append(mode+'_feature_contract_and_leaf_stubs')

        for label, flags in (('default', []), ('stage3', ['-D'+OLD_FLAG+'=1']), ('both', enabled)):
            binary = output/('legacy-'+label)
            command('legacy-'+label+'-compile', ['/usr/bin/cc', *common, *flags,
                candidate/SDK/'experimental/resident_attention/test_executor.c', *other, '-lm', '-o', binary])
            text = command('legacy-'+label+'-run', [binary])
            require('EXECUTOR_HOST_PASS' in text, 'Old executor test did not finish')
            checks.append('unchanged_stage3_tests_'+label)
        command('public-header-cxx', ['/usr/bin/c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
            '-fsyntax-only', '-x', 'c++', '-include', candidate/FEATURES/'executor.h', '/dev/null'])
        checks.append('public_cxx_header')

        native = [*ARCH, '-mcmodel=medany', '-mno-relax',
                  '-O3', '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize',
                  '-Wno-unknown-pragmas', '-DAKV_REFILL_OVERLAP=0']
        variants = [('baseline-default', baseline, []), ('baseline-stage3', baseline, ['-D'+OLD_FLAG+'=1']),
            ('default', candidate, []), ('off', candidate, ['-D'+OLD_FLAG+'=0', '-D'+FLAG+'=0']),
            ('stage3', candidate, ['-D'+OLD_FLAG+'=1']),
            ('stage3-off', candidate, ['-D'+OLD_FLAG+'=1', '-D'+FLAG+'=0']), ('on', candidate, enabled)]
        for label, tree, flags in variants:
            command(label+'-gnu', [GNU+'gcc', *native, '-I'+str(tree/SDK/'include'),
                *flags, '-c', tree/CORE, '-o', output/(label+'.o')])
            command(label+'-symbols', [GNU+'nm', output/(label+'.o')])
        for before, after in (('baseline-default', 'default'), ('baseline-default', 'off'),
                              ('baseline-stage3', 'stage3'), ('baseline-stage3', 'stage3-off')):
            require((output/(before+'.o')).read_bytes() == (output/(after+'.o')).read_bytes(),
                    'GNU whole-object identity differs: '+after)
            checks.append('whole_object_identity_'+after)
        for label in ('default', 'off', 'stage3', 'stage3-off'):
            require(ENTRY not in (output/(label+'-symbols.log')).read_text(), 'New entry leaked: '+label)
        symbols = (output/'on-symbols.log').read_text()
        require(re.search(r'\bT '+ENTRY+r'$', symbols, re.M) and
                re.search(r'\bT akv_experimental_attention_execute_v2_native$', symbols, re.M) and
                all(re.search(r'\bU akv_experimental_resident_'+n+r'$', symbols, re.M) for n in ('qk', 'pv')),
                'Missing enabled SDK entry or resident leaf binding')
        checks.append('independent_entry_and_leaf_symbols')
        command('on-disassembly', [GNU+'objdump', '-dr', '-M', 'no-aliases,numeric', output/'on.o'])
        entry = command('entry-disassembly', [GNU+'objdump', '-dr', '-M', 'no-aliases,numeric',
                        '--disassemble='+ENTRY, output/'on.o'])
        first_call = entry.index('R_RISCV_CALL')
        require(all(entry.index(name) < first_call for name in ('vlenb', 'frm', 'vstart')),
                'Actual entry CSR guard must precede any snapshot/libc call')
        checks.append('entry_csrs_before_snapshot_libc')
        start_read = re.search(r'\bcsrrs\s+(x\d+),vstart,x0', entry)
        require(start_read is not None, 'Missing actual VSTART capture')
        reg = start_read.group(1)
        require(re.search(r'\b(?:bne|beq)\s+'+reg+r',x0,|\bc\.b(?:ne|eq)z\s+'+reg+r',',
                          entry[start_read.end():first_call]),
                'Missing VSTART branch before first snapshot/libc call')
        checks.append('entry_vstart_branch_before_snapshot_libc')
        command('overlap-gnu', [GNU+'gcc', *[x for x in native if x != '-DAKV_REFILL_OVERLAP=0'],
            '-DAKV_REFILL_OVERLAP=1', '-I'+str(include), *enabled, '-c', candidate/CORE, '-o', output/'overlap.o'])
        checks.append('effective_overlap_build')
        for label, flags in (('invalid-feature-flag', ['-D'+OLD_FLAG+'=1', '-D'+FLAG+'=2']),
                              ('missing-resource-flag', ['-D'+FLAG+'=1'])):
            command(label, [GNU+'gcc', *native, '-I'+str(include), *flags, '-c', candidate/CORE,
                '-o', output/(label+'.o')], success=False)
            checks.append(label+'_rejected')

        before, after = (path.read_text() for path in (baseline/CORE, candidate/CORE))
        require(function(before, 'prepare_resident_schedule') == function(after, 'prepare_resident_schedule'),
                'Original Stage3 preflight function changed')
        for name in ('apply_scale_mask_and_softmax', 'store_outputs', 'initialize_workspace',
                     'apply_prefill_scale_mask_softmax', 'akv_attention_execute_v2_prefill_native'):
            require(function(before, name) == function(after, name), 'Arithmetic/Prefill body changed: '+name)
        first, last = ('  initialize_workspace(workspace, q_rows, head_dim);',
                       '  return AKV_STATUS_OK;')
        old_core = function(before, 'execute_v2_with_features_native_internal')
        new_core = function(after, 'execute_v2_with_features_native_internal')
        require(old_core[old_core.index(first):old_core.index(last)] ==
                new_core[new_core.index(first):new_core.index(last)], 'Sink/tile/normalization order changed')
        checks.append('unchanged_arithmetic_and_entire_execution_loop')

        # Reuse the exact enabled object, with real archived SDK leaves/dependencies.
        # No SPIKE macro, arithmetic stubs, wrappers or relaxed unresolved symbols.
        objects = [output/'on.o']
        leaves = candidate/SDK/'experimental/resident_attention'
        for index, source in enumerate([test, *other, src/'akv_v2_attention_rvv.S',
                                       src/'akv_attention_rvv.S', leaves/'qk.S', leaves/'pv.S']):
            obj = output/('guard-%02d.o' % index)
            command('guard-compile-%02d' % index, [GNU+'gcc', *native, *enabled,
                '-DAKV_FEATURES_V2_TARGET_GUARD=1', '-ffunction-sections', '-fdata-sections',
                '-I'+str(include), '-iquote', src, '-c', source, '-o', obj])
            objects.append(obj)
        elf = output/'guard.elf'
        command('guard-link', [GNU+'gcc', *ARCH, '-mcmodel=medany', '-mno-relax',
            '-static', '-nostdlib', '-nostartfiles', '-Wl,-Ttext-segment=0x80000000',
            '-Wl,--gc-sections', '-Wl,-Map='+str(output/'guard.map'), *objects,
            '-Wl,--start-group', '-lm', '-lc', '-lgcc', '-lnosys', '-Wl,--end-group', '-o', elf])
        command('guard-disassembly', [GNU+'objdump', '-d', '-M', 'no-aliases,numeric', elf])
        nm = command('guard-symbols', [GNU+'nm', '-n', '-S', '--defined-only', elf])
        symbols = {parts[-1]: (int(parts[0],16), int(parts[1],16) if len(parts) == 4 else 0)
                   for line in nm.splitlines() if len(parts := line.split()) in (3,4)}
        lo, size = symbols[ENTRY]
        require(size > 0 and 'memcpy' in symbols and
                all('akv_experimental_resident_'+n in symbols for n in ('qk', 'pv')),
                'Missing actual entry/libc/resident bindings')
        trace = output/'guard.trace'
        report['simulator_launched'] = True
        command('guard-spike', [SPIKE, '-m16', '--isa=rv64gcv_zfh_zvfh_zvl1024b',
            '--instructions=10000', '-l', '--log-commits', '--log='+str(trace), elf], timeout=10)
        retired = [(int(pc,16),int(op,16)) for pc,op in re.findall(
            r'^core\s+\d+:\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)', trace.read_text(), re.M)]
        pcs = [pc for pc,op in retired]
        require(pcs.count(lo) == 2 and pcs.count(symbols['guard_return'][0]) == 2 and
                pcs.count(symbols['guard_pass'][0]) == 1 and symbols['guard_fail'][0] not in pcs,
                'Missing both requested=1/0 poison-pointer rejections or target assertion failure')
        for index,pc in enumerate(pcs):
            if pc == lo:
                end = pcs.index(symbols['guard_return'][0], index)
                require(all(lo <= x < lo+size for x in pcs[index:end]),
                        'Entry made a call before rejection')
        require(all(op & 0x7f not in (0x0b,0x2b,0x5b,0x7b,0x57,0x07,0x27) for pc,op in retired),
                'Unexpected custom/vector/FP memory instruction in guard-only execution')
        report.update(native_execution=True, target_guard_executed=True,
            target_guard=dict(scope='Actual entry rejection only; no native attention arithmetic',
                requested=[1,0], status=2, vstart_before=1, vstart_after=1, cleared_before_next_call=True,
                poison_arguments=dict(device=0x40, plan=0x80, workspace=0xc0, features=0x100),
                entry_calls=2, inner_calls=0, custom_vector_instructions=0,
                elf_sha256=sha(elf), trace_sha256=sha(trace), instructions=len(retired)))
        checks.append('actual_gnu_spike_poison_vstart_guard')
        require(all(sha(p) == digest for p, digest in pins.items()), 'Pinned input drift during host checks')
        report.update(state='HOST_GNU_SPIKE_GUARD_PASS_NO_ATTENTION', checks=checks, checks_passed=len(checks),
            feature_combinations=32, maps=15360, leaf_stub_calls=76800, post_pins_match=True,
            default_object_sha256=sha(output/'default.o'), stage3_object_sha256=sha(output/'stage3.o'))
    except Exception as exc:
        report['error'] = repr(exc)
        report['checks'] = checks
    save(output/'commands.json', commands)
    report['source_pins_sha256'] = sha(output/'source-pins.json') if (output/'source-pins.json').exists() else None
    report['artifacts'] = {str(p): sha(p) for p in output.rglob('*') if p.is_file()}
    save(output/'result.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'artifacts'}, indent=2))
    return report['state'] == 'HOST_GNU_SPIKE_GUARD_PASS_NO_ATTENTION'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(not run(parser.parse_args().output))
