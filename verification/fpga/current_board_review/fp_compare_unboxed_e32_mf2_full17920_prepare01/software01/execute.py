#!/usr/bin/env python3
"""Single conditional generation, independent original-C Host, fixed dualcompile."""
import difflib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BASE = ROOT.parent / 'fp_compare_unboxed_full17920_prepare01'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def main():
    gen = module('fp32_source_generator', HERE / 'generate.py')
    common = module('sealed_fixed_compile', BASE / 'compile01/execute.py')
    save, text, sha, require = gen.save, gen.text, gen.sha, gen.require
    out = HERE / 'execution01'
    out.mkdir()
    pins = {str(p): sha(p) for p in [Path(__file__), HERE / 'host.c', HERE / 'generate.py',
            BASE / 'compile01/execute.py', ROOT / 'source_review01/review.json',
            common.CC.resolve(), Path('/usr/bin/gcc').resolve()]}
    save(out / 'stage_inputs.json', pins)
    try:
        common.command([sys.executable, HERE / 'generate.py'], out / 'generate', timeout=120)
        source = HERE / 'generated01/software'
        generated = HERE / 'generated01'
        pins.update(json.loads((generated / 'artifact_pins.json').read_text()))
        pins.update(json.loads((generated / 'inputs_after.json').read_text()))
        for p, digest in pins.items():
            require(sha(Path(p)) == digest, 'Generated source drift ' + p)
        host = out / 'host'
        host.mkdir()
        for name in ('case.c', 'generated_tables.h'):
            shutil.copyfile(source / name, host / name)
        core = (source / 'packed_core.h').read_text()
        begin, end = core.index('#define SD_AT('), core.index('#define ALL_16_SD(')
        adapted = core[:begin] + '#define SD_AT(b,o,v) host_store(b,o,(uint64_t)(v),8)\n#define SH_AT(b,o,v) host_store(b,o,(uint64_t)(v),2)\n' + core[end:]
        begin = adapted.index('static inline uint32_t result_and_guards')
        end = adapted.index('static inline unsigned packed_errors')
        adapted = adapted[:begin] + 'static inline uint32_t result_and_guards(const void *p) {return host_lwu(p);}\n\n' + adapted[end:]
        require(adapted[adapted.index('static inline unsigned packed_errors'):] ==
                core[core.index('static inline unsigned packed_errors'):], 'Unmodified packed error C')
        text(host / 'packed_core.h', adapted)
        text(host / 'core_adapter.diff', ''.join(difflib.unified_diff(core.splitlines(True), adapted.splitlines(True))))
        original = (source / 'original/parent.c').read_text()
        indices = original[original.index('static unsigned bit('):original.index('void probe_main(')]
        begin = original.index('        if((uint32_t)status)')
        end = original.index('        if(errors!=prior', begin)
        oracle_begin_line = original[:begin].count('\n') + 1
        oracle_body = original[begin:end]
        text(host / 'original_oracle.h', indices + '\nstatic unsigned original_oracle(unsigned op,unsigned seed,unsigned vl,unsigned mode,unsigned sticky,uint64_t status,unsigned *returned_flags) {\n'
             'unsigned cap=16,bytes=2,start=0,errors=0,flags=sticky;\n(void)mode;\n' + oracle_body +
             '*returned_flags=flags;return errors;\n}\n')
        # Execute the full original C loops/oracle/diagnostic formatting as a separate Host binary.
        original_host = original[:original.index('__asm__(".global _start')]
        begin, end = original_host.index('static long syscall3('), original_host.index('static void text(')
        original_host = original_host[:begin] + 'extern long replay_write(long,long,long,long);\n#define syscall3 replay_write\n' + original_host[end:]
        original_host = gen.replace_once(original_host, 'void probe_main(void)', 'int ' + gen.NAME + '_main(void)')
        original_host = gen.replace_once(original_host, 'syscall3(94,2,0,0);for(;;){}', 'return 2;')
        original_host = gen.replace_once(original_host, 'syscall3(94,errors ? 1:0,0,0);for(;;){}', 'return errors ? 1:0;')
        text(host / 'original_case.c', original_host)
        text(host / 'original_host_adapter.diff', ''.join(difflib.unified_diff(original.splitlines(True), original_host.splitlines(True))))
        save(host / 'oracle_origin.json', dict(original_sha256=sha(source / 'original/parent.c'),
             exact_oracle_begin_line=oracle_begin_line,
             original_oracle_text=oracle_body, unchanged_functions=indices,
             numerical_method='Full original C and literal original fixture table; not Python-model agreement'))
        defs = ['-DSEW=32' if x == '-DSEW=16' else x for x in common.DEFS]
        host_flags = ['-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-const-variable',
                      '-fsanitize=undefined', '-fsanitize-undefined-trap-on-error']
        for kind in ('original', 'packed'):
            common.command(['/usr/bin/gcc', *host_flags, *defs, '-DORIGINAL_RUN=' + str(int(kind == 'original')),
                 '-I' + str(host), '-I' + str(source / 'original'), HERE / 'host.c', '-o', host / kind],
                 host / ('compile_' + kind), timeout=120)
        tests = {}
        for mode in ('positive', 'details', 'all_errors'):
            outputs = []
            for kind in ('original', 'packed'):
                label = kind + '_' + mode
                tests[label] = common.command([host / kind, mode], host / label, timeout=120)
                log = (host / (label + '.log')).read_text()
                require('HOST_PASS original=' in log, 'Actual complete Host receipt')
                outputs.append('\n'.join(line for line in log.splitlines() if not line.startswith('HOST_PASS ')))
            require(outputs[0] == outputs[1], 'Byte-exact original diagnostics: ' + mode)
        for mode, reason in [('missing_same_input', 'event_count == 49'),
                             ('missing_same_mask', 'event_count == 49'),
                             ('missing_same_tail', 'event_count == 49'),
                             ('wrong_high_input', 'a[i] == inputs'),
                             ('wrong_raw_seed', 'b[i] == inputs')]:
            tests[mode] = common.command([host / 'packed', mode], host / mode, timeout=120, expected=90)
            require('HOST_REJECT' in (host / (mode + '.log')).read_text() and
                    reason in (host / (mode + '.log')).read_text(), 'Exact negative cause ' + mode)
        save(host / 'RESULT.json', dict(status='ORIGINAL_C_FULL17920_NUMERICAL_PASS_NOT_REFERENCE',
             full_modes=['positive', 'details', 'all_errors'], full_cases_per_mode=17920,
             per_packed_mode_original_C_oracle_comparisons=430080, stores_per_call=49,
             all_input_upper_BSS_checked=True, diagnostics_compared_byte_exact=True,
             UB_trap_instrumentation=True, tests=tests))
        print('HOST_NUMERICAL_PASS; entering fixed dualcompile', flush=True)
        for name in ('as', 'ld', 'cc1'):
            tool = Path(subprocess.check_output([str(common.CC), '-print-prog-name=' + name], text=True).strip()).resolve()
            require(tool.is_file(), 'Pinned GCC component ' + name)
            pins[str(tool)] = sha(tool)
        save(out / 'FIXED_CONFIGURATION.json', dict(compiler=str(common.CC), flags=common.FLAGS,
             defines=defs, backends=['soc', 'spike'], source=str(source), retries=0,
             original_Linux_recompiled=False, reference=False, DUT=False))
        binaries = {}
        for backend in ('soc', 'spike'):
            dest = out / backend
            dest.mkdir()
            elf = dest / 'program.elf'
            extra = ['-DSPIKE_REFERENCE=1'] if backend == 'spike' else []
            command = [common.CC, *common.FLAGS, *defs, *extra, '-T', source / 'replay.ld',
                 '-Wl,-Map=' + str(dest / 'program.map'), '-I' + str(source / 'original'),
                 source / 'case.c', source / 'original/scenario.S', source / 'main.c',
                 source / 'startup.S', source / 'runtime.c', '-lgcc', '-o', elf]
            common.command(command, dest / 'compile', timeout=120)
            common.command([common.CC.with_name('riscv64-unknown-elf-objdump'), '-d', elf], dest / 'disassemble')
            common.command([common.CC.with_name('riscv64-unknown-elf-nm'), '-S', '-n', elf], dest / 'symbols')
            common.command([common.CC.with_name('riscv64-unknown-elf-readelf'), '-l', '-A', elf], dest / 'layout')
            binaries[backend] = dict(path=str(elf), sha256=sha(elf))
        require(all(sha(Path(p)) == h for p, h in pins.items()), 'Input/tool drift')
        save(out / 'inputs_after.json', pins)
        save(out / 'RESULT.json', dict(status='HOST_NUMERICAL_PASS_DUAL_COMPILED_CFG_PENDING',
             binaries=binaries, source_pins_unchanged=True, reference=False, DUT=False))
        print(json.dumps(binaries), flush=True)
    except BaseException as error:
        save(out / 'FIRST_FAILURE.json', dict(type=type(error).__name__, error=str(error),
             retries=0, reference=False, DUT=False))
        raise


if __name__ == '__main__':
    main()
