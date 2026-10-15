#!/usr/bin/env python3
"""Read-only, single-pass audit of the nine already completed NF2 references."""
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
P = HERE.parent / 'nf2_remaining34_prepare01'
ARCHIVE = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_segment_fault_handoff01')
READY_SHA = '47d7e85317fdd848ce1cfb7094920019588cde0f92183667602e6dd7b54ed3ca'
sys.path.insert(0, str(P))
import reference_core as core


def need(ok, message):
    if not ok:
        raise ValueError(message)


def read(p):
    return json.loads(Path(p).read_text())


def save(name, obj):
    with (HERE / name).open('x') as f:
        json.dump(obj, f, indent=2)
        f.write('\n')


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


class Elf:
    def __init__(self, p):
        self.data = Path(p).read_bytes()
        need(self.data[:6] == b'\x7fELF\x02\x01', 'Not ELF64 little endian')
        h = struct.unpack_from('<16sHHIQQQIHHHHHH', self.data)
        self.sections = [struct.unpack_from('<IIQQQQIIQQ', self.data, h[6]+i*h[11])
                         for i in range(h[12])]
        self.symbols = {}
        for s in self.sections:
            if s[1] != 2:
                continue
            strings = self.sections[s[6]]
            names = self.data[strings[4]:strings[4]+strings[5]]
            for off in range(s[4], s[4]+s[5], s[9]):
                n, info, other, section, addr, size = struct.unpack_from('<IBBHQQ', self.data, off)
                name = names[n:names.find(b'\0', n)].decode()
                if name:
                    self.symbols[name] = (addr, size)
        self.code = {}
        for s in self.sections:
            if not s[2] & 4:
                continue
            off = 0
            while off < s[5]:
                b = self.data[s[4]+off:s[4]+off+4]
                width = 4 if b[0] & 3 == 3 else 2
                self.code[s[3]+off] = int.from_bytes(b[:width], 'little')
                off += width


