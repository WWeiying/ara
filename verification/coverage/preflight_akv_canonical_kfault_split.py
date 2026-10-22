"""Preserve dual preflight; build two complete independently bounded phases."""
import argparse
import json
import re
from pathlib import Path

import preflight_akv_canonical_kfault as p

h, need, ROOT = p.h, p.need, p.ROOT
PARENT = ROOT/'verification/out/akv-canonical-kfault-preflight-agent-20261008-01/preflight.json'
PARENT_SHA = '94303bee27da10a34ae65c89386ba1000f15a63374b5651792cd7e740af5edc5'


def boot_gate(symbols, word, index):
    boot = symbols['rvtest_init']
    need([word(boot+i*4) for i in range(3)] == [0x00300293,0x00b29293,0x3002a073],
        'Exact li3/shift11 MPP=M boot')
    a,b = word(boot+12),word(boot+16)
    need(a & 0xfff == 0x297 and b & 0xfffff == 0x28293
        and word(boot+20) == 0x30529073 and word(boot+24) == 0x00008067, 'Exact stack-free mtvec setup')
    hi = a & 0xfffff000; hi -= 1 << 32 if hi & (1 << 31) else 0
    lo = b >> 20; lo -= 4096 if lo & 2048 else 0
    need(boot+12+hi+lo == symbols['akvc%d_handler_entry'%index], 'Exact initial handler target')


def validate(trace, symbols, index):
    import collect_akv_canonical_kfault as oracle
    pre = 'akvc%d_' % index
    info = dict(symbols={'gap71_'+k[len(pre):]:v for k,v in symbols.items() if k.startswith(pre)})
    memory = oracle.owner_oracle(index)['final_memory']('gap71_akv_fault', info)
    commits = [(int(m[1]),int(m[2],16),int(m[3],16),m[4]) for m in re.finditer(r'(?m)^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)([^\n]*)$',trace)]
    need(commits and len(commits) < 150000 and all(w & 127 != 91 for _,_,w,_ in commits), 'Bounded software-only phase')
    traps = [(m[1],int(m[2],16)) for m in re.finditer(r'exception\s+(\w+), epc 0x([0-9a-f]+)',trace)]
    need(traps == [('trap_load_page_fault',symbols[pre+'site']),('trap_supervisor_ecall',symbols[pre+'s_exit'])], 'Exact phase exceptions')
    reads = set(); checking = False; ledger = {}; repairs = []; handlers = 0
    for mode,pc,word,tail in commits:
        if pc == symbols[pre+'check_begin']: checking = True
        if pc == symbols[pre+'restore_end']: checking = False
        if pc == symbols[pre+'handler_entry']: handlers += 1; need(mode == 3, 'M handler')
        stores = [(int(a,16),int(v,16)) for a,v in re.findall(r'\bmem 0x([0-9a-f]+) 0x([0-9a-f]+)',tail)]
        for addr,value in stores:
            if symbols[pre+'records'] <= addr < symbols[pre+'records']+192: ledger[addr] = value
        if pc == symbols[pre+'pte_repair']: repairs.extend(stores)
        ld64 = (word & 127 == 3 and (word >> 12) & 7 == 3) or (word & 3 in (0,2) and (word >> 13) & 7 == 3)
        if checking and ld64:
            changes = [int(v,16) for _,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)]
            for a in re.findall(r'\bmem 0x([0-9a-f]+)(?![0-9a-f])',tail):
                addr = int(a,16)
                if addr in memory:
                    need(changes == [memory[addr]], 'Full independent phase readback'); reads.add(addr)
    need(reads == set(memory) and len(reads) == 5680 and handlers == 2, 'No reduction in checks')
    repair = symbols[pre+'pages']+8192+(p.ADDRESSES[index] >> 12 & 511)*8
    need(repairs == [(repair,memory[repair])], 'Exact repair')
    for j,(cause,pc,tval) in enumerate(((13,symbols[pre+'site'],p.ADDRESSES[index]),(9,symbols[pre+'s_exit'],0))):
        for k,value in {0:cause,1:pc,2:tval,4:(8<<60)|(0x71<<44)|(symbols[pre+'pages']>>12),5:16,6:24,7:0,8:5,9:0,10:j+1,11:1}.items():
            need(ledger.get(symbols[pre+'records']+j*96+k*8) == value,'Exact phase trap/CSR ledger')
    return dict(status='SOFTWARE_REFERENCE_PASS_NOT_AKV_EXECUTION',retired=len(commits),compared_words=len(reads),traps=2)


