#!/usr/bin/env python3
"""Independent LR-only integer oracle, ELF layout and full Spike commit audit."""
import hashlib
import re

NAME = 'rvv:lr_gap64_wd_drain_pmp0'
CHECKS = 51
MAX_RETIRED = 45000
VCS_TIMEOUT = 240
MASK = (1 << 64) - 1
IMAGES = ((0x0123456789abcdef, 0x800000007fffffff, 0xfedcba9876543210, 0x00000001ffffffff),
          (0x89abcdef01234567, 0x7fffffff80000000, 0x76543210fedcba98, 0xffffffff00000001))
BUFFERS = dict(payload=4, results=24, images=8, seed=544, capture=544,
               restored=544, gpr_before=32, gpr_after=32, gpr_restored=32,
               csr_orig=22, csr_before=22, csr_after=22, traps=4)
CSRS = (0x300,0x100,0x304,0x305,0x341,0x342,0x343,0x180,0x302,0x303,0x340,
        0x105,0x141,0x142,0x143,0x140,0xc20,0xc21,0x008,0x00f,0x003,0xc22)
WORDS = dict(gap64_lr_d=0x10033e2f, gap64_lr_w_low=0x10032e2f, gap64_lr_w_high=0x10032e2f)


def require(ok, why):
    if not ok:
        raise ValueError(why)


def expected_values(phase):
    values = []
    for image in IMAGES[phase]:
        raw = image.to_bytes(8, 'little')
        values += [image, int.from_bytes(raw[:4], 'little', signed=True) & MASK,
                   int.from_bytes(raw[4:], 'little', signed=True) & MASK]
    return values


def seed_word(i):
    return 0x64a53c9600000000 ^ i


def guard(b, high, i):
    low = (0x6b6b6b6b6b6b6b6b if b == 0 else 0x13579bdf2468ace0 if b == 1
           else 0x6464646464646400 ^ (b * 256))
    return (low ^ (MASK if high else 0)) ^ i


def expected_command(tool, elf):
    return [tool, '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0',
            '-l', '--log-commits', elf]


def validate_pmp_dts(text):
    require(re.findall(r'riscv,pmpregions\s*=\s*<([0-9]+)>;', text) == ['0'], 'not one PMP0 hart')


def metadata(obj, blob):
    symbols = {r['Symbol']['Name']['Name']: r['Symbol'] for r in obj['Symbols']}
    names = list(WORDS) + ['gap64_'+n for n in BUFFERS] + [
        'gap64_sweep','gap64_payload_begin','gap64_payload_end','gap64_check_begin',
        'gap64_check_end','gap64_return','gap64_handler','gap64_recover']
    selected = {n: symbols[n]['Value'] for n in names}
    for name, count in BUFFERS.items():
        symbol = symbols['gap64_'+name]
        require(symbol['Size'] == (count+16)*8 and symbol['Value'] % 64 == 0,
                'incorrect full guarded buffer layout: '+name)
    require(all(0x80000000 <= p < 0x80200000 for p in selected.values()), 'symbol outside L2')
    require(all(selected['gap64_'+n]+(count+16)*8 <= 0x80200000 for n,count in BUFFERS.items()),
            'buffer crosses L2 end')

    def code(start, end):
        matches = []
        for row in obj['Sections']:
            s = row['Section']
            if s['Flags']['Value'] & 4 and s['Address'] <= start < end <= s['Address']+s['Size']:
                offset = s['Offset']+start-s['Address']
                matches.append(blob[offset:offset+end-start])
        require(len(matches) == 1, 'ambiguous instruction range')
        return matches[0]

    sites = {}
    for name, word in WORDS.items():
        pc = selected[name]
        require(int.from_bytes(code(pc,pc+4),'little') == word, 'wrong LR word at '+name)
        sites[name] = dict(pc=hex(pc),word=hex(word))
    payload = code(selected['gap64_payload_begin'],selected['gap64_payload_end'])
    words = [int.from_bytes(payload[i:i+4],'little') for i in range(0,len(payload),4)]
    require(len(payload) % 4 == 0 and sum(w & 0x7f == 0x2f for w in words) == 3,
            'payload must have exactly three static LR sites')
    require(not any(w & 0x7f in (0x0f,0x73,0x07,0x27,0x53,0x57) for w in words),
            'fence/CSR/FP/vector in LR payload')
    return dict(symbols=selected,sites=sites,payload_sha256=hashlib.sha256(payload).hexdigest(),
                guarded_words=sum(n+16 for n in BUFFERS.values()), guard_words=16*len(BUFFERS))


def check_log(log, source):
    require(re.findall(r'^gap35 checks=(\d+) failures=0$',log,re.M) == [str(CHECKS)], 'wrong selfcheck count')
    require(log.splitlines().count('PASSED: '+source+'!') == 1 and
            sum(s.startswith('PASSED:') for s in log.splitlines()) == 1, 'wrong absolute PASS source')
    require(not re.search(r'(?im)^\s*(?:FAIL|check=|Fatal:|Error:)',log), 'selfcheck failure')


