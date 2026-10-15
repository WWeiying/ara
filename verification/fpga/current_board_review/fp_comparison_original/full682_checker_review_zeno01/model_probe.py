"""Independent pure-model audit; no worker, Spike, compilation or DUT launch."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
OWNER=HERE.parent/'full682_vcs_m8_plan01'
PREP=HERE.parent/'full682_packed_prepare01'
OLD=HERE.parent/'prepared02/prepared/alias_v8_e16m8_prefix682'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def literal(text,name):
    m=re.search(re.escape(name)+r'\s*=\s*(\{.*?\});',text,re.S)
    assert m
    x=re.sub(r'UINT64_C\((0x[0-9a-f]+|[0-9]+)\)',r'\1',m[1])
    return ast.literal_eval(x.replace('{','[').replace('}',']'))
def main():
    files=[OWNER/n for n in ('model.py','elf.py','newscope.py')]
    files += [PREP/'READY.json',PREP/'run01/tables.h',OLD/'call_sequence.json',OLD/'original/fixtures.h']
    pins={str(p):sha(p) for p in files}
    sys.path.insert(0,str(OWNER))
    spec=importlib.util.spec_from_file_location('zeno_live_model',OWNER/'model.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    fixture=(OLD/'original/fixtures.h').read_text()
    inputs=[int(x,16) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)',fixture)]
    expect=literal(fixture,'expected[6][16][16]')
    assert m.INPUT==inputs
    pairs=0
    for op in range(6):
        for ai,a in enumerate(inputs):
            for bi,b in enumerate(inputs):
                assert tuple(expect[op][ai][bi])==m.compare(op,a,b),(op,ai,bi)
                pairs+=1
    actual=m.model()['rows']
    sequence=json.loads((OLD/'call_sequence.json').read_text())
    tables=(PREP/'run01/tables.h').read_text()
    inputrows=literal(tables,'input_rows[][128]')
    packed=literal(tables,'packed_cases[682]')
    bits=0
    for n,(row,source,pc) in enumerate(zip(actual,sequence,packed)):
        assert (row['ordinal'],row['seed'],row['op'],row['vl'],row['mode'],row['sticky'],row['vstart'])==(n+1,source['seed'],source['op'],source['vl'],source['mask'],source['sticky'],source['vstart'])
        for name,idx in (('a',pc[5]),('b',pc[6])):
            values=[(word>>(16*j))&65535 for word in inputrows[idx] for j in range(4)]
            assert row[name]==values
        assert row['flags']==pc[7]
        assert row['mask']==[(255,170,36,0)[source['mask']]]*128
        for i,allowed in enumerate(row['allowed']):
            packed_allowed={b for b in (0,1) if not ((b and (pc[8][i//8]>>(i%8))&1) or (not b and (pc[9][i//8]>>(i%8))&1))}
            assert set(allowed)==packed_allowed,(n,i,allowed,packed_allowed)
            bits+=1
    assert len(actual)==len(sequence)==len(packed)==682 and bits==349184
    assert all(sha(p)==h for p,h in pins.items()),'Live owner source changed during model review'
    result=dict(status='PURE_MODEL_AND_SOURCE_TABLE_MATCH_NOT_CHECKER_ENTRY',pairs=pairs,calls=682,
      result_bits=bits,input_halfwords=682*1024,flags=682,all_mask_bytes=682*128,
      pins=pins,pins_pre_post_unchanged=True,missing=['dynamic checker','worker integration','negative Host tests'],
      DUT_launched=False,owner_files_modified=False)
    with (HERE/'model_evidence.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(result['status'],pairs,bits)
if __name__=='__main__':main()