def prepare(out):
    need(out.parent == ROOT/'verification/out' and not out.exists(), 'Fresh split software output')
    need(h.sha(PARENT) == PARENT_SHA, 'Preserve dual preflight')
    parent = h.read(PARENT); pins = {str(PARENT):PARENT_SHA}
    for key in ('input_pins','source_pins','tool_pins','link_pins','output_pins'): pins.update(parent[key])
    pins.update(h.pins([Path(__file__),Path(__file__).with_name('test_preflight_akv_canonical_kfault_split.py')]))
    h.verify(pins); out.mkdir()
    plan = h.read(ROOT/'verification/out/repaired-aligned-600-20260930-01/plan.json')
    prior = next(c for c in plan['cases'] if c.get('spike')); spike = Path(prior['spike'])
    need(h.sha(spike) == prior['spike_sha256'], 'Frozen Spike')
    artifacts = []
    for index in range(2):
        directory = out/('phase%d'%index); directory.mkdir()
        main = directory/'main.c'; text = (PARENT.parent/'software/main.c').read_text()
        text = p.replace_one(text, 'int main(void) { int a=akvc0_run(); int b=akvc1_run(); return a||b; }', 'int main(void) { return akvc%d_run(); }'%index)
        text = text.replace('la t0,akvc0_handler_entry','la t0,akvc%d_handler_entry'%index)
        main.write_text(text)
        b = h.Build(directory); b.sources = dict(pins); b.tools.update(h.pins([spike]))
        result = dict(index=index,address=hex(p.ADDRESSES[index]))
        for label,soft in [('dut',False),('reference',True)]:
            runtime = ROOT/'apps/riscv-tests/benchmarks/common'
            extra = ['-D__SPIKE__=1','-DAKVC%d_SOFTWARE_REFERENCE=1'%index,'-DPREALLOCATE=1','-I'+str(runtime),'-I'+str(ROOT/'apps/riscv-tests/env'),'-fno-function-sections','-fno-data-sections'] if soft else []
            sources = [main,PARENT.parent/('software/akvc%d.c'%index)]
            sources += [runtime/'crt.S',runtime/'syscalls.c'] if soft else [b.common/n for n in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
            objects = [b.compile(s,label+'-'+str(i),extra) for i,s in enumerate(sources)]
            elf = directory/(label+'.elf'); link = runtime/'test.ld' if soft else b.common/'link.ld'; b.bind_sources([link])
            b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostdlib' if soft else '-nostartfiles','-T'+str(link),*objects,'-lm','-L'+str(b.llvm/'lib/generic'),'-lclang_rt.builtins-riscv64','-o',elf],label+'-link')
            r = b.run([b.llvm/'bin/llvm-readobj','--elf-output-style=JSON','--sections','--symbols','--program-headers',elf],label+'-metadata')
            symbols,word = p.metadata(json.loads(r.stdout)[0],elf.read_bytes())
            prefix = 'akvc%d_'%index
            need(word(symbols[prefix+'site']) == (0x000f3f83 if soft else 0x00b5205b), 'Exact linked fault site')
            if not soft:
                boot_gate(symbols,word,index)
                need(word(symbols[prefix+'load_site']) == 0x0005345b and word(symbols[prefix+'release_site']) == 0x0000505b, 'Exact linked recovery/release')
            result[label] = dict(elf=str(elf),sha256=h.sha(elf),symbols=symbols)
        fit = ROOT/'verification/coverage/check_elf_fit.py'; b.bind_sources([fit])
        b.run([ROOT/'verification/tools/soc-venv/bin/python',fit,'--elf',directory/'dut.elf','--ram-bytes','0x200000','--output',directory/'elf-fit.json'],'fit')
        r = b.run([spike,'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-m0x80000000:0x200000','-l','--log-commits',directory/'reference.elf'],'spike',timeout=120)
        need(r.stdout.decode().splitlines().count('PASSED: gap71_akv_fault checks=208 errors=0') == 1 and 'FAILED' not in r.stdout.decode(),'Complete unchanged phase selfcheck')
        result['trace'] = validate(r.stderr.decode(),result['reference']['symbols'],index)
        result['pins'] = {}
        for book in (b.sources,b.tools,b.link_inputs): h.verify(book); result['pins'].update(book)
        result['pins'].update(h.pins(f for f in directory.iterdir() if f.is_file()))
        artifacts.append(result)
    h.verify(pins)
    h.save(out/'preflight.json',dict(status='AKV_CANONICAL_KFAULT_SPLIT_HOST_SPIKE_PASS_NOT_DUT',
        parent_preflight=str(PARENT),parent_seal=PARENT_SHA,host_words=12288,phases=artifacts,
        input_pins=pins,VCS_budget_per_phase=480,parallel_allowed=True,EDA_launched=False,
        historical_matched_AKV_wall_seconds=347.675922696013,
        historical_summary=str(ROOT/'verification/out/closure92-current-20261005-01/results/gap71_akv_fault/summary.json'),
        no_checks_removed=True))
    print(json.dumps(dict(output=str(out),seal=h.sha(out/'preflight.json'),counts=[a['trace'] for a in artifacts])),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path,required=True)
    prepare(parser.parse_args().output.resolve())