def independent_compare(memory, s, c, phase, cases):
    cfg = cases[c]
    fault, store, start, off = (cfg[k] for k in ('fault', 'store', 'start', 'base'))
    active = lambda i: i < 8 and bool(cfg['mask'] >> i & 1)
    original = lambda h: (37*h+11) & 65535
    initial = lambda field, i: 101+13*i+29*field if store else 91
    def get(a, size):
        need(all(a+j in memory for j in range(size)), f'Missing bytes at {a:x}')
        return int.from_bytes(bytes(memory[a+j] for j in range(size)), 'little')
    def eq(a, value, size):
        need(get(a, size) == value, f'Independent oracle {cfg["id"]} phase{phase} addr{a:x}')
    pages = s['mx_pages']
    golden = [original(h) for h in range(4096)]
    for i in range(8):
        if not active(i):
            continue
        for f in range(2):
            h = (off+4*i+2*f)//2
            if store and (phase != 1 or i < start):
                golden[h] = initial(f, i)
            if phase == 2 and fault and i < start:
                golden[h] = (initial(f, i) if store else original(h)) ^ 91
    for h, value in enumerate(golden):
        if phase == 1 and store and fault and off+4*start < 4096 and 2*h == off+4*start:
            need(get(pages+2*h, 2) in (original(h), initial(0, start)), 'Invalid partial field')
        else:
            eq(pages+2*h, value, 2)
    for page in (2, 3, 4):
        for word in range(512):
            value = 0
            if page == 2 and word == 1: value = ((pages+12288) >> 12 << 10) | 1
            if page == 2 and word == 2: value = 0x200000cf
            if page == 3 and word == 0: value = ((pages+16384) >> 12 << 10) | 1
            if page == 4 and (word == 0 or word == 1 and phase == 2):
                value = ((pages+4096*word) >> 12 << 10) | 0xc7
            eq(pages+page*4096+8*word, value, 8)
    for name in ('mx_guard_lo', 'mx_guard_hi'):
        for word in range(8): eq(s[name]+8*word, 0xe370697ce370697c, 8)
    for f in range(2):
        for i in range(64):
            value = 91
            if phase != 1:
                value = original((off+4*i+2*f)//2) if not store and active(i) else initial(f, i)
            eq(s['mx_out']+260*c+2*(1+64*f+i), value, 2)
    for i in (0, 129): eq(s['mx_out']+260*c+2*i, 91, 2)
    for i in range(16): eq(s['mx_mask']+16*c+i, cfg['mask'], 1)
    for j, v in enumerate((8,8,0,117,5) if phase != 1 else (2**64-1,)*5):
        eq(s['mx_post']+40*c+8*j, v, 8)


class Trace:
    """Stream once; intercept only the mature observer's final exception lookup."""
    def __init__(self, path, elf, symbols):
        self.path, self.elf, self.s = path, elf, symbols
        self.digest = hashlib.sha256()
        self.traps, self.boot, self.violations, self.target = [], [], [], []
        self.bytes = self.commits = self.park = self.htif_commit = 0
        self.before = self.stamp()
        self.iterator = self.lines()
        self.gpr = {0:0}
        self.csrs = {}
        self.vector_pcs = {}

    def stamp(self):
        s = self.path.stat()
        return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]

    def lines(self):
        with self.path.open('rb') as stream:
            for b in stream:
                self.digest.update(b)
                self.bytes += len(b)
                line = b.decode()
                self.traps += re.findall(r'exception\s+(\w+), epc 0x([0-9a-f]+)', line)
                m = re.match(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$', line)
                if m:
                    self.commits += 1
                    pc, insn, tail = int(m[2],16), int(m[3],16), m[4]
                    if pc < 0x80000000:
                        self.boot.append([pc, insn])
                    elif self.elf.code.get(pc) != insn:
                        self.violations.append(['pc_code', self.commits, hex(pc), hex(insn)])
                    if self.htif_commit:
                        pure_park = insn in (0xa001, 0x0000006f)
                        if not pure_park or tail.strip():
                            self.violations.append(['post_htif', self.commits, hex(pc), hex(insn), tail])
                        self.park += 1
                    if pc in (self.s['mx_segment_load'], self.s['mx_segment_store']):
                        self.target.append(dict(commit=self.commits, pc=hex(pc), insn=hex(insn),
                                                address=self.gpr.get(10), privilege=int(m[1]),
                                                csrs_before=dict(self.csrs)))
                    if insn & 127 == 0x57 or insn & 127 in (7,39) and (insn >> 12 & 7) in (0,5,6,7):
                        key = f'{pc:x}:{insn:08x}'
                        self.vector_pcs[key] = self.vector_pcs.get(key,0)+1
                    for a,v in re.findall(r'\bmem 0x([0-9a-f]+) 0x([0-9a-f]+)', tail):
                        if int(a,16) == self.s['tohost']:
                            if int(v,16) != 1 or self.htif_commit:
                                self.violations.append(['htif', self.commits, v])
                            self.htif_commit = self.commits
                    self.gpr.update({int(r):int(v,16) for r,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)})
                    self.csrs.update({name:int(v,16) for name,v in re.findall(r'\bc[0-9]+_([A-Za-z0-9_]+)\s+0x([0-9a-f]+)',tail)})
                yield line

    def splitlines(self):
        return self.iterator


class RegexProxy:
    match = staticmethod(re.match)
    @staticmethod
    def findall(pattern, value):
        if isinstance(value, Trace):
            need(pattern == r'exception\s+(\w+), epc 0x([0-9a-f]+)', 'Unexpected whole-trace operation')
            return value.traps
        return re.findall(pattern, value)


