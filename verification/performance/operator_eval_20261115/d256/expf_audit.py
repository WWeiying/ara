"""Bind the independently modeled scalar expf to actual installed target libm."""
from pathlib import Path
import re
from contract import ANCHOR,require,sha
import elf


def signature(text,image):
    _,memory=elf.read(image)
    match=re.search(r'^\w+ <__ieee754_expf>:\n(.*?)(?=\n\w+ <|\Z)',text,re.M|re.S)
    require(match is not None,'Missing target expf arithmetic')
    result=[]
    for line in match[1].splitlines():
        fields=line.split('\t');require(len(fields)>=4,'Malformed libm disassembly')
        op,operand=fields[2].strip(),fields[3].split('#')[0].strip()
        address=re.search(r'# ([0-9a-f]+)',line)
        if op=='flw' and address:result.append(('flw',operand.split(',')[0],memory(int(address[1],16),4).hex()))
        elif op.startswith('f'):result.append((op,operand))
        table=re.search(r'# ([0-9a-f]+) <(ln2HI|ln2LO|halF)>',line)
        if table:result.append((table[2],memory(int(table[1],16),8).hex()))
    require(len(result)==84,'Incomplete/changed scalar expf schedule')
    return result


def audit(output):
    dump=ANCHOR/'objdump.log';image=ANCHOR/'attention.elf'
    require(sha(dump)=='6dafaf33da8bcffaa19b6d0264cbe2885242c103847ce87f994da98342f90e36' and
        sha(image)=='8614f075aeaf5cea320967e932a091297420c9439ed486474400de5addf65881',
        'Target libm anchor drift')
    require(signature((output/'objdump.log').read_text(),output/'d256.elf')==signature(dump.read_text(),image),
            'Linked target scalar expf differs from independent model')
    return dict(state='MATCH',fp_and_table_records=84,domain='nonpositive |x|<88, plus expf(-Inf)=+0',
        anchor_use='Target libm code identity only; NOT old RTL acceptance or timing',
        anchor_elf_sha256=sha(image),anchor_disassembly_sha256=sha(dump))
