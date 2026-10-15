"""Finite Spike reset-ROM prefix and post-HTIF park contract, through EOF."""
import re

BOOT = (
    (0x1000,0x00000297,'x5 0x0000000000001000'),
    (0x1004,0x02028593,'x11 0x0000000000001020'),
    (0x1008,0xf1402573,'x10 0x0000000000000000'),
    (0x100c,0x0182b283,'x5 0x0000000080000000 mem 0x0000000000001018'),
    (0x1010,0x00028067,''),
)
def require(ok,why):
    if not ok:raise ValueError(why)

class RawBoundary:
    def __init__(self):
        self.boot=0;self.firmware=False;self.completed=False;self.park=0
    def enter(self,pc,insn,rest):
        if pc<0x80000000:
            require(not self.firmware and self.boot<len(BOOT),'Unexpected boot reentry/extra instruction')
            wpc,winsn,wrest=BOOT[self.boot]
            require((pc,insn)==(wpc,winsn) and re.sub(r'\s+','',rest)==re.sub(r'\s+','',wrest),
                    'Exact Spike reset-ROM PC/code/side effects')
            self.boot+=1;return 'boot'
        require(self.boot==len(BOOT),'Incomplete actual reset-ROM prefix')
        if not self.firmware:require(pc==0x80000000,'Actual firmware entry')
        self.firmware=True
        if self.completed:
            require(pc==0x8000007e and insn==0xa001 and not rest.strip(),
                    'Post-HTIF activity not exact side-effect-free park')
            self.park+=1;return 'park'
        return 'firmware'
    def success(self,pc,insn,value):
        require(self.firmware and not self.completed and (pc,insn,value)==(0x8000007a,0x00a2b023,1),
                'Exact single actual HTIF success store')
        self.completed=True
    def finish(self):
        require(self.boot==len(BOOT) and self.firmware and self.completed,'EOF without complete actual HTIF success')