def trace_check(trace, info):
    sym = info['symbols']
    for n,w in WORDS.items():
        require(info['sites'][n] == dict(pc=hex(sym[n]),word=hex(w)), 'LR metadata mismatch')
    commits = [(int(m[1]),int(m[2],16),int(m[3],16),m[4]) for m in re.finditer(
        r'(?m)^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)([^\n]*)$',trace)]
    require(0 < len(commits) <= MAX_RETIRED, 'empty trace or >45000 Spike retirements')
    require(not re.search(r'exception |trap_illegal|trap_load|trap_store|(?m:^core\s+[1-9][0-9]*:)',trace),
            'unexpected trap/hart')
    base = {n:sym['gap64_'+n]+64 for n in BUFFERS}
    memory, gpr, csrs, fp, vec = {}, {0:0}, {}, {}, {}
    want_fp = {r:seed_word(512+r) for r in range(32)}
    want_vec = {r:sum(seed_word(r*16+i) << (64*i) for i in range(16)) for r in range(32)}
    phase, active, checking, ends, returns = -1, False, False, 0, 0
    lr_seen, stores, reads_by_phase, entry, original_csrs = [], [], [], {}, None
    fpvec_reads, fpvec_writes = [], []
    compared, before_csrs, csr_restores = set(), {}, set()
    expected_memory = {}
    orig_addr = set(range(base['csr_orig'],base['csr_orig']+22*8,8))
    orig_reads = set()
    for mode,pc,word,tail in commits:
        changes = {int(r):int(v,16) for r,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)}
        mem = [(int(a,16),int(v,16) if v else None) for a,v in
               re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail)]
        if word & 0x7f == 0x73 and (word>>12)&7:
            csr = word>>20
            require(not 0x3a0 <= csr <= 0x3ef, 'PMP CSR probe in PMP0 case')
            if csr in CSRS and changes:
                csrs[csr] = next(iter(changes.values()))
            if ends == 2 and not checking and (word>>12)&3 in (1,2,3) and (word>>15)&31:
                if csr in CSRS:
                    csr_restores.add(csr)
        if pc == sym['gap64_sweep']:
            phase += 1
            require(phase < 2 and not active and not checking and mode == 3, 'invalid sweep entry')
            require(set(gpr) == set(range(32)), 'incomplete entry GPR model')
            entry = dict(gpr)
            require(entry[10] == phase, 'wrong phase argument')
            require(fp == want_fp and vec == want_vec, 'complete known FP/vector entry state differs')
            before_csrs = {c:memory[base['csr_before']+i*8] for i,c in enumerate(CSRS)}
            require(before_csrs[0x180] == 0 and before_csrs[0x304] == 0 and
                    before_csrs[0x008] == 0 and before_csrs[0x00f] == 5 and
                    before_csrs[0x003] == 117 and before_csrs[0xc22] == 128,
                    'not Bare/IRQ-off/known vector-FP CSR setup')
            require(before_csrs[0x300] & 8 == 0, 'MIE enabled')
            if original_csrs is None:
                original_csrs = {c:memory[base['csr_orig']+i*8] for i,c in enumerate(CSRS)}
        if pc == sym['gap64_payload_begin']:
            require(not active and phase in (0,1), 'invalid LR boundary')
            active = True; stores = []; lr_seen = []
        if word & 0x7f == 0x2f:
            require(active and mode == 3 and word in WORDS.values() and (word>>20)&31 == 0,
                    'SC/RMW or out-of-scope atomic')
            i = len(lr_seen)
            require(i < 12, 'extra LR')
            name = ('gap64_lr_d','gap64_lr_w_low','gap64_lr_w_high')[i % 3]
            address = base['payload']+(i//3)*8+(4 if i%3==2 else 0)
            require(pc == sym[name] and word == WORDS[name] and
                    mem == [(address,None)] and changes == {28:expected_values(phase)[i]},
                    'LR address/width/sign/value differs at phase %d index %d'%(phase,i))
            require(stores[:4] == [(base['payload']+j*8,IMAGES[phase][j]) for j in range(4)],
                    'four immediate predecessor stores differ')
            lr_seen.append(i)
        if active and pc != sym['gap64_payload_end']:
            require(mode == 3 and word & 0x7f not in (0x0f,0x73,0x07,0x27,0x53,0x57),
                    'non-scalar/fence/CSR in LR body')
            stores += [(a,v) for a,v in mem if v is not None]
        if pc == sym['gap64_payload_end']:
            require(active and len(lr_seen) == 12, 'missing LR execution')
            require(stores == [(base['payload']+j*8,IMAGES[phase][j]) for j in range(4)] +
                    [(base['results']+(phase*12+j)*8,v) for j,v in enumerate(expected_values(phase))],
                    'unexpected payload write or result capture')
            active=False; ends += 1
            want = {r:0x6400+r for r in range(32)}
            want.update({0:0,2:entry[2]-16,5:base['gpr_after'],6:base['payload']+32,
                         7:base['results']+96*(phase+1),28:expected_values(phase)[11],29:0})
            want.update({10+i:v for i,v in enumerate(IMAGES[phase])})
            require(gpr == want, 'full seeded GPR state differs')
        if pc == sym['gap64_return']:
            require(not active and gpr == entry and mode == 3, 'full GPR/ABI restoration differs')
            require(fp == want_fp and vec == want_vec, 'full FP/vector restored state differs')
            returns += 1
        if pc == sym['gap64_check_begin']:
            require(returns == ends == phase+1 and not checking, 'invalid checker boundary')
            checking=True; compared=set()
            expected_memory = {}
            def region(n,values):
                require(len(values) == BUFFERS[n], 'wrong expected region size')
                expected_memory.update({base[n]+i*8:v for i,v in enumerate(values)})
            region('payload',IMAGES[phase])
            region('results',expected_values(0)+(expected_values(1) if phase else
                                               [0xa55aa55aa55aa55a^i for i in range(12,24)]))
            region('images',list(IMAGES[0])+list(IMAGES[1]))
            region('seed',[seed_word(i) for i in range(544)])
            region('capture',[seed_word(i) for i in range(544)])
            region('restored',[seed_word(i) for i in range(544)])
            region('gpr_before',[entry[i] for i in range(32)])
            region('gpr_restored',[entry[i] for i in range(32)])
            region('gpr_after',[want[i] for i in range(32)])
            region('csr_before',[before_csrs[c] for c in CSRS])
            region('csr_after',[before_csrs[c] for c in CSRS])
            region('traps',[0]*4)
            for b,(n,size) in enumerate(BUFFERS.items()):
                for high in (0,1):
                    start = base[n]+size*8 if high else base[n]-64
                    expected_memory.update({start+i*8:guard(b,high,i) for i in range(8)})
            require(all(memory.get(a)==v for a,v in expected_memory.items()),
                    'full buffer/guard contents differ before software comparison')
        if pc == sym['gap64_check_end']:
            require(checking and compared == set(expected_memory),
                    'checker omitted words: '+str(len(set(expected_memory)-compared)))
            checking=False; reads_by_phase.append(len(compared))
        for a,v in mem:
            if checking and a in expected_memory:
                require(mode == 3 and v is None and len(changes)==1 and
                        next(iter(changes.values())) == expected_memory[a], 'wrong full comparison load')
                compared.add(a)
            if a in orig_addr and v is None:
                orig_reads.add(a)
            if v is not None:
                if word & 0x7f == 0x27 and (word>>12)&7 == 0:
                    aligned, shift = a & ~7, (a & 7)*8
                    require(v <= 255, 'unexpected whole-register store element width')
                    memory[aligned] = (memory.get(aligned,0) & ~(255 << shift)) | (v << shift)
                else:
                    memory[a] = v
        # Whole-register instructions are outside the LR body. Their complete stored
        # data are independently checked above; these counts prohibit partial snapshots.
        if phase >= 0 and returns <= phase:
            if word & 0x7f == 0x07:
                fpvec_reads.append(word)
            if word & 0x7f == 0x27:
                fpvec_writes.append(word)
        gpr.update(changes)
        fp.update({int(r):int(v,16) for r,v in re.findall(r'\bf([0-9]+)\s+0x([0-9a-f]+)',tail)})
        vec.update({int(r):int(v,16) for r,v in re.findall(r'\bv([0-9]+)\s+0x([0-9a-f]+)',tail)})
    require(phase == 1 and ends == returns == 2 and len(reads_by_phase)==2 and not active and not checking,
            'incomplete two-phase execution')
    require(len(fpvec_reads)==72 and len(fpvec_writes)==144, 'missing FP/vector capture/restore')
    require(orig_reads == orig_addr, 'not all original CSR words consumed')
    require(set(CSRS)-{0x100,0xc20,0xc21,0xc22} <= csr_restores, 'CSR restoration writes missing')
    return dict(status='PASS',retired=len(commits),retired_limit=MAX_RETIRED,lr_d=8,lr_w=16,
                phases=2,ordinary_payload_stores=8,full_compared_words=reads_by_phase,
                guards_per_phase=16*len(BUFFERS),gprs_per_phase=32,fp_per_phase=32,
                vector_registers_per_phase=32,vector_bytes_per_phase=4096,csr_words_per_phase=22,
                unexpected_traps=0,pmp_regions=0,pmp_csr_accesses=0,full_abi_restored=True,
                reservation_claim=False,ordering_claim=False,coverage_gain_required=False)
