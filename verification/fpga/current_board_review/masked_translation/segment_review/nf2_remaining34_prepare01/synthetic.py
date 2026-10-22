"""Shared Host-only synthetic observer fixture; never DUT evidence."""
import reference_core as ref
import csv_check as cc

def synthetic(s, alternate=False):
    rows=[]; checks=0
    def emit(pc=0x80000020,insn=0x13,rd=0,value=0,addr=0,mask=0,data=0,trap=0):
        n=len(rows)
        rows.append(dict(zip(cc.FIELDS,map(str,[n*2+82,'retire',n,0,-1,f'{pc:016x}',f'{insn:08x}',rd,
            f'{value&((1<<64)-1):016x}',f'{addr:016x}','00',f'{mask:02x}',f'{data&((1<<64)-1):016x}',trap]))))
    def reg(r,v,pc=0x80000020): emit(pc=pc,rd=r,value=v)
    def store(a,v,width=8,pc=0x80000020,allpc=None):
        reg(5,a,allpc or 0x80000020); reg(8,v,allpc or 0x80000020)
        emit(allpc or pc,0x00828023|({1:0,2:1,4:2,8:3}[width]<<12),addr=a,mask=((1<<width)-1)<<(a%8),data=v)
    def oracle(n):
        nonlocal checks
        for _ in range(n):
            reg(10,0x5b);reg(11,0x5b);emit(s['check']);checks+=1;store(s['mx_checks'],checks)
    def trap(c,n):
        emit(s['mx_handler']);cfg=ref.CASES[c];fault=cfg['fault'] and n==0
        vals=[(15 if cfg['store'] else 13) if fault else 9,s[ref.SITE[c]] if fault else s['mx_ecall'],
              ref.VA+ref.OFF[c]+4*cfg['start']+2*int(alternate) if fault else 0,0x800,
              (8<<60)|((s['mx_pages']+8192)>>12),8,8,cfg['start'] if fault else 0,117,5,
              0 if fault else 1,0 if fault or not cfg['fault'] else ((s['mx_pages']+4096)>>12<<10)|0xc7]
        for csr,j in cc.CSR.items():emit(s['mx_trap'],(csr<<20)|0x2573,10,vals[j])
        for j,v in enumerate(vals):store(s['mx_records']+192*c+96*n+8*j,v)
        store(s['mx_count']+8*c,n+1)
    def refill():
        emit(s['mx_refill_page'])
        for i in range(2048):store(s['mx_pages']+4096+2*i,ref.orig(2048+i),2,allpc=s['mx_refill_page']+2)
        emit()
    for name in ('mx_errors','mx_unexpected','mx_current','mx_checks'):store(s[name],0)
    for c in range(ref.N):
        for name in ('mx_count','mx_marker','mx_case_checks'):store(s[name]+8*c,0)
        for j in range(24):store(s['mx_records']+192*c+8*j,(1<<64)-1)
    oracle(3)
    for c,cfg in enumerate(ref.CASES):
        skip=int(alternate and cfg['fault']);begin=checks
        store(s['mx_current'],c)
        for i,v in enumerate((ref.VA+ref.OFF[c],s[ref.SITE[c]])):store(s['mx_args']+8*i,v)
        for i in range(16):store(s['mx_mask']+16*c+i,cfg['mask'],1)
        leaf=s['mx_pages']+16392;store(leaf,0);emit(s['mx_enter_s'])
        if cfg['fault']:
            trap(c,0);store(s['mx_restart'],cfg['start'])
            oracle((302 if cfg['store'] else 300)-skip)
            store(s['mx_phase'],1);emit(s['mx_checkpoint'])
            store(leaf,((s['mx_pages']+4096)>>12<<10)|0xc7)
            reg(28,ref.VA+4096);emit(s['mx_repair_sfence'],0x120e0073)
            if cfg['unmapped']:refill()
            for i in range(cfg['start']):
                if not ref.active(c,i):continue
                for f in (0,1):
                    off=ref.OFF[c]+4*i+2*f
                    poison=(ref.seed(c,f+1,i) if cfg['store'] else ref.orig(off//2))^0x5b
                    store(s['mx_pages']+off,poison,2)
            reg(5,cfg['start']);emit(insn=0x00829073);emit(s['mx_trap_mret'],0x30200073)
        emit(s[ref.SITE[c]],0x20055c27 if cfg['store'] else 0x20055c07)
        for j,v in enumerate((8,8,0,117,5)):store(s['mx_post']+40*c+8*j,v)
        store(s['mx_marker']+8*c,1,pc=s['mx_younger_store'])
        trap(c,int(cfg['fault']));emit(s['mx_trap_mret'],0x30200073)
        if not cfg['fault']:
            oracle(30);store(s['mx_phase'],3);emit(s['mx_checkpoint'])
            store(leaf,((s['mx_pages']+4096)>>12<<10)|0xc7)
            reg(28,ref.VA+4096);emit(s['mx_cleanup_sfence'],0x120e0073)
            if cfg['unmapped']:refill()
        oracle(cc.COUNTS[c]-skip-(checks-begin))
        store(s['mx_phase'],2);emit(s['mx_checkpoint']);store(s['mx_case_checks']+8*c,cc.COUNTS[c]-skip)
    oracle(ref.TOTAL-sum(c['fault'] for c in ref.CASES)*int(alternate)-checks)
    store(s['mx_completed'],ref.DONE);store(0xd0000000,0)
    return rows
