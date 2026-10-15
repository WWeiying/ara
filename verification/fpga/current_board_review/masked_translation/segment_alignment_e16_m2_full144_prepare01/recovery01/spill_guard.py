"""Learn an otherwise unknown initial GPR only from its actual full-width spill."""
import model as m
from prepare import window

class StoreGuard:
    def __init__(self):
        self.evidence=[]

    def check(self,value,regs,desc,pc,mode,current,address,symbols,code):
        m.require(value is not None,'Scalar store has no actual value')
        register=desc['register'];width=desc['size']
        if register not in regs:
            prologue=window(code,symbols['main'],14)
            saved=[8,9,*range(18,28)]
            expected_pc={reg:prologue[i+2] for i,reg in enumerate(saved)}
            expected_offset={reg:176-8*i for i,reg in enumerate(saved)}
            m.require(register in saved and pc==expected_pc.get(register) and current==-1 and mode==3 and
                      desc['kind']=='write' and width==8 and desc['base']==2 and
                      desc['offset']==expected_offset[register] and address%8==0 and
                      address==regs.get(2,-1)+desc['offset'],
                      'Unknown source register outside exact initial main spill')
            m.require(0<=value<1<<64,'Initial full-width spill value')
            regs[register]=value
            self.evidence.append(dict(pc=pc,register=register,address=address,value=value,width=width))
        m.require(value==(regs[register]&((1<<(width*8))-1)),'Actual scalar store value mismatch')
