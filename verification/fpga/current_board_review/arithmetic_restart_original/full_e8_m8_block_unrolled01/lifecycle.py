"""Exact hash-bound full-unroll ELF initializer in actual scheduled order."""
INIT=(
    (0x80000b60,0x1243023,8,0),
    (0x80000b64,0x1243423,8,8),
    (0x80000b68,0x1243823,8,16),
    (0x80000b6c,0x1243c23,8,24),
    (0x80000b70,0x3243023,8,32),
    (0x80000b74,0x3243423,8,40),
    (0x80000b78,0x3243823,8,48),
    (0x80000b7c,0x3243c23,8,56),
    (0x80000b80,0x5243023,8,64),
    (0x80000b84,0x5243423,8,72),
    (0x80000b88,0x5243823,8,80),
    (0x80000b8c,0x5243c23,8,88),
    (0x80000b90,0x7243023,8,96),
    (0x80000b94,0x7243423,8,104),
    (0x80000b98,0x7243823,8,112),
    (0x80000b9c,0x7243c23,8,120),
    (0x80000ba0,0x9243023,8,128),
    (0x80000ba4,0x9243423,8,136),
    (0x80000ba8,0x9243823,8,144),
    (0x80000bac,0x9243c23,8,152),
    (0x80000bb0,0xb243023,8,160),
    (0x80000bb4,0xb243423,8,168),
    (0x80000bb8,0xb243823,8,176),
    (0x80000bbc,0xb243c23,8,184),
    (0x80000bc0,0xd243023,8,192),
    (0x80000bc4,0xd243423,8,200),
    (0x80000bc8,0xd243823,8,208),
    (0x80000bcc,0xd243c23,8,216),
    (0x80000bd0,0xf243023,8,224),
    (0x80000bd4,0xf243423,8,232),
    (0x80000bd8,0xf243823,8,240),
    (0x80000bdc,0xf243c23,8,248),
    (0x80000be0,0x11243023,8,256),
    (0x80000be4,0x11243423,8,264),
    (0x80000be8,0x11243823,8,272),
    (0x80000bec,0x11243c23,8,280),
    (0x80000bf0,0x13243023,8,288),
    (0x80000bf4,0x13243423,8,296),
    (0x80000bf8,0x13243823,8,304),
    (0x80000bfc,0x13243c23,8,312),
    (0x80000c00,0x15243023,8,320),
    (0x80000c04,0x15243423,8,328),
    (0x80000c08,0x15243823,8,336),
    (0x80000c0c,0x15243c23,8,344),
    (0x80000c10,0x17243023,8,352),
    (0x80000c14,0x17243423,8,360),
    (0x80000c18,0x17243823,8,368),
    (0x80000c1c,0x17243c23,8,376),
    (0x80000c20,0x19243023,8,384),
    (0x80000c24,0x19243423,8,392),
    (0x80000c28,0x19243823,8,400),
    (0x80000c2c,0x19243c23,8,408),
    (0x80000c30,0x1b243023,8,416),
    (0x80000c34,0x1b243423,8,424),
    (0x80000c38,0x1b243823,8,432),
    (0x80000c3c,0x1b243c23,8,440),
    (0x80000c40,0x1d243023,8,448),
    (0x80000c44,0x1d243423,8,456),
    (0x80000c48,0x1d243823,8,464),
    (0x80000c4c,0x1d243c23,8,472),
    (0x80000c50,0x1f243023,8,480),
    (0x80000c54,0x1f243423,8,488),
    (0x80000c58,0x1f243823,8,496),
    (0x80000c5c,0x1f243c23,8,504),
    (0x80000c60,0x21243023,8,512),
    (0x80000c64,0x21243423,8,520),
    (0x80000c68,0x21243823,8,528),
    (0x80000c6c,0x21243c23,8,536),
    (0x80000c70,0x23243023,8,544),
    (0x80000c74,0x23243423,8,552),
    (0x80000c78,0x23243823,8,560),
    (0x80000c7c,0x23243c23,8,568),
    (0x80000c80,0x25243023,8,576),
    (0x80000c84,0x25243423,8,584),
    (0x80000c88,0x25243823,8,592),
    (0x80000c8c,0x25243c23,8,600),
    (0x80000c90,0x27243023,8,608),
    (0x80000c94,0x27243423,8,616),
    (0x80000c98,0x27243823,8,624),
    (0x80000c9c,0x27243c23,8,632),
    (0x80000ca0,0x29243023,8,640),
    (0x80000ca4,0x29243423,8,648),
    (0x80000ca8,0x29243823,8,656),
    (0x80000cac,0x29243c23,8,664),
    (0x80000cb0,0x2b243023,8,672),
    (0x80000cb4,0x2b243423,8,680),
    (0x80000cb8,0x2b243823,8,688),
    (0x80000cbc,0x2b243c23,8,696),
    (0x80000cc0,0x2d243023,8,704),
    (0x80000cc4,0x2d243423,8,712),
    (0x80000cc8,0x2d243823,8,720),
    (0x80000ccc,0x2d243c23,8,728),
    (0x80000cd0,0x2f243023,8,736),
    (0x80000cd4,0x2f243423,8,744),
    (0x80000cd8,0x2f243823,8,752),
    (0x80000cdc,0x2f243c23,8,760),
    (0x80000ce0,0x31243023,8,768),
    (0x80000ce4,0x31243423,8,776),
    (0x80000ce8,0x31243823,8,784),
    (0x80000cf0,0x31243c23,8,792),
    (0x80000cf4,0x40f41023,2,1024),
    (0x80000cf8,0x33243023,8,800),
    (0x80000cfc,0x33243423,8,808),
    (0x80000d00,0x33243823,8,816),
    (0x80000d04,0x33243c23,8,824),
    (0x80000d08,0x35243023,8,832),
    (0x80000d0c,0x35243423,8,840),
    (0x80000d10,0x35243823,8,848),
    (0x80000d14,0x35243c23,8,856),
    (0x80000d18,0x37243023,8,864),
    (0x80000d1c,0x37243423,8,872),
    (0x80000d20,0x37243823,8,880),
    (0x80000d24,0x37243c23,8,888),
    (0x80000d28,0x39243023,8,896),
    (0x80000d2c,0x39243423,8,904),
    (0x80000d30,0x39243823,8,912),
    (0x80000d34,0x39243c23,8,920),
    (0x80000d38,0x3b243023,8,928),
    (0x80000d3c,0x3b243423,8,936),
    (0x80000d40,0x3b243823,8,944),
    (0x80000d44,0x3b243c23,8,952),
    (0x80000d48,0x3d243023,8,960),
    (0x80000d4c,0x3d243423,8,968),
    (0x80000d50,0x3d243823,8,976),
    (0x80000d54,0x3d243c23,8,984),
    (0x80000d58,0x3f243023,8,992),
    (0x80000d5c,0x3f243423,8,1000),
    (0x80000d60,0x3f243823,8,1008),
    (0x80000d64,0x3f243c23,8,1016),
)

