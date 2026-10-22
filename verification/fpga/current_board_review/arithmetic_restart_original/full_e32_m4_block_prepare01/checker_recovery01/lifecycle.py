"""Narrow successor: classify every compiled seed path, match only current seed."""
import importlib.util
from context import HERE,require,width

_spec=importlib.util.spec_from_file_location('sealed_source_lifecycle',HERE.parent/'reference_entry02/lifecycle.py')
_old=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_old)
full_group,words,REGS=_old.full_group,_old.words,_old.REGS

class Lifecycle(_old.Lifecycle):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        require(set(self.fp)=={0,1,2},'Exactly three actual FP seed paths')
        self.fp_store_pcs={int(e['pc'],16) for events in self.fp.values()
            for e in events if e['kind'] in ('A','B')}
        rng_pcs={e[1] for e in self.seed}
        require(not(self.fp_store_pcs & rng_pcs),'FP classification cannot consume a source RNG store')
        for seed,events in self.fp.items():
            require(len(events)==264 and all(e['kind']=='FP' and e['size']==4 and
                width(self.code[int(e['pc'],16)],False)==4 for e in events[:8]),'Actual eight fresh FP LW per seed')
            for n,e in enumerate(events[8:]):
                bank='a' if n%2==0 else 'b'
                require(e['kind']==bank.upper() and e['address']==self.s[bank]+4*(n//2) and
                    e['size']==4 and width(self.code[int(e['pc'],16)],True)==4,
                    'Actual ordered256 full-width A/B SW per seed')

# Inherited store/read still match self.fp[row['seed']][self.fp_cursor] exactly.
# Union membership is classification only, never authorization of a different path.
