"""Compare all regular ar member bytes, ignoring archive creation timestamps only."""
import hashlib
import struct

HEADER=struct.Struct('16s12s6s6s8s10s2s')


def members(data):
    if not data.startswith(b'!<arch>\n'):raise ValueError('Not a regular ar archive')
    offset=8;result=[];view=memoryview(data)
    while offset<len(data):
        if offset+HEADER.size>len(data):raise ValueError('Truncated ar header')
        name,mtime,uid,gid,mode,size,magic=HEADER.unpack_from(data,offset)
        if magic!=b'`\n' or not size.strip().isdigit():raise ValueError('Malformed ar header')
        count=int(size);start=offset+HEADER.size;end=start+count
        if end>len(data):raise ValueError('Truncated ar member')
        result.append(dict(name=name.hex(),uid=uid.hex(),gid=gid.hex(),mode=mode.hex(),
            size=count,sha256=hashlib.sha256(view[start:end]).hexdigest()))
        offset=end
        if count&1:
            if data[offset:offset+1]!=b'\n':raise ValueError('Missing ar padding')
            offset+=1
    return result
