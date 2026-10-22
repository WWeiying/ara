"""Build native/Spike harnesses from one body; independent byte oracle, no EDA."""
import argparse
import csv
from io import BytesIO
import json
from pathlib import Path
import re

from elftools.elf.elffile import ELFFile
from build_gap38_i8_f16_lane3 import Build, ROOT, PIN_PLAN, pins, require, save, sha, verify

SOURCE = Path(__file__).with_name('masklogical_restart8.c')
FUNCTS = (0x19, 0x1d, 0x18, 0x1a, 0x1e, 0x1c, 0x1b, 0x1f)
PASS_LINE = 'PASSED: masklogical_restart8 cases=8 checks=8337 errors=0'


def expected(op):
    require(0 <= op < 8, 'Bad operation')
    a = bytes((0x69 ^ (i * 13)) & 255 for i in range(128))
    b = bytes((0xc3 ^ (i * 29)) & 255 for i in range(128))
    old = a if op == 3 else bytes((0xa5 ^ (i * 7)) & 255 for i in range(128))
    # Whole-register integer Boolean reference, independent of the C bit loop.
    x, y = int.from_bytes(b, 'little'), int.from_bytes(a, 'little')
    value = (x & y, ~(x & y), x & ~y, x | y, ~(x | y), x | ~y, x ^ y, ~(x ^ y))[op]
    full = (1 << 1024) - 1
    prefix = (1 << 256) - 1
    merged = (value & (full ^ prefix)) | (int.from_bytes(old, 'little') & prefix)
    return b'\xd3' * 8 + merged.to_bytes(128, 'little') + b'\xd3' * 8


def check_dump(text):
    require(text.splitlines().count(PASS_LINE) == 1 and 'FAILED:' not in text,
            'Complete self-check missing')
    rows = re.findall(r'^RESTART8 ([0-7]) ([0-9a-f]{288})$', text, re.M)
    require([int(i) for i, _ in rows] == list(range(8)), 'Missing/duplicate dump')
    for op, data in rows:
        require(bytes.fromhex(data) == expected(int(op)), 'Independent byte mismatch: ' + op)
    return dict(status='PASS', cases=8, independent_bytes=1152, checks=8337,
                prefix_bits=2048, active_bits=6144, tail_bits=0, guard_bytes=128,
                tail_note='VL equals VLEN; no architectural tail exists in these eight operations')


def elf_sites(path):
    elf = ELFFile(BytesIO(path.read_bytes()))
    sym = elf.get_section_by_name('.symtab')
    sites = []
    for op, funct in enumerate(FUNCTS):
        pc = sym.get_symbol_by_name('restart8_site' + str(op))[0]['st_value']
        vd, vs1 = (8 if op == 3 else 16), (0 if op == 6 else 8)
        want = funct << 26 | 1 << 25 | 9 << 20 | vs1 << 15 | 2 << 12 | vd << 7 | 0x57
        sections = [s for s in elf.iter_sections() if s['sh_type'] != 'SHT_NOBITS'
                    and s['sh_addr'] <= pc and pc + 4 <= s['sh_addr'] + s['sh_size']]
        require(len(sections) == 1, 'Ambiguous instruction section')
        sec = sections[0]; offset = pc - sec['sh_addr']
        require(int.from_bytes(sec.data()[offset:offset+4], 'little') == want, 'Wrong instruction')
        sites.append(dict(op=op, pc=pc, word=want, vd=vd, vs1=vs1, vs2=9))
    return sites


def audit_native_readback(directory):
    """Supplement the parent's terminal/contract/VRF checks; not full RTL acceptance."""
    directory = Path(directory)
    elf = ELFFile(BytesIO((directory / 'input.elf').read_bytes()))
    base = elf.get_section_by_name('.symtab').get_symbol_by_name('restart8_got')[0]['st_value']
    want = b''.join(expected(op) for op in range(8))
    seen = set()
    with (directory / 'commit_trace.csv').open(newline='') as stream:
        for row in csv.DictReader(stream):
            if row['event'] != 'retire' or not int(row['mem_rmask'], 16):
                continue
            addr = int(row['mem_addr'], 16)
            if not base <= addr < base + len(want):
                continue
            word = int(row['insn'], 16)
            require(word & 127 == 3 and (word >> 12) & 7 == 4, 'Expected LBU readback')
            require(int(row['rd_wdata'], 16) == want[addr-base], 'Independent RTL readback mismatch')
            seen.add(addr-base)
    require(seen == set(range(len(want))), 'Incomplete RTL readback')
    require((directory / 'console.log').read_text().splitlines().count(PASS_LINE) == 1,
            'Native self-check missing')
    return dict(status='PASS', scope='independent_readback_only', independent_bytes=len(seen),
                checks=8337, terminal_contract_and_vrf_acceptance='parent runner required')


