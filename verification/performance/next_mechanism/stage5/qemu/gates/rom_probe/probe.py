#!/usr/bin/env python3
"""One ROM-vs-RAM access-fault probe. GNU build/check only; never launches QEMU."""
import argparse
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
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
OWN = ('main.c', 'issue.S', 'probe.py', 'test_probe.py')
SEALED = dict(start_S='73487a725a226dd05202b05f26040b892ec554eb1baa86470d11333aa29eaa00',
    link_ld='180a2b423791af7025d2a49ac3be8eb57ed8ece14ab98de4e7ede2ccdda466b5',
    build_py='e8587cd81fbca28573d5e3e540055effd04891e3916734291110b7304c157846',
    check_py='32ae013e8a2ac995adfd23b2944e80cfe767210a26496d7c8bf85e118a22a31f')


def require(ok, message):
    if not ok: raise ValueError(message)
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text())
def save(path, value):
    with Path(path).open('x') as f: json.dump(value, f, indent=2, sort_keys=True); f.write('\n')
def verify(pins):
    for path, digest in pins.items(): require(sha(path) == digest, 'Pin drift: ' + str(path))
def dependencies():
    root = HERE/'sealed' if (HERE/'sealed').is_dir() else HERE.parent
    paths = {name.replace('_', '.'): root/name.replace('_', '.') for name in SEALED}
    verify({paths[name.replace('_', '.')]: digest for name, digest in SEALED.items()})
    return paths
def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


def audit_text(log, trace, binding):
    base = module(dependencies()['check.py'], 'rom_sealed_checker')
    schemas = dict(BEGIN='pc address insn mstatus', TRAP='pc cause tval count fatal',
        CSR='before_fcsr after_fcsr before_vcsr after_vcsr before_vstart after_vstart before_vl after_vl before_vtype after_vtype',
        DONE='traps errors')
    rows = []
    for line in log.splitlines():
        if line.startswith('ROM_'):
            tag, sep, body = line.partition(' '); tag = tag[4:]
            require(sep and tag in schemas, 'Unknown/malformed ROM record')
            rows.append((tag, base.fields(body, schemas[tag].split(), {'pc', 'address', 'insn', 'mstatus', 'tval'})))
        else:
            require(not re.search(r'(?i)ROM_|fatal|failed|assertion|segmentation|traceback', line), 'Guest/transport failure')
    require([tag for tag, _ in rows] == ['BEGIN', 'TRAP', 'CSR', 'DONE'], 'Unique ordered ROM terminal required')
    begin, trap, csr, done = [row for _, row in rows]
    require({k: begin[k] for k in ('pc', 'address', 'insn')} == dict(pc=binding['pc'], address=0x1000, insn=0x00b5605b)
            and begin['mstatus'] & 0x6000 and begin['mstatus'] & 0x600, 'Legal exact FULL admission not exercised')
    require(trap == dict(pc=binding['pc'], cause=5, tval=0x1000, count=1, fatal=0), 'Precise load-access trap mismatch')
    expected = {side+'_'+name: value for side in ('before', 'after') for name, value in
        (('fcsr', 8), ('vcsr', 5), ('vstart', 0), ('vl', 0), ('vtype', 0xc8))}
    require(csr == expected and done == dict(traps=1, errors=0), 'CSR/terminal mismatch')
    require(base.trace_rows(trace) == [('begin', dict(seq=1, pc=binding['pc'], insn=0x00b5605b,
        rs1=0x1000, rs2=0, frm=0, fflags=8))], 'ROM fault must be real BEGIN with no descriptor read/END')
    return dict(state='ROM_RAM_ONLY_FAULT_CHECKED', traps=1, cause=5, tval=0x1000, native_full_begin=1,
        descriptor_reads=0, helper_ends=0, csr_unchanged=True, qemu_image_checked=False, rtl_timing=False)


