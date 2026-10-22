"""Derive only from the actual SoC ELF/disassembly and reviewed lowering."""
from functools import lru_cache
from scope import *

source = load('unboxed17920_reference_methods', REF/'checker.py')
linked = load('unboxed17920_linked_soc', G/'fp_compare_unboxed_full17920_prepare01/compile01/inspect_linked.py')

linked.RUN = STAGE/'execution01'

def csr(c): return c & 127 == 0x73 and (c >> 12) & 7 != 0
def vector(c):
    return c & 127 == 0x57 or c & 127 in (7, 39) and (c >> 12) & 7 in (0, 5, 6, 7)
def offload(c):
    return vector(c) or csr(c) and c >> 20 in (8, 9, 10, 15, 0xc20, 0xc21, 0xc22)

@lru_cache(maxsize=1)
def specification():
    require(sha(ELF) == ELF_SHA, 'Actual SoC ELF identity')
    d, code, funcs, sy, sizes = linked.parse('soc')
    require(d == SOFTWARE and 'replay_log' not in sy and 'tohost' not in sy, 'SoC not Spike')
    image = source.elf_image(ELF)
    for pc, r in code.items():
        require(source.word(image, pc, len(r['insn'])//2) == int(r['insn'], 16), 'ELF PC/code bytes')
    lower = read(STAGE/'linked_cfg01/soc.json')
    require(lower['elf_sha256']==ELF_SHA and lower['extra_vector_FP']==[], 'Reviewed actual FP32 lowering')
    blob=ELF.read_bytes()
    # num() supplies decimal fields at runtime; the complete line is not a ROM literal.
    for marker in ('RVV_FP_COMPARE_PASS sew=',' cases=',' errors=',
                   'BOARD_CASE_BEGIN '+NAME,'BOARD_CASE_PASS '+NAME,'BOARD_REPLAY_PASS'):
        require(marker.encode() in blob,'Actual ELF console marker '+marker)
    helpers = [funcs['op_'+str(i)] for i in range(10)]
    require([len(h) for h in helpers] == [17]*4+[19]*6, 'All185 original helper instructions')
    # Match the reviewed original encoding proof, independent of relocation.
    old = read(REF/'spec.json')['helpers']
    require([[r['insn'] for r in h] for h in helpers] == [[r['insn'] for r in h] for h in old],
            'Original helper185 byte identity')
    def one(name, op=None, args=None, insn=None):
        rows = [r for r in funcs[name] if (op is None or r['op'] == op)
                and (args is None or r['args'].split(' #')[0] == args)
                and (insn is None or int(r['insn'], 16) == insn)]
        require(len(rows) == 1, 'Unique actual linked site '+repr((name, op, args, insn)))
        return rows[0]['pc']
    prelude = [r['pc'] for n in ('_start', 'main') for r in funcs[n] if csr(int(r['insn'],16))]
    require([int(code[p]['insn'],16) for p in prelude] ==
            [0x30401073,0x30529073,0x3002a073,0x00305073,0x00805073,0xc2202773], 'Bootstrap CSR six')
    opaque = []
    for n in (NAME+'_main','main'):
        for r in funcs[n]:
            if r['op'] == 'jal': break
            if r['op'] == 'sd' and '(sp)' in r['args'] and r['args'].split(',')[0] not in ('ra','zero'):
                opaque.append(r['pc'])
    # Source failure PCs come from the reviewed complete positive CFG partition.
    failure = [int(p,16) for p in lower['zero_positive_execution_PCs']]
    # Exact SoC wrapper diagnostics, not a relocation of the Spike wrapper.
    ranges = [(0x80000762,0x80000772),(0x80000790,0x800007a0),(0x8000081c,0x80000834)]
    failure += [p for p in code if any(lo<=p<hi for lo,hi in ranges)]
    failure += [r['pc'] for n in ('trap_entry','replay_trap','hex') for r in funcs[n]]
    require(all(p in code for p in failure),'Every failure PC is an actual instruction')
    sites = dict(record_load=one(NAME+'_main','ld','s6,0(a4)'),
                 output_read=one(NAME+'_main','lwu','s0,0(s0)'),
                 caller_record=one(NAME+'_main','srli','a4,s6,0x20'),
                 caller_flags=one(NAME+'_main','or','a4,a4,t0'),
                 bss_store=one('_start',insn=0x0002b023),
                 main_call=one('_start','jal',hex(sy['main'])[2:]+' <main>'),
                 exit_store=one('replay_exit',insn=0x00a2b023))
    sites['park'] = sites['exit_store']+4
    require(int(code[sites['park']]['insn'],16)==0xa001, 'Actual CTRL park')
    return dict(elf=str(ELF),elf_sha256=ELF_SHA,symbols=sy,sizes=sizes,
        code={str(p):r for p,r in code.items()},helpers=helpers,capacity=funcs['capacity'],
        stores=lower['fresh_stores'],input_loads=lower['input_LD_sites'],
        prelude=prelude,opaque_initial_spills=opaque,failure_pcs=sorted(set(failure)),
        uart_stores=[one(n,'sb','a4,0(a5)') for n in ('replay_text','replay_write')],
        BSS_bytes=sy['__bss_end']-sy['__bss_start'],**sites)

@lru_cache(maxsize=1)
def model():
    rows = read(STAGE/'generated01/model.json')['rows']
    require(len(rows)==17920, 'Full original parent, no prefix')
    return rows

def helper_owner(spec, op, i, g):
    c = int(spec['helpers'][op][i]['insn'],16)
    if not offload(c): return None
    if c & 127 in (7,39):
        require(i in (2,3,4,5,15+(2 if op>=4 else 0)), 'Unclassified helper memory')
        return ('memory',True)
    if c & 127 == 0x57 and (c>>12)&7 != 7:
        require(i == 8+(2 if op>=4 else 0), 'Unclassified target')
        return ('target',g['vl']>0)
    return ('configuration',False)

def owner_contract():
    s=specification(); counts={'memory':0,'target_required':0,'target_elidable':0}
    for g in model():
        for i in range(len(s['helpers'][g['op']])):
            v=helper_owner(s,g['op'],i,g)
            if v and v[0]=='memory': counts['memory']+=1
            if v and v[0]=='target': counts['target_required' if v[1] else 'target_elidable']+=1
    require(counts==dict(memory=89600,target_required=15360,target_elidable=2560), 'Derived185 owner coverage')
    return counts
