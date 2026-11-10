#!/usr/bin/env python3
"""Freeze accepted dependencies; bounded host/GNU/Spike correctness only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
LLAMA = Path('/home/wangwy/llama/llama.cpp')
BASE = 'da56aa750559c180d631b466de983ff2bb5d54d9'
SDK = 'd3d92ad72a3cabb91e8c333186160ae422f0866b'
HELPER = ROOT/'software/qbs/experimental/m4_preflight'
CXX = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-g++')
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
REAL = OUT/'m4-prepared-qkv-build-20261027-02/activation_f32.bin'
REAL_SHA = '913afc315e1a3da1191ec74fe9faab17bdf25d4c672624a2c65192438cc8beb1'
ACCEPTED = {
    'q8_K-m4-packed.h': '969ee4656a6e67e167cd298bff10bccbd4993b95f8eef918f1056ed1791d5993',
    'q8_K-m4.h': '5ff0dce85d5d2d1c5e8eec99d369d2a6a6c6badd6323866f1347c60690b501d2',
    'q8_K-signed-max.h': 'f6d442fc7b5a0f73423719c10db223433fdb5b7c69d5db47963365892e2b5917',
    'q8_K-m4-group-sums.h': '8fc4d6a4e16b464b295e6097d5510e7264bd3d33ad9001e09eeb66fd779e8997',
}
SUMMARY = ('STAGE4_M4_PREFLIGHT_PASS checks=323 metadata=178 real=256 large=11 '
           'vector=286 generic=37 fallback_entries=74 bytes_flags_guards=exact performance=not_measured')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, why):
    if not condition:
        raise ValueError(why)


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def check_spike(log, returncode, vlen):
    require(returncode == 0, 'Spike process failed')
    require(log.splitlines().count(SUMMARY) == 1, 'Missing/extraneous exact target extent')
    require('FAIL' not in log and 'TRAP' not in log, 'Target failure/trap')
    require(len(re.findall(r'^0x0000000000000000$', log, re.M)) == 1, 'Exit register not zero')
    require(log.splitlines().count('STAGE4_M4_VLEN bits='+str(vlen)) == 1, 'Actual VLEN mismatch')


def audit_preflight(disassembly):
    bodies = []
    for section in re.split(r'(?=^[0-9a-f]+ <)', disassembly, flags=re.M):
        name = section.splitlines()[0] if section else ''
        if 'qbs_experimental_m4_preflight::preflight<' in name or 'bool preflight_probe<' in name:
            bodies.append(section)
    require(bool(bodies), 'No retained-preflight disassembly')
    text = '\n'.join(bodies)
    require('vredmaxu.vs' in text and 'vredminu.vs' in text, 'Integer extrema/index reductions absent')
    require(not re.search(r'\s(?:v?f(?:add|sub|mul|div|macc|madd|msub|nmadd|nmsub|sqrt|min|max|cvt|eq|lt|le)[.\w]*)\s', text),
            'FP arithmetic in preflight')
    return len(bodies)


class Gate:
    def __init__(self, out):
        self.out = out
        self.pins = {}
        self.commands = []

    def pin(self, path):
        path = Path(path).resolve(strict=True)
        value = digest(path)
        require(str(path) not in self.pins or self.pins[str(path)] == value, 'Pin changed: '+str(path))
        self.pins[str(path)] = value

    def run(self, label, argv, timeout=180, cwd=None, binary=None):
        argv = list(map(str, argv)); cwd = Path(cwd or self.out)
        executable = shutil.which(argv[0]) if '/' not in argv[0] else argv[0]
        self.pin(executable)
        record = dict(label=label, argv=argv, cwd=str(cwd), timeout_seconds=timeout, start_ns=time.time_ns())
        self.commands.append(record); write(self.out/'commands.json', self.commands)
        log = self.out/(binary or label+'.log')
        try:
            with log.open('xb') as stream:
                result = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                        timeout=timeout, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
            record['returncode'] = result.returncode
            require(result.returncode == 0, label+' failed; original log preserved')
        finally:
            record['end_ns'] = time.time_ns()
            record['log'] = str(log)
            if log.exists(): record['log_sha256'] = digest(log)
            write(self.out/'commands.json', self.commands)
        return log.read_text() if binary is None else log

    def archive(self, repo, sha, paths, directory, label):
        archive = self.run(label, ['git', '-C', repo, 'archive', '--format=tar', sha, *paths], binary=label+'.tar')
        directory.mkdir()
        self.run(label+'-extract', ['tar', '-xf', archive, '-C', directory])
        for path in directory.rglob('*'):
            if path.is_file(): self.pin(path)

    def verify(self):
        for path, value in self.pins.items(): require(digest(path) == value, 'Source/tool drift: '+path)


def execute(out):
    require(out.parent == OUT and re.fullmatch(r'stage4_m4_preflight_[A-Za-z0-9_]+', out.name)
            and not out.exists(), 'Fresh stage4_m4_preflight_* output required')
    out.mkdir(); gate = Gate(out)
    report = dict(state='PREPARING', baseline_llama=BASE, sdk=SDK, performance_measured=False,
                  scope='Host/GNU/Spike producer correctness only; no RTL, QBS execution, GGML graph or cycles')
    try:
        inputs = out/'inputs'; inputs.mkdir()
        for source in [*sorted(HERE.glob('*')), *sorted(HELPER.glob('*'))]:
            if source.is_file():
                gate.pin(source); destination = inputs/source.name
                require(not destination.exists(), 'Source basename collision')
                shutil.copyfile(source, destination); gate.pin(destination)
        gate.archive(LLAMA, BASE, ['ggml'], inputs/'llama', 'archive-llama')
        gate.archive(ROOT, SDK, ['software/qbs/include'], inputs/'sdk', 'archive-sdk')
        ggml = inputs/'llama/ggml'; arch = ggml/'src/ggml-cpu/arch/riscv'
        for name, sha in ACCEPTED.items(): require(digest(arch/name) == sha, 'Unaccepted dependency: '+name)
        require(REAL.stat().st_size == 24576 and digest(REAL) == REAL_SHA, 'Real capture identity')
        provenance = REAL.parent/'manifest.json'
        require(json.loads(provenance.read_text()).get(str(REAL)) == REAL_SHA, 'Real capture manifest')
        gate.pin(REAL); gate.pin(provenance)
        shutil.copyfile(REAL, inputs/'real.bin'); gate.pin(inputs/'real.bin')
        data = inputs/'data.S'
        data.write_text('.section .rodata\n.balign 64\n.global real_input\nreal_input:\n.incbin "'+str(inputs/'real.bin')+'"\n')
        gate.pin(data)
        include = [f'-I{inputs}']
        for directory in (ggml/'include', ggml/'src', ggml/'src/ggml-cpu', arch,
                          inputs/'sdk/software/qbs/include'):
            include += ['-isystem', str(directory)]
        host = gate.run('host-contracts', [sys.executable, '-B', '-m', 'unittest', 'test_host', '-v'], cwd=inputs)
        require('Ran 8 tests' in host and '\nOK\n' in host, 'Host test extent')
        gate.run('host-compile', ['g++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', *include,
                                  inputs/'host.cpp', '-o', out/'host'])
        host_result = gate.run('host-run', [out/'host'], timeout=30)
        require(host_result.strip() == 'STAGE4_M4_HOST_PASS non_rvv_fallback=4 metadata_bytes=384 cache_checks=9', 'Host fallback/cache extent')
        flags = ['-std=c++17', '-O3', '-DNDEBUG', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d',
                 '-mcmodel=medany', '-mno-relax', '-fno-fast-math', '-ffp-contract=fast',
                 '-ffunction-sections', '-fdata-sections', '-fno-exceptions', '-fno-rtti',
                 '-fno-stack-protector', '-msmall-data-limit=0', *include]
        objects = []
        for name, source, extra in (
            ('frozen-repack', ggml/'src/ggml-cpu/repack.cpp',
             ['-Dggml_quantize_mat_q8_K_4x1_ara_generic=frozen_generic']),
            ('test', inputs/'test.cpp', ['-Wall', '-Wextra', '-Werror']),
            ('runtime', inputs/'runtime.cpp', ['-ffreestanding', '-fno-builtin', '-fno-tree-loop-distribute-patterns']),
            ('start', inputs/'start.S', []), ('data', data, [])):
            args = [CXX, *flags, *extra]
            if source.suffix != '.S':
                deps = gate.run(name+'-deps', [*args, '-M', '-MT', 'unit', source])
                for path in shlex.split(deps.replace('\\\n', ' ').split(':', 1)[1]): gate.pin(path)
            obj = out/(name+'.o'); objects.append(obj)
            gate.run(name+'-compile', [*args, '-c', source, '-o', obj])
            gate.pin(obj)
        for name in ('cc1plus', 'as', 'ld'):
            tool = gate.run('locate-'+name, [CXX, '-print-prog-name='+name]).strip(); gate.pin(tool)
        library = gate.run('locate-libgcc', [CXX, '-print-libgcc-file-name']).strip(); gate.pin(library)
        elf = out/'test.elf'
        gate.run('link', [CXX, *flags, '-nostdlib', '-static', *objects, '-Wl,--gc-sections',
                          '-Wl,--build-id=none', '-Wl,-Map='+str(out/'link.map'), '-T', inputs/'link.ld', library, '-o', elf])
        gate.pin(elf)
        dis = gate.run('disassembly', [CXX.with_name('riscv64-unknown-elf-objdump'), '-dC', elf])
        report['integer_preflight_bodies'] = audit_preflight(dis)
        require('vfmacc.vf' in dis and 'vsse16.v' in dis and 'vse32.v' in dis, 'Accepted packed/parallel producer absent')
        symbols = gate.run('symbols', [CXX.with_name('riscv64-unknown-elf-nm'), '-n', elf])
        def symbol(name):
            matches = re.findall(r'^([0-9a-f]+) \w '+re.escape(name)+r'$', symbols, re.M)
            require(len(matches) == 1, 'Missing symbol '+name)
            return matches[0]
        debug = out/'spike.cmd'
        debug.write_text('until pc 0 '+symbol('test_exit')+'\nreg 0 a0\nstr '+symbol('test_log')+'\nrs\n')
        gate.pin(debug)
        write(out/'source-pins.json', gate.pins); gate.verify()
        configurations = []
        for vlen in (128, 256, 512, 1024):
            log = gate.run('spike-'+str(vlen), [SPIKE, '-d', '--debug-cmd='+str(debug),
                           '--isa=rv64gcv_zfh_zvfh_zvl'+str(vlen)+'b', '-m2', elf], timeout=180)
            check_spike(log, 0, vlen)
            configurations.append(dict(vlen=vlen, checks=323, metadata=178, real=256,
                                       log_sha256=digest(out/('spike-'+str(vlen)+'.log'))))
        gate.verify(); write(out/'source-pins.json', gate.pins)
        report.update(state='PASS', host_tests=8, host_non_rvv_fallback=4, host_cache_checks=9,
                      configurations=configurations, elf_sha256=digest(elf),
                      source_pins_sha256=digest(out/'source-pins.json'), post_pins_match=True,
                      accepted_dependencies=ACCEPTED, real_input_sha256=REAL_SHA)
    except BaseException as error:
        report.update(state='FAIL', error=repr(error)); raise
    finally:
        write(out/'source-pins.json', gate.pins)
        write(out/'result.json', report)
        print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    execute(parser.parse_args().output.resolve())
