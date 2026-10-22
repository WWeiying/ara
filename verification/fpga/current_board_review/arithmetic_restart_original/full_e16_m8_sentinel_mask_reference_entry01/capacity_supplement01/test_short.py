"""Small real-extracted witness mutations only; never opens original raw."""
import json
from pathlib import Path
from check import validate
HERE=Path(__file__).resolve().parent
text=(HERE/'matched.log').read_text();lines=text.splitlines()
expected=json.loads((HERE/'preflight.json').read_text())['expected']
validate(text,expected);bad=[]
for i in range(3):
    bad.append(('drop_'+str(i),'\n'.join(lines[:i]+lines[i+1:])))
    bad.append(('duplicate_'+str(i),'\n'.join(lines+[lines[i]])))
    bad.append(('wrong_code_'+str(i),'\n'.join(lines[:i]+[lines[i].replace('('+('0x52fd','0x00b2f557','0x8082')[i]+')','(0x00000013)')]+lines[i+1:])))
bad += [('reorder','\n'.join([lines[1],lines[0],lines[2]])),
    ('window_gap',text.replace('7302:','7304:')),
    ('t0',text.replace('0xffffffffffffffff','0xfffffffffffffffe')),
    ('a0',text.replace('x10 0x0000000000000200','x10 0x0000000000000100')),
    ('VL',text.replace('c3104_vl 0x0000000000000200','c3104_vl 0x0000000000000100')),
    ('VTYPE',text.replace('c3105_vtype 0x000000000000000b','c3105_vtype 0x000000000000000a')),
    ('missing_VTYPE',text.replace(' c3105_vtype 0x000000000000000b','')),
    ('vstart',text.replace('c8_vstart 0x0000000000000000','c8_vstart 0x0000000000000001')),
    ('ret_effect',text.rstrip()+' x1 0x0\n'),
    ('ret_memory',text.rstrip()+' mem 0x80000000 0x0\n')]
for label,mutated in bad:
    assert mutated!=text,label+' mutation ineffective'
    try:validate(mutated,expected)
    except ValueError:continue
    raise AssertionError('Accepted negative '+label)
with (HERE/'HOST.json').open('x') as f:json.dump(dict(status='PASS_FOCUSED_WITNESS_HOST',
    positive=1,negatives=len(bad),scope='Actual 273B rg witness; not fullstream proof',
    raw_reads=0,reference_runs=0,DUT_runs=0),f,indent=2)
print('SHORT_HOST',1,len(bad))
