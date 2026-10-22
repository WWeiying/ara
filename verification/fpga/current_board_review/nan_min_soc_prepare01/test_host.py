"""Host-only preflight: shape-specific positive witnesses and negative gates."""
import tempfile
from common import *
from check_reference import specification, validate, host_negatives, extract, input_value, BOOT


def boot_raw():
    lines=[]
    for pc,code,regs,mem in BOOT:
        suffix=''.join(f' x{k} 0x{v:016x}' for k,v in regs.items())
        suffix+=''.join(f' mem 0x{a:016x}' for a,v in mem)
        lines.append(f'core   0: 3 0x{pc:016x} (0x{code:08x}){suffix}\n')
    return ''.join(lines)


def witness(s):
    c,sy=s['config'],s['symbols'];w=c['word_bytes'];cap=c['cap']
    inp=b''.join(input_value(s['input_bits'],1,i,c['sew']).to_bytes(w,'little') for i in range(cap))
    setup={'ordinal':100,'args':[sy['input'],sy['seed'],sy['output']+8,c['vl'],cap,sy['mask'],0,0],
           'input':list(inp),'seed':list(c['seed_payload'].to_bytes(w,'little')*64),'mask':[c['mask_byte']]*64,'output':[91]*144}
    h=[{'ordinal':100+i,'pc':r[0],'insn':r[1],'regs':{},'csrs':{},'vectors':{},'memory':[],
        'before_regs':[0]*32} for i,r in enumerate(s['helper'])]
    typ=8 if w==2 else 16;lm={'mf2':7,'m1':0,'m2':1,'m4':2,'m8':3}[c['lmul']]
    for i,vl,t in [(0,128//w,typ),(3,cap,typ|lm),(6,c['vl'],typ|lm),(18,128//w,typ)]:
        h[i]['regs']={'5':vl};h[i]['csrs']={'vl':vl,'vtype':t,'vstart':0}
    previous=typ|lm
    for i in (0,3,6,18):
        current=h[i]['csrs']['vtype']
        if current==previous:h[i]['csrs'].pop('vtype')
        previous=current
    for i,first,data,addresses in [(1,16,c['seed_payload'].to_bytes(w,'little')*(128//w),range(sy['seed'],sy['seed']+128,w)),
        (2,24,b'\x5b'*128,range(sy['output']+8,sy['output']+136,w)),
        (4,8,inp,range(sy['input'],sy['input']+cap*w,w)),
        (5,0,bytes([c['mask_byte']])*((cap+7)//8),range(sy['mask'],sy['mask']+(cap+7)//8))]:
        h[i]['vectors']={str(first+j//128):data[j:j+128].ljust(128,b'\0').hex() for j in range(0,len(data),128)}
        h[i]['memory']=[[a,None] for a in addresses]
    h[7]['regs']={'29':0};h[8]['regs']={'30':0}
    h[9]['csrs']={'frm':0};h[10]['csrs']={'fflags':0}
    result=c['expected'].to_bytes(w,'little')+b'\x5b'*(128-w)
    h[11]['vectors']={'24':result.hex()};h[11]['csrs']={'fflags':0,'vstart':0}
    for i,r,v in [(12,10,0),(13,6,0),(14,6,0),(15,10,0)]:h[i]['regs']={str(r):v}
    h[16]['csrs']={'frm':0};h[17]['csrs']={'fflags':0}
    h[19]['memory']=[[sy['output']+8+i,int.from_bytes(result[i:i+w],'little')] for i in range(0,128,w)]
    return {'setup':setup,'helper':h,'capacity':[{}, {'csrs':{'vtype':typ|lm,'vl':cap,'vstart':0}}, {}],'prelude':[r[0] for r in s['csr']],
            'counts':{'rvv':11,'input_elements':8*cap,'seed_elements':512,'fixture_fields':6720,'mask_bytes':215040,'output_init':144},
            'selected_fixture':[[sy['fixtures']+(3360+c['fixture_row'])*16,c['expected']],[sy['fixtures']+(3360+c['fixture_row'])*16+8,0]],
            'output_reads':[[i,b] for i,b in enumerate(b'\x5b'*8+result+b'\x5b'*8)],
            'console':f"BOARD_CASE_BEGIN {c['identity']}\n{marker(c)}\nBOARD_CASE_PASS {c['identity']}\nBOARD_REPLAY_PASS\n",
            'terminal':{'value':1,'firmware_retired':2000000},'retired_total':2000100}


def main():
    rows=[]
    for shape in SHAPES:
        dest=HERE/shape;s=specification(dest)
        data=witness(s);checks=host_negatives(s,data)
        raw_neg=[]
        # Every unused helper PC, not only vector targets or entry, is forbidden.
        for row in s['unused']+s['helper'][1:]:
            with tempfile.TemporaryDirectory(prefix='redspecial-host-') as td:
                raw=Path(td)/'raw.log'
                raw.write_text(boot_raw()+f'core   0: 3 0x{row[0]:016x} (0x{int(row[1],16):08x})\n')
                try:extract(dest,raw)
                except ValueError as e:
                    require(str(e) in ('unused helper interior/trap','op1 contiguous21/no interior replay'), 'expected early PC gate: '+str(e))
                    raw_neg.append({'pc':hex(row[0]),'reason':str(e)})
                else:raise ValueError('raw illegal PC accepted')
        boot_neg=[]
        for name,rawtext in [('wrong_boot_CSR',boot_raw().replace('f1402573','c2202573')),
                             ('wrong_hart',boot_raw().replace('x10 0x0000000000000000','x10 0x0000000000000001')),
                             ('repeated_boot',boot_raw()+boot_raw())]:
            with tempfile.TemporaryDirectory(prefix='redspecial-host-') as td:
                raw=Path(td)/'raw.log';raw.write_text(rawtext)
                try:extract(dest,raw)
                except ValueError as e:
                    require(str(e) in ('exact five Spike boot instructions/effects','firmware cannot return to boot'), 'boot-specific rejection')
                    boot_neg.append({'negative':name,'reason':str(e)})
                else:raise ValueError('bad boot accepted')
        rows.append({'shape':shape,'ledger_tests':checks,'raw_pc_negatives':raw_neg,'boot_negatives':boot_neg})
        print(shape,'HOST_LEDGER_AND_62_PC_NEGATIVES_PASS',flush=True)
    save(HERE/'host03.json',{'status':'PASS_HOST_ONLY','shapes':rows,
        'ledger_tests':sum(1+len(r['ledger_tests']['negatives']) for r in rows),
        'raw_pc_negatives':sum(len(r['raw_pc_negatives']) for r in rows),
        'boot_negatives':sum(len(r['boot_negatives']) for r in rows),'reference_run':False})


if __name__=='__main__':main()