def require(ok,why):
    if not ok:raise ValueError(why)

class Lifecycle:
    def __init__(self,symbols,code,entries):
        self.s=symbols;self.entries=set(entries);self.next_bss=symbols['__bss_start']
        self.boot_locked=False;self.entered=False;self.stores=0;self.calls=0
        require(all(code.get(pc)==insn for pc,insn,_,_ in INIT),'Actual initializer PC/insn drift')
        require(code.get(0x80000046)==0x0002b023,'Actual BSS initializer drift')
    def enter(self,pc):
        if pc==self.s['main']:
            require(self.next_bss==self.s['__bss_end'] and not self.boot_locked,'Incomplete/duplicate BSS/main')
            self.boot_locked=True
        if pc==self.s['arithmetic_main']:
            require(self.boot_locked and not self.entered,'Actual arithmetic entry')
            self.entered=True
        if pc in self.entries:
            require(self.entered and self.stores==129,'Per-call exact128 SD plus SH missing/duplicated')
            self.calls+=1;self.stores=0
    def store(self,pc,insn,address,size,value):
        if pc==0x80000046:
            require(not self.boot_locked and insn==0x0002b023 and size==8 and value==0 and
                address==self.next_bss and address%8==0 and address+8<=self.s['__bss_end'],'Actual ordered startup BSS')
            self.next_bss+=8;return
        out=self.s['out']
        if address<out+1026 and address+size>out:
            require(self.entered and out<=address and address+size<=out+1026,'Unowned/wide output store')
            i=self.stores
            require(i<129,'Extra output initialization')
            require((pc,insn,size)==INIT[i][:3] and address==out+INIT[i][3] and
                value==(0x5b5b if INIT[i][2]==2 else 0x5b5b5b5b5b5b5b5b),'Exact output initializer PC/address/width/value/order')
            self.stores+=1
