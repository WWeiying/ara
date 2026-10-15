"""Bounded static feasibility inspection; never executes either input ELF."""
import hashlib
import json
from pathlib import Path
import re
import struct
import time
from collections import deque

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
OLD = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_additions30/binaries/rvv_fp_compare_unmasked_e16_mf4')
NEW = BASE / 'rebuilt.elf'
DIS = BASE / 'old_new.disassembly.txt'
BRANCH = {'beq', 'bne', 'beqz', 'bnez', 'bltu', 'bgeu', 'blt', 'bge'}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(name, value):
    with (HERE / name).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def elf(p):
    d = p.read_bytes()
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', d)
    assert h[0][:6] == b'\x7fELF\x02\x01' and h[2] == 243
    rows = [struct.unpack_from('<IIQQQQIIQQ', d, h[6]+i*h[11]) for i in range(h[12])]
    sn = rows[h[13]]
    names = d[sn[4]:sn[4]+sn[5]]
    s = {}
    for r in rows:
        n = names[r[0]:].split(b'\0')[0].decode()
        s[n] = dict(address=r[3], offset=r[4], size=r[5], align=r[8], type=r[1])
    return d, s, h[4]


def payload(e, name):
    d, s, _ = e
    q = s[name]
    return d[q['offset']:q['offset']+q['size']]


