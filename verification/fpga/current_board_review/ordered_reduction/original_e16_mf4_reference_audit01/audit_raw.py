"""Read existing evidence only; do not import or execute production helpers."""
import collections
import hashlib
import json
from pathlib import Path
import re
import struct
import time

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / 'original_e16_mf4_prepare01'
REF = SRC / 'reference03M'


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def obj(p):
    return json.loads(Path(p).read_text())


def elf_reader(path):
    data = Path(path).read_bytes()
    assert data[:6] == b'\x7fELF\x02\x01'
    phoff = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    segments = []
    for i in range(count):
        typ, flags, off, va, pa, filesz, memsz, align = struct.unpack_from('<IIQQQQQQ', data, phoff + i * size)
        if typ == 1:
            segments.append((va, va + filesz, off))
    def read(addr, size):
        for lo, hi, off in segments:
            if lo <= addr and addr + size <= hi:
                return data[off + addr - lo:off + addr - lo + size]
        raise AssertionError(('ELF unmapped', hex(addr)))
    return read


def scalar_fp(insn):
    if insn & 3 != 3:
        return insn & 3 in (0, 2) and insn >> 13 in (1, 5)
    return insn & 127 in (0x43, 0x47, 0x4b, 0x4f, 0x53) or (
        insn & 127 in (7, 0x27) and (insn >> 12) & 7 in (1, 2, 3, 4))