def build(out):
    out = Path(out).resolve()
    require(not out.exists(), 'Fresh output directory required')
    out.mkdir(parents=True)
    b = Build(out)
    b.sources = pins([Path(__file__), SOURCE, Path(__file__).with_name('build_gap38_i8_f16_lane3.py')])
    objects = [b.compile(b.common / n, 'native-' + n) for n in
               ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')]
    objects.insert(0, b.compile(SOURCE, 'native-test', ['-Wall', '-Wextra', '-Werror']))
    native = out / 'input.elf'
    b.bind_sources([b.common / 'link.ld'])
    b.link([b.cc, *b.flags, '-fuse-ld=lld', '-static', '-nostartfiles', '-Wl,--gc-sections',
            f'-T{b.common / "link.ld"}', *objects, '-lm', f'-L{b.llvm / "lib/generic"}',
            '-lclang_rt.builtins-riscv64', '-o', native], 'native-link')
    native_sites = elf_sites(native)
    b.run([b.llvm / 'bin/llvm-objdump', '-d', native], 'native-disassembly')
    fit = ROOT / 'verification/coverage/check_elf_fit.py'
    b.bind_sources([fit])
    b.run([ROOT / 'verification/tools/soc-venv/bin/python', fit, '--elf', native,
           '--ram-bytes', '0x200000', '--output', out / 'elf-fit.json'], 'elf-fit')
    runtime = ROOT / 'apps/riscv-tests/benchmarks/common'
    extra = ['-D__SPIKE__=1', '-DPREALLOCATE=1', f'-I{runtime}',
             f'-I{ROOT / "apps/riscv-tests/env"}', '-fno-function-sections', '-fno-data-sections']
    objs = [b.compile(src, label, extra) for src, label in
            ((runtime / 'crt.S', 'spike-crt'), (runtime / 'syscalls.c', 'spike-syscalls'),
             (SOURCE, 'spike-test'))]
    spike_elf = out / 'input.spike'
    b.bind_sources([runtime / 'test.ld'])
    b.link([b.cc, *b.flags, '-fuse-ld=lld', '-static', '-nostdlib',
            f'-T{runtime / "test.ld"}', *objs, '-o', spike_elf], 'spike-link')
    spike_sites = elf_sites(spike_elf)
    reference = next(c for c in json.loads(PIN_PLAN.read_text())['cases'] if c.get('spike'))
    spike = Path(reference['spike'])
    require(sha(spike) == reference['spike_sha256'], 'Pinned Spike changed')
    b.tools.update(pins([spike]))
    result = b.run([spike, '--isa=rv64gcv_zfh_zvfh_zvl1024b', '-l', '--log-commits', spike_elf],
                   'spike-run', timeout=60)
    proof = check_dump(result.stdout.decode())
    trace = result.stderr.decode()
    commits = [(int(m[1], 16), int(m[2], 16)) for m in re.finditer(
        r'(?m)^core\s+\d+:\s+[0-3]\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)', trace)]
    pcs = {site['pc'] for site in spike_sites}
    require([(pc, word) for pc, word in commits if pc in pcs] ==
            [(s['pc'], s['word']) for s in spike_sites], 'Wrong dynamic eight operations')
    require(not re.search(r'trap_|exception ', trace), 'Unexpected Spike exception')
    verify(b.sources)
    save(out / 'manifest.json', dict(status='SPIKE_PREFLIGHT_PASS', proof=proof,
         native_elf=str(native), native_sha256=sha(native), native_sites=native_sites,
         spike_sites=spike_sites, source_pins=b.sources, tool_pins=b.tools,
         binary_pins=pins([native, spike_elf]), link_inputs=b.link_inputs,
         rtl_simulated=False, coverage_admitted=False, original_68_unchanged=True,
         harness='Native MMIO CRT; Spike HTIF CRT, same test body, Spike-only result dump'))
    print(json.dumps(dict(elf=str(native), sha256=sha(native), **proof), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output', type=Path)
    group.add_argument('--audit-native-readback', type=Path)
    args = parser.parse_args()
    if args.output:
        build(args.output)
    else:
        print(json.dumps(audit_native_readback(args.audit_native_readback), indent=2))
