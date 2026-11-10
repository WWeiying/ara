#!/usr/bin/env python3
"""Build two unchanged HEAD smoke apps privately with GNU GCC; never execute them."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
BASE = ROOT / 'verification/performance/chain_profile/q6_decode/build.py'
TOOLCHAIN = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin')
CASES = {
    'qbs_control_smoke': dict(pass_line='QBS control smoke (enabled): PASS',
        expected_exception_instructions=[0x0205155b, 0x00b5045b],
        required_words=[0x0005155b, 0x0205155b, 0x00b5045b, 0x04b5045b]),
    'qbs_akv_handoff_smoke': dict(pass_line='QBS/AKV handoff smoke: PASS traps=0',
        expected_exception_instructions=[],
        required_words=[0x0005155b, 0x0005455b, 0x00b5045b, 0x00b5605b,
                        0x0005345b, 0x0000505b]),
}
ARCHIVE = ('apps/common', *(f'apps/{name}' for name in CASES))
RUNTIME = ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')


def load_helper():
    source = HERE / 'q6_build.py' if (HERE / 'q6_build.py').is_file() else BASE
    spec = importlib.util.spec_from_file_location('smoke_build_tools', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = ROOT
    return module, source


def check_log(case, text):
    """Only an enabled case PASS plus successful EOC is acceptable, never SKIP."""
    marker = CASES[case]['pass_line']
    if sum(line.strip() == marker for line in text.splitlines()) != 1:
        raise ValueError('Missing/duplicate exact enabled case PASS')
    if len(re.findall(r'Core Test \*\*\* SUCCESS \*\*\* \(tohost = 0\)', text)) != 1:
        raise ValueError('Missing/duplicate successful EOC')
    if re.search(r'(?im)(\bSKIP\b|\bFAIL(?:ED)?\b|\bTIMEOUT\b|\bTIMED OUT\b|'
                 r'\bdisabled\b|Error-\[|\bError:|\bFatal:|\$fatal|Assertion failed)', text):
        raise ValueError('Skipped, disabled, failed, or fatal smoke')
    for line in text.splitlines():
        if re.search(r'\bUVM_(ERROR|FATAL)\b', line) and not re.fullmatch(
                r'\s*UVM_(ERROR|FATAL)\s*:\s*0\s*', line):
            raise ValueError('UVM error/fatal cannot be waived for expected traps')
    return dict(case=case, exact_pass_line=marker, successful_eoc=True, skip_accepted=False)


def build(out):
    base, helper_path = load_helper()
    base.require(out.parent == OUT and re.fullmatch(r'stage2_smoke_build_[A-Za-z0-9_]+', out.name)
                 and not out.exists(), 'Fresh direct stage2_smoke_build_* signoff output required')
    out.mkdir()
    b = base.Builder(out)
    b.pin(Path(__file__))
    b.pin(helper_path)
    b.pin(sys.executable)
    revision = b.run('source-head', ['git', '-C', ROOT, 'rev-parse', 'HEAD']).decode().strip()
    inputs = out / 'inputs'
    b.archive(ROOT, revision, ARCHIVE, inputs)
    for source, name in ((Path(__file__), 'build_smokes.py'), (helper_path, 'q6_build.py')):
        target = inputs / name
        shutil.copyfile(source, target)
        b.pin(target)
    for source in inputs.rglob('*'):
        if source.is_file():
            b.pin(source)
    common = inputs / 'apps/common'
    cc = TOOLCHAIN / 'riscv64-unknown-elf-gcc'
    objdump = TOOLCHAIN / 'riscv64-unknown-elf-objdump'
    version = b.run('compiler-version', [cc, '--version']).decode()
    for name in ('cc1', 'as', 'ld', 'collect2'):
        name_or_path = b.run('locate-' + name, [cc, '-print-prog-name=' + name]).decode().strip()
        b.pin(Path(name_or_path) if Path(name_or_path).is_file() else shutil.which(name_or_path))
    arch = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d']
    for name in ('libc.a', 'libm.a', 'libgcc.a', 'libnosys.a'):
        b.pin(b.run('locate-' + name, [cc, *arch, '-print-file-name=' + name]).decode().strip())
    flags = [*arch, '-std=gnu11', '-mcmodel=medany', '-mno-relax', '-O3',
             '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize',
             '-falign-functions=4', '-ffunction-sections', '-fdata-sections',
             '-DNR_LANES=4', '-DVLEN=1024', '-I' + str(common)]
    common_objects = []
    for name in RUNTIME:
        obj = out / (Path(name).stem + '.o')
        b.compile(cc, flags + (['-fno-builtin'] if name == 'string.c' else []), common / name, obj)
        common_objects.append(obj)
    link = out / 'link.ld'
    b.run('linker-script', [cc, '-E', '-P', '-x', 'c', '-DALIGNMENT=16',
                          common / 'arch.link.ld', '-o', link])
    b.pin(link)
    programs = {}
    for case, contract in CASES.items():
        work = out / case
        work.mkdir()
        source_dir = inputs / 'apps' / case
        sources = [source_dir / 'main.c']
        if (source_dir / 'data.S').is_file():
            sources.append(source_dir / 'data.S')
        objects = []
        for source in sources:
            obj = work / (source.stem + '.o')
            b.compile(cc, flags, source, obj)
            objects.append(obj)
        elf = work / (case + '.elf')
        b.run(case + '-link', [cc, *flags, '-static', '-nostartfiles', '-nostdlib',
            *objects, *common_objects, '-Wl,--gc-sections', '-Wl,-Map=' + str(work / 'link.map'),
            '-T', link, '-Wl,--start-group', '-lm', '-lc', '-lgcc', '-lnosys', '-Wl,--end-group',
            '-o', elf])
        disassembly = b.run(case + '-disassembly', [objdump, '-d', elf]).decode()
        words = {int(value, 16) for value in re.findall(
            r'(?m)^\s*[0-9a-f]+:\s+([0-9a-f]{8})\b', disassembly)}
        base.require(set(contract['required_words']) <= words, 'Missing native instructions: ' + case)
        if case == 'qbs_akv_handoff_smoke':
            base.require(all(op in disassembly for op in ('vle32.v', 'vadd.vi', 'vse32.v')),
                         'Missing normal RVV handoff work')
        symbols = b.run(case + '-symbols', [objdump, '-t', elf]).decode()
        handlers = re.findall(r'(?m)^([0-9a-f]+)\s+.*\bmtvec_handler$', symbols)
        base.require(len(handlers) == 1 and int(handlers[0], 16) % 4 == 0,
                     'Trap handler must have a direct-mode aligned address')
        for artifact in (elf, work / 'link.map'):
            b.pin(artifact)
        programs[case] = dict(elf=str(elf), elf_sha256=base.digest(elf), **contract)
    b.pin(out / 'commands.json')
    for path, digest in b.pins.items():
        base.require(base.digest(path) == digest, 'Build input drift: ' + path)
    base.write_json(out / 'source-pins.json', b.pins)
    base.write_json(out / 'build.json', dict(state='BUILT_NOT_EXECUTED', source_commit=revision,
        configuration=dict(nr_lanes=4, vlen=1024, march='rv64gcv_zfh_zvfh', abi='lp64d'),
        compiler=str(cc), compiler_version=version.splitlines()[0], compile_flags=flags,
        archive_paths=list(ARCHIVE), programs=programs, post_pins_match=True,
        source_pins_sha256=base.digest(out / 'source-pins.json'),
        dirty_makefile_used=False, sdk_akv_assembly_used=False, rtl_executed=False,
        scope='Fresh unchanged HEAD smoke ELF builds only; no simulation or performance acceptance'))
    print('BUILT_NOT_EXECUTED ' + str(out / 'build.json'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output.resolve())
