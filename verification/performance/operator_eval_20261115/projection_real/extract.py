#!/usr/bin/env python3
"""Read-only capture-log extraction with exact row/offset closure, no simulator."""
import argparse
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode=True
from contract import owned_output
from check import require


def extract(text,phase):
    prefix='DECODE_CAPTURE_' if phase == 'decode' else 'FFN_CAPTURE_'
    shapes,words={},{}
    begun=phase == 'prefill'
    done=False
    for line in text.splitlines():
        if line.startswith(prefix+'BEGIN '):
            require(phase == 'decode' and not begun and not done,'Duplicate/misplaced capture BEGIN')
            require('prompt=40 token=22406 position=40 ' in line,'Not reviewed actual Decode position40')
            begun=True
        elif line.startswith(prefix+'SHAPE '):
            require(begun and not done,'Shape outside capture')
            pattern=(r'source=(\S+) k=(\d+) rows=(\d+) type=f32' if phase == 'decode' else
                     r'source=(\S+) k=(\d+) rows=(\d+) tokens=40 type=f32')
            match=re.fullmatch(prefix+'SHAPE '+pattern,line)
            require(match is not None,'Malformed shape')
            source,k,rows=match.groups(); k,rows=int(k),int(rows)
            require(source not in shapes and k > 0 and rows == (1 if phase == 'decode' else 4),'Shape/rows')
            shapes[source]=(k,rows); words[source]={}
        elif line.startswith(prefix+'DATA '):
            require(begun and not done,'Data outside capture')
            pattern=(r'source=(\S+) offset=(\d+) bits=([0-9a-f]+)' if phase == 'decode' else
                     r'source=(\S+) row=(\d+) offset=(\d+) bits=([0-9a-f]+)')
            match=re.fullmatch(prefix+'DATA '+pattern,line)
            require(match is not None,'Malformed data')
            if phase == 'decode':
                source,offset,bits=match.groups(); row=0
            else:
                source,row,offset,bits=match.groups(); row=int(row)
            require(source in shapes and len(bits)%8 == 0 and bits,'Missing shape/incomplete word')
            k,rows=shapes[source]; offset=int(offset)
            require(0 <= row < rows and 0 <= offset < k and offset+len(bits)//8 <= k,'Data extent')
            for index in range(len(bits)//8):
                key=row*k+offset+index
                require(key not in words[source],'Duplicate data offset')
                words[source][key]=int(bits[8*index:8*index+8],16)
        elif line.startswith(prefix+'DONE '):
            require(begun and not done,'Duplicate/misplaced footer')
            stop='before_decode_vocabulary' if phase == 'decode' else 'before_first_down'
            require('stop='+stop+' performance=not_measured' in line,'Wrong capture stop')
            done=True
    require(begun and done and len(shapes) == (4 if phase == 'decode' else 3),'Incomplete capture')
    result={}
    for source,(k,rows) in shapes.items():
        require(set(words[source]) == set(range(k*rows)),'Missing capture words')
        raw=b''.join(struct.pack('<I',words[source][i]) for i in range(k*rows))
        require(all(abs(value)<float('inf') for value, in struct.iter_unpack('<f',raw)),'Nonfinite activation')
        result[source]=dict(k=k,rows=rows,raw=raw,
            distinct_rows=len({raw[row*k*4:(row+1)*k*4] for row in range(rows)}))
    return result


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--log',type=Path,required=True)
    p.add_argument('--phase',choices=('decode','prefill'),required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); out=owned_output(a.output)
    require(not out.exists(),'Fresh extraction output required'); records=extract(a.log.read_text(),a.phase)
    out.mkdir()
    for name,record in records.items():
        (out/(name+'_f32.bin')).write_bytes(record['raw'])
    print({name:{k:v for k,v in record.items() if k != 'raw'} for name,record in records.items()})
