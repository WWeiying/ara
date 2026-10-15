"""Share FP32 successor observer, explicit SEW16 geometry/count changes only."""
from shared import module
_m=module('masked17920_soc_strict','strict.py',expressions=[
 ('self.fresh==49','self.fresh==41',1),('self.input_reads==16','self.input_reads==8',1),
 ("('a',g['a'],4)","('a',g['a'],2)",1),("('b',g['b'],4)","('b',g['b'],2)",1),
 ('range(64,4096)','range(32,2048)',1),
 ('self.csr.update(vl=expected,vtype=23,vstart=0)','self.csr.update(vl=expected,vtype=14,vstart=0)',1),
 ("(g['vl'],23,0)","(g['vl'],14,0)",1),
 ("('a',4096)","('a',2048)",1),("('b',4096)","('b',2048)",1),
 ('self.record_loads==2240','self.record_loads==8960',1),
 ('dict(fresh_stores=878080,input_LD=286720,output_LWU=17920)',
  'dict(fresh_stores=734720,input_LD=143360,output_LWU=17920)',1)])
Strict,word=_m.Strict,_m.word
