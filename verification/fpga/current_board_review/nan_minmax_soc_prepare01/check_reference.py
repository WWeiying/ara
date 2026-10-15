"""One SEW/LMUL-configured raw reference checker; no simulator invocation."""
from collections import Counter
import copy
from common import *
from oracle import bitwise_oracle

def c_mask(spec):
    return spec['config']['mask_byte'] ^ 1

LINE = re.compile(r'^core\s+0:\s+3\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)(.*)$')
REG = re.compile(r'\bx(\d+)\s+(0x[0-9a-f]+)')
CSR = re.compile(r'\bc\d+_(\w+)\s+(0x[0-9a-f]+)')
MEM = re.compile(r'\bmem\s+(0x[0-9a-f]+)(?:\s+(0x[0-9a-f]+))?')
VECTOR = re.compile(r'\bv(\d+)\s+(0x[0-9a-f]+)')
BOOT = [(0x1000,0x00000297,{5:0x1000},[]),
        (0x1004,0x02028593,{11:0x1020},[]),
        (0x1008,0xf1402573,{10:0},[]),
        (0x100c,0x0182b283,{5:0x80000000},[[0x1018,None]]),
        (0x1010,0x00028067,{},[])]


def rvv(code):
    return code & 0x7f == 0x57 or (code & 0x7f in (7, 0x27) and (code >> 12) & 7 in (0, 5, 6, 7))


def specification(dest):
    proof = read(dest / 'sourceproof.json')
    c = proof['config']
    syms = read(dest / 'spike/symbols.json')
    ins = instructions((dest / 'spike/program.dis').read_text())
    require(disassemble(dest / 'spike/program.elf') == (dest / 'spike/program.dis').read_text(), 'actual ELF disassembly')
    op = proof['helper_windows']['spike']['op_2']['new']
    unused = [r for n in ('op_0', 'op_1') for r in proof['helper_windows']['spike'][n]['new']]
    capacity = [r for r in ins if syms['capacity'] <= r[0] < syms['op_0']]
    require(len(capacity) == 3 and capacity[0][1] == '52fd' and capacity[-1][1] == '8082', 'capacity3')
    csr = [r for r in ins if int(r[1], 16) & 0x7f == 0x73 and (int(r[1], 16) >> 12) & 7
           and r[0] < syms['capacity'] and not syms['trap_entry'] <= r[0] < syms['replay_exit']]
    require(len(csr)==7 and [r[1] for r in csr[:5]] == ['30401073', '30529073', '3002a073', '00305073',
              '00805073'] and all(int(r[1],16)&~0xf80 == 0xc2202073 for r in csr[5:]), 'original CSR prelude')
    lbu, = [r for r in ins if syms[c['identity']+'_main'] <= r[0] < syms['capacity']
            and int(r[1],16)&~0xf80 == 0x00064003]
    bits = [int(x, 16) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)', (dest / 'prepared/input_bits.h').read_text())]
    require(len(bits) == 16 and bits[12] == c['inf'] and bits[13] == c['inf'] | (1 << (c['sew']-1)), 'source FP constants')
    pairs = fixtures(dest / 'prepared/fixtures.h')
    require(len(pairs) == 6720 and pairs[3360+c['fixture_row']] == [c['expected'], 0], 'source fixture')
    return dict(config=c, symbols=syms, instructions=ins, helper=op, unused=unused,
                capacity=capacity, csr=csr, input_bits=bits, fixtures=pairs, output_lbu=lbu)


def input_value(bits, scenario, i, sew):
    if scenario == 0: return bits[i % 2]
    if scenario == 1: return bits[14]
    if scenario == 2: return bits[2 if i % 2 else 15]
    if scenario == 3: return bits[13 if i % 2 else 12]
    if scenario == 4: return bits[[2, 7, 3, 7, 11, 11][i % 6]] ^ ((1 << (sew-1)) if i % 6 in (3, 5) else 0)
    if scenario == 5: return bits[[8, 9, 10, 8, 9, 10][i % 6]] ^ ((1 << (sew-1)) if i % 6 >= 3 else 0)
    if scenario == 6: return bits[15 if i % 2 else 2]
    return bits[7 if i % 2 else 2]


