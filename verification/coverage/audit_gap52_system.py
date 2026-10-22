#!/usr/bin/env python3
"""Independent integer oracle and read-only ELF/Spike execution audit for gap52."""
import hashlib
import re

NAME = 'rvv:sv39_gap52_superpage_sfence_pmp0'
CHECKS = 110
MAX_RETIRED = 45000
PA = 0x80000000
DVA = 0x17fe00000
GUARD = 0x6b6b6b6b6b6b6b6b
MASK64 = (1 << 64)-1
REMAP = (0x5201000000000100, 0x5202000000000100, 0x5203000000000100)
WORDS = dict(gap52_hop_pc=0x297, gap52_hop_load=0x33f03,
             gap52_hop_store=0x1d33023, gap52_hop_readback=0x33f03,
             gap52_hop_ecall=0x73, gap52_remap_load=0x6b303,
             gap52_remap_store=0x116b023, gap52_remap_readback=0x6b303,
             gap52_remap_ecall=0x73)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def expected_pages(base):
    pages = [[0]*512 for _ in range(3)] + [[GUARD ^ w for w in range(512)] for _ in range(2)]
    for slot in [2, *range(32, 64)]:
        pages[0][slot] = 0x200000cf
    for slot in (4, 5):
        pages[0][slot] = ((base+4096) // 4096)*1024 + 1
    for slot in range(32):
        pages[1][slot] = 0x200000cf
    pages[1][511] = ((base+8192) // 4096)*1024 + 1
    pages[2][0] = ((base+12288) // 4096)*1024 + 0xc7
    for phase in range(2):
        for i in range(32):
            pages[3][32+phase*32+i] = 0x5200000000000000 + (phase+1)*65536 + i
    pages[3][256], pages[4][256] = REMAP[2], REMAP[1]
    return pages


def expected_command(tool, elf):
    return [tool, '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0',
            '-l', '--log-commits', elf]


def validate_pmp_dts(text):
    require(re.findall(r'riscv,pmpregions\s*=\s*<([0-9]+)>;', text) == ['0'], 'not one PMP0 hart')


def metadata(obj, blob):
    symbols = {r['Symbol']['Name']['Name']: r['Symbol']['Value'] for r in obj['Symbols']}
    names = list(WORDS) + ['gap52_remap_entry', 'gap52_payload_begin', 'gap52_payload_end',
                          'gap52_pages', 'gap52_guard_lo', 'gap52_guard_hi', 'records']
    selected = {n: symbols[n] for n in names}
    p = selected['gap52_pages']
    require(p % 4096 == 0 and PA <= p and selected['gap52_guard_hi']+64 <= PA+0x200000,
            'five pages outside aligned physical test prefix')
    require(selected['gap52_guard_lo']+64 == p and selected['gap52_guard_hi'] == p+5*4096,
            'guards not adjacent to all five pages')
    require(all(PA <= selected[n] < PA+0x200000 for n in names), 'symbol outside physical prefix')
    sites = {}
    for name, expected in WORDS.items():
        address = selected[name]
        words = []
        for row in obj['Sections']:
            sec = row['Section']
            if sec['Flags']['Value'] & 4 and sec['Address'] <= address and address+4 <= sec['Address']+sec['Size']:
                offset = sec['Offset']+address-sec['Address']
                words.append(int.from_bytes(blob[offset:offset+4], 'little'))
        require(words == [expected], 'wrong instruction word at '+name)
        sites[name] = dict(pc=hex(address), word=hex(expected))
    payload_hashes = {}
    for first,last in (('gap52_hop_pc','gap52_hop_ecall'),('gap52_remap_entry','gap52_remap_ecall')):
        start,end = selected[first],selected[last]+4
        spans = []
        for row in obj['Sections']:
            sec = row['Section']
            if sec['Flags']['Value'] & 4 and sec['Address'] <= start < end <= sec['Address']+sec['Size']:
                offset = sec['Offset']+start-sec['Address']
                spans.append(blob[offset:offset+end-start])
        require(len(spans)==1,'ambiguous S instruction range')
        payload_hashes[first] = hashlib.sha256(spans[0]).hexdigest()
    return dict(symbols=selected, sites=sites, data_words=1024, pte_words=1536, guard_words=16,
                s_payload_sha256=payload_hashes)


def check_log(log, source):
    require(re.findall(r'^gap35 checks=(\d+) failures=0$', log, re.M) == [str(CHECKS)], 'wrong selfcheck count')
    require(log.splitlines().count('PASSED: '+source+'!') == 1 and
            sum(l.startswith('PASSED:') for l in log.splitlines()) == 1, 'wrong PASS source binding')
    require(not re.search(r'(?im)^(?:FAIL|check=|Fatal:|Error:)', log), 'selfcheck failure')


def trace_check(trace, info):
    sym = info['symbols']
    for n, w in WORDS.items():
        require(info['sites'][n] == dict(pc=hex(sym[n]), word=hex(w)), 'trace site metadata differs')
    commits = [(int(m[1]), int(m[2], 16), int(m[3], 16), m[4]) for m in re.finditer(
        r'(?m)^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)([^\n]*)$', trace)]
    require(0 < len(commits) <= MAX_RETIRED, 'Spike retirement budget exceeded or empty trace')
    require(not re.search(r'(?m)^core\s+[1-9][0-9]*:', trace), 'unexpected additional hart')
    traps = [(m[1], int(m[2],16)) for m in re.finditer(r'exception\s+(\w+), epc 0x([0-9a-f]+)',trace)]
    ecall_pcs = [base+31*step+sym['gap52_hop_ecall']-PA for base,step in
                 ((0x100000000,0x200000),(0x800000000,0x40000000))] + [sym['gap52_remap_ecall']]*3
    require(traps == [('trap_supervisor_ecall', pc) for pc in ecall_pcs], 'not exactly five expected S ecalls')

    expected_sites = {}
    for phase, (base,step) in enumerate(((0x100000000,0x200000),(0x800000000,0x40000000))):
        for i in range(32):
            va = base+i*step
            word = 32+phase*32+i
            address = va+sym['gap52_pages']+3*4096-PA+8*word
            stamp = 0x5200000000000000+(phase+1)*65536+i
            for suffix, value in (('pc',va+sym['gap52_hop_pc']-PA), ('load',GUARD^word),
                                  ('store',stamp), ('readback',stamp)):
                name = 'gap52_hop_'+suffix
                expected_sites[va+sym[name]-PA] = (name, address, value)
    seen_sites, remap_seen, record_words, reads = set(), {'load':0,'store':0,'readback':0}, {}, set()
    gpr = {0:0}
    before = {}
    active, finished, begins, ends = False, False, 0, 0
    sfences = []
    page_values = expected_pages(sym['gap52_pages'])
    final_memory = {sym['gap52_pages']+p*4096+w*8:value
                    for p,page in enumerate(page_values) for w,value in enumerate(page)}
    final_memory.update({sym['gap52_guard_lo']+w*8:GUARD^w for w in range(8)})
    final_memory.update({sym['gap52_guard_hi']+w*8:(MASK64^GUARD)^w for w in range(8)})
    for mode,pc,word,tail in commits:
        if pc == sym['gap52_payload_begin']:
            begins += 1; active = True
        if pc == sym['gap52_payload_end']:
            ends += 1; active = False; finished = True
        changes = {int(r):int(v,16) for r,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)}
        mem = [(int(addr,16), int(val,16) if val else None)
               for addr,val in re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail)]
        if (word & 0x7f) == 0x73 and ((word>>12)&7):
            csr = word>>20
            require(not 0x3a0 <= csr <= 0x3ef, 'PMP CSR access in zero-PMP program')
            if not active and not finished and csr in (0xc20,0xc21) and changes:
                before[csr] = next(iter(changes.values()))
        if active:
            # This region includes the scalar S loop, M handler and selective fences only.
            require((word & 0x7f) not in (0x07,0x27,0x43,0x47,0x4b,0x4f,0x53,0x57),
                    'unexpected FP/vector instruction in scalar payload')
            require(not ((word & 3) in (0,2) and ((word>>13)&7) in (1,5)),
                    'unexpected compressed FP instruction in scalar payload')
            if word & 0xfe007fff == 0x12000073:
                r1,r2 = (word>>15)&31,(word>>20)&31
                require(r1 in gpr and r2 in gpr, 'unknown SFENCE operand')
                sfences.append((gpr[r1],gpr[r2]))
            for address,value in mem:
                if value is not None and sym['records'] <= address < sym['records']+5*13*8:
                    record_words[address] = value
        if mode == 1:
            require(active, 'S code outside payload')
            require(not mem or pc in expected_sites or pc in
                    {sym['gap52_remap_'+suffix] for suffix in remap_seen}, 'unexpected S memory access')
            if pc in expected_sites:
                require(pc not in seen_sites, 'repeated superpage site')
                seen_sites.add(pc)
                name,address,value = expected_sites[pc]
                require(word == WORDS[name], 'wrong instruction at alias')
                if name.endswith('_pc'):
                    require(changes == {5:value} and not mem, 'wrong virtual PC observation')
                elif name.endswith('_store'):
                    require(mem == [(address,value)], 'wrong alias store address/value')
                else:
                    require(mem == [(address,None)] and changes == {30:value}, 'wrong alias load address/value')
            for suffix in remap_seen:
                name = 'gap52_remap_'+suffix
                if pc != sym[name]:
                    continue
                index = remap_seen[suffix]
                require(index < 3 and word == WORDS[name], 'extra/wrong remap instruction')
                value = (GUARD^256 if index < 2 else REMAP[0]) if suffix=='load' else REMAP[index]
                if suffix == 'store':
                    require(mem == [(DVA+2048,value)], 'wrong remap store')
                else:
                    require(mem == [(DVA+2048,None)] and changes == {6:value}, 'wrong remap load')
                remap_seen[suffix] += 1
        if finished:
            for address,value in mem:
                if address in final_memory:
                    require(mode == 3 and value is None and len(changes)==1 and
                            next(iter(changes.values())) == final_memory[address],
                            'final full-region comparison read differs')
                    reads.add(address)
        gpr.update(changes)
    require(begins == ends == 1 and finished and not active, 'payload boundary count differs')
    require(seen_sites == set(expected_sites) and set(remap_seen.values()) == {3}, 'missing alias/remap execution')
    require(reads == set(final_memory), 'final comparison did not read all 2576 words')
    require(set(before) == {0xc20,0xc21}, 'missing original vector CSR snapshots')
    root = 8<<60 | sym['gap52_pages']>>12
    for i in range(5):
        expected = [0,32 if i<2 else 1,9,ecall_pcs[i],0,0x800,
                    root | ((0x22 if i==1 else 0x21)<<44),before[0xc20],before[0xc21],0,5,117,1]
        for j,value in enumerate(expected):
            address = sym['records']+(i*13+j)*8
            require(address in record_words, 'missing saved S trap CSR word')
            actual = record_words[address]
            if j == 5:
                actual &= 0x8000021888
            require(actual == value, 'S trap record differs at %d/%d' % (i,j))
    expected_fences = []
    for base,step,asid in ((0x100000000,0x200000,0x21),(0x800000000,0x40000000,0x22)):
        expected_fences += [(base+16*step,0),(base+17*step,asid),(0,asid)]
        expected_fences += [(base+i*step,asid) for i in range(32)] + [(0,0x23)]
    expected_fences += [(DVA,0x21),(0,0x21)]
    require(sfences == expected_fences, 'selective SFENCE values/order differ')
    return dict(status='PASS', retired=len(commits), retired_limit=MAX_RETIRED,
                superpage_hops=64, alias_site_commits=len(seen_sites), remap_accesses=3,
                s_ecalls=5, ecall_pcs=[hex(p) for p in ecall_pcs], trap_record_words=65,
                selective_sfences=len(sfences), pte_words=1536, data_words=1024, guard_words=16,
                final_compared_words=len(reads), pmp_regions=0, pmp_csr_accesses=0,
                asid_width=16, coverage_gain_required=False, retention_oracle=False)
