"""Two canonical K faults; host and labelled software Spike only, never EDA."""
import argparse
import json
import re
import struct
from pathlib import Path

import preflight_gap71_canonical779 as inherited

ROOT, h, audit = inherited.ROOT, inherited.h, inherited.audit
need = h.require
ADDRESSES = (0x0000001555555550, 0xffffffeaaaaaaaa8)
BOOK = ROOT / 'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json'
BOOK_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
RTL = inherited.RTL + ('hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv',)


def address_gate(a):
    need(a in ADDRESSES and a % 8 == 0, 'Exact aligned canonical address')
    need(a >> 39 == ((1 << 25)-1 if a >> 38 & 1 else 0), 'Sv39 canonical')
    need((a >> 30 & 511) != 2 and (a >> 12 & 511) not in (0, 1, 2), 'No mapped-page collision')
    need((a & 4095) + 128 <= 4096, 'One-page K payload')


def replace_one(text, before, after):
    need(text.count(before) == 1, 'Source replacement identity: ' + before)
    return text.replace(before, after)


def phase_sources(index):
    a = ADDRESSES[index]; address_gate(a)
    window = a & ~((1 << 21)-1); leaf = a >> 12 & 511
    prefix = 'akvc%d' % index
    data = (ROOT / 'apps/common/gap71_data.h').read_text()
    data = data.replace('0x40000000', hex(window)).replace('0x40002080', hex(a)).replace('0x40001080', hex(window+0x1080))
    data = replace_one(data, 'p[0][1]=', 'p[0][%d]=' % (a >> 30 & 511))
    data = replace_one(data, 'p[1][0]=', 'p[1][%d]=' % (a >> 21 & 511))
    data = replace_one(data, 'p[2][2]=fault', 'p[2][2]=((base+16384)>>12)*1024+0x43;\n  p[2][%d]=fault' % leaf)
    data = replace_one(data, '.v_base=GAP71_A+384', '.v_base=UINT64_C(%s)' % hex(window+0x2200))
    data = replace_one(data, '((uint16_t*)&p[4][16])[i]', '((uint16_t*)&p[4][%d])[i]' % ((a & 4095)//8))
    for before, rel in (('qbs_abi.h', 'apps/common/qbs_abi.h'),
                        ('../../verification/qbs/qbs_ref.h', 'verification/qbs/qbs_ref.h'),
                        ('../../software/akv/include/akv/akv_abi.h', 'software/akv/include/akv/akv_abi.h')):
        data = data.replace('"'+before+'"', '"'+str(ROOT/rel)+'"')
    header = (ROOT / 'apps/common/gap71_sv39_custom.h').read_text()
    header = header.replace('"gap71_data.h"', '"'+prefix+'_data.h"')
    header = header.replace('0x40002080', hex(a)).replace('0x40001080', hex(window+0x1080)).replace('0x40002200', hex(window+0x2200)).replace('0x40000000', hex(window))
    header = header.replace('8208', str(8192+leaf*8))
    header = replace_one(header, 'addi t4,t4,384', 'li t4,%s' % hex(window+0x2200))
    header = replace_one(header, '(stream==2?64:16)+w', '(stream==2?64:(stream==1?%d:16))+w' % ((a & 4095)//8))
    header = replace_one(header, 'gap71_expected[2][2]=', 'gap71_expected[2][%d]=' % leaf)
    start = header.index('#ifdef GAP71_SOFTWARE_REFERENCE\nvoid rvtest_init')
    end = header.index('\n#endif\nint main(void)', start)
    header = header[:start] + header[end+len('\n#endif'):]
    header = replace_one(header, 'int main(void)', 'int gap71_run(void)')
    data = data.replace('GAP71', prefix.upper()).replace('gap71', prefix)
    header = header.replace('GAP71', prefix.upper()).replace('gap71', prefix)
    unit = '#define %s_AKV 1\n#define %s_FAULT 1\n#define %s_NAME "gap71_akv_fault"\n#include "%s.h"\n' % (prefix.upper(), prefix.upper(), prefix.upper(), prefix)
    return data, header, unit


def pages(base, index, fault):
    a = ADDRESSES[index]; window = a & ~((1 << 21)-1); leaf = a >> 12 & 511
    p = audit.pages(base, True, fault)
    p[0][a >> 30 & 511] = p[0][1]; p[0][1] = 0
    p[1][a >> 21 & 511] = p[1][0]; p[1][0] = 0
    p[2][2] = ((base+16384) >> 12)*1024+0x43
    p[2][leaf] = 0 if fault else p[2][2]
    p[3][3:6] = [window+0x1080, a, window+0x2200]
    # Restore the unused old K region, then independently construct F16 bytes.
    for w in range(16, 32):
        p[4][w] = 0x71a5c39e00000000 ^ (4 << 32) ^ w
    raw = bytearray(struct.pack('<512Q', *p[4]))
    for i in range(64):
        struct.pack_into('<H', raw, (a & 4095)+2*i, 0xb400+i*5)
    p[4] = list(struct.unpack('<512Q', raw))
    return p


def metadata(obj, blob):
    symbols = {r['Symbol']['Name']['Name']: r['Symbol']['Value'] for r in obj['Symbols']}
    def word(pc):
        rows = [r['Section'] for r in obj['Sections'] if r['Section']['Flags']['Value'] & 4 and r['Section']['Address'] <= pc < r['Section']['Address']+r['Section']['Size']]
        need(len(rows) == 1, 'Unique executable ELF section')
        s = rows[0]; off = s['Offset']+pc-s['Address']
        return int.from_bytes(blob[off:off+4], 'little')
    return symbols, word


def software_trace(trace, symbols):
    commits = [(int(m[1]), int(m[2], 16), int(m[3], 16), m[4]) for m in re.finditer(r'(?m)^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)([^\n]*)$', trace)]
    need(commits and len(commits) < 300000 and all(w & 127 != 91 for _, _, w, _ in commits), 'Bounded software-only trace')
    traps = [(m[1], int(m[2], 16)) for m in re.finditer(r'exception\s+(\w+), epc 0x([0-9a-f]+)', trace)]
    wanted = [(kind, symbols['akvc%d_%s' % (i, site)]) for i in range(2) for kind, site in [('trap_load_page_fault', 'site'), ('trap_supervisor_ecall', 's_exit')]]
    need(traps == wanted, 'Exact two page faults and two S ecalls')
    results = []
    for i in range(2):
        pre = 'akvc%d_' % i; s = lambda key: symbols[pre+key]
        base = s('pages'); p = pages(base, i, False)
        memory = {base+j*4096+k*8: v for j, page in enumerate(p) for k, v in enumerate(page)}
        for key in ('guard_lo', 'guard_hi'):
            memory.update({s(key)+k*8: (audit.GUARD if key == 'guard_lo' else audit.GUARD ^ audit.M64)^k for k in range(8)})
        for key, count in [('seed', 1), ('output', 4)]:
            memory.update({s(key)+k*8: audit.GUARD ^ k for k in range(8)})
            memory.update({s(key)+64+count*4096+k*8: (audit.GUARD ^ audit.M64)^k for k in range(8)})
            for j in range(count):
                row = [audit.seed(k) for k in range(512)]
                if key == 'output' and j:
                    stream = j-1; off = 16 if stream == 0 else (ADDRESSES[i] & 4095)//8 if stream == 1 else 64
                    row[128:144] = p[5 if stream == 0 else 4][off:off+16]
                memory.update({s(key)+64+j*4096+k*8: v for k, v in enumerate(row)})
        checking = False; reads = set(); repairs = []; handlers = 0
        ledger = {}
        for mode, pc, insn, tail in commits:
            if pc == s('check_begin'): checking = True
            if pc == s('restore_end'): checking = False
            if pc == s('handler_entry'): handlers += 1; need(mode == 3, 'M-mode trap handler')
            stores = re.findall(r'\bmem 0x([0-9a-f]+) 0x([0-9a-f]+)', tail)
            for addr, value in stores:
                addr, value = int(addr, 16), int(value, 16)
                if s('records') <= addr < s('records')+192: ledger[addr] = value
            if pc == s('pte_repair'): repairs.extend(stores)
            ld64 = (insn & 127 == 3 and (insn >> 12) & 7 == 3) or (insn & 3 in (0, 2) and (insn >> 13) & 7 == 3)
            if checking and ld64:
                changes = [int(v, 16) for _, v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)', tail)]
                for addr in re.findall(r'\bmem 0x([0-9a-f]+)(?![0-9a-f])', tail):
                    addr = int(addr, 16)
                    if addr in memory:
                        need(changes == [memory[addr]], 'Independent complete readback at '+hex(addr)); reads.add(addr)
        need(reads == set(memory) and handlers == 2, 'Complete pages/source/VRF/guards and handler count')
        leaf = ADDRESSES[i] >> 12 & 511; repair = base+8192+leaf*8
        need([(int(a, 16), int(v, 16)) for a, v in repairs] == [(repair, memory[repair])], 'One exact PTE repair')
        for j, (cause, pc, tval) in enumerate(((13, s('site'), ADDRESSES[i]), (9, s('s_exit'), 0))):
            for k, value in {0:cause, 1:pc, 2:tval, 4:(8 << 60)|(0x71 << 44)|(base >> 12), 5:16, 6:24, 7:0, 8:5, 9:0, 10:j+1, 11:1}.items():
                need(ledger.get(s('records')+j*96+k*8) == value, 'Exact fault/recovery ledger')
        results.append(dict(address=hex(ADDRESSES[i]), compared_words=len(reads), traps=2))
    return dict(status='SOFTWARE_REFERENCE_PASS_NOT_AKV_EXECUTION', retired=len(commits), phases=results)


def prepare(out):
    need(out.parent == ROOT/'verification/out' and not out.exists(), 'Fresh output')
    need(h.sha(BOOK) == BOOK_SHA, 'Frozen source book')
    book = h.read(BOOK); bound = {str(ROOT/p): book[str(ROOT/p)] for p in RTL}
    bound.update(h.pins([BOOK, Path(__file__), Path(__file__).with_name('test_preflight_akv_canonical_kfault.py'), ROOT/'apps/common/gap71_data.h', ROOT/'apps/common/gap71_sv39_custom.h', Path(inherited.__file__), Path(audit.__file__)]))
    h.verify(bound); inherited.driver_gate((ROOT/RTL[0]).read_text())
    out.mkdir(); software = out/'software'; software.mkdir()
    for i in range(2):
        data, header, unit = phase_sources(i)
        for suffix, text in [('_data.h', data), ('.h', header), ('.c', unit)]:
            (software/('akvc%d'%i+suffix)).write_text(text)
    main = software/'main.c'
    main.write_text('int akvc0_run(void); int akvc1_run(void);\n#ifndef __SPIKE__\n__attribute__((naked,used)) void rvtest_init(void) { __asm__ volatile(".option push\\n.option norvc\\nli t0,6144\\ncsrs mstatus,t0\\nla t0,akvc0_handler_entry\\ncsrw mtvec,t0\\nret\\n.option pop\\n"); }\n#else\nvoid rvtest_init(void) {}\n#endif\nint main(void) { int a=akvc0_run(); int b=akvc1_run(); return a||b; }\n')
    host = software/'host.c'
    host.write_text('#include <stdio.h>\n#include "akvc0_data.h"\n#include "akvc1_data.h"\nint main(void) { uint64_t p[6][512]; if(akvc0_seed_word(0)!=akvc1_seed_word(0)) return 1; for(int n=0;n<2;n++) for(int f=0;f<2;f++) { if(n) akvc1_init(p,0x80040000,1,f); else akvc0_init(p,0x80040000,1,f); for(int j=0;j<6;j++) for(int k=0;k<512;k++) printf("P %d %d %d %d %016lx\\n",n,f,j,k,p[j][k]); } return 0; }\n')
    b = h.Build(out); b.sources = dict(bound)
    obj = b.compile(host, 'host', host=True); exe = out/'host'; b.link([b.host, obj, '-o', exe], 'host-link')
    r = b.run([exe], 'host-reference')
    actual = [tuple(int(v, 16) if k == 4 else int(v) for k, v in enumerate(line.split()[1:])) for line in r.stdout.decode().splitlines()]
    expected = [(i, f, j, k, v) for i in range(2) for f in range(2) for j, page in enumerate(pages(0x80040000, i, f)) for k, v in enumerate(page)]
    need(actual == expected, 'Independent 12288 host page/data words')
    plan = h.read(ROOT/'verification/out/repaired-aligned-600-20260930-01/plan.json')
    prior = next(c for c in plan['cases'] if c.get('spike')); spike = Path(prior['spike'])
    need(h.sha(spike) == prior['spike_sha256'], 'Frozen Spike')
    b.tools.update(h.pins([spike]))
    artifacts = {}
    for label, soft in [('dut', False), ('reference', True)]:
        runtime = ROOT/'apps/riscv-tests/benchmarks/common'
        extra = []
        if soft:
            extra = ['-D__SPIKE__=1', '-DAKVC0_SOFTWARE_REFERENCE=1', '-DAKVC1_SOFTWARE_REFERENCE=1', '-DPREALLOCATE=1', '-I'+str(runtime), '-I'+str(ROOT/'apps/riscv-tests/env'), '-fno-function-sections', '-fno-data-sections']
        sources = [main, software/'akvc0.c', software/'akvc1.c']
        sources += [runtime/'crt.S', runtime/'syscalls.c'] if soft else [b.common/n for n in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
        objs = [b.compile(s, label+'-'+str(i), extra) for i, s in enumerate(sources)]
        elf = out/(label+'.elf'); link = runtime/'test.ld' if soft else b.common/'link.ld'; b.bind_sources([link])
        b.link([b.cc, *b.flags, '-fuse-ld=lld', '-static', '-nostdlib' if soft else '-nostartfiles', '-T'+str(link), *objs, '-lm', '-L'+str(b.llvm/'lib/generic'), '-lclang_rt.builtins-riscv64', '-o', elf], label+'-link')
        result = b.run([b.llvm/'bin/llvm-readobj', '--elf-output-style=JSON', '--sections', '--symbols', '--program-headers', elf], label+'-metadata')
        symbols, word = metadata(json.loads(result.stdout)[0], elf.read_bytes())
        for i in range(2):
            prefix = 'akvc%d_' % i
            for name, opcode in [('site', 0x000f3f83 if soft else 0x00b5205b), ('s_exit', 0x73), ('pte_repair', 0x0062b023)]:
                need(word(symbols[prefix+name]) == opcode, 'Linked owner/trap/repair opcode')
            if not soft:
                need(word(symbols[prefix+'load_site']) == 0x0005345b and word(symbols[prefix+'release_site']) == 0x0000505b, 'Context load/release opcode')
        artifacts[label] = dict(elf=str(elf), sha256=h.sha(elf), symbols=symbols)
    fit = ROOT/'verification/coverage/check_elf_fit.py'; b.bind_sources([fit])
    b.run([ROOT/'verification/tools/soc-venv/bin/python', fit, '--elf', out/'dut.elf', '--ram-bytes', '0x200000', '--output', out/'elf-fit.json'], 'fit')
    r = b.run([spike, '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0', '-m0x80000000:0x200000', '-l', '--log-commits', out/'reference.elf'], 'spike', timeout=120)
    lines = r.stdout.decode().splitlines()
    need(lines.count('PASSED: gap71_akv_fault checks=%d errors=0' % audit.checks('gap71_akv_fault')) == 2 and not any('FAILED' in x for x in lines), 'Both complete software contracts')
    trace = software_trace(r.stderr.decode(), artifacts['reference']['symbols'])
    for pins in (bound, b.sources, b.tools, b.link_inputs): h.verify(pins)
    h.save(out/'preflight.json', dict(status='AKV_CANONICAL_KFAULT_HOST_SPIKE_PASS_NOT_DUT_QUALIFIED', addresses=[hex(a) for a in ADDRESSES], host_words=len(expected), trace=trace, artifacts=artifacts, input_pins=bound, source_pins=b.sources, tool_pins=b.tools, link_pins=b.link_inputs, output_pins=h.pins(p for p in out.iterdir() if p.is_file()), VCS_budget_seconds=540, EDA_launched=False, custom_instruction_execution_verified=False))
    print(json.dumps(dict(output=str(out), seal=h.sha(out/'preflight.json'), trace=trace)), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    prepare(parser.parse_args().output.resolve())