def build(output):
    output = Path(output).absolute()
    require(output.parent == OUT and output == output.resolve() and not output.exists(), 'Fresh direct output required')
    output.mkdir(); inputs = output/'inputs'; inputs.mkdir(); (inputs/'sealed').mkdir()
    report = dict(state='FAIL', qemu_executed=False); pins = {}; commands = []
    env = dict(PATH='/usr/bin:/bin', HOME='/home/wangwy', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')
    def pin(path): pins[str(Path(path).resolve())] = sha(path)
    def run(label, argv):
        verify(pins); argv = list(map(str, argv))
        with (output/(label+'.log')).open('x') as log:
            result = subprocess.run(argv, cwd=output, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120)
        commands.append(dict(label=label, argv=argv, cwd=str(output), timeout_seconds=120, returncode=result.returncode))
        require(result.returncode == 0, 'GNU/host command failed: ' + label)
        return (output/(label+'.log')).read_text()
    try:
        for name in OWN:
            pin(HERE/name); shutil.copyfile(HERE/name, inputs/name)
        for name, path in dependencies().items():
            pin(path); shutil.copyfile(path, inputs/'sealed'/name)
        for path in inputs.rglob('*'):
            if path.is_file(): pin(path)
        pin(CC); pin(Path(sys.executable).resolve())
        for name in ('cc1', 'as', 'ld'):
            path = run('locate-'+name, [CC, '-print-prog-name='+name]).strip()
            pin(Path(shutil.which(path, path=env['PATH']) or path).resolve(strict=True))
        objdump = CC.with_name('riscv64-unknown-elf-objdump'); pin(objdump)
        run('host-tests', [sys.executable, '-B', inputs/'test_probe.py', '-v'])
        flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax', '-O2',
            '-ffreestanding', '-fno-builtin', '-fno-stack-protector', '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
            '-fno-tree-loop-distribute-patterns', '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror']
        objects = []
        for name, path in (('start', inputs/'sealed/start.S'), ('issue', inputs/'issue.S'), ('main', inputs/'main.c')):
            obj = output/(name+'.o'); objects.append(obj)
            run(name, [CC, *flags, '-MD', '-MF', obj.with_suffix('.d'), '-c', path, '-o', obj])
            text = obj.with_suffix('.d').read_text().replace('\\\n', ' ')
            for path in shlex.split(text.split(':', 1)[1]): pin(Path(path))
        elf = output/'rom.elf'
        run('link', [CC, *flags[:4], '-nostdlib', '-nostartfiles', '-static', *objects,
                    '-T', inputs/'sealed/link.ld', '-Wl,--gc-sections', '-Wl,-Map='+str(output/'link.map'), '-o', elf])
        run('disassembly', [objdump, '-d', '-M', 'no-aliases,numeric', elf])
        symbols, word = module(inputs/'sealed/build.py', 'rom_sealed_elf').elf_contract(elf)
        pc = symbols['rom_full_pc']['address']
        require(pc % 4 == 0 and word(pc) == 0x00b5605b, 'Exact FULL PC/opcode mismatch')
        verify(pins); save(output/'source-pins.json', pins)
        report.update(state='ROM_PROBE_BUILT_NOT_EXECUTED', elf=str(elf), elf_sha256=sha(elf),
            binding=dict(pc=pc, insn=word(pc)), source_pins_sha256=sha(output/'source-pins.json'), post_pins_match=True)
    except BaseException as exc: report['error'] = repr(exc)
    save(output/'commands.json', commands)
    report['artifacts'] = {str(p): sha(p) for p in output.rglob('*') if p.is_file()}
    save(output/'build.json', report)
    return report


def check(build_dir, log, trace):
    root = Path(build_dir); receipt = read(root/'build.json')
    require(receipt['state'] == 'ROM_PROBE_BUILT_NOT_EXECUTED' and receipt['post_pins_match'] is True and
            sha(root/'source-pins.json') == receipt['source_pins_sha256'], 'Probe not built/pinned')
    verify(read(root/'source-pins.json')); verify(receipt['artifacts'])
    require(sha(receipt['elf']) == receipt['elf_sha256'], 'Probe ELF drift')
    result = audit_text(Path(log).read_text(), Path(trace).read_text(), receipt['binding'])
    result.update(elf_sha256=receipt['elf_sha256'], log_sha256=sha(log), trace_sha256=sha(trace), build_sha256=sha(root/'build.json'))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False); sub = p.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build'); b.add_argument('--output', type=Path, required=True)
    c = sub.add_parser('check')
    for name in ('build', 'log', 'trace'): c.add_argument('--'+name, type=Path, required=True)
    args = p.parse_args()
    result = build(args.output) if args.command == 'build' else check(args.build, args.log, args.trace)
    print(json.dumps(result, indent=2)); raise SystemExit(int(result['state'] == 'FAIL'))