def main():
    start = time.monotonic()
    ready = obj(SRC / 'READY.json')
    assert sha(SRC / 'READY.json') == 'f858249f61dc7b9c4e3507f78bb483543d0439ef74942e838fc1251931a661de'
    assert ready['status'] == 'REFERENCE_EXECUTOR_PASS_PENDING_INDEPENDENT_REVIEW'
    allpins = dict(ready['pins'])
    allpins[str(SRC / 'READY.json')] = sha(SRC / 'READY.json')
    for p, digest in allpins.items():
        assert sha(p) == digest, p
    proof = obj(SRC / 'sourceproof.json')
    canonical = Path(proof['canonical'])
    assert '/rvv_verified_handoff03/rvv_small_redspecial02/' in str(canonical)
    for p, digest in {**proof['external_pins'], **proof['prepared_pins']}.items():
        assert sha(p) == digest, p
    case = obj(canonical / 'case.json')['case']
    for name, digest in case['scenario_sources'].items():
        assert sha(canonical / name) == sha(SRC / 'prepared' / name) == digest
    for name, key in [('scenario.elf', 'sha256'), ('original.elf', 'original_elf_sha256')]:
        assert sha(canonical / name) == sha(SRC / 'prepared' / name) == case[key]
    original = Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/fp_reduction_oracle.c')
    archived = (canonical / 'scenario.c').read_text()
    selector = '                if(!(scenario==3 && l==4 && mode==3 && rm==0 && op==0 && sticky==0))continue;\n'
    assert archived.count(selector) == 1 and archived.replace(selector, '', 1) == original.read_text()
    adapted = (SRC / 'prepared/case.c').read_text()
    body = '    unsigned long vlenb;'
    oldbody = archived[archived.index(body):]
    oldbody = oldbody[:oldbody.index('__asm__(".global _start')]
    oldbody = oldbody.replace('syscall3(94,2,0,0);for(;;){}', 'return 2;').replace('syscall3(94,errors ? 1:0,0,0);for(;;){}', 'return errors ? 1 : 0;')
    assert adapted[adapted.index(body):].strip() == oldbody.strip()
    fixtures = [(int(a, 16), int(b)) for a, b in re.findall(r'\{UINT64_C\(0x([0-9a-fA-F]+)\),\s*(\d+)\}', (SRC / 'prepared/fixtures.h').read_text())]
    supplement = obj(SRC / 'source_supplement.json')
    fixturejson = next(Path(p) for p in supplement['pins'] if p.endswith('/fixtures.json'))
    assert [tuple(x) for bank in obj(fixturejson) for x in bank] == fixtures
    assert len(fixtures) == 6720 and fixtures[4905] == (0x7e00, 16) and fixtures[1545] == (0x7c00, 0)
    readers = {k: elf_reader(SRC / k / 'program.elf') for k in ('spike', 'soc')}
    original_read = elf_reader(canonical / 'scenario.elf')
    for kind, windows in proof['helper_windows'].items():
        for name, window in windows.items():
            assert len(window['new']) == len(window['original']) == 21
            for old, new in zip(window['original'], window['new']):
                assert old[1] == new[1]
                width = len(old[1]) // 2
                assert original_read(old[0], width) == readers[kind](new[0], width) == bytes.fromhex(old[1])[::-1]
    dis = (SRC / 'spike/program.dis').read_text()
    disrows = re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([^\n]+)', dis, re.M)
    for pc, code, mnemonic in disrows:
        assert readers['spike'](int(pc, 16), len(code)//2) == bytes.fromhex(code)[::-1]
        assert not scalar_fp(int(code, 16)), (pc, mnemonic)
    host = obj(SRC / 'host.json')
    assert host['status'] == 'PASS_13' and len(host['tests']) == 13
    for row in host['tests']:
        log = (SRC / 'host' / (row['mode'] + '.log')).read_text()
        positive = row['mode'] == 'positive'
        assert row['PASS'] and row['returncode'] == (0 if positive else 1)
        assert 'HOST_SETUP_FULL_PASS' in log
        assert ('RVV_FP_REDSPECIAL_PASS sew=16 cases=1 flags_seen=16 errors=0' in log) == positive
        assert ('RVV_FP_REDSPECIAL_FAIL' in log) != positive
    negatives = obj(REF / 'checker_host.json')
    assert negatives['status'] == 'PASS_15' and negatives['positive']
    assert len(negatives['negatives']) == len({x['negative'] for x in negatives['negatives']}) == 14
    assert all(x['rejected'] for x in negatives['negatives'])
    syms = obj(SRC / 'spike/symbols.json')
    ledger = obj(REF / 'ledger.json')
    counts = collections.Counter()
    regs, memory, csrs = [0]*32, {}, {}
    helper, reads, fixture_reads = [], [], []
    hpcs = {row[0]: i for i, row in enumerate(proof['helper_windows']['spike']['op_0']['new'])}
    linepat = re.compile(r'^core\s+0: 3 (0x[0-9a-f]+) \((0x[0-9a-f]+)\)(.*)\n$')
    ranges = [(syms[n], syms[n]+size) for n, size in [('input', 1024), ('seed', 128), ('mask', 64), ('output', 144), ('replay_log', 8192)]]
    def get(name, n):
        return bytes(memory[syms[name]+i] for i in range(n))
    terminal, setup, total, firmware, park = None, None, 0, 0, 0
    for line in (REF / 'commits.log').open():
        m = linepat.fullmatch(line)
        assert m, line[:120]
        pc, insn, suffix = int(m[1], 16), int(m[2], 16), m[3]
        total += 1
        firmware += pc >= 0x80000000
        counts[pc] += 1
        assert not scalar_fp(insn)
        if pc >= 0x80000000:
            width = 4 if insn & 3 == 3 else 2
            assert readers['spike'](pc, width) == insn.to_bytes(width, 'little')
        assert pc not in (syms['trap_entry'], syms['op_1'], syms['op_2'])
        wr = {int(r): int(v,16) for r,v in re.findall(r'\bx(\d+)\s+(0x[0-9a-f]+)', suffix)}
        cw = {r:int(v,16) for r,v in re.findall(r'\bc\d+_(\w+)\s+(0x[0-9a-f]+)', suffix)}
        vw = {r:int(v,16).to_bytes(128,'little').hex() for r,v in re.findall(r'\bv(\d+)\s+(0x[0-9a-f]+)', suffix)}
        mem = [[int(a,16), int(v,16) if v else None] for a,v in re.findall(r'\bmem\s+(0x[0-9a-f]+)(?:\s+(0x[0-9a-f]+))?', suffix)]
        if terminal:
            assert pc == 0x8000007e and insn == 0xa001 and not (wr or cw or vw or mem)
            park += 1
        if pc == syms['op_0']:
            assert setup is None
            setup = dict(args=regs[10:18], input=list(get('input',32)), seed=list(get('seed',128)), mask=list(get('mask',64)), output=list(get('output',144)), ordinal=total)
        if pc in hpcs:
            i = hpcs[pc]
            code = proof['helper_windows']['spike']['op_0']['new'][i][1]
            helper.append(dict(index=i, ordinal=total, pc=pc, insn=f'{insn:0{len(code)}x}', regs={str(k):v for k,v in wr.items()}, csrs=cw, vectors=vw, memory=mem))
        if pc in (0x8000050e,0x80000510):
            row, field = divmod(mem[0][0]-syms['fixtures'],16)
            assert mem == [[syms['fixtures']+row*16+field,None]] and field in (0,8)
            assert list(wr.values()) == [fixtures[row][field//8]]
            fixture_reads.append([row,field])
        if pc == 0x800005d6:
            assert len(mem)==1 and mem[0][1] is None and set(wr)=={16}
            reads.append([mem[0][0]-syms['output'],wr[16]])
        for addr,val in mem:
            if val is None:
                continue
            if addr == syms['tohost']:
                assert terminal is None and pc == 0x8000007a and insn == 0x00a2b023
                terminal = dict(ordinal=total,firmware_retired=firmware,pc=pc,value=val)
            if not any(lo <= addr < hi for lo,hi in ranges):
                continue
            if pc == 0x80000782:
                width=2
            elif insn & 127 == 0x23:
                width=1<<((insn>>12)&7)
            else:
                assert insn & 3 in (0,2) and insn>>13 in (6,7)
                width=4 if insn>>13==6 else 8
            for j,b in enumerate(val.to_bytes(width,'little')):
                memory[addr+j]=b
        for r,v in wr.items():
            regs[r]=v
        regs[0]=0
        csrs.update(cw)
    assert setup == ledger['setup'] and helper == ledger['helper'] and reads == ledger['output_reads']
    assert terminal == ledger['terminal'] and total == ledger['retired_total'] == 1860000
    assert terminal['value']==1 and terminal['firmware_retired']==1858335 and park==1660
    assert total-terminal['firmware_retired']-park==5
    assert fixture_reads == [[r,f] for r in range(3360,6720) for f in (0,8)]
    assert setup['args']==[syms['input'],syms['seed'],syms['output']+8,8,16,syms['mask'],0,0]
    assert setup['input']==list(bytes.fromhex('007c00fc')*8)
    assert setup['seed']==list(bytes.fromhex('007c')*64)
    assert setup['mask']==[36]*64 and setup['output']==[91]*144
    assert len(helper)==21 and [x['ordinal'] for x in helper]==list(range(setup['ordinal'],setup['ordinal']+21))
    for i,vl,vtype in [(0,64,8),(3,16,14),(6,8,14),(18,64,8)]:
        assert helper[i]['regs']=={'5':vl}
        assert helper[i]['csrs']['vl']==vl and helper[i]['csrs']['vstart']==0
        assert helper[i]['csrs'].get('vtype',vtype)==vtype
    for i,reg,payload,addresses in [
        (1,'16',bytes.fromhex('007c')*64,range(syms['seed'],syms['seed']+128,2)),
        (2,'24',bytes([91])*128,range(syms['output']+8,syms['output']+136,2)),
        (4,'8',bytes.fromhex('007c00fc')*8,range(syms['input'],syms['input']+32,2)),
        (5,'0',b'\x24\x24',range(syms['mask'],syms['mask']+2))]:
        assert bytes.fromhex(helper[i]['vectors'][reg])[:len(payload)]==payload
        assert helper[i]['memory']==[[a,None] for a in addresses]
    assert helper[9]['csrs']['frm']==helper[10]['csrs']['fflags']==0
    result=bytes.fromhex('007e')+bytes([91])*126
    expected=bytes([91])*8+result+bytes([91])*8
    assert reads==list(map(list,enumerate(expected)))
    assert helper[11]['vectors']=={'24':result.hex()}
    assert helper[11]['csrs']['fflags']==16 and helper[11]['csrs']['vstart']==0
    assert helper[12]['regs']=={'10':0} and helper[13]['regs']=={'6':16}
    assert helper[15]['regs']=={'10':16<<32}
    assert helper[7]['regs']=={'29':0} and helper[8]['regs']=={'30':0}
    assert helper[16]['csrs']['frm']==0 and helper[17]['csrs']['fflags']==0
    assert csrs['frm']==csrs['fflags']==csrs['vstart']==0
    assert helper[19]['memory']==[[syms['output']+8+i,int.from_bytes(result[i:i+2],'little')] for i in range(0,128,2)]
    assert [counts[x] for x in (0x800003f8,0x8000043a,0x8000052e,0x80000566)]==[128,512,215040,144]
    mask_count=sum(counts[x] for x in (0x8000051c,0x80000520,0x80000524,0x80000526,0x8000052a,0x8000052e,0x80000532,0x80000534))
    assert mask_count==1612800
    console=get('replay_log',8192).split(b'\0')[0].decode()
    assert console=='BOARD_CASE_BEGIN original_e16_mf4\nRVV_FP_REDSPECIAL_PASS sew=16 cases=1 flags_seen=16 errors=0\nBOARD_CASE_PASS original_e16_mf4\nBOARD_REPLAY_PASS\n'
    assert console==ledger['console']==(REF/'runtime.log').read_text()
    approval, execution = obj(REF/'approval.json'), obj(REF/'execution.json')
    assert '--isa=rv64gcv_zfh_zvfh_zvl1024b' in approval['command']
    assert approval['limits']=={'steps':3000000,'seconds':120,'raw_bytes':268435456}
    assert execution['returncode']==0 and execution['error'] is None and execution['elapsed_s']<120
    assert execution['input_pins_unchanged'] and execution['approval_sha256']==sha(REF/'approval.json')
    assert (REF/'spike.cmd').read_text().startswith('rs 3000000\n')
    for name,row in execution['raw'].items():
        assert sha(REF/name)==row['sha256'] and (REF/name).stat().st_size==row['bytes']<=268435456
    for p,digest in allpins.items():
        assert sha(p)==digest,p
    result=dict(status='INDEPENDENT_RAW_SOURCE_REFERENCE_ACCEPTED_SINGLE_ONLY',ready_sha256=sha(SRC/'READY.json'),pins_checked=len(allpins),raw_sha256=sha(REF/'commits.log'),firmware_to_HTIF=1858335,total_commits=total,boot_commits=5,park_commits=park,mask_loop_instructions=mask_count,fixture_loads=len(fixture_reads),helper_instructions=len(helper),oracle_bytes=len(reads),scalar_FP_instructions_static=0,scalar_FP_instructions_retired=0,actual_ISA='rv64gcv_zfh_zvfh_zvl1024b',review_minimum_ISA='rv64gcv_zvfh_zvl1024b',profiles_exact_equal=False,reference_seconds=execution['elapsed_s'],raw_bytes=(REF/'commits.log').stat().st_size,offline_audit_seconds=time.monotonic()-start,script_sha256=sha(__file__),DUT_accepted=False,Linux_accepted=False)
    with (HERE/'result.json').open('x') as f:
        json.dump(result,f,indent=2)
        f.write('\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
