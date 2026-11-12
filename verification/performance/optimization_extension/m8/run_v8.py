#!/usr/bin/env python3
"""Fresh, bounded GNU/Spike numerical and capability-selection contract check."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess

ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
LLAMA = Path('/home/wangwy/llama/llama.cpp')
HERE = ROOT/'verification/performance/optimization_extension/m8'
CXX = ROOT.parent/'ara/install/riscv-gcc/bin/riscv64-unknown-elf-g++'
SPIKE = ROOT.parent/'riscv-isa-sim-ara-dsa-vstart/build/spike'
CAPTURE = OUT/'stage2_qwen3_rows8_20261109_02'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, why):
    if not ok:
        raise ValueError(why)


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    require(out.parent == OUT and out.name.startswith('optimization_extension_m8_') and not out.exists(),
            'Use a fresh optimization_extension_m8_* signoff output')
    out.mkdir()
    inputs = out/'inputs'
    inputs.mkdir()
    pins, origins, commands = {}, {}, []
    report = dict(state='FAIL', actual_rtl_executed=False, performance_measured=False,
                  model_executed=False, native_info_transport_is_test_metadata=True)

    def pin(path):
        path = Path(path).resolve()
        digest = sha(path)
        require(str(path) not in pins or pins[str(path)] == digest, 'Pin drift: '+str(path))
        pins[str(path)] = digest

    def copy(source, destination):
        source = Path(source).resolve()
        digest = sha(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        require(sha(destination) == digest, 'Copy race: '+str(source))
        origins[str(destination)] = dict(source=str(source), sha256=digest)
        pin(destination)

    def run(label, argv, timeout=120):
        argv = list(map(str, argv))
        pin(Path(argv[0]).resolve())
        with (out/(label+'.log')).open('x') as log:
            result = subprocess.run(argv, cwd=out, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        commands.append(dict(label=label, argv=argv, returncode=result.returncode))
        require(result.returncode == 0, 'Failed '+label+'; preserve original log')
        return (out/(label+'.log')).read_text()

    def verify():
        for path, digest in pins.items():
            require(sha(path) == digest, 'Sealed input drift: '+path)

    try:
        for base in ('include', 'src'):
            for source in sorted((LLAMA/'ggml'/base).rglob('*')):
                if source.is_file() and source.suffix in ('.h', '.hpp', '.c', '.cpp', '.inc'):
                    copy(source, inputs/'ggml'/source.relative_to(LLAMA/'ggml'))
        # Only QBS C sources and headers: never dirty AKV assembly/dependencies.
        for source in sorted((ROOT/'software/qbs/include').rglob('*.h')):
            copy(source, inputs/'sdk'/source.relative_to(ROOT))
        copy(ROOT/'software/qbs/src/qbs_runtime.c', inputs/'sdk/software/qbs/src/qbs_runtime.c')
        for name in ('start.S', 'runtime.cpp', 'link.ld'):
            copy(ROOT/'verification/performance/next_mechanism/stage4/m4_preflight'/name, inputs/name)
        copy(HERE/'target_v4.cpp', inputs/'target.cpp')
        copy(HERE/'reuse_target_v2.cpp', inputs/'reuse_target.cpp')
        copy(HERE/'repack_target_v3.cpp', inputs/'repack_target.cpp')
        copy(Path(__file__).resolve(), inputs/'run.py')
        for view in ('attn_q', 'ffn_gate'):
            metadata = json.loads((CAPTURE/view/'operator.json').read_text())
            source = CAPTURE/view/'activation_f32.bin'
            require(metadata['activation_shape'] == [2048, 8] and metadata['distinct_rows'] == 8 and
                    metadata['model_sha256'] == 'd2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5' and
                    sha(source) == metadata['activation_sha256'], 'Real Qwen3 capture identity')
            copy(source, inputs/(view+'.bin'))
            copy(CAPTURE/view/'operator.json', inputs/(view+'.json'))
        data = inputs/'data.S'
        data.write_text('.section .rodata\n.balign 64\n.global real_attn\nreal_attn:\n.incbin "'+
                        str(inputs/'attn_q.bin')+'"\n.balign 64\n.global real_ffn\nreal_ffn:\n.incbin "'+
                        str(inputs/'ffn_gate.bin')+'"\n')
        pin(data)
        ggml = inputs/'ggml'
        arch = ggml/'src/ggml-cpu/arch/riscv'
        includes = []
        for path in (inputs, ggml/'include', ggml/'src', ggml/'src/ggml-cpu', arch,
                     inputs/'sdk/software/qbs/include'):
            includes += ['-isystem', str(path)]
        flags = ['-std=c++17', '-O2', '-DNDEBUG', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d',
                 '-mcmodel=medany', '-mno-relax', '-msmall-data-limit=0', '-fno-fast-math', '-ffp-contract=off',
                 '-ffunction-sections', '-fdata-sections', '-fno-exceptions', '-fno-rtti',
                 '-fno-threadsafe-statics', '-fno-stack-protector', '-fno-tree-vectorize',
                 '-fno-tree-slp-vectorize', *includes]
        objects = []
        for name, source, extra, link in (
            ('generic', ggml/'src/ggml-cpu/repack.cpp',
             ['-Dggml_quantize_mat_q8_K_4x1_ara_generic=frozen_generic'], True),
            ('repack-hook', ggml/'src/ggml-cpu/repack.cpp',
             ['-DGGML_USE_RISCV_QBS', '-DGGML_RISCV_ACCEL_AUTO=1'], False),
            ('qbs', arch/'qbs.cpp', ['-DGGML_RISCV_ACCEL_AUTO=1'], True),
            ('sdk', inputs/'sdk/software/qbs/src/qbs_runtime.c', ['-x', 'c', '-std=c11'], True),
            ('target', inputs/'target.cpp', ['-DGGML_RISCV_ACCEL_AUTO=1'], True),
            ('runtime', inputs/'runtime.cpp', ['-ffreestanding', '-fno-builtin', '-fno-tree-loop-distribute-patterns'], True),
            ('start', inputs/'start.S', [], True), ('data', data, [], True)):
            if source.suffix != '.S':
                dep = out/(name+'.d')
                run(name+'-deps', [CXX, *flags, *extra, '-M', '-MF', dep, source])
                for path in shlex.split(dep.read_text().replace('\\\n', '').split(':', 1)[1]):
                    pin(path)
            obj = out/(name+'.o')
            run(name+'-compile', [CXX, *flags, *extra, '-c', source, '-o', obj])
            pin(obj)
            if link:
                objects.append(obj)
        lib = Path(run('libgcc', [CXX, '-print-libgcc-file-name']).strip())
        pin(lib)
        for name in ('cc1plus', 'cc1', 'as', 'ld'):
            pin(run('tool-'+name, [CXX, '-print-prog-name='+name]).strip())
        reuse_objects = []
        for name, source, extra in (
            ('qbs-reuse', arch/'qbs.cpp', ['-DGGML_RISCV_ACCEL_AUTO=1',
                '-Dggml_riscv_qbs_supports_tensor=unused_weight_support']),
            ('reuse-target', inputs/'reuse_target.cpp', ['-DGGML_RISCV_ACCEL_AUTO=1'])):
            dep, obj = out/(name+'.d'), out/(name+'.o')
            run(name+'-deps', [CXX, *flags, *extra, '-M', '-MF', dep, source])
            for path in shlex.split(dep.read_text().replace('\\\n', '').split(':', 1)[1]):
                pin(path)
            run(name+'-compile', [CXX, *flags, *extra, '-c', source, '-o', obj])
            pin(obj)
            reuse_objects.append(obj)
        hook_objects = []
        rename = ('supports_tensor', 'trace_activation_lifetime_enabled', 'prepare_activation_context',
                  'trace_activation_lifetime', 'repack_r4', 'mul_mat_view', 'gemv', 'gemm', 'gemm_wide')
        for name, source, extra in (
            ('qbs-hook', arch/'qbs.cpp', ['-DGGML_RISCV_ACCEL_AUTO=1',
                *('-Dggml_riscv_qbs_'+n+'=unused_hook_'+n for n in rename)]),
            ('hook-target', inputs/'repack_target.cpp', ['-DGGML_RISCV_ACCEL_AUTO=1', '-DGGML_USE_RISCV_QBS'])):
            dep, obj = out/(name+'.d'), out/(name+'.o')
            run(name+'-deps', [CXX, *flags, *extra, '-M', '-MF', dep, source])
            for path in shlex.split(dep.read_text().replace('\\\n', '').split(':', 1)[1]):
                pin(path)
            run(name+'-compile', [CXX, *flags, *extra, '-c', source, '-o', obj])
            pin(obj)
            hook_objects.append(obj)
        elfs = []
        for case in range(38):
            source = inputs/('case-'+str(case)+'.S')
            source.write_text('.section .rodata\n.balign 4\n.global test_case\ntest_case:\n.word '+str(case)+'\n')
            pin(source)
            obj, elf = out/('case-'+str(case)+'.o'), out/('case-'+str(case)+'.elf')
            run('case-'+str(case)+'-compile', [CXX, *flags, '-c', source, '-o', obj])
            pin(obj)
            run('case-'+str(case)+'-link', [CXX, *flags, '-nostdlib', '-static', *objects, obj,
                '-Wl,--gc-sections', '-Wl,--build-id=none', '-T', inputs/'link.ld', lib, '-o', elf])
            pin(elf)
            names = run('case-'+str(case)+'-symbols', [CXX.with_name('riscv64-unknown-elf-nm'), '-n', elf])

            def symbol(name):
                matches = re.findall(r'^([0-9a-f]+) \w '+name+'$', names, re.M)
                require(len(matches) == 1, 'Missing symbol '+name)
                return matches[0]

            cmd = out/('case-'+str(case)+'.cmd')
            cmd.write_text('until pc 0 '+symbol('test_exit')+'\nreg 0 a0\nstr '+symbol('test_log')+'\nrs\n')
            pin(cmd)
            elfs.append((case, elf, cmd))
        reuse = out/'reuse.elf'
        run('reuse-link', [CXX, *flags, '-nostdlib', '-static',
            *(obj for obj in objects if obj.name not in ('qbs.o', 'target.o')),
            *reuse_objects, out/'case-0.o', '-Wl,--gc-sections', '-Wl,--build-id=none',
            '-T', inputs/'link.ld', lib, '-o', reuse])
        pin(reuse)
        names = run('reuse-symbols', [CXX.with_name('riscv64-unknown-elf-nm'), '-n', reuse])
        reuse_cmd = out/'reuse.cmd'
        reuse_cmd.write_text('until pc 0 '+symbol('test_exit')+'\nreg 0 a0\nstr '+symbol('test_log')+'\nrs\n')
        pin(reuse_cmd)
        start = inputs/'hook-start.S'
        start.write_text((inputs/'start.S').read_text().replace('    la sp, __stack_top',
            '    la tp, __tls_base\n    la sp, __stack_top'))
        pin(start)
        link = inputs/'hook-link.ld'
        link.write_text((inputs/'link.ld').read_text().replace('    __bss_start = .;\n', '').replace('  .bss (NOLOAD)',
            '  .tdata : { *(.tdata .tdata.*) } > RAM\n'
            '  ASSERT(SIZEOF(.tdata) == 0, "initialized TLS not supported by test startup")\n'
            '  .tbss (NOLOAD) : ALIGN(64) { __tls_base = .; __bss_start = .; *(.tbss .tbss.*) } > RAM\n'
            '  .bss ALIGN(ADDR(.tbss) + SIZEOF(.tbss), 64) (NOLOAD)'))
        pin(link)
        start_obj = out/'hook-start.o'
        run('hook-start-compile', [CXX, *flags, '-c', start, '-o', start_obj])
        pin(start_obj)
        hook = out/'hook.elf'
        run('hook-link', [CXX, *flags, '-nostdlib', '-static',
            *(obj for obj in objects if obj.name not in ('generic.o', 'qbs.o', 'target.o', 'start.o')),
            *hook_objects, start_obj, out/'case-0.o', '-Wl,--gc-sections', '-Wl,--build-id=none',
            '-T', link, lib, '-o', hook])
        pin(hook)
        names = run('hook-symbols', [CXX.with_name('riscv64-unknown-elf-nm'), '-n', hook])
        hook_cmd = out/'hook.cmd'
        hook_cmd.write_text('until pc 0 '+symbol('test_exit')+'\nreg 0 a0\nstr '+symbol('test_log')+'\nrs\n')
        pin(hook_cmd)
        pin(SPIKE)
        save(out/'snapshot-origins.json', origins)
        save(out/'source-pins.json', pins)
        verify()
        cases = []
        for case, elf, cmd in elfs:
            log = run('case-'+str(case)+'-spike', [SPIKE, '-d', '--debug-cmd='+str(cmd),
                      '--isa=rv64gcv_zfh_zvfh_zvl1024b', '-m2', elf], timeout=90)
            marker = 'M8_VSTART_ABORT_PASS' if case == 11 else 'M8_TARGET_PASS case='+str(case)+' '
            require(log.count(marker) == 1 and 'FAIL' not in log and 'TRAP' not in log and
                    len(re.findall(r'^0x0000000000000000$', log, re.M)) == 1,
                    'Target rejection/failure: '+str(case))
            cases.append(dict(case=case, elf_sha256=sha(elf), log_sha256=sha(out/('case-'+str(case)+'-spike.log'))))
        log = run('reuse-spike', [SPIKE, '-d', '--debug-cmd='+str(reuse_cmd),
                  '--isa=rv64gcv_zfh_zvfh_zvl1024b', '-m2', reuse], timeout=90)
        require(log.count('M8_REUSE_PRIORITY_PASS computations=2 hits=2 one_shot=1 context_reuse_veto=1 nth2_veto=1') == 1
                and 'FAIL' not in log and 'TRAP' not in log and
                len(re.findall(r'^0x0000000000000000$', log, re.M)) == 1, 'Reuse priority failure')
        log = run('hook-spike', [SPIKE, '-d', '--debug-cmd='+str(hook_cmd),
                  '--isa=rv64gcv_zfh_zvfh_zvl1024b', '-m2', hook], timeout=90)
        require(log.count('M8_REPACK_LAYOUT_PASS one_shot_m8=1 qkv_m4=2 nth2_m4=2 context_m4=1 markers_exact=1') == 1
                and 'FAIL' not in log and 'TRAP' not in log and
                len(re.findall(r'^0x0000000000000000$', log, re.M)) == 1, 'Actual repack layout/marker failure')
        verify()
        report.update(state='M8_GNU_SPIKE_CHECKED', cases=cases, post_pins_match=True,
                      source_pins_sha256=sha(out/'source-pins.json'), actual_repack_hook_compiled=True,
                      actual_sdk_query_and_ggml_planner_executed=True, actual_ggml_graph_executed=False)
        report['actual_m4_cache_reuse_priority_checked'] = True
        report['actual_repack_trait_executed_layout_sink_metadata_only'] = True
        report['multiworker_check'] = 'Two real trait entries, single-core cooperative barrier; not concurrent stress'
    except BaseException as exc:
        report['error'] = repr(exc)
    save(out/'commands.json', commands)
    save(out/'result.json', report)
    print(json.dumps(report, sort_keys=True), flush=True)
    return report['state'] != 'M8_GNU_SPIKE_CHECKED'


if __name__ == '__main__':
    raise SystemExit(main())
