#!/usr/bin/env python3
"""Bounded client checks. Spike tests CSR wrappers, not Linux or custom compute."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
HERE = Path(__file__).resolve().parent
CLIENT = ROOT / 'software/llama/platform/linux'
GNU = Path('/home/wangwy/llama/platforms/cva6-qemu/tools/bin')
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    assert out.parent == OUT and out.name.startswith('resident_deployment_client_') and not out.exists()
    out.mkdir()
    sources = [Path(__file__).resolve(), *[CLIENT / p for p in
        ('client_v2.c', 'client.h', 'client_rv64.S', 'ara_resident_uapi.h', 'job_layout.h')],
        *[HERE / p for p in ('test_linux_client_v2.c', 'test_client_csr.c', 'client.ld', 'client_start.S')]]
    pins = {str(p): sha(p) for p in sources}
    commands = []

    def run(name, argv):
        result = subprocess.run(list(map(str, argv)), cwd=ROOT, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        (out / (name + '.log')).write_text(result.stdout)
        commands.append(dict(name=name, argv=list(map(str, argv)), returncode=result.returncode))
        assert result.returncode == 0, (name, result.stdout[-4000:])
        return result.stdout

    report = dict(state='FAIL', linux_executed=False, custom_compute_executed=False,
                  board_executed=False, automatic_retry=False)
    try:
        for compiler, flags, label in (('/usr/bin/gcc', [], 'gnu'),
                ('/usr/lib64/ccache/clang', ['-fsanitize=undefined', '-fno-sanitize-recover=all'], 'ubsan')):
            binary = out / label
            run(label + '-build', [compiler, '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror',
                *flags, '-DARA_RESIDENT_CLIENT_TEST', '-I'+str(CLIENT),
                HERE/'test_linux_client_v2.c', CLIENT/'client_v2.c', '-o', binary])
            assert 'RESIDENT_LINUX_CLIENT_PASS layouts=6144' in run(label, [binary])
        elf = out/'client-csr.elf'
        flags = ['-O2', '-std=gnu11', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany',
            '-mno-relax', '-msmall-data-limit=0', '-fno-stack-protector', '-fno-tree-vectorize',
            '-fno-tree-slp-vectorize', '-fno-builtin', '-ffreestanding', '-I'+str(CLIENT)]
        run('target-build', [GNU/'riscv64-linux-gcc', *flags, '-nostdlib', '-static',
            '-T'+str(HERE/'client.ld'), HERE/'client_start.S', HERE/'test_client_csr.c',
            CLIENT/'client_rv64.S', '-lgcc', '-o', elf])
        symbols = run('symbols', [GNU/'riscv64-linux-nm', '-n', elf])
        match = re.findall(r'^([0-9a-f]+) T test_exit$', symbols, re.M)
        assert len(match) == 1
        debug = out/'debug.cmd'
        debug.write_text('until pc 0 '+match[0]+'\nreg 0 a0\nquit\n')
        log = run('spike-csr', [SPIKE, '-d', '--debug-cmd='+str(debug),
            '--isa=rv64gcv_zfh_zvfh_zvl1024b', '-m2', elf])
        assert re.findall(r'^0x[0-9a-f]+$', log, re.M) == ['0x0000000000000000'], log
        obj = out/'client.o'
        run('scalar-build', [GNU/'riscv64-linux-gcc', *flags, '-c', CLIENT/'client_v2.c', '-o', obj])
        dis = run('scalar-disassembly', [GNU/'riscv64-linux-objdump', '-d', obj])
        ops = re.findall(r'^\s*[0-9a-f]+:\s+[0-9a-f]+\s+([a-z][a-z0-9_.]*)', dis, re.M)
        assert ops and 'ecall' in ops and not any(op.startswith(('v', 'f')) for op in ops), ops
        assert all(sha(p) == digest for p, digest in pins.items())
        report.update(state='CLIENT_HOST_AND_RV64_CSR_CHECKED', source_pins_match=True,
            valid_layouts_per_host=6144, invalid_jobs_per_host=19, malformed_info_per_host=9,
            no_retry_error_paths_per_host=4, os_admission_rejections_per_host=8, csr_cases=3, scalar_client_no_fp_vector=True,
            elf_sha256=sha(elf))
    except Exception as error:
        report['error'] = repr(error)
    (out/'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
    (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
    (out/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))
    return int(report['state'] == 'FAIL')


if __name__ == '__main__':
    raise SystemExit(main())
