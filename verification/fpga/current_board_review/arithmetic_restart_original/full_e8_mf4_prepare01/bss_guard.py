"""Exact original startup BSS initialization, followed by byte-only printing."""
def require(ok,why):
    if not ok:raise ValueError(why)

class BSSGuard:
    def __init__(self,symbols,code):
        self.s=symbols;self.begin=symbols['__bss_start'];self.end=symbols['__bss_end']
        self.log=symbols['replay_log'];self.logend=self.log+8192
        require(self.begin%8==self.end%8==self.log%8==0 and
                self.begin<=self.log<self.logend<=self.end,'Pinned BSS/log alignment and containment')
        matches=[pc for pc,insn in code.items() if symbols['_start']<=pc<symbols['trap_entry'] and insn==0x0002b023]
        require(matches==[symbols['_start']+0x46],'Unique actual original sd zero,0(t0) PC')
        self.store_pc=matches[0];self.next=self.begin;self.entered_main=False;self.printed=False;self.stores=0

    def pc(self,pc):
        if pc==self.s['main']:
            require(not self.entered_main and self.next==self.end,'Complete BSS clear exactly before first main')
            self.entered_main=True

    def store(self,pc,insn,addr,value,width,regs,calls):
        overlap=addr<self.logend and addr+width>self.log
        if pc==self.store_pc:
            require(insn==0x0002b023 and width==8 and value==0 and not self.entered_main and not self.printed and calls==0,
                    'Only pre-main zero BSS sd is initialization')
            require(addr==self.next and addr%8==0 and self.begin<=addr and addr+8<=self.end and
                    regs.get(0)==0 and regs.get(5)==addr and regs.get(6)==self.end,
                    'Original BSS stride/aligned bounds/t0/t1 context')
            if overlap:require(self.log<=addr and addr+8<=self.logend,'No partial console-boundary clear')
            self.next+=8;self.stores+=1
        elif overlap:
            require(self.entered_main and self.next==self.end and width==1 and
                    self.log<=addr<self.logend,'After initialization runtime console is sb-only')
            self.printed=True

    def finish(self):
        require(self.entered_main and self.printed and self.next==self.end,'BSS/printing phases incomplete')
        return dict(store_pc=self.store_pc,bss_start=self.begin,bss_end=self.end,
                    zero_doubleword_stores=self.stores,runtime_console_byte_only=True)
