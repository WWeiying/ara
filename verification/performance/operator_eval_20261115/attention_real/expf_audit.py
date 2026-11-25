"""Bind independent scalar-exp model to the actual linked newlib FP schedule."""
from pathlib import Path
import re
import struct
from contract import require, sha


def function(text, name):
    match = re.search(r'^\w+ <'+re.escape(name)+r'>:\n(.*?)(?=\n\w+ <|\Z)',text,re.M|re.S)
    require(match is not None, 'Missing libm symbol '+name)
    return match[1]


def memory(raw, addr, size):
    h = struct.unpack_from('<16sHHIQQQIHHHHHH',raw)
    for i in range(h[12]):
        s = struct.unpack_from('<IIQQQQIIQQ',raw,h[6]+i*h[11])
        if s[1] != 8 and s[3] <= addr and addr+size <= s[3]+s[5]:
            return raw[s[4]+addr-s[3]:s[4]+addr-s[3]+size]
    raise ValueError('Unmapped libm constant')


def signature(text, raw):
    result = []
    for line in function(text,'__ieee754_expf').splitlines():
        fields = line.split('\t')
        require(len(fields) >= 4, 'Malformed libm disassembly')
        mnemonic, operands = fields[2].strip(),fields[3].split('#')[0].strip()
        if mnemonic == 'flw':
            address = re.search(r'# ([0-9a-f]+)',line)
            if address:
                result.append(('flw',operands.split(',')[0],memory(raw,int(address[1],16),4).hex()))
            else:
                result.append((mnemonic,operands))
        elif mnemonic.startswith('f'):
            result.append((mnemonic,operands))
        if any('<'+name+'>' in line for name in ('ln2HI','ln2LO','halF')):
            address = re.search(r'# ([0-9a-f]+) <(ln2HI|ln2LO|halF)>',line)
            require(address is not None, 'Missing expf table reference')
            result.append((address[2],memory(raw,int(address[1],16),8).hex()))
    require(len(result) > 60, 'Incomplete expf FP schedule')
    return result


def audit_expf(output, derivation):
    oldtext = Path(derivation['expf_anchor']).read_text()
    oldraw = Path(derivation['expf_elf']).read_bytes()
    current = signature((output/'objdump.log').read_text(),(output/'attention.elf').read_bytes())
    anchor = signature(oldtext,oldraw)
    require(current == anchor, 'Linked scalar expf FP schedule/constants differ from independent model anchor')
    return dict(state='MATCH',fp_and_table_records=len(anchor),
        anchor_sha256=sha(derivation['expf_anchor']),
        domain='finite |x|<88; normal result, with exact zero/tiny branch; reject other oracle inputs',
        glibc_used_as_golden=False)
