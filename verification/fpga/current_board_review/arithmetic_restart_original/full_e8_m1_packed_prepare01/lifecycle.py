"""Hash-bound Spike ELF scalar setup and output-read ownership, no RVFI claim."""
INIT = [(0x8000050a, 0x08fb1023, 2, 128)] + [
    (0x8000050e + i*4, insn, 8, i*8) for i, insn in enumerate((
        0x012b3023, 0x012b3423, 0x012b3823, 0x012b3c23,
        0x032b3023, 0x032b3423, 0x032b3823, 0x032b3c23,
        0x052b3023, 0x052b3423, 0x052b3823, 0x052b3c23,
        0x072b3023, 0x072b3423, 0x072b3823, 0x072b3c23))]
READS = [(0x8000057a, 8, 0)] + [(0x80000846+i*10, 8, (i+1)*8) for i in range(15)] + [(0x800008e2, 2, 128)]
INPUT_CODE = {0x800003fa:0x00e60023, 0x800003fe:0x00f58023,
    0x80000412:0x01058023, 0x80000416:0x01160023,
    0x80000bf4:0x00660023, 0x80000bfc:0x00058023,
    0x80000c00:0x00060023, 0x80000c0e:0x01d58023, 0x80000c12:0x01060023}

def require(ok, why):
    if not ok: raise ValueError(why)

def full_group(vectors, first):
    require(first in vectors, 'Missing actual full physical register')
    require(0 <= vectors[first] < (1 << 1024), 'Actual physical VLEN128 bytes')
    result = vectors[first].to_bytes(128, 'little')
    require(len(result) == 128, 'Exact CAP128 expected input/output length')
    return result

def input_schedule():
    result = []
    for seed in range(3):
        rng = 0x937ad68de41c725f ^ seed
        for i in range(128):
            rng ^= (rng << 13) & ((1 << 64)-1); rng ^= rng >> 7
            rng ^= (rng << 17) & ((1 << 64)-1)
            result.extend([(seed,0x800003fa,'b',i,(rng >> 19)&255),
                           (seed,0x800003fe,'a',i,rng&255)])
            if i%8 == 0: result.extend([(seed,0x80000bfc,'a',i,0),(seed,0x80000c00,'b',i,0)])
            elif i%8 == 1: result.extend([(seed,0x80000412,'a',i,255),(seed,0x80000416,'b',i,1)])
            elif i%8 == 2: result.extend([(seed,0x80000c0e,'a',i,128),(seed,0x80000c12,'b',i,255)])
            elif i%8 == 3: result.append((seed,0x80000bf4,'b',i,8))
    require(len(result) == 1104, 'Original three full128 RNG/store schedules')
    return result

class Lifecycle:
    def __init__(self, symbols, code, entries, rows, masks):
        self.s,self.code,self.entries = symbols,code,set(entries)
        self.rows,self.masks = rows,masks
        self.next_bss=symbols['__bss_start'];self.boot_locked=False;self.entered=False
        self.stores=0;self.calls=0;self.input_cursor=0;self.input=input_schedule()
        self.mask_cursor=0;self.mask_groups=0;self.read_cursor=0;self.output_reads=0
        require(all(code.get(pc)==insn for pc,insn,_,_ in INIT),'Actual initializer PC/insn drift')
        require(all(code.get(pc)==insn for pc,insn in INPUT_CODE.items()),'Actual seed PC/code drift')
        require(code.get(0x80000046)==0x0002b023 and code.get(0x800004da)==0xe394,'BSS/mask site drift')
        for pc,size,_ in READS:
            require(code.get(pc,0)&127 == 3 and ((code[pc]>>12)&7)==(5 if size==2 else 3), 'Actual read width/code')
    def enter(self,pc):
        if pc==self.s['main']:
            require(self.next_bss==self.s['__bss_end'] and not self.boot_locked,'Incomplete/duplicate BSS/main')
            self.boot_locked=True
        if pc==self.s['arithmetic_main']:
            require(self.boot_locked and not self.entered,'Actual arithmetic entry')
            self.entered=True
        if pc in self.entries:
            require(self.calls<len(self.rows) and self.entered and self.stores==17,'Missing/extra exact16 SD plus SH')
            require(self.calls==0 or self.read_cursor==17,'Previous output oracle incomplete')
            row=self.rows[self.calls]
            require(self.input_cursor==368*(row['seed']+1),'Fresh complete original seed writes')
            require(self.mask_cursor==(16 if row['si']==0 else 0),'Mask owner/fresh complete128 bytes')
            if row['si']==0:self.mask_groups+=1
            self.mask_cursor=0;self.calls+=1;self.stores=0;self.read_cursor=0
    def store(self,pc,insn,address,size,value):
        if pc==0x80000046:
            require(not self.boot_locked and insn==0x0002b023 and size==8 and value==0 and
                address==self.next_bss and address%8==0 and address+8<=self.s['__bss_end'],'Ordered startup BSS')
            self.next_bss+=8;return
        out=self.s['out']
        if address<out+1026 and address+size>out:
            require(self.entered and out<=address and address+size<=out+130,'Unowned/wide output store')
            require(self.stores<17,'Extra output initialization')
            want=INIT[self.stores]
            require((pc,insn,size)==want[:3] and address==out+want[3] and
                value==(0x5b5b if size==2 else 0x5b5b5b5b5b5b5b5b),'Exact initializer PC/address/width/value/order')
            self.stores+=1
        for name in ('a','b'):
            base=self.s[name]
            if address<base+1024 and address+size>base:
                require(self.entered and self.input_cursor<len(self.input),'Unowned input store')
                seed,wpc,key,offset,wvalue=self.input[self.input_cursor]
                require(self.calls==seed*1365 and size==1 and
                    (pc,insn,address,value)==(wpc,INPUT_CODE[wpc],self.s[key]+offset,wvalue),'Original RNG write order/value/owner')
                self.input_cursor+=1
        base=self.s['mask']
        if address<base+128 and address+size>base:
            require(self.entered and self.calls<len(self.rows) and self.mask_cursor<16,'Mask owner')
            row=self.rows[self.calls];offset=self.mask_cursor*8
            require(row['si']==0 and pc==0x800004da and insn==0xe394 and
                address==base+offset and size==8 and
                value==int.from_bytes(self.masks[row['mode']][offset:offset+8],'little'),'Exact physical mask write')
            self.mask_cursor+=1
    def read(self,pc,address,size):
        out=self.s['out']
        if address<out+1026 and address+size>out:
            require(self.calls>0 and self.read_cursor<17,'Extra/unowned output read')
            wpc,wsize,offset=READS[self.read_cursor]
            require((pc,address,size)==(wpc,out+offset,wsize),'Exact actual output read PC/address/width/order')
            self.read_cursor+=1;self.output_reads+=1
    def finish(self):
        require((self.calls,self.stores,self.read_cursor,self.output_reads,self.mask_cursor,
                 self.mask_groups,self.input_cursor)==(4095,0,17,69615,0,1575,1104),'Complete setup/read lifecycle')
