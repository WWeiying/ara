"""Independent gap70 integer, ELF and ordered architectural trace audit."""
import hashlib
import re

NAME = 'rvv:vgap70_indexed_fault_recover'
CHECKS = 85
MAX_RETIRED = 35000
VA = 0x40000000
GUARD = 0xe370697c
OFFSETS = (0x300, 0x40, 0x98, 0x384, 0x1f0, 0x730, 0x404, 0xc08)
REGS = (7, 8, 9, 15, 16, 17)
WORDS = dict(gap70_indexed_load=0x0f03e407, gap70_repair_store=0x006e3023,
             gap70_repair_sfence=0x120e0073, gap70_retry_mret=0x30200073,
             gap70_younger_store=0x0062b023, gap70_ecall=0x73)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def expected_vectors():
    seed = [[0x6c700000 ^ (r << 16) ^ w for w in range(32)] for r in range(6)]
    seed[4][:8] = OFFSETS
    result = [r[:] for r in seed]
    result[1][:8] = [0x91700000 ^ (a // 4) for a in OFFSETS]
    return seed, result


def expected_command(tool, elf):
    return [tool, '--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0',
            '-l', '--log-commits', elf]


def validate_pmp_dts(text):
    require(re.findall(r'riscv,pmpregions\s*=\s*<([0-9]+)>;', text) == ['0'], 'not one PMP0 hart')


def check_log(log, source):
    require(re.findall(r'^gap35 checks=(\d+) failures=0$', log, re.M) == [str(CHECKS)], 'wrong selfcheck count')
    require(log.splitlines().count('PASSED: '+source+'!') == 1 and
            sum(l.startswith('PASSED:') for l in log.splitlines()) == 1, 'wrong PASS source')
    require(not re.search(r'(?im)^(?:FAIL|check=|Fatal:|Error:)', log), 'selfcheck failure')


def metadata(obj, blob):
    symbols = {r['Symbol']['Name']['Name']: r['Symbol']['Value'] for r in obj['Symbols']}
    names = list(WORDS) + ['gap70_s_entry', 'gap70_s_end', 'gap70_handler', 'gap70_handler_end',
        'gap70_checks_begin', 'gap70_checks_end', 'gap70_pages', 'gap70_guard_lo', 'gap70_guard_hi',
        'seed', 'fault', 'result', 'records', 'post', 'marker', 'trap_count', 'repair_pte', 'm_frame',
        'gap70_m_resume']
    sym = {n: symbols[n] for n in names}
    require(all(0x80000000 <= a < 0x80200000 for a in sym.values()), 'symbol outside DUT RAM prefix')
    p = sym['gap70_pages']
    require(p % 4096 == 0 and sym['gap70_guard_lo']+64 == p and
            sym['gap70_guard_hi'] == p+16384, 'illegal page/guard layout')
    require(sym['gap70_guard_hi']+64 <= 0x80200000, 'high guard outside RAM')
    for n in ('seed', 'fault', 'result'):
        require(sym[n] % 64 == 0 and sym[n]+896 <= 0x80200000, 'illegal vector buffer layout')

    def bytes_at(start, size):
        spans = []
        for row in obj['Sections']:
            sec = row['Section']
            if sec['Flags']['Value'] & 4 and sec['Address'] <= start and start+size <= sec['Address']+sec['Size']:
                off = sec['Offset']+start-sec['Address']
                spans.append(blob[off:off+size])
        require(len(spans) == 1 and len(spans[0]) == size, 'ambiguous executable bytes')
        return spans[0]

    sites = {}
    for n, w in WORDS.items():
        actual = int.from_bytes(bytes_at(sym[n], 4), 'little')
        require(actual == w and sym[n] % 4 == 0, 'wrong raw opcode at '+n)
        sites[n] = dict(pc=hex(sym[n]), word=hex(actual))
    # Normalize only verified PC-relative la pairs. Raw bytes remain sealed too.
    # C/CRT layout differs between DUT and Spike, but no semantic instruction may differ.
    payloads = {}
    reverse = {a:n for n,a in sym.items()}
    for first, last in (('gap70_s_entry','gap70_s_end'), ('gap70_handler','gap70_handler_end')):
        start, end = sym[first], sym[last]
        require(start < end and (end-start) % 4 == 0, 'unaligned payload extent')
        raw = bytes_at(start, end-start)
        words = [int.from_bytes(raw[i:i+4], 'little') for i in range(0,len(raw),4)]
        normalized, relocations, i = [], [], 0
        while i < len(words):
            w = words[i]
            require(w & 3 == 3, 'compressed instruction in audited payload')
            if w & 0x7f == 0x17:
                require(i+1 < len(words), 'trailing auipc')
                a = words[i+1]; rd = (w >> 7) & 31
                require(a & 0x707f == 0x13 and (a >> 7) & 31 == rd and
                        (a >> 15) & 31 == rd, 'auipc not a verified la pair')
                upper = w & 0xfffff000
                if upper & (1 << 31): upper -= 1 << 32
                lower = a >> 20
                if lower & 0x800: lower -= 4096
                target = start+4*i+upper+lower
                require(target in reverse, 'la points to unreviewed symbol')
                token = 'la:x%d:%s' % (rd,reverse[target])
                normalized.append(token); relocations.append(dict(offset=4*i,target=reverse[target]))
                i += 2
            else:
                normalized.append('%08x' % w); i += 1
        payloads[first] = dict(raw_sha256=hashlib.sha256(raw).hexdigest(),
            normalized_sha256=hashlib.sha256('\n'.join(normalized).encode()).hexdigest(),
            bytes=len(raw), relocations=relocations)
    return dict(symbols=sym, sites=sites, payloads=payloads)


def payload_identity(info):
    return {n: (p['normalized_sha256'],p['bytes'],p['relocations']) for n,p in info['payloads'].items()}


def final_memory(sym):
    seed, result = expected_vectors()
    final = {sym['gap70_pages']+8*w:(8,((0x91700000 ^ (2*w+1)) << 32) | (0x91700000 ^ (2*w)))
             for w in range(512)}
    p = sym['gap70_pages']
    pte = lambda a,f: (a >> 12 << 10) | f
    tables = [[0]*512 for _ in range(3)]
    tables[0][1], tables[0][2] = pte(p+8192,1), 0x200000cf
    tables[1][0], tables[2][0] = pte(p+12288,1), pte(p,0xc7)
    for t,page in enumerate(tables):
        final.update({p+(t+1)*4096+w*8:(8,v) for w,v in enumerate(page)})
    for n in ('gap70_guard_lo','gap70_guard_hi'):
        final.update({sym[n]+4*w:(4,GUARD) for w in range(16)})
    for n,values in (('seed',seed),('fault',seed),('result',result)):
        final.update({sym[n]+64+r*128+w*4:(4,v) for r,row in enumerate(values) for w,v in enumerate(row)})
        for off in (0,832):
            final.update({sym[n]+off+4*w:(4,GUARD) for w in range(16)})
    return final


def trace_check(trace, info):
    sym, sites = info['symbols'], info['sites']
    for n,w in WORDS.items():
        require(sites[n] == dict(pc=hex(sym[n]),word=hex(w)), 'trace site metadata differs')
    pattern = re.compile(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)([^\n]*)$')
    retired, traps, actions = 0, [], []
    indexed_attempts = 0
    awaiting_retry = False
    partial_logs = 0
    partial_pending = False
    records, post, reads, gpr = {}, {}, set(), {0:0}
    final = final_memory(sym)
    check_active = False
    check_begin = check_end = 0
    s_active = False
    seed, result = expected_vectors()
    seen_sites = {n:0 for n in WORDS}
    vector_stores = {'fault':set(), 'result':set()}
    leaf_address = sym['gap70_pages']+12288
    for line in trace.splitlines():
        require(not re.match(r'^core\s+[1-9][0-9]*:',line), 'additional hart')
        executed = re.match(r'^core\s+0:\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)',line)
        if executed and int(executed[1],16)==sym['gap70_indexed_load']:
            require(int(executed[2],16)==WORDS['gap70_indexed_load'], 'wrong indexed attempted opcode')
            indexed_attempts += 1
            actions.append('indexed_attempt')
        trap = re.search(r'exception\s+(\w+), epc 0x([0-9a-f]+)',line)
        if trap:
            traps.append((trap[1],int(trap[2],16)))
            actions.append('fault' if trap[1]=='trap_load_page_fault' else 'ecall')
            if trap[1]=='trap_load_page_fault':
                require(partial_pending, 'fault missing exact first-element partial log')
                partial_pending = False
                awaiting_retry = True
        m = pattern.match(line)
        if not m: continue
        retired += 1
        mode,pc,word,tail = int(m[1]),int(m[2],16),int(m[3],16),m[4]
        require(not partial_pending, 'retired instruction between partial vector log and fault')
        changes = {int(r):int(v,16) for r,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)}
        mem = [(int(a,16),int(v,16) if v else None) for a,v in
               re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail)]
        if pc==sym['gap70_indexed_load'] and indexed_attempts==1 and not traps:
            # execute.cc logs the vector's vstart even when mem_trap_t prevents retirement.
            require(mode==1 and word==WORDS['gap70_indexed_load'] and not mem and not changes and
                re.fullmatch(r'\s+e32 m1 l8 c8_vstart 0x0+\s*',tail), 'nonzero/side-effecting partial log')
            partial_logs += 1; partial_pending = True; actions.append('indexed_partial')
            continue
        if pc == sym['gap70_s_entry']: s_active = True
        if pc == sym['gap70_m_resume']: s_active = False
        if pc == sym['gap70_checks_begin']: check_active = True; check_begin += 1
        if pc == sym['gap70_checks_end']: check_active = False; check_end += 1
        if word & 0x7f == 0x73 and (word >> 12) & 7:
            require(not 0x3a0 <= word >> 20 <= 0x3ef, 'absent PMP CSR accessed')
            if awaiting_retry and word >> 20 == 0x341:
                funct,rs1 = (word >> 12) & 7,(word >> 15) & 31
                require(funct in (2,3,6,7) and rs1==0, 'fault EPC modified instead of original-PC retry')
        for n in WORDS:
            if pc != sym[n]: continue
            require(word == WORDS[n], 'wrong executed opcode')
            seen_sites[n] += 1
            require(mode == (1 if n in ('gap70_indexed_load','gap70_younger_store','gap70_ecall') else 3),
                    'wrong execution privilege')
            actions.append(n)
            if n == 'gap70_retry_mret': awaiting_retry = False
            if n == 'gap70_indexed_load':
                require(traps == [('trap_load_page_fault',sym[n])], 'indexed commit before exact fault')
                require(mem == [(VA+a,None) for a in OFFSETS], 'wrong successful indexed addresses')
                vector = re.findall(r'\bv8\s+0x([0-9a-f]+)',tail)
                expected = sum(v << (32*w) for w,v in enumerate(result[1]))
                require(len(vector)==1 and int(vector[0],16)==expected and 'e32 m1 l8' in tail,
                        'wrong full destination/tail or indexed shape')
            elif n == 'gap70_repair_store':
                require(mem == [(leaf_address,(sym['gap70_pages'] >> 12 << 10)|0xc7)], 'wrong repaired PTE')
            elif n == 'gap70_repair_sfence':
                require(gpr.get(28)==VA and not mem, 'wrong exact SFENCE operands')
            elif n == 'gap70_younger_store':
                require(mem == [(sym['marker'],1)], 'wrong younger marker store')
        for a,v in mem:
            if s_active and v is not None:
                # No data/page-table store is allowed except the single M repair.
                require(not sym['gap70_pages'] <= a < sym['gap70_pages']+16384 or
                        pc == sym['gap70_repair_store'], 'payload has data/page-table store side effect')
                if sym['records'] <= a < sym['records']+192:
                    require(mode==3 and a not in records, 'trap record overwritten or wrong mode')
                    records[a]=v
                if sym['post'] <= a < sym['post']+40:
                    require(mode==1 and a not in post, 'post CSR overwritten or wrong mode')
                    post[a]=v
                for n in vector_stores:
                    start = sym[n]+64
                    if start <= a < start+768:
                        require(mode==(3 if n=='fault' else 1), 'snapshot privilege differs')
                        r,w = divmod((a-start)//4,32)
                        expected = seed[r][w] if n=='fault' else result[r][w]
                        require(v == expected and a not in vector_stores[n], 'snapshot data overwritten/wrong')
                        vector_stores[n].add(a)
            if check_active and a in final:
                width,expected = final[a]
                require(mode==3 and v is None and len(changes)==1 and
                        next(iter(changes.values())) & ((1 << (width*8))-1) == expected,
                        'full final comparison read differs')
                reads.add(a)
        # An S store may only write the post CSRs, successful marker, or full result.
        if mode == 1:
            require(s_active, 'S instruction outside payload')
            for a,v in mem:
                if v is None: continue
                require(sym['post'] <= a < sym['post']+40 or
                        sym['result']+64 <= a < sym['result']+832 or
                        (a == sym['marker'] and pc==sym['gap70_younger_store']), 'foreign S store')
        gpr.update(changes)
    require(partial_logs==1 and not partial_pending, 'wrong partial vector log count')
    retired -= partial_logs
    require(0 < retired <= MAX_RETIRED, 'retirement budget exceeded or empty trace')
    require(traps == [('trap_load_page_fault',sym['gap70_indexed_load']),
                      ('trap_supervisor_ecall',sym['gap70_ecall'])], 'not exactly fault then S ecall')
    require(indexed_attempts==2 and actions == ['indexed_attempt','indexed_partial','fault','gap70_repair_store',
        'gap70_repair_sfence','gap70_retry_mret','indexed_attempt','gap70_indexed_load',
        'gap70_younger_store','ecall'], 'wrong fault/retry/store ordering or attempt count')
    require(seen_sites == {n:(0 if n=='gap70_ecall' else 1) for n in WORDS}, 'missing/duplicate retired site')
    satp = (8 << 60) | ((sym['gap70_pages']+4096) >> 12)
    for i in range(2):
        values = [9 if i else 13,sym['gap70_ecall' if i else 'gap70_indexed_load'],
                  0 if i else VA+OFFSETS[0],0x800,satp,8,16,0,117,5,i,
                  ((sym['gap70_pages'] >> 12 << 10)|0xc7) if i else 0]
        for j,v in enumerate(values):
            a = sym['records']+(i*12+j)*8
            require(a in records and (records[a] & 0x8000021888 if j==3 else records[a]) == v,
                    'exact trap record differs at %d/%d' % (i,j))
    require(post == {sym['post']+8*i:v for i,v in enumerate((8,16,0,117,5))}, 'post CSR capture differs')
    require(all(len(v)==192 for v in vector_stores.values()), 'incomplete before/after vector snapshots')
    require(check_begin == check_end == 1 and reads == set(final), 'incomplete full memory/guard comparisons')
    return dict(status='PASS',retired=retired,retired_limit=MAX_RETIRED,partial_vector_logs=1,load_page_faults=1,
        indexed_attempts=2,indexed_commits=1,s_ecalls=1,exact_epc_retry=True,trap_record_words=24,
        pre_fault_vector_words=192,final_compared_words=len(reads),data_words=1024,pte_words=1536,
        guard_words=128,source_index_words=32,destination_tail_words=24,
        precise_younger_store=True,pmp_regions=0,pmp_csr_accesses=0)
