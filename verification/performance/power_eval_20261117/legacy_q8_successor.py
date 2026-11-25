#!/usr/bin/env python3
"""Rebuild the preserved legacy Q8 workload, not RTL; never launch a simulator.

Descriptor v1 in the original ELF is rejected by the DC-matched v2 decoder.
Use reviewed SDK sources, identical captured blobs/shape/tolerance, prebuilt
descriptors (as in the original ELF), and a private valid-mtvec CRT adaptation.
This is a successor measurement, not instruction/cycle equivalence to the old ELF.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile

ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
OLD = OUT / 'power_legacy_q8_prepare_20261117_01/qbs'
RUN = OUT / 'power_precheck_20261117_native_projection_01/runs/legacy_q8_qbs'
SDK = 'dbe2b78817ef45b912444afcb85ad6e01a2be135'
TOOLS = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin')
ARCHIVE = ('apps/common', 'apps/llama_qwen25_q8_0_decode_attn_q_qbs',
           'apps/llama_qwen25_real/common', 'apps/llama_q4k_repack_bench',
           'apps/llama_q4km_micro', 'software/qbs')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1048576), b''):
            h.update(data)
    return h.hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def save(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2) + '\n')


def analyze():
    pins = json.loads((OLD / 'source-pins.json').read_text())
    for path, expected in pins.items():
        require(sha(path) == expected, 'Original frozen input drift: ' + path)
    rows = list(csv.DictReader((RUN / 'commit.csv').open()))
    data = {}
    for row in rows:
        if row['event'] != 'retire':
            continue
        address, mask, value = (int(row[key], 16) for key in ('mem_addr', 'mem_wmask', 'mem_wdata'))
        for i in range(8):
            if mask >> i & 1:
                data[address + i] = (value >> (8 * i)) & 255
    descriptor = bytes(data[a] for a in range(0x8003e780, 0x8003e790))
    header, weight = struct.unpack('<QQ', descriptor)
    require(header == 0x37f12261 and weight == 0x80001580, 'Unexpected original descriptor')
    vector = list(csv.DictReader((RUN / 'vector.csv').open()))
    qbs = [r for r in vector if r['event'] == 'alloc' and r['insn'] == '00b5045b']
    require(len(qbs) == 1 and qbs[0]['vstart'] == '0', 'Unexpected QBS allocation')
    with (RUN / 'run.vcs.log').open(errors='replace') as stream:
        perf = next(line.strip() for line in stream if line.startswith('[QBS_PERF]'))
    require('validation_error=2 ' in perf and 'validation_fault=1 ' in perf and
            'payload_bytes=16 ' in perf and 'phase_compute_cycles=0 ' in perf, 'Unexpected QBS fault')
    return dict(fault_pc='0x800003bc', instruction='0x00b5045b', operation='qbexec v8,a0,a1; M=1',
                descriptor_address='0x8003e780', descriptor_bytes=descriptor.hex(),
                descriptor_version=header & 15, required_descriptor_version=2,
                expected_successor_header='0x37f12262', vstart=0,
                expected_exception=dict(cause=2, tval=0, basis='frozen vlsu validation-fault mapping'),
                cause='QBS descriptor version 1 rejected by version 2 decoder; not vstart',
                secondary='CRT at 0x8000005a writes PMP value 0x001fffffffffffff to mtvec',
                qbs_perf=perf, evidence={str(RUN / n): sha(RUN / n)
                                       for n in ('commit.csv', 'vector.csv', 'result.json')})


def build(out):
    require(out.parent == OUT and out.name.startswith('power_legacy_q8_successor_20261117_')
            and not out.exists(), 'Fresh successor output required')
    analysis = analyze()
    out.mkdir()
    save(out / 'analysis.json', analysis)
    archive = subprocess.check_output(['git', '-C', str(ROOT), 'archive', SDK, *ARCHIVE])
    (out / 'sdk.tar').write_bytes(archive)
    source = out / 'source'
    source.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for item in tar:
            rel = Path(item.name)
            require(not rel.is_absolute() and '..' not in rel.parts, 'Unsafe archive')
            if item.isdir():
                (source / rel).mkdir(parents=True, exist_ok=True)
            else:
                require(item.isfile(), 'Unsupported SDK archive entry')
                (source / rel).parent.mkdir(parents=True, exist_ok=True)
                (source / rel).write_bytes(tar.extractfile(item).read())
    originals = {str(p.relative_to(source)): sha(p) for p in source.rglob('*') if p.is_file()}
    for name in ('activation_f32.bin', 'embedded_weight.bin', 'source_weight.bin',
                 'golden_f32.bin', 'provenance.json'):
        shutil.copyfile(OLD / name, out / name)
        require(sha(out / name) == sha(OLD / name), 'Blob copy drift')
    shutil.copyfile(__file__, out / 'legacy_q8_successor.py')
    shutil.copyfile(OLD / 'legacy_q8.py', out / 'original_checker.py')
    common = source / 'apps/common'
    crt = (common / 'crt0.S').read_text()
    preimage = '#if defined(ARA_FPGA)\n    la      t0, trap_vector\n#endif\n    csrw    mtvec, t0'
    require(crt.count(preimage) == 1, 'CRT preimage mismatch')
    crt = crt.replace(preimage, '    la      t0, trap_vector\n    csrw    mtvec, t0')
    (out / 'crt0.S').write_text(crt)
    # Only a private diagnostic replacement: report full RV64 CSRs; do not use
    # the SDK printer's int32_t/%lu mismatch for high addresses.
    (out / 'trap_report.c').write_text(
        '#include "printf.h"\n'
        'void print_trap_cause(void) {\n'
        '  unsigned long cause, epc, tval, tvec;\n'
        '  __asm__ volatile("csrr %0,mcause":"=r"(cause));\n'
        '  __asm__ volatile("csrr %0,mepc":"=r"(epc));\n'
        '  __asm__ volatile("csrr %0,mtval":"=r"(tval));\n'
        '  __asm__ volatile("csrr %0,mtvec":"=r"(tvec));\n'
        '  printf("Q8_TRAP cause=0x%lx epc=0x%lx tval=0x%lx tvec=0x%lx\\n",cause,epc,tval,tvec);\n'
        '}\n')
    asm = '.section .rodata,"a",@progbits\n'
    for symbol, name in (('weight', 'embedded_weight.bin'), ('activation', 'activation_f32.bin'),
                         ('golden', 'golden_f32.bin')):
        label = 'benchmark_' + symbol
        asm += (f'.balign 64\n.global {label}_start\n{label}_start:\n'
                f'.incbin "{out / name}"\n.global {label}_end\n{label}_end:\n')
    (out / 'data.S').write_text(asm)
    cc = TOOLS / 'riscv64-unknown-elf-gcc'
    flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax',
             '-O3', '-fno-fast-math', '-ffp-contract=off', '-fno-tree-vectorize',
             '-ffunction-sections', '-fdata-sections', '-DNR_LANES=4', '-DVLEN=1024',
             '-DQBS_BENCH_PREBUILT_DESCRIPTOR=1', '-I' + str(common),
             '-I' + str(source / 'software/qbs/include')]
    commands = []

    def run(label, argv):
        commands.append(dict(label=label, argv=[str(x) for x in argv]))
        save(out / 'commands.json', commands)
        with (out / (label + '.log')).open('x') as stream:
            subprocess.run(argv, cwd=out, stdout=stream, stderr=subprocess.STDOUT,
                           timeout=180, check=True)

    obj = out / 'objects'
    obj.mkdir()
    sources = [out / 'crt0.S', *(common / n for n in ('printf.c', 'string.c', 'serial.c', 'util.c')),
               out / 'trap_report.c', out / 'data.S',
               source / 'apps/llama_qwen25_q8_0_decode_attn_q_qbs/main.c']
    objects = []
    for src in sources:
        dest = obj / (src.stem + '.o')
        run('compile-' + src.stem, [cc, *flags, '-fno-builtin', '-c', src, '-o', dest])
        objects.append(dest)
    run('linker', [cc, '-E', '-P', '-x', 'c', '-DALIGNMENT=16',
                   common / 'arch.link.ld', '-o', out / 'link.ld'])
    elf = out / 'operator.elf'
    run('link', [cc, *flags, '-static', '-nostartfiles', '-nostdlib', *objects,
                 '-Wl,--gc-sections', '-Wl,-Map=' + str(out / 'link.map'), '-T', out / 'link.ld',
                 '-Wl,--start-group', '-lm', '-lc', '-lgcc', '-lnosys', '-Wl,--end-group', '-o', elf])
    run('disassembly', [TOOLS / 'riscv64-unknown-elf-objdump', '-d', elf])
    data = elf.read_bytes()
    phoff = struct.unpack_from('<Q', data, 32)[0]
    phsize, phnum = struct.unpack_from('<HH', data, 54)
    for i in range(phnum):
        kind, _, _, va, _, filesz, memsz, _ = struct.unpack_from('<IIQQQQQQ', data, phoff+i*phsize)
        if kind == 1:
            require(0x80000000 <= va <= va+memsz <= 0x80100000 and filesz <= memsz,
                    'ELF does not fit low 1 MiB')
    for name in ('activation_f32.bin', 'embedded_weight.bin', 'golden_f32.bin'):
        require((out / name).read_bytes() in data, 'Missing exact capture: ' + name)
    save(out / 'build.json', dict(state='SOFTWARE_BUILT_NOT_SIMULATED', sdk_commit=SDK,
         shape=dict(m=1, n=256, k=896), descriptor_version=2, prebuilt_descriptors=True,
         unchanged_captured_inputs=True, atol=0.002, rtol=0.002, sim_l2_bytes=1048576,
         private_adaptations=['valid mtvec in CRT', 'full-width CSR trap printer'],
         archived_source_hashes=originals, old_elf_sha256=sha(OLD / 'operator.elf'),
         successor_elf_sha256=sha(elf), simulations_launched=0,
         caveat='Successor SDK code/timing is not instruction-identical to old ELF; use same successor for later GLS'))
    save(out / 'manifest.json', dict(cases=[dict(id='legacy_q8_qbs_sdk_v2_successor',
        category='projection', elf=str(elf), elf_sha256=sha(elf), timeout_seconds=10800,
        source_pins=str(out / 'source-pins.json'), plusargs=['+QBS_PERF'],
        checker=['/usr/bin/python3', '-B', str(out / 'original_checker.py'), 'check',
                 '--build', str(out), '--log', '{log}', '--output', '{result}', '--mode', 'qbs'])],
        max_campaign_rtl_prechecks=4, successor_prechecks_run=0))
    save(out / 'source-pins.json', {str(p): sha(p) for p in out.rglob('*') if p.is_file()})
    print(json.dumps(dict(state='SOFTWARE_BUILT_NOT_SIMULATED', output=str(out))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('analyze', 'build'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.action == 'analyze':
        print(json.dumps(analyze(), indent=2))
    else:
        require(args.output is not None, '--output required')
        build(args.output.resolve())


if __name__ == '__main__':
    main()