def helper_effect(spec, index, row):
    c, sy = spec['config'], spec['symbols']
    word = c['seed_payload'].to_bytes(4, 'little')
    loads = {
        1: (16, word * 32, range(sy['seed'], sy['seed']+128, 4)),
        2: (24, b'\x5b' * 128, range(sy['output']+8, sy['output']+136, 4)),
        4: (8, word * 32, range(sy['input'], sy['input']+128, 4)),
        5: (0, bytes([c['mask_byte']])*4, range(sy['mask'], sy['mask']+4)),
    }
    if index in loads:
        register, expected, addresses = loads[index]
        require(set(row['vectors']) == {str(register)}, 'raw vector load register')
        actual = bytes.fromhex(row['vectors'][str(register)])
        require(actual[:len(expected)] == expected and
                row['memory'] == [[a, None] for a in addresses], 'raw vector input/seed/mask/old-vd data')
    result_bits, flags = bitwise_oracle(c['seed_payload'], [c['seed_payload']]*3, c['mask_byte'])
    result = result_bits.to_bytes(4, 'little') + b'\x5b'*124
    if index == 11:
        require(row['vectors'] == {'24': result.hex()} and
                row['csrs'].get('fflags') == flags and row['csrs'].get('vstart') == 0,
                'raw bitwise result/flags/vstart')
    if index == 19:
        require(row['memory'] == [[sy['output']+8+i, int.from_bytes(result[i:i+4], 'little')]
                for i in range(0,128,4)], 'raw full destination store')
    if index in (7,8,12,13,14,15):
        register, value = {7:(29,0), 8:(30,0), 12:(10,0), 13:(6,flags),
                           14:(6,flags<<32), 15:(10,flags<<32)}[index]
        require(row['regs'] == {str(register):value}, 'raw saved/returned CSR')
    if index in (9,10,16,17):
        name = 'frm' if index in (9,16) else 'fflags'
        require(row['csrs'].get(name) == 0, 'raw requested/restored CSR')


