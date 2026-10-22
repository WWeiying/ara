"""Actual typed16 fractional ELF lifecycle, full original scalar seed chronology."""
INIT=[(0x8000050e+i*4,
    ((i*8>>5)<<25)|(18<<20)|(23<<15)|(3<<12)|((i*8&31)<<7)|0x23,8,i*8) for i in range(32)]+[(0x8000059c,0x108ba023,4,256)]
READS=[(0x800005e4,8,0)]+[(0x8000090a+i*10,8,(i+1)*8) for i in range(6)]+[(0x80000946,8,56)]
for block in range(1,4):
    READS.extend([(0x8000095a+(block-1)*96,8,block*64)]+
        [(0x8000096a+(block-1)*96+i*10,8,block*64+(i+1)*8) for i in range(6)]+
        [(0x800009a6+(block-1)*96,8,block*64+56)])
READS.append((0x80000a7e,4,256))
INPUT_CODE={0x80000402:0x00e61023,0x80000406:0x00f59023,
    0x8000041a:0x01059023,0x8000041e:0x01161023,
    0x80000db2:0x00661023,0x80000dba:0x00059023,
    0x80000dbe:0x00061023,0x80000dcc:0x01d59023,0x80000dd0:0x01061023}

def require(ok,why):
    if not ok:raise ValueError(why)

def scalar_width(code,write):
    if code&3!=3:
        quadrant,kind=code&3,(code>>13)&7
        if quadrant in (0,2) and kind in ((6,7) if write else (2,3)):
            return 4 if kind in (2,6) else 8
        return None
    if code&127==(35 if write else 3):return 1<<(((code>>12)&7)&3)
    return None

def full_group(vectors,first):
    raw=[]
    for register in range(first,first+2):
        require(register in vectors,'Missing actual physical group register')
        require(0<=vectors[register]<(1<<1024),'Actual physical VLEN128 bytes')
        raw.append(vectors[register].to_bytes(128,'little'))
    return b''.join(raw)

def input_schedule():
    result=[]
    for seed in range(3):
        rng=0x937ad68de41c725f^seed
        for i in range(128):
            rng^=(rng<<13)&((1<<64)-1);rng^=rng>>7;rng^=(rng<<17)&((1<<64)-1)
            result.extend([(seed,0x80000402,'b',i*2,(rng>>19)&65535),
                (seed,0x80000406,'a',i*2,rng&65535)])
            if i%8==0:result.extend([(seed,0x80000dba,'a',i*2,0),(seed,0x80000dbe,'b',i*2,0)])
            elif i%8==1:result.extend([(seed,0x8000041a,'a',i*2,65535),(seed,0x8000041e,'b',i*2,1)])
            elif i%8==2:result.extend([(seed,0x80000dcc,'a',i*2,32768),(seed,0x80000dd0,'b',i*2,65535)])
            elif i%8==3:result.append((seed,0x80000db2,'b',i*2,16))
    require(len(result)==1104,'Original three full128 typed16 seed schedules')
    return result

class Lifecycle:
    def __init__(self,symbols,code,entries,rows,masks):
        self.s,self.code,self.entries=symbols,code,set(entries);self.rows,self.masks=rows,masks
        self.next_bss=symbols['__bss_start'];self.boot_locked=False;self.entered=False
        self.stores=0;self.calls=0;self.input_cursor=0;self.input=input_schedule()
        self.mask_cursor=0;self.mask_groups=0;self.read_cursor=0;self.output_reads=0
        require(all(code.get(pc)==insn and scalar_width(insn,True)==size for pc,insn,size,_ in INIT),'Actual initializer PC/width drift')
        require(all(code.get(pc)==insn and scalar_width(insn,True)==2 for pc,insn in INPUT_CODE.items()),'Actual typed16 seed PC/code drift')
        require(code.get(0x80000046)==0x0002b023 and code.get(0x800004e6)==0xe394,'Actual BSS/mask site')
        for pc,size,_ in READS:require(scalar_width(code.get(pc,0),False)==size,'Actual LD/LW code width')
    def enter(self,pc):
        if pc==self.s['main']:
            require(self.next_bss==self.s['__bss_end'] and not self.boot_locked,'Incomplete/duplicate BSS/main')
            self.boot_locked=True
        if pc==self.s['arithmetic_main']:
            require(self.boot_locked and not self.entered,'Actual arithmetic entry');self.entered=True
        if pc in self.entries:
            require(self.calls<len(self.rows) and self.entered and self.stores==33,'Missing/extra16 SD plus SW')
            require(self.calls==0 or self.read_cursor==33,'Previous oracle incomplete')
            row=self.rows[self.calls]
            require(self.input_cursor==368*(row['seed']+1),'Fresh full original128 RNG writes')
            require(self.mask_cursor==(16 if row['si']==0 else 0),'Complete128B mask owner')
            if row['si']==0:self.mask_groups+=1
            self.mask_cursor=0;self.calls+=1;self.stores=0;self.read_cursor=0
    def store(self,pc,insn,address,size,value):
        if pc==0x80000046:
            require(not self.boot_locked and insn==0x0002b023 and size==8 and value==0 and
                address==self.next_bss and address%8==0 and address+8<=self.s['__bss_end'],'Ordered startup BSS')
            self.next_bss+=8;return
        out=self.s['out']
        if address<out+2052 and address+size>out:
            require(self.entered and out<=address and address+size<=out+260,'Unowned/wide output store')
            require(self.stores<33,'Extra initializer')
            want=INIT[self.stores]
            require((pc,insn,size)==want[:3] and address==out+want[3] and
                value==(0x005b005b if size==4 else 0x005b005b005b005b),'Typed005b initializer PC/value/order')
            self.stores+=1
        for name in ('a','b'):
            base=self.s[name]
            if address<base+2048 and address+size>base:
                require(self.entered and self.input_cursor<len(self.input),'Unowned input store')
                seed,wpc,key,offset,wvalue=self.input[self.input_cursor]
                require(self.calls==seed*1365 and size==2 and
                    (pc,insn,address,value)==(wpc,INPUT_CODE[wpc],self.s[key]+offset,wvalue),
                    'Original typed16 RNG write order/value/owner')
                self.input_cursor+=1
        base=self.s['mask']
        if address<base+128 and address+size>base:
            require(self.entered and self.calls<len(self.rows) and self.mask_cursor<16,'Mask owner')
            row=self.rows[self.calls];offset=self.mask_cursor*8
            require(row['si']==0 and pc==0x800004e6 and insn==0xe394 and
                address==base+offset and size==8 and
                value==int.from_bytes(self.masks[row['mode']][offset:offset+8],'little'),'Full physical mask write')
            self.mask_cursor+=1
    def read(self,pc,address,size):
        out=self.s['out']
        if address<out+2052 and address+size>out:
            require(self.calls>0 and self.read_cursor<33,'Unowned/extra output read')
            wpc,wsize,offset=READS[self.read_cursor]
            require((pc,address,size)==(wpc,out+offset,wsize),'Actual output read PC/width/order')
            self.read_cursor+=1;self.output_reads+=1
    def finish(self):
        require((self.calls,self.stores,self.read_cursor,self.output_reads,self.mask_cursor,
            self.mask_groups,self.input_cursor)==(4095,0,33,135135,0,1575,1104),'Full original lifecycle')