def main():
    need(not (HERE/'audit.json').exists(), 'Audit is single-use; never overwrite results')
    need(sha(P/'READY.json') == READY_SHA, 'READY drift')
    ready, source = read(P/'READY.json'), read(P/'source_manifest.json')
    pins = dict(ready['pins'])
    pins[str(P/'READY.json')] = READY_SHA
    raw_paths = {str(P/g['id']/'reference02/spike.trace') for g in ready['groups']}
    need(len(raw_paths) == 9, 'Expected nine raw references')
    for p, h in pins.items():
        if p not in raw_paths: need(sha(p) == h, 'Pre-pin drift: '+p)
    pre = dict(status='NON_RAW_PINS_VERIFIED_RAW_DEFERRED_TO_SINGLE_PASS', pins=pins)
    if (HERE/'pins_pre.json').exists():
        need(read(HERE/'pins_pre.json') == pre, 'Existing pre-pin record differs')
    else:
        save('pins_pre.json', pre)
    originals = read(ARCHIVE/'evidence/single_manifest.json')['cases']
    board = {c['name']:c for c in read(ARCHIVE/'evidence/single_board_report.json')['results']}
    excluded = {'u0_s0_b3_m2_f1','u0_s1_b3_m2_f1','u0_s0_b1_m2_f1',
                'u1_s1_b3_m2_f0','u0_s1_b5_m3_f1','u1_s0_b1_m3_f0'}
    cases, original_evidence = [], []
    for meta in originals:
        d = ARCHIVE/'singles'/meta['name']
        need(read(d/'case.json') == meta, 'Case differs from archive manifest')
        cfg = dict(meta['selected_trial'])
        ident = 'u%d_s%d_b%d_m%d_f%d' % tuple(cfg[k] for k in ('unmapped','store','boundary','mode','split'))
        need(meta['scenario_role']=='single_current_oracle_trial' and meta['original_rebuild_byte_identical'] is False,
             'Wrong provenance class')
        b = board[meta['name']]
        need(b['status']=='failed' and b['exit_code']==1 and 'RVV_FAULT_CONTEXT' in b['output'], 'No standalone failure')
        text = (d/'scenario.c').read_text()
        selector = ' && '.join(f'{"store_case" if k=="store" else k}=={v}' for k,v in cfg.items())
        need('if(!('+selector+'))continue;' in text, 'Original source selection mismatch')
        need('#define CAPACITY_LIMIT (128*LMUL_NUM)' in text and 'mask[CAPACITY_LIMIT/8]' in text, 'Mask declaration')
        elf = Elf(d/'scenario.elf')
        need('#define LMUL_NUM 1' in text, 'Original mask source multiplier differs')
        need(0x20055c07 in elf.code.values() and 0x20055c27 in elf.code.values(), 'Original target opcodes missing')
        if ident in excluded: continue
        offset = 4096 - 4*cfg['boundary'] - 2*cfg['split']
        mask = 0x24 if cfg['mode']==2 else 0
        start = next((i for i in range(8) if mask >> i & 1 and
                      any(offset+4*i+2*f>=4096 for f in (0,1))), 8)
        c = dict(id=ident, **cfg, base=offset, mask=mask, start=start, fault=start<8)
        cases.append(c)
        original_evidence.append(dict(**c, case_path=str(d/'case.json'), case_sha256=sha(d/'case.json'),
            elf_sha256=sha(d/'scenario.elf'), sources=meta['scenario_sources'], measured_failure=b,
            original_mask_source_size=16, original_ELF_stripped=not bool(elf.symbols)))
    need(len(cases)==34 and len({c['id'] for c in cases})==34, 'Wrong disjoint34')
    need([c['id'] for c in cases]==[c['id'] for g in source['groups'] for c in g['cases']], 'Ordering or membership drift')
    save('source_audit.json', dict(status='SOURCE34_VERIFIED', count=34, excluded=sorted(excluded),
         cases=original_evidence, original_mask_bytes=16, prepared_metadata_original_mask_bytes=128,
         correction='Metadata only: actual original and fixture both allocate16B; vlm consumes8B.',
         original_parent_byte_identity=False, Linux_signalframe_proved=False))
    groups=[]
    original_compare = core.model.compare
    core.re = RegexProxy
    boot = [[0x1000,0x297],[0x1004,0x02028593],[0x1008,0xf1402573],
            [0x100c,0x0182b283],[0x1010,0x00028067]]
    for gi, g in enumerate(ready['groups']):
        root=P/g['id']/'reference02'
        configured=cases[4*gi:4*gi+4]
        need(g['MX_N']==len(configured), 'Group count drift')
        dims={}; elfs={}
        for kind in ('soc','spike'):
            elf=Elf(root/(kind+'.elf')); elfs[kind]=elf
            symbols=read(root/(kind+'.symbols.json'))
            need(all(elf.symbols[k][0]==v for k,v in symbols.items()), 'Symbol JSON differs from ELF')
            sizes={'mx_seed':640,'mx_fault':640,'mx_result':640,'mx_out':260,'mx_mask':16,
                   'mx_records':192,'mx_post':40,'mx_count':8,'mx_marker':8,'mx_case_checks':8}
            dims[kind]={k:elf.symbols[k][1] for k in sizes}
            need(all(dims[kind][k]==v*len(configured) for k,v in sizes.items()), 'Compiled group dimensions')
            need(symbols['mx_guard_lo']+64==symbols['mx_pages'] and
                 symbols['mx_guard_hi']==symbols['mx_pages']+20480 and symbols['__bss_end']<0x800f0000,
                 'Page/guard/BSS layout differs')
            for site, opcode in [('mx_segment_load',0x20055c07),('mx_segment_store',0x20055c27)]:
                need(elf.code[symbols[site]]==opcode, 'Compiled target code mismatch')
        s=read(root/'spike.symbols.json')
        core.configure(configured)
        checkpoints=[]
        def compare(memory, symbols, c, phase):
            independent_compare(memory,symbols,c,phase,configured)
            count=original_compare(memory,symbols,c,phase)
            checkpoints.append(dict(case=configured[c]['id'],phase=phase,full_outputs=128,
                                    output_guards=2,fullmemory_bytes=8192,PTE_words=1536,
                                    mature_checked_bytes=count))
            return count
        core.compare=compare
        trace=Trace(root/'spike.trace',elfs['spike'],s)
        errors=[]; result=None; started=time.monotonic()
        try:
            result=core.validate(trace,s)
        except Exception as error:
            errors.append(type(error).__name__+': '+str(error))
            for unused in trace.iterator: pass
        stored=read(root/'status.json')
        raw_sha=trace.digest.hexdigest()
        if raw_sha!=pins[str(trace.path)] or raw_sha!=stored['raw_sha256']:errors.append('Raw hash drift')
        if trace.before!=trace.stamp():errors.append('Raw stat changed during single pass')
        if trace.boot!=boot:errors.append('Unexpected boot instruction identities: '+str(trace.boot))
        if trace.violations:errors.append('PC/code/HTIF violations')
        if result is not None:
            for k,v in result.items():
                if json.loads(json.dumps(v))!=stored[k]:errors.append('Stored status mismatch: '+k)
        if stored['process_returncode']!=0:errors.append('Stored reference returncode not zero')
        if stored['isa']!='rv64gcv_zfh_zvfh_zvl1024b':errors.append('ISA mismatch')
        if trace.bytes!=stored['raw_bytes']:errors.append('Raw size mismatch')
        entry=dict(id=g['id'],status='REFERENCE_ACCEPTED' if not errors else 'NOT_ACCEPTED',errors=errors,
            original_cases=configured,actual_dimensions=dims,raw_sha256=raw_sha,raw_bytes=trace.bytes,
            raw_stat_before=trace.before,raw_stat_after=trace.stamp(),raw_passes=1,
            reference_result=result,independent_checkpoints=checkpoints,pc_code_violations=trace.violations,
            target_registers=trace.target,vector_pc_counts=trace.vector_pcs,boot=trace.boot,
            htif_commit=trace.htif_commit,post_htif_park=trace.park,
            firmware_commits_to_htif=trace.htif_commit-len(trace.boot),
            reference_elapsed_s=stored['reference_elapsed_s'],audit_elapsed_s=time.monotonic()-started,
            soc_elf_sha256=sha(root/'soc.elf'),spike_elf_sha256=sha(root/'spike.elf'))
        save(g['id']+'.json',entry);groups.append(entry)
        print(g['id'],entry['status'],trace.commits,errors,flush=True)
        if errors: break
    for p,h in pins.items():
        if p not in raw_paths:need(sha(p)==h,'Post-pin drift: '+p)
    accepted=len(groups)==9 and all(g['status']=='REFERENCE_ACCEPTED' for g in groups)
    out=dict(schema='nf2_remaining34_independent_reference_audit_v1',
        status='ACCEPTED_REFERENCE34_NOT_DUT' if accepted else 'NOT_ACCEPTED',
        READY_sha256=READY_SHA,source_audit_sha256=sha(HERE/'source_audit.json'),
        audit_script_sha256=sha(__file__),pins_sha256=sha(HERE/'pins_pre.json'),
        pins_count=len(pins),nonraw_pins_pre_post_equal=True,
        raw_pin_policy='SHA256 during sole complete parse; stat identity before/after; no second raw read',
        groups=[dict(id=g['id'],status=g['status'],audit_sha256=sha(HERE/(g['id']+'.json')),
                     commits=g['reference_result']['commits'] if g['reference_result'] else None,
                     checks=g['reference_result']['checks'] if g['reference_result'] else None,
                     soc_elf_sha256=g['soc_elf_sha256']) for g in groups],
        reference_only=True,DUT_started=False,pilot_queried=False,PASS40=False,
        nonblocking_findings=['Original mask bytes metadata128 is incorrect: original C proves16; original ELF stripped; fixture16, consumed8.'],
        blockers=[] if accepted else ['See per-group independent results; no automatic reparse.'])
    save('audit.json',out)
    print(out['status'],sha(HERE/'audit.json'),flush=True)


if __name__=='__main__':
    main()