def extract(dest, raw, mutation=None):
    spec = specification(dest)
    c, sy = spec['config'], spec['symbols']
    w, cap = c['word_bytes'], c['cap']
    op = spec['helper']
    code = {r[0]: int(r[1], 16) for r in spec['instructions']}
    op_pcs = {r[0] for r in op}
    unused = {r[0] for r in spec['unused']}
    cap_pcs = {r[0] for r in spec['capacity']}
    csr_pcs = {r[0] for r in spec['csr']}
    counts = Counter()
    regs = [0] * 32
    memory = {}
    pcs = Counter()
    helper, reads, selected = [], [], []
    capacity_rows, csr_rows = [], []
    setup = terminal = None
    total = firmware = park = 0
    in_main = False
    tracked = [('input', 512*w), ('seed', 64*w), ('mask', 64), ('output', 144), ('replay_log', 8192)]
    def get(name, size):
        return [memory.get(sy[name]+i) for i in range(size)]
    with Path(raw).open() as stream:
        for line in stream:
            if mutation is not None:
                line = mutation(line)
            m = LINE.fullmatch(line.rstrip('\n'))
            require(m is not None, 'unparsed raw commit')
            pc, insn, tail = int(m[1],16), int(m[2],16), m[3]
            total += 1
            firmware += pc >= 0x80000000
            pcs[pc] += 1
            wr = {int(k):int(v,16) for k,v in REG.findall(tail)}
            cs = {k:int(v,16) for k,v in CSR.findall(tail)}
            ve = {k:int(v,16).to_bytes(128,'little').hex() for k,v in VECTOR.findall(tail)}
            me = [[int(a,16), int(v,16) if v else None] for a,v in MEM.findall(tail)]
            if total <= 5:
                require((pc,insn,wr,me)==BOOT[total-1] and not (cs or ve), 'exact five Spike boot instructions/effects')
                for k,v in wr.items():regs[k]=v
                continue
            require(pc >= 0x80000000, 'firmware cannot return to boot')
            if pc >= 0x80000000:
                require(code.get(pc) == insn, 'actual ELF PC/encoding')
            require(pc not in unused and pc != sy['trap_entry'], 'unused helper interior/trap')
            if terminal is not None:
                require(insn == 0xa001 and pc == sy['_start'] + 0x7e and not (wr or cs or ve or me), 'nonempty post-HTIF park')
                park += 1
            if pc == sy[c['identity'] + '_main']:
                require(not in_main, 'main repetition')
                in_main = True
            if pc in csr_pcs:
                require(not capacity_rows and len(csr_rows) < 7 and pc == spec['csr'][len(csr_rows)][0], 'CSR prelude phase/order')
                if len(csr_rows) >= 5:
                    require(list(wr.values()) == [128], 'VLENB128')
                csr_rows.append(pc)
            elif insn & 0x7f == 0x73 and (insn >> 12) & 7:
                require(pc in op_pcs, 'extra CSR retirement')
            if pc in cap_pcs:
                i = len(capacity_rows)
                require(len(csr_rows) == 7 and setup is None and i < 3 and pc == spec['capacity'][i][0], 'capacity once/order')
                require(i == 0 or total == capacity_rows[-1]['ordinal'] + 1, 'capacity continuity')
                if i == 1:
                    require(regs[5] == (1<<64)-1 and wr == {10:cap}, 'capacity actual result')
                capacity_rows.append({'ordinal': total, 'pc': pc, 'csrs':cs, 'regs':{str(k):v for k,v in wr.items()}})
            if pc == op[0][0]:
                require(setup is None and len(capacity_rows) == 3, 'unique helper after capacity')
                setup = {'ordinal': total, 'args': regs[10:18], 'input': get('input',cap*w),
                         'seed': get('seed',64*w), 'mask': get('mask',64), 'output': get('output',144)}
                require(setup['args'] == [sy['input'],sy['seed'],sy['output']+8,3,32,sy['mask'],0,0],
                        'raw source single arguments')
            if pc in op_pcs:
                i = len(helper)
                require(setup is not None and i < 21 and pc == op[i][0] and total == setup['ordinal'] + i, 'op2 contiguous21/no interior replay')
                helper.append({'ordinal':total,'pc':pc,'insn':format(insn,'0'+str(len(op[i][1]))+'x'),
                               'regs':{str(k):v for k,v in wr.items()},'csrs':cs,'vectors':ve,'memory':me,
                               'before_regs':regs.copy()})
                helper_effect(spec, i, helper[-1])
            if rvv(insn):
                require(pc in op_pcs or pc == spec['capacity'][1][0], 'unexpected vector instruction')
                counts['rvv'] += 1
            for address,value in me:
                if value is None:
                    if sy['fixtures'] <= address < sy['fixtures']+6720*16:
                        i = counts['fixture_fields']
                        row, field = 3360+i//2, (i%2)*8
                        require(i < 6720 and address == sy['fixtures']+row*16+field and len(wr)==1,
                                'bank1 complete fixture address/order')
                        require(next(iter(wr.values())) == spec['fixtures'][row][field//8], 'fixture field value')
                        if row == 3360+c['fixture_row']: selected.append([address,next(iter(wr.values()))])
                        counts['fixture_fields'] += 1
                    if len(helper)==21 and sy['output'] <= address < sy['output']+144:
                        rd=(int(spec['output_lbu'][1],16)>>7)&31
                        require(pc==spec['output_lbu'][0] and insn==int(spec['output_lbu'][1],16) and len(wr)==1 and rd in wr, 'original output LBU')
                        offset = address-sy['output']
                        wanted = c['expected'].to_bytes(w, 'little')[offset-8] if 8 <= offset < 12 else 91
                        require(wr[rd] == wanted, 'raw full144B oracle byte')
                        reads.append([address-sy['output'], wr[rd]])
                    continue
                if address == sy['tohost']:
                    require(terminal is None and pc == sy['_start']+0x7a and insn == 0x00a2b023, 'actual HTIF store')
                    terminal = {'ordinal':total,'firmware_retired':firmware,'value':value,'pc':pc}
                if pc == op[19][0]:
                    size = w
                elif insn & 0x7f == 0x23:
                    size = 1 << ((insn>>12)&7)
                    require(size <= 8, 'scalar store width')
                elif insn & 3 in (0,2) and insn>>13 in (6,7):
                    size = 4 if insn>>13==6 else 8
                else:
                    require(not any(sy[n]<=address<sy[n]+z for n,z in tracked), 'unknown tracked store')
                    continue
                if any(sy[n]<=address<sy[n]+z for n,z in tracked):
                    for j,byte in enumerate(value.to_bytes(size,'little')): memory[address+j]=byte
                if in_main and pc not in op_pcs:
                    if sy['input'] <= address < sy['input']+512*w:
                        i = counts['input_elements']; scenario,index = divmod(i,cap)
                        require(scenario<8 and address==sy['input']+index*w and size==w and
                                value==input_value(spec['input_bits'],scenario,index,c['sew']), 'all original scenario input stores')
                        counts['input_elements'] += 1
                    elif sy['seed'] <= address < sy['seed']+64*w:
                        i=counts['seed_elements']; scenario,index=divmod(i,64)
                        require(scenario<8 and address==sy['seed']+index*w and size==w and
                                value==spec['input_bits'][[1,14,2,12,2,8,1,12][scenario]], 'all original seed64 stores')
                        counts['seed_elements'] += 1
                    elif sy['mask'] <= address < sy['mask']+64:
                        i=counts['mask_bytes']; fill,index=divmod(i,64); mode=(fill//15)%4
                        require(fill<3360 and address==sy['mask']+index and size==1 and value==[255,0,85,36][mode], 'all original mask fills')
                        counts['mask_bytes'] += 1
                    elif sy['output'] <= address < sy['output']+144:
                        i=counts['output_init']
                        require(setup is None and i<144 and address==sy['output']+i and size==1 and value==91, 'original output initialization')
                        counts['output_init'] += 1
            for k,v in wr.items(): regs[k]=v
            regs[0]=0
    console = bytes(get('replay_log',8192)).split(b'\0',1)[0].decode('ascii')
    return {'setup':setup,'helper':helper,'output_reads':reads,'selected_fixture':selected,
            'counts':dict(counts),'capacity':capacity_rows,'prelude':csr_rows,'console':console,
            'terminal':terminal,'retired_total':total,'parking_retired':park,
            'pc_counts':{hex(k):v for k,v in pcs.items()}}


def validate(spec, data):
    c,sy=spec['config'],spec['symbols']; w,cap=c['word_bytes'],c['cap']
    setup=data['setup']; require(setup is not None, 'missing setup')
    require(setup['args']==[sy['input'],sy['seed'],sy['output']+8,c['vl'],cap,sy['mask'],0,0], 'full args')
    expected_input=b''.join(input_value(spec['input_bits'],1,i,c['sew']).to_bytes(w,'little') for i in range(cap))
    require(setup['input']==list(expected_input), 'full capacity input')
    require(setup['seed']==list(c['seed_payload'].to_bytes(w,'little')*64), 'full seed64 initialization')
    require(setup['mask']==[c['mask_byte']]*64 and setup['output']==[91]*144, 'full setup mask/output')
    require(data['counts']=={'rvv':11,'input_elements':8*cap,'seed_elements':512,
            'fixture_fields':6720,'mask_bytes':215040,'output_init':144}, 'complete original loop counts')
    require(len(data['capacity'])==3 and len(data['prelude'])==7, 'capacity/CSR count')
    require(data['selected_fixture']==[[sy['fixtures']+(3360+c['fixture_row'])*16,c['expected']],
            [sy['fixtures']+(3360+c['fixture_row'])*16+8,0]], 'actual bank1 selected row, even when bank0 same value')
    h=data['helper']; require(len(h)==21, '21 original helper')
    for i,row in enumerate(h):
        original=spec['helper'][i]
        require(row['pc']==original[0] and row['insn']==original[1] and row['ordinal']==setup['ordinal']+i, 'helper code/order')
        helper_effect(spec, i, row)
    lmul={'mf2':7,'m1':0,'m2':1,'m4':2,'m8':3}[c['lmul']]
    m1type=8 if c['sew']==16 else 16
    capacity_cs=data['capacity'][1]['csrs']
    require(capacity_cs.get('vtype')==m1type|lmul and capacity_cs.get('vl')==cap and
            capacity_cs.get('vstart')==0, 'actual capacity CSR state')
    vt=capacity_cs['vtype']
    for i,vl,typ in [(0,128//w,m1type),(3,cap,m1type|lmul),(6,c['vl'],m1type|lmul),(18,128//w,m1type)]:
        cs=h[i]['csrs'];vt=cs.get('vtype',vt)
        require(h[i]['regs']=={'5':vl} and cs.get('vl')==vl and vt==typ and cs.get('vstart')==0, 'actual VL/SEW/LMUL')
    for i,first,expected,addresses in [
        (1,16,c['seed_payload'].to_bytes(w,'little')*(128//w),range(sy['seed'],sy['seed']+128,w)),
        (2,24,b'\x5b'*128,range(sy['output']+8,sy['output']+136,w)),
        (4,8,expected_input,range(sy['input'],sy['input']+cap*w,w)),
        (5,0,bytes([c['mask_byte']])*((cap+7)//8),range(sy['mask'],sy['mask']+(cap+7)//8))]:
        chunks=(len(expected)+127)//128
        require(set(h[i]['vectors'])=={str(first+j) for j in range(chunks)}, 'vector register group')
        actual=b''.join(bytes.fromhex(h[i]['vectors'][str(first+j)]) for j in range(chunks))
        require(actual[:len(expected)]==expected and h[i]['memory']==[[a,None] for a in addresses], 'full vector data/load footprint')
    require(h[7]['regs']=={'29':0} and h[8]['regs']=={'30':0}, 'saved original CSR')
    require(h[9]['csrs'].get('frm')==0 and h[10]['csrs'].get('fflags')==0, 'requested CSR')
    result=bitwise_oracle(spec['input_bits'][14], [spec['input_bits'][14]]*c['vl'], c['mask_byte'])[0].to_bytes(w,'little')+b'\x5b'*(128-w)
    require(h[11]['vectors']=={'24':result.hex()} and h[11]['csrs'].get('fflags')==0 and h[11]['csrs'].get('vstart')==0, 'result/NV/vstart')
    require(h[12]['regs']=={'10':0} and h[13]['regs']=={'6':0} and h[14]['regs']=={'6':0}
            and h[15]['regs']=={'10':0}, 'returned flags/vstart')
    require(h[16]['csrs'].get('frm')==0 and h[17]['csrs'].get('fflags')==0 and
            h[16]['before_regs'][29]==0 and h[17]['before_regs'][30]==0, 'CSR restore')
    require(h[19]['memory']==[[sy['output']+8+i,int.from_bytes(result[i:i+w],'little')] for i in range(0,128,w)], 'full destination store')
    expected=b'\x5b'*8+result+b'\x5b'*8
    require(data['output_reads']==[[i,b] for i,b in enumerate(expected)], '144 original LBU result/tail/guards')
    console=data['console']
    require(not re.search('FAIL|DETAIL|TRAP|MISMATCH',console), 'raw diagnostic veto')
    require(console==f"BOARD_CASE_BEGIN {c['identity']}\n{marker(c)}\nBOARD_CASE_PASS {c['identity']}\nBOARD_REPLAY_PASS\n", 'full original console')
    require(data['terminal'] and data['terminal']['value']==1, 'actual HTIF success')
    require(1612800 < data['terminal']['firmware_retired'] < 3000000 and data['retired_total']<=3000000, 'retired resource bound')


def host_negatives(spec,data):
    checks={
        'spurious_NV':lambda d:d['helper'][13]['regs'].update({'6':16}),
        'wrong_NaN':lambda d:d['helper'][11]['vectors'].update({'24':'00'*128}),
        'vstart':lambda d:d['helper'][12]['regs'].update({'10':1}),
        'missing_guard':lambda d:d['output_reads'].pop(),
        'tail':lambda d:d['output_reads'][100].__setitem__(1,0),
        'wrong_bank_same_value':lambda d:d['selected_fixture'][0].__setitem__(0,d['selected_fixture'][0][0]-3360*16),
        'wrong_type':lambda d:d['helper'][3]['csrs'].update({'vtype':31}),
        'missing_seed64':lambda d:d['setup']['seed'].pop(),
        'missing_last_group_input':lambda d:d['setup']['input'].pop(),
        'wrong_mask':lambda d:d['setup']['mask'].__setitem__(0,c_mask(spec)),
        'restore':lambda d:d['helper'][17]['csrs'].update({'fflags':16}),
        'short_store':lambda d:d['helper'][19]['memory'].pop(),
        'no_HTIF':lambda d:d.update({'terminal':None}),
        'wrong_encoding':lambda d:d['helper'][11].update({'insn':'14881c57'}),
        'short_oracle':lambda d:d['output_reads'].pop(70),
        'short_maskloop':lambda d:d['counts'].update({'mask_bytes':64}),
        'short_fixture':lambda d:d['counts'].update({'fixture_fields':2}),
        'wrong_capacity_vtype':lambda d:d['capacity'][1]['csrs'].update({'vtype':31}),
        'missing_capacity_vtype':lambda d:d['capacity'][1]['csrs'].pop('vtype'),
        'active_payload_or_alloff_canonical':lambda d:d['helper'][11]['vectors'].update(
            {'24': (spec['config']['expected'] ^ 0x12345).to_bytes(4,'little').hex()+'5b'*124}),
        'infinity_result':lambda d:d['helper'][11]['vectors'].update({'24':'0000807f'+'5b'*124}),
        'wrong_VL':lambda d:d['setup']['args'].__setitem__(3,4),
        'wrong_CAP':lambda d:d['setup']['args'].__setitem__(4,16),
        'wrong_frm':lambda d:d['setup']['args'].__setitem__(6,1),
        'wrong_sticky':lambda d:d['setup']['args'].__setitem__(7,1),
        'wrong_seed_vector':lambda d:d['helper'][1]['vectors'].update({'16':'00'*128}),
        'wrong_input_vector':lambda d:d['helper'][4]['vectors'].update({'8':'00'*128}),
        'wrong_mask_vector':lambda d:d['helper'][5]['vectors'].update({'0':'ff'*128}),
        'guard_first':lambda d:d['output_reads'][0].__setitem__(1,0),
        'guard_last':lambda d:d['output_reads'][143].__setitem__(1,0),
        'PASS_plus_FAIL':lambda d:d.update({'console':d['console']+'FAIL\n'}),
        'runtime_identity':lambda d:d.update({'console':d['console'].replace(spec['config']['identity'],'historical_parent')}),
        'partial_helper':lambda d:d['helper'].pop(),
    }
    rows=[]
    validate(spec,data)
    for name,fn in checks.items():
        altered=copy.deepcopy(data);fn(altered)
        try:validate(spec,altered)
        except ValueError as error:rows.append({'negative':name,'rejected':str(error)})
        else:raise ValueError('negative accepted: '+name)
    return {'status':'PASS_HOST_ONLY','positive':True,'negatives':rows}