def decode(text, e):
    out = {}
    for line in text.splitlines():
        m = re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(\S+)\s*(.*?)\s*$', line)
        if not m:
            continue
        pc, code, op, arg = m.groups()
        pc = int(pc, 16)
        arg = arg.split('#')[0].strip()
        out[pc] = dict(pc=pc, code=code, op=op, arg=arg, size=len(code)//2)
    s = e[1]['.text']
    at = s['address']
    for pc, i in sorted(out.items()):
        assert pc == at and i['size'] in (2, 4)
        off = s['offset'] + pc-s['address']
        assert int.from_bytes(e[0][off:off+i['size']], 'little') == int(i['code'], 16)
        at += i['size']
    assert at == s['address']+s['size']
    return out


def target(i):
    return int(i['arg'].split(',')[-1], 16)


def cfg(ins):
    result = []
    for pc, i in ins.items():
        op = i['op']
        nxt = pc+i['size']
        edges = []
        boundary = None
        if op == 'j':
            edges = [('jump', target(i))]
        elif op in BRANCH:
            edges = [('taken', target(i)), ('fallthrough', nxt)]
        elif op == 'jal':
            edges = [('call', target(i)), ('continuation', nxt)]
        elif op == 'ret':
            boundary = 'RETURN_REQUIRES_LINK_STACK_RELATION'
        elif op == 'jalr':
            boundary = 'INDIRECT_TARGET_PROVENANCE_REQUIRED'
            edges = [('continuation', nxt)]
        else:
            edges = [('fallthrough', nxt)]
            if op == 'ecall':
                boundary = 'EXTERNAL_SYSCALL_CONTRACT_REQUIRED'
        assert all(dest in ins for _, dest in edges)
        result.append(dict(**i, edges=edges, boundary=boundary))
    return result


def main():
    started = time.monotonic()
    assert not (HERE / 'result.json').exists(), 'No repeated analysis'
    expected = {OLD: 'bef54674b16fdeefdb37295d035b1b9a58cd446cd54662078aa24e83cced7b2d',
                NEW: '673d58fc8c83581bae8b5ee008a4c9a41403982c84c67dd830639aca6d4723bb',
                DIS: '8ac711b1ddce664a831763a905ddbb5f9a740b7ad97fa6d0e1ad21829446c098'}
    assert all(sha(p) == v for p, v in expected.items())
    pins = {str(p): sha(p) for p in [*expected, Path(__file__), HERE/'ALGORITHM.md']}
    save('pins_pre.json', pins)
    es = [elf(OLD), elf(NEW)]
    parts = re.split(r'^.*:     file format elf64-littleriscv\s*$', DIS.read_text(), flags=re.M)[1:]
    assert len(parts) == 2
    ins = [decode(parts[n], es[n]) for n in range(2)]
    graphs = [cfg(x) for x in ins]
    save('full_cfg.json', dict(old=graphs[0], new=graphs[1]))
    rd = [payload(e, '.rodata') for e in es]
    assert len(rd[0]) == len(rd[1]) == 12648
    ptrs = [(struct.unpack_from('<Q', rd[0], o)[0], struct.unpack_from('<Q', rd[1], o)[0])
            for o in range(280, 360, 8)]
    assert all(a in ins[0] and b in ins[1] and b == a+2 for a, b in ptrs)
    assert rd[0][:280] == rd[1][:280] and rd[0][360:] == rd[1][360:]
    assert all(es[0][1]['.bss'][k] == es[1][1]['.bss'][k] for k in ('address','size','align','type'))
    suffix = [payload(e,'.text')[start-e[1]['.text']['address']:] for e,start in zip(es,[0x10538,0x1053a])]
    assert suffix[0] == suffix[1] and len(suffix[0]) == 744
    q = deque([(es[0][2],es[1][2]), *ptrs])
    mapped, reverse, unknown, stutters, relocations = {}, {}, [], [], []

    def chase(pc, side):
        seen = set()
        while ins[side][pc]['op'] == 'j':
            if pc in seen:
                return pc, True
            seen.add(pc)
            dest = target(ins[side][pc])
            stutters.append(dict(side=side, pc=pc, destination=dest))
            pc = dest
        return pc, False

    while q:
        assert time.monotonic()-started < 110
        a,b = q.popleft()
        a,ad = chase(a,0)
        b,bd = chase(b,1)
        if ad or bd:
            unknown.append(dict(old=a,new=b,reason='DIVERGENCE_MAPPING_REQUIRED'))
            continue
        if a in mapped or b in reverse:
            if mapped.get(a) != b or reverse.get(b) != a:
                unknown.append(dict(old=a,new=b,reason='NONBIJECTIVE_MAPPING'))
            continue
        x,y = ins[0][a],ins[1][b]
        reason = None
        if x['op'] != y['op']:
            reason = 'OPCODE_MISMATCH_NOT_J_STUTTER_OR_RELOCATION'
        elif x['op'] in BRANCH or x['op'] == 'jal':
            if x['arg'].split(',')[:-1] != y['arg'].split(',')[:-1]:
                reason = 'CONTROL_REGISTER_MISMATCH'
        elif x['arg'] != y['arg'] or x['code'] != y['code']:
            # Only adjacent constant lui/addi pairs; no blanket segment masking.
            valid = False
            if x['op'] == 'addi':
                ax,by = x['arg'].split(','),y['arg'].split(',')
                px,py = ins[0].get(a-2,ins[0].get(a-4)),ins[1].get(b-2,ins[1].get(b-4))
                if ax[:2] == by[:2] and len(ax)==len(by)==3 and ax[0]==ax[1] and px and py and px['op']==py['op']=='lui':
                    lx,ly = px['arg'].split(','),py['arg'].split(',')
                    if lx[0]==ly[0]==ax[0]:
                        va=(int(lx[1],0)<<12)+int(ax[2],0)
                        vb=(int(ly[1],0)<<12)+int(by[2],0)
                        oa,ob=va-es[0][1]['.rodata']['address'],vb-es[1][1]['.rodata']['address']
                        valid = oa==ob and 0<=oa<len(rd[0]) and not 280<=oa<360
                        if valid:
                            relocations.append(dict(old_pc=a,new_pc=b,old_address=va,new_address=vb,offset=oa))
            if not valid:
                reason = 'OPERAND_ENCODING_OR_ADDRESS_PROVENANCE_UNPROVEN'
        if reason:
            unknown.append(dict(old=a,new=b,reason=reason,old_instruction=x,new_instruction=y))
            continue
        mapped[a]=b
        reverse[b]=a
        op=x['op']
        if op in ('ret','ecall','jalr'):
            unknown.append(dict(old=a,new=b,reason={'ret':'RETURN_LINK_STACK_RELATION_UNPROVEN','ecall':'EXTERNAL_SYSCALL_CONTRACT_UNPROVEN','jalr':'INDIRECT_TABLE_LOAD_PROVENANCE_UNPROVEN'}[op]))
        if op == 'ret':
            continue
        if op in BRANCH or op == 'jal':
            q.append((target(x),target(y)))
        q.append((a+x['size'],b+y['size']))
    # Exact known differing block, independently recorded even if traversal stops earlier.
    known = dict(old=ins[0][0x1045e],new=ins[1][0x1046e],
                 obligation='Requires s8==1 on every incoming state; not an authorized relocation/stutter rule')
    save('partial_mapping.json', dict(pc_pairs=sorted(mapped.items()),stutters=stutters,
                                    relocations=relocations,frontiers=unknown,known_add_addi=known))
    post={p:sha(Path(p)) for p in pins}
    assert post==pins
    save('pins_post.json',post)
    save('result.json',dict(status='UNKNOWN_STRICT_WHOLE_PROGRAM_EQUIVALENCE_NOT_PROVEN',
        instruction_counts=[len(x) for x in ins],strict_matched_nonjump_pairs=len(mapped),
        old_unmapped_pcs=[p for p in ins[0] if p not in mapped],
        new_unmapped_pcs=[p for p in ins[1] if p not in reverse],
        unresolved_frontiers=len(unknown),data_except_exact_pointer_table_equal=True,
        helper_suffix_identical_bytes=744,pins_unchanged=True,
        historical_C_status='NOT_RECOVERED',semantic_equivalence_claim=False,
        elapsed_s=time.monotonic()-started,new_compile_Host_Spike_DUT_runs=0))
    print('UNKNOWN: strict instruction/CFG relation incomplete', len(mapped), 'matched pairs')


if __name__ == '__main__':
    main()
